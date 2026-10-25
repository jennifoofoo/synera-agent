#!/usr/bin/env bash
# Answer every question of a split, a building folder or a questions file, without stopping.
#
#   ./run_benchmark.sh <split_dir | building_dir | questions_file> [out_dir]
#
# Writes <out_dir>/answers.json and <out_dir>/answers.csv (default out_dir: benchmark_out) and checks them.
# The Anthropic key comes from ANTHROPIC_API_KEY in the environment or from a .env file in this folder.
set -euo pipefail
cd "$(dirname "$0")"

if [ $# -lt 1 ]; then
  echo "usage: ./run_benchmark.sh <split_dir | building_dir | questions_file> [out_dir]" >&2
  exit 2
fi
input="$1"
out="${2:-benchmark_out}"
mkdir -p "$out"

uv sync --quiet
env_args=()
if [ -f .env ]; then env_args=(--env-file .env); fi
if [ -z "${ANTHROPIC_API_KEY:-}" ] && ! grep -qs '^ANTHROPIC_API_KEY=.' .env; then
  echo "note: no ANTHROPIC_API_KEY set; questions that match a known template still get answered, others stay empty" >&2
fi

uv run ${env_args[@]+"${env_args[@]}"} python -m building_agent.submission "$input" --csv "$out/answers.csv" --json "$out/answers.json"
