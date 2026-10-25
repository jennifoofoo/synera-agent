#!/usr/bin/env bash
# Copy the demo buildings (demo/buildings/<id>/) into agent_output/buildings/, where the page lists buildings saved
# from floor plans as user/<id>. agent_output/ is git-ignored, so a fresh clone or worktree needs this once.
# Existing folders are left alone (never overwrites a building someone edited on this machine).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p agent_output/buildings
for dir in demo/buildings/*/; do
  id="$(basename "$dir")"
  if [ -e "agent_output/buildings/$id" ]; then
    echo "skip $id (already in agent_output/buildings)"
  else
    cp -R "$dir" "agent_output/buildings/$id"
    echo "added user/$id"
  fi
done
