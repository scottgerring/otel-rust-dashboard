#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ -z "${GITHUB_TOKEN:-}" ]; then
    GITHUB_TOKEN=$(gh auth token 2>/dev/null) || {
        echo "Error: GITHUB_TOKEN not set and 'gh auth token' failed. Log in with 'gh auth login' or set GITHUB_TOKEN." >&2
        exit 1
    }
    export GITHUB_TOKEN
fi

# Use venv if it exists
if [ -d .venv ]; then
    source .venv/bin/activate
fi

echo "==> Collecting data..."
python3 collect.py

echo "==> Rendering dashboard..."
python3 render.py

echo "==> Done. Open site/index.html to view."
