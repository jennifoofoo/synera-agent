#!/usr/bin/env bash
# Build the 3D twin page (twin/, React and three.js) into twin/dist/, which web/server.py serves.
# Needs Node 20 or newer and npm. First run installs the packages from twin/package-lock.json (about a minute).
# Then start the server: `uv run python -m web` (or `scripts/tunnel.sh` for the phone), open http://127.0.0.1:8765
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d twin ]; then
  echo "twin/ is not in this checkout yet (the page lives on the branch that adds it). Merge it first." >&2
  exit 1
fi
if ! command -v node >/dev/null || ! command -v npm >/dev/null; then
  echo "Node.js and npm are missing. Install them with: brew install node" >&2
  exit 1
fi

cd twin
if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi
npm run build
echo "Built: $(pwd)/dist ($(du -sh dist | cut -f1)). Start the server with: uv run python -m web"
