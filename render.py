#!/usr/bin/env python3
"""Render dashboard from accumulated snapshots."""

import json
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).parent
SNAPSHOTS_DIR = ROOT / "data" / "snapshots"
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
SITE_DIR = ROOT / "site"


def load_snapshots():
    """Load all snapshot JSON files, sorted by date ascending."""
    snapshots = []
    for p in sorted(SNAPSHOTS_DIR.glob("*.json")):
        with open(p) as f:
            snapshots.append(json.load(f))
    return snapshots


def build_trends(snapshots):
    """Extract time-series data from snapshots for charting."""
    trends = {
        "dates": [],
        "issues_open": [],
        "issues_triage_todo": [],
        "issues_median_triage_days_30d": [],
        "issues_median_triage_days_1y": [],
        "prs_open": [],
        "prs_merged_30d": [],
        "prs_median_hours_to_merge": [],
        "prs_median_hours_to_first_review": [],
        "ci_workflows": {},  # workflow_name -> [{date, pass_rate}]
        "releases": [],
    }

    for snap in snapshots:
        d = snap["date"]
        trends["dates"].append(d)

        issues = snap.get("community", {}).get("issues") or {}
        trends["issues_open"].append(issues.get("open_count"))
        trends["issues_triage_todo"].append(issues.get("triage_todo_count"))
        trends["issues_median_triage_days_30d"].append(issues.get("median_triage_days_30d"))
        trends["issues_median_triage_days_1y"].append(issues.get("median_triage_days_1y"))

        prs = snap.get("community", {}).get("prs") or {}
        trends["prs_open"].append(prs.get("open_count"))
        trends["prs_merged_30d"].append(prs.get("merged_30d"))
        trends["prs_median_hours_to_merge"].append(prs.get("median_hours_to_merge"))
        trends["prs_median_hours_to_first_review"].append(prs.get("median_hours_to_first_review"))

        ci = snap.get("project", {}).get("ci") or {}
        for wf_name, wf_data in ci.items():
            if wf_name == "error":
                continue
            if wf_name not in trends["ci_workflows"]:
                trends["ci_workflows"][wf_name] = []
            trends["ci_workflows"][wf_name].append({
                "date": d,
                "pass_rate": wf_data.get("pass_rate_30d") if isinstance(wf_data, dict) else None,
            })

        releases = snap.get("community", {}).get("releases") or {}
        if isinstance(releases, dict) and releases.get("releases"):
            trends["releases"] = releases["releases"]

    return trends


def main():
    snapshots = load_snapshots()
    if not snapshots:
        print("No snapshots found. Run collect.py first.")
        return

    latest = snapshots[-1]
    trends = build_trends(snapshots)

    # Set up Jinja2
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    template = env.get_template("index.html.j2")

    html = template.render(
        latest=latest,
        trends=trends,
        snapshot_count=len(snapshots),
    )

    # Write output
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "data").mkdir(exist_ok=True)

    with open(SITE_DIR / "index.html", "w") as f:
        f.write(html)

    with open(SITE_DIR / "data" / "trends.json", "w") as f:
        json.dump(trends, f, indent=2)

    # Copy static assets
    if STATIC_DIR.exists():
        for p in STATIC_DIR.iterdir():
            shutil.copy2(p, SITE_DIR / p.name)

    print(f"Dashboard rendered to {SITE_DIR / 'index.html'}")
    print(f"Trend data written to {SITE_DIR / 'data' / 'trends.json'}")


if __name__ == "__main__":
    main()
