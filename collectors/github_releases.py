"""Collect release cadence metrics from GitHub REST API."""

import os
from datetime import datetime, timezone

import requests

API_BASE = "https://api.github.com"


def _headers():
    return {
        "Authorization": f"token {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json",
    }


def _median(values):
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return round((s[n // 2 - 1] + s[n // 2]) / 2, 1)


def collect(config):
    """Return release metrics."""
    owner = config["repo"]["owner"]
    name = config["repo"]["name"]

    resp = requests.get(
        f"{API_BASE}/repos/{owner}/{name}/releases",
        params={"per_page": 20},
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    releases = resp.json()

    if not releases:
        return {"latest": None, "latest_date": None, "median_interval_days": None, "releases": []}

    parsed = []
    for rel in releases:
        if rel.get("draft"):
            continue
        parsed.append({
            "tag": rel["tag_name"],
            "date": rel["published_at"][:10] if rel.get("published_at") else rel["created_at"][:10],
            "prerelease": rel.get("prerelease", False),
        })

    # Compute intervals between consecutive releases
    intervals = []
    for i in range(len(parsed) - 1):
        d1 = datetime.strptime(parsed[i]["date"], "%Y-%m-%d")
        d2 = datetime.strptime(parsed[i + 1]["date"], "%Y-%m-%d")
        interval = abs((d1 - d2).days)
        if interval > 0:
            intervals.append(interval)

    return {
        "latest": parsed[0]["tag"] if parsed else None,
        "latest_date": parsed[0]["date"] if parsed else None,
        "median_interval_days": _median(intervals),
        "releases": parsed[:10],  # Keep last 10 for timeline chart
    }
