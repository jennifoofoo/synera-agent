#!/usr/bin/env bash
# Mobile smoke tests for the twin page (Pixel 7 Chromium + iPhone 14 WebKit). Prints a pass/fail summary per item.
# Not part of scripts/check.sh (slow, needs browsers). No API key needed: the chat turn is faked.
# One-time setup: uv sync --group e2e && uv run playwright install chromium webkit
# Needs a current twin/dist: scripts/build_twin.sh
set -euo pipefail
cd "$(dirname "$0")/.."
uv run --group e2e pytest -m e2e tests/e2e/test_mobile.py -q -rs "$@"
