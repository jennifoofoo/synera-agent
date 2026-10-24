#!/usr/bin/env bash
# The one command for "done": lint + tests. No API key needed.
set -euo pipefail
cd "$(dirname "$0")/.."
uv run ruff format --check .
uv run ruff check .
uv run pytest -q
