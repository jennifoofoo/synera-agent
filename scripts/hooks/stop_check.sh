#!/usr/bin/env bash
# Stop hook: run the project check before Claude may finish. Runs once per stop, never loops.
input=$(cat)
if echo "$input" | grep -q '"stop_hook_active": *true'; then exit 0; fi
cd "$(dirname "$0")/../.."
if ! out=$(scripts/check.sh 2>&1); then
  echo "scripts/check.sh is red, fix it before finishing:" >&2
  echo "$out" | tail -30 >&2
  exit 2
fi
