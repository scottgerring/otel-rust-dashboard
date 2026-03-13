#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d site ]; then
    echo "Error: site/ directory not found. Run ./run.sh first." >&2
    exit 1
fi

echo "==> Publishing site/ to gh-pages..."
ghp-import -n -p -f site/
echo "==> Published to GitHub Pages."
