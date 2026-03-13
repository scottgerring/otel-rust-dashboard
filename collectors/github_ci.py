"""Collect CI workflow run metrics from GitHub REST API."""

import os
from datetime import datetime, timezone, timedelta
from collections import defaultdict

import requests

API_BASE = "https://api.github.com"


def _headers():
    return {
        "Authorization": f"token {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json",
    }


def collect(config):
    """Return CI pass/fail metrics per workflow."""
    owner = config["repo"]["owner"]
    name = config["repo"]["name"]
    lookback = config["dashboard"].get("lookback_days", 30)
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback)

    # List workflows
    resp = requests.get(
        f"{API_BASE}/repos/{owner}/{name}/actions/workflows",
        headers=_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    workflows = resp.json().get("workflows", [])

    results = {}

    for wf in workflows:
        if wf.get("state") != "active":
            continue

        wf_name = wf["name"]
        wf_id = wf["id"]

        # Get recent runs for this workflow (default branch only)
        runs_resp = requests.get(
            f"{API_BASE}/repos/{owner}/{name}/actions/workflows/{wf_id}/runs",
            params={"per_page": 50, "branch": "main", "status": "completed"},
            headers=_headers(),
            timeout=30,
        )
        runs_resp.raise_for_status()
        runs = runs_resp.json().get("workflow_runs", [])

        total = 0
        passed = 0
        durations = []

        for run in runs:
            created = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
            if created < cutoff:
                continue
            total += 1
            if run["conclusion"] == "success":
                passed += 1

            if run.get("run_started_at") and run.get("updated_at"):
                started = datetime.fromisoformat(run["run_started_at"].replace("Z", "+00:00"))
                ended = datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))
                duration_min = round((ended - started).total_seconds() / 60, 1)
                if duration_min > 0:
                    durations.append(duration_min)

        if total > 0:
            results[wf_name] = {
                "pass_rate_30d": round(passed / total, 3),
                "total_runs": total,
                "passed": passed,
                "median_duration_min": _median(durations),
            }

    return results


def _median(values):
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return round((s[n // 2 - 1] + s[n // 2]) / 2, 1)
