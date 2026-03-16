"""Collect issue metrics from GitHub GraphQL API."""

import os
from datetime import datetime, timezone, timedelta

import requests

GRAPHQL_URL = "https://api.github.com/graphql"


def _headers():
    return {
        "Authorization": f"bearer {os.environ['GITHUB_TOKEN']}",
        "Content-Type": "application/json",
    }


# Query 1: counts only
COUNTS_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    openIssueCount: issues(states: OPEN) { totalCount }
    triageTodoCount: issues(states: OPEN, labels: ["triage:todo"]) { totalCount }
  }
}
"""

# Query 2: fetch issues with triage:accepted label, ordered by update time.
# These are the issues that completed triage — we inspect their timeline to
# find when triage:todo and triage:accepted were applied.
TRIAGE_ACCEPTED_QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    issues(
      first: 100,
      states: [OPEN, CLOSED],
      labels: ["triage:accepted"],
      orderBy: {field: UPDATED_AT, direction: DESC},
      after: $cursor
    ) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        createdAt
        timelineItems(first: 100, itemTypes: [LABELED_EVENT]) {
          nodes {
            ... on LabeledEvent {
              createdAt
              label { name }
            }
          }
        }
      }
    }
  }
}
"""

# Query 3: fetch recently closed issues to find ones closed-as-triaged
# (had triage:todo but never triage:accepted, closed to resolve triage).
CLOSED_TRIAGE_QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    issues(
      first: 100,
      states: [CLOSED],
      orderBy: {field: UPDATED_AT, direction: DESC},
      after: $cursor
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        createdAt
        closedAt
        labels(first: 10) { nodes { name } }
        timelineItems(first: 100, itemTypes: [LABELED_EVENT]) {
          nodes {
            ... on LabeledEvent {
              createdAt
              label { name }
            }
          }
        }
      }
    }
  }
}
"""


def _compute_triage_times_accepted(issues):
    """Compute days from triage:todo (or issue creation) to triage:accepted."""
    triage_durations = []
    for issue in issues:
        timeline = issue["timelineItems"]["nodes"]

        todo_at = None
        accepted_at = None
        for event in timeline:
            if not event:
                continue
            label_name = event.get("label", {}).get("name", "")
            if label_name == "triage:todo" and todo_at is None:
                todo_at = datetime.fromisoformat(event["createdAt"].replace("Z", "+00:00"))
            elif label_name == "triage:accepted" and accepted_at is None:
                accepted_at = datetime.fromisoformat(event["createdAt"].replace("Z", "+00:00"))

        if accepted_at:
            start = todo_at or datetime.fromisoformat(issue["createdAt"].replace("Z", "+00:00"))
            days = (accepted_at - start).total_seconds() / 86400
            if days >= 0:
                triage_durations.append({
                    "days": round(days, 1),
                    "completed_at": accepted_at,
                })

    return triage_durations


def _compute_triage_times_closed(issues, cutoff):
    """Compute triage times for issues closed-as-triaged.

    These are closed issues that had triage:todo applied but never received
    triage:accepted. Closing the issue is the triage action.
    """
    triage_durations = []
    for issue in issues:
        closed_at_str = issue.get("closedAt")
        if not closed_at_str:
            continue
        closed_at = datetime.fromisoformat(closed_at_str.replace("Z", "+00:00"))
        if closed_at < cutoff:
            continue

        timeline = issue["timelineItems"]["nodes"]

        todo_at = None
        has_accepted = False
        for event in timeline:
            if not event:
                continue
            label_name = event.get("label", {}).get("name", "")
            if label_name == "triage:todo" and todo_at is None:
                todo_at = datetime.fromisoformat(event["createdAt"].replace("Z", "+00:00"))
            elif label_name == "triage:accepted":
                has_accepted = True

        # Skip if this issue was also triage:accepted (already counted)
        if has_accepted:
            continue
        # Must have had triage:todo at some point
        if todo_at is None:
            continue

        start = todo_at
        days = (closed_at - start).total_seconds() / 86400
        if days >= 0:
            triage_durations.append({
                "days": round(days, 1),
                "completed_at": closed_at,
            })

    return triage_durations


def _median(values):
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return round((s[n // 2 - 1] + s[n // 2]) / 2, 1)


def collect(config):
    """Return issue metrics dict."""
    owner = config["repo"]["owner"]
    name = config["repo"]["name"]

    # 1. Get counts
    resp = requests.post(
        GRAPHQL_URL,
        json={"query": COUNTS_QUERY, "variables": {"owner": owner, "name": name}},
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    counts = resp.json()["data"]["repository"]
    open_count = counts["openIssueCount"]["totalCount"]
    triage_todo_count = counts["triageTodoCount"]["totalCount"]

    now = datetime.now(timezone.utc)
    cutoff_1y = now - timedelta(days=365)

    # 2. Fetch all triage:accepted issues (paginate to get them all)
    accepted_issues = []
    cursor = None
    for _ in range(5):  # up to 500 issues, well above the 35 current
        resp = requests.post(
            GRAPHQL_URL,
            json={"query": TRIAGE_ACCEPTED_QUERY, "variables": {"owner": owner, "name": name, "cursor": cursor}},
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        page = resp.json()["data"]["repository"]["issues"]
        accepted_issues.extend(page["nodes"])

        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    # 3. Fetch recently closed issues to find closed-as-triaged
    closed_issues = []
    cursor = None
    for _ in range(10):  # up to 1000 issues as safety bound
        resp = requests.post(
            GRAPHQL_URL,
            json={"query": CLOSED_TRIAGE_QUERY, "variables": {"owner": owner, "name": name, "cursor": cursor}},
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        page = resp.json()["data"]["repository"]["issues"]
        nodes = page["nodes"]
        closed_issues.extend(nodes)

        if not page["pageInfo"]["hasNextPage"]:
            break
        # Stop if we've gone past the 1y window (ordered by UPDATED_AT)
        if nodes and nodes[-1].get("closedAt"):
            last_closed = datetime.fromisoformat(nodes[-1]["closedAt"].replace("Z", "+00:00"))
            if last_closed < cutoff_1y:
                break
        cursor = page["pageInfo"]["endCursor"]

    # 4. Compute triage durations from both sources and merge
    triage_entries = _compute_triage_times_accepted(accepted_issues)
    triage_entries.extend(_compute_triage_times_closed(closed_issues, cutoff_1y))

    # 5. Split into 30d and 1y windows
    cutoff_30d = now - timedelta(days=30)

    durations_30d = [e["days"] for e in triage_entries if e["completed_at"] >= cutoff_30d]
    durations_1y = [e["days"] for e in triage_entries if e["completed_at"] >= cutoff_1y]

    return {
        "open_count": open_count,
        "triage_todo_count": triage_todo_count,
        "median_triage_days_30d": _median(durations_30d),
        "triage_sample_size_30d": len(durations_30d),
        "median_triage_days_1y": _median(durations_1y),
        "triage_sample_size_1y": len(durations_1y),
    }
