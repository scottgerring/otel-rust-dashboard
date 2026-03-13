"""Collect PR metrics from GitHub GraphQL API."""

import os
from datetime import datetime, timezone, timedelta

import requests

GRAPHQL_URL = "https://api.github.com/graphql"


def _headers():
    return {
        "Authorization": f"bearer {os.environ['GITHUB_TOKEN']}",
        "Content-Type": "application/json",
    }


PRS_QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    openPrCount: pullRequests(states: OPEN) { totalCount }
    recentMerged: pullRequests(
      first: 50,
      states: MERGED,
      orderBy: {field: UPDATED_AT, direction: DESC},
      after: $cursor
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        createdAt
        mergedAt
        reviews(first: 50) {
          nodes {
            state
            submittedAt
            author { login }
          }
        }
      }
    }
  }
}
"""


def _median(values):
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return round((s[n // 2 - 1] + s[n // 2]) / 2, 1)


def collect(config):
    """Return PR metrics dict."""
    owner = config["repo"]["owner"]
    name = config["repo"]["name"]
    lookback = config["dashboard"].get("lookback_days", 30)
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback)

    merged_prs = []
    cursor = None
    open_count = 0

    for _ in range(3):
        resp = requests.post(
            GRAPHQL_URL,
            json={"query": PRS_QUERY, "variables": {"owner": owner, "name": name, "cursor": cursor}},
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()["data"]["repository"]

        open_count = data["openPrCount"]["totalCount"]

        for pr in data["recentMerged"]["nodes"]:
            merged_at = datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00"))
            if merged_at < cutoff:
                continue
            merged_prs.append(pr)

        page = data["recentMerged"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    # Compute metrics from merged PRs
    review_rounds = []
    hours_to_first_review = []
    hours_to_merge = []

    bot_logins = {"codecov", "linux-foundation-easycla", "copilot-pull-request-reviewer", "github-actions"}

    for pr in merged_prs:
        created = datetime.fromisoformat(pr["createdAt"].replace("Z", "+00:00"))
        merged = datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00"))

        hours_to_merge.append(round((merged - created).total_seconds() / 3600, 1))

        reviews = [
            r for r in pr["reviews"]["nodes"]
            if r.get("author") and r["author"]["login"] not in bot_logins
        ]

        if reviews:
            first_review_at = min(
                datetime.fromisoformat(r["submittedAt"].replace("Z", "+00:00"))
                for r in reviews if r.get("submittedAt")
            )
            hours_to_first_review.append(
                round((first_review_at - created).total_seconds() / 3600, 1)
            )

        # Count review rounds: each CHANGES_REQUESTED before final APPROVED
        changes_requested = sum(1 for r in reviews if r["state"] == "CHANGES_REQUESTED")
        review_rounds.append(changes_requested + 1)  # 1 round = direct approval

    return {
        "open_count": open_count,
        "merged_30d": len(merged_prs),
        "median_review_rounds": _median(review_rounds),
        "median_hours_to_first_review": _median(hours_to_first_review),
        "median_hours_to_merge": _median(hours_to_merge),
    }
