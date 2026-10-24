#!/usr/bin/env bash
# Fetch the kit data (data/) into this repo. data/ is git-ignored (300+ MB), so every machine runs this once.
set -euo pipefail

cd "$(dirname "$0")/.."
if [ -d data/dev ]; then
  echo "data/ already exists, nothing to do."
  exit 0
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
git clone --depth 1 https://github.com/Synera-GmbH/industrial-agents-hackathon-2026 "$tmp/kit"
mv "$tmp/kit/data" data
echo "data/ ready: $(ls data)"
