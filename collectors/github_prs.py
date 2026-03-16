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
        title
        url
        createdAt
        mergedAt
        reviews(first: 50) {
          nodes {
            state
            submittedAt
            author { login }
          }
        }
        comments(first: 1) { totalCount }
        reviewThreads(first: 100) {
          nodes {
            comments(first: 1) { totalCount }
          }
        }
      }
    }
  }
}
"""

OPEN_PRS_COMMENTS_QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(
      first: 100,
      states: OPEN,
      orderBy: {field: UPDATED_AT, direction: DESC},
      after: $cursor
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        title
        url
        createdAt
        comments(first: 1) { totalCount }
        reviewThreads(first: 100) {
          nodes {
            comments(first: 1) { totalCount }
          }
        }
      }
    }
  }
}
"""


def _count_pr_comments(pr):
    """Count total comments on a PR (issue comments + review thread comments)."""
    thread_comments = sum(
        t.get("comments", {}).get("totalCount", 0)
        for t in pr.get("reviewThreads", {}).get("nodes", [])
    )
    return pr.get("comments", {}).get("totalCount", 0) + thread_comments


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
    pr_comments_merged = []

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

        pr_comments_merged.append(_count_pr_comments(pr))

    # Fetch open PRs for comment counts
    open_prs = []
    cursor = None
    for _ in range(2):  # up to 200, covers the ~79 open PRs
        resp = requests.post(
            GRAPHQL_URL,
            json={"query": OPEN_PRS_COMMENTS_QUERY, "variables": {"owner": owner, "name": name, "cursor": cursor}},
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        page = resp.json()["data"]["repository"]["pullRequests"]
        open_prs.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    pr_comments_open = [_count_pr_comments(pr) for pr in open_prs]

    # Build detail lists for popup tables
    now = datetime.now(timezone.utc)

    # Open PRs detail (sorted by age descending)
    open_prs_detail = {
        "title": "Open PRs",
        "sort_column": "Age (days)",
        "columns": ["#", "Title", "Age (days)"],
        "rows": [],
    }
    for pr in open_prs:
        created = datetime.fromisoformat(pr["createdAt"].replace("Z", "+00:00"))
        age_days = round((now - created).total_seconds() / 86400, 1)
        open_prs_detail["rows"].append({
            "number": pr["number"],
            "title": pr.get("title", ""),
            "url": pr.get("url", ""),
            "sort_value": age_days,
        })
    open_prs_detail["rows"].sort(key=lambda r: r["sort_value"], reverse=True)

    # Merged PRs detail (sorted by merge date descending)
    merged_prs_detail = {
        "title": "PRs Merged (30d)",
        "sort_column": "Merged",
        "columns": ["#", "Title", "Merged"],
        "rows": [],
    }
    for pr in merged_prs:
        merged_at = datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00"))
        merged_prs_detail["rows"].append({
            "number": pr["number"],
            "title": pr.get("title", ""),
            "url": pr.get("url", ""),
            "sort_value": merged_at.strftime("%Y-%m-%d"),
        })
    merged_prs_detail["rows"].sort(key=lambda r: r["sort_value"], reverse=True)

    # Per-PR computed data for detail rows
    pr_detail_data = {}  # keyed by PR number
    for pr in merged_prs:
        created = datetime.fromisoformat(pr["createdAt"].replace("Z", "+00:00"))
        merged = datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00"))
        h_to_merge = round((merged - created).total_seconds() / 3600, 1)

        reviews_list = [
            r for r in pr["reviews"]["nodes"]
            if r.get("author") and r["author"]["login"] not in bot_logins
        ]

        h_to_first = None
        if reviews_list:
            first_review_at = min(
                datetime.fromisoformat(r["submittedAt"].replace("Z", "+00:00"))
                for r in reviews_list if r.get("submittedAt")
            )
            h_to_first = round((first_review_at - created).total_seconds() / 3600, 1)

        changes_req = sum(1 for r in reviews_list if r["state"] == "CHANGES_REQUESTED")
        rounds = changes_req + 1

        comments = _count_pr_comments(pr)

        pr_detail_data[pr["number"]] = {
            "title": pr.get("title", ""),
            "url": pr.get("url", ""),
            "hours_to_merge": h_to_merge,
            "hours_to_first_review": h_to_first,
            "review_rounds": rounds,
            "comments": comments,
        }

    # Time to First Review detail
    first_review_detail = {
        "title": "Time to First Review (30d)",
        "sort_column": "Hours",
        "columns": ["#", "Title", "Hours"],
        "rows": [],
    }
    for num, d in pr_detail_data.items():
        if d["hours_to_first_review"] is not None:
            first_review_detail["rows"].append({
                "number": num,
                "title": d["title"],
                "url": d["url"],
                "sort_value": d["hours_to_first_review"],
            })
    first_review_detail["rows"].sort(key=lambda r: r["sort_value"], reverse=True)

    # Time to Merge detail
    time_to_merge_detail = {
        "title": "Time to Merge (30d)",
        "sort_column": "Hours",
        "columns": ["#", "Title", "Hours"],
        "rows": [],
    }
    for num, d in pr_detail_data.items():
        time_to_merge_detail["rows"].append({
            "number": num,
            "title": d["title"],
            "url": d["url"],
            "sort_value": d["hours_to_merge"],
        })
    time_to_merge_detail["rows"].sort(key=lambda r: r["sort_value"], reverse=True)

    # Review Rounds detail
    review_rounds_detail = {
        "title": "Review Rounds (30d)",
        "sort_column": "Rounds",
        "columns": ["#", "Title", "Rounds"],
        "rows": [],
    }
    for num, d in pr_detail_data.items():
        review_rounds_detail["rows"].append({
            "number": num,
            "title": d["title"],
            "url": d["url"],
            "sort_value": d["review_rounds"],
        })
    review_rounds_detail["rows"].sort(key=lambda r: r["sort_value"], reverse=True)

    # PR Comments (Merged) detail
    pr_comments_merged_detail = {
        "title": "PR Comments (Merged 30d)",
        "sort_column": "Comments",
        "columns": ["#", "Title", "Comments"],
        "rows": [],
    }
    for num, d in pr_detail_data.items():
        pr_comments_merged_detail["rows"].append({
            "number": num,
            "title": d["title"],
            "url": d["url"],
            "sort_value": d["comments"],
        })
    pr_comments_merged_detail["rows"].sort(key=lambda r: r["sort_value"], reverse=True)

    # PR Comments (Open) detail
    pr_comments_open_detail = {
        "title": "PR Comments (Open)",
        "sort_column": "Comments",
        "columns": ["#", "Title", "Comments"],
        "rows": [],
    }
    for pr in open_prs:
        comments = _count_pr_comments(pr)
        pr_comments_open_detail["rows"].append({
            "number": pr["number"],
            "title": pr.get("title", ""),
            "url": pr.get("url", ""),
            "sort_value": comments,
        })
    pr_comments_open_detail["rows"].sort(key=lambda r: r["sort_value"], reverse=True)

    return {
        "open_count": open_count,
        "merged_30d": len(merged_prs),
        "median_review_rounds": _median(review_rounds),
        "min_review_rounds": min(review_rounds) if review_rounds else None,
        "max_review_rounds": max(review_rounds) if review_rounds else None,
        "median_hours_to_first_review": _median(hours_to_first_review),
        "median_hours_to_merge": _median(hours_to_merge),
        "median_pr_comments_merged": _median(pr_comments_merged),
        "min_pr_comments_merged": min(pr_comments_merged) if pr_comments_merged else None,
        "max_pr_comments_merged": max(pr_comments_merged) if pr_comments_merged else None,
        "median_pr_comments_open": _median(pr_comments_open),
        "min_pr_comments_open": min(pr_comments_open) if pr_comments_open else None,
        "max_pr_comments_open": max(pr_comments_open) if pr_comments_open else None,
        "open_prs_detail": open_prs_detail,
        "merged_prs_detail": merged_prs_detail,
        "first_review_detail": first_review_detail,
        "time_to_merge_detail": time_to_merge_detail,
        "review_rounds_detail": review_rounds_detail,
        "pr_comments_merged_detail": pr_comments_merged_detail,
        "pr_comments_open_detail": pr_comments_open_detail,
    }
