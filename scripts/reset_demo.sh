#!/usr/bin/env bash
# Before a take: put the demo building back to the seeded state (fresh plans, the seeded notes and events only;
# rehearsal notes like "hose cracked" are gone). Restart the server afterwards so it reloads the store.
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf agent_output/buildings/plan-89323a15 agent_output/knowledge/plan-89323a15
scripts/install_demo_buildings.sh >/dev/null
uv run python scripts/demo_knowledge_seed.py | tail -1
uv run python scripts/demo_events_seed.py | tail -1
