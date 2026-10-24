#!/usr/bin/env bash
# Mobile smoke tests (Pixel 7 Chromium + iPhone 14 WebKit). Prints a pass/xfail summary per audit item.
# One-time setup: uv sync --group e2e && uv run playwright install chromium webkit
set -euo pipefail
cd "$(dirname "$0")/.."
uv run --group e2e pytest -m e2e tests/e2e -q -rs "$@"
