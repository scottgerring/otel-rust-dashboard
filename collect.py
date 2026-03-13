#!/usr/bin/env python3
"""Orchestrator: runs all collectors and writes a daily snapshot."""

import json
import os
import sys
from datetime import date
from pathlib import Path

import toml

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config.toml"
SNAPSHOTS_DIR = ROOT / "data" / "snapshots"


def load_config():
    with open(CONFIG_PATH) as f:
        return toml.load(f)


def run_collector(name, module_path, config):
    """Import and run a collector, returning its data or an error placeholder."""
    try:
        import importlib
        mod = importlib.import_module(module_path)
        data = mod.collect(config)
        print(f"  [ok] {name}")
        return data
    except Exception as e:
        print(f"  [FAIL] {name}: {e}", file=sys.stderr)
        return {"error": str(e)}


def main():
    config = load_config()
    today = date.today().isoformat()

    print(f"Collecting snapshot for {today}...")

    snapshot = {
        "date": today,
        "community": {},
        "project": {},
    }

    # Community collectors
    snapshot["community"]["issues"] = run_collector(
        "issues", "collectors.github_issues", config
    )
    snapshot["community"]["prs"] = run_collector(
        "prs", "collectors.github_prs", config
    )
    snapshot["community"]["releases"] = run_collector(
        "releases", "collectors.github_releases", config
    )

    # Project collectors
    snapshot["project"]["ci"] = run_collector(
        "ci", "collectors.github_ci", config
    )

    # Placeholders for Phase 2+ collectors
    snapshot["community"]["milestones"] = None
    snapshot["community"]["slack"] = None
    snapshot["project"]["coverage_pct"] = None
    snapshot["project"]["benchmarks"] = None
    snapshot["project"]["cargo_deny"] = None

    # Write snapshot
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SNAPSHOTS_DIR / f"{today}.json"
    with open(out_path, "w") as f:
        json.dump(snapshot, f, indent=2)

    print(f"Snapshot written to {out_path}")


if __name__ == "__main__":
    main()
