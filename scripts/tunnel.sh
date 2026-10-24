#!/usr/bin/env bash
# Open the local page on a phone over https (the browser only allows the microphone on https).
# Starts the web server and a temporary Cloudflare quick tunnel. The https link is public while this runs,
# anyone with the link can use the chat and the voice and spend the API credits, so share it with nobody and
# stop it with Ctrl+C when done. Data and API keys stay on this machine.
set -euo pipefail

cd "$(dirname "$0")/.."
PORT="${PORT:-8765}"

if ! command -v cloudflared >/dev/null; then
  echo "cloudflared is missing. Install it with: brew install cloudflared" >&2
  exit 1
fi

uv run python -m web --host 127.0.0.1 --port "$PORT" "$@" &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null || true' EXIT
sleep 3

echo "Look for the https://....trycloudflare.com line below and open it on the phone."
cloudflared tunnel --url "http://127.0.0.1:$PORT"
