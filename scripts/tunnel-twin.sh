#!/usr/bin/env bash
# Open the React twin (twin/) on a phone over https; the browser only allows the microphone on https.
# Builds the twin, starts the Python API and the twin's preview server, then a temporary Cloudflare quick tunnel.
# The https link is public while this runs: anyone with it can use the chat and voice and spend API credits.
# Share it with nobody and stop it with Ctrl+C when done. Data and API keys stay on this machine.
set -euo pipefail

cd "$(dirname "$0")/.."
API_PORT="${API_PORT:-8780}"
TWIN_PORT="${TWIN_PORT:-5185}"

if ! command -v cloudflared >/dev/null; then
  echo "cloudflared is missing. Install it with: brew install cloudflared" >&2
  exit 1
fi

(cd twin && { [ -d node_modules ] || npm ci; } && npm run build)

uv run --env-file .env python -m web --host 127.0.0.1 --port "$API_PORT" &
api_pid=$!
(cd twin && TWIN_API="http://127.0.0.1:$API_PORT" npx vite preview --port "$TWIN_PORT" --strictPort --host 127.0.0.1) &
twin_pid=$!
trap 'kill "$api_pid" "$twin_pid" 2>/dev/null || true' EXIT
sleep 4

echo "Look for the https://....trycloudflare.com line below and open it in Safari on the iPhone."
echo "Then go through twin/IPHONE-CHECK.md."
cloudflared tunnel --url "http://127.0.0.1:$TWIN_PORT"
