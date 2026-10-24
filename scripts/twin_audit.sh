#!/usr/bin/env bash
# Drawn-vs-data audit of the twin: starts the Python server (no API key) and the twin dev server on free ports,
# opens 10 buildings in headless Chromium, prints one table, exits non-zero on a mismatch. About 3 to 5 minutes.
# Run it after every push of the twin frontend. Options: -n 3 (first 3 buildings), --building dev/swiss-203, --no-campus.
# Needs: `cd twin && npm install` once, data/ (scripts/get_data.sh), Playwright's Chromium (once:
# `uv run --with playwright playwright install chromium`). Reuse running servers with TWIN_AUDIT_BASE=http://host:port.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x twin/node_modules/.bin/vite ]; then
  echo "twin/node_modules is missing: cd twin && npm install" >&2
  exit 2
fi
exec uv run --frozen --with playwright python -m tests.e2e.twin_audit "$@"
