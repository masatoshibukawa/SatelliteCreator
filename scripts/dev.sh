#!/usr/bin/env bash
# Starts the API (port 8010) and the web UI (port 3010) together. Ctrl-C stops both.
set -euo pipefail

API_PORT=8010
WEB_PORT=3010
MINIMUM_NODE_MAJOR=18
API_START_TIMEOUT_S=30

cd "$(dirname "$0")/.."
unset VIRTUAL_ENV

# The web UI needs Node 18.18 or newer, which may differ from the system default.
export PATH="${SATELLITECREATOR_NODE_BIN:-$HOME/.local/opt/node22/bin}:$PATH"

port_in_use() {
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
}

wait_for_api() {
  for _ in $(seq 1 "$API_START_TIMEOUT_S"); do
    if curl -fsS "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1; then
      return 0
    fi
    if ! kill -0 "$api_pid" 2>/dev/null; then
      break
    fi
    sleep 1
  done
  echo "The API did not start on port $API_PORT." >&2
  return 1
}

node_major="$(node --version | sed -E 's/^v([0-9]+).*/\1/')"
if [ "$node_major" -lt "$MINIMUM_NODE_MAJOR" ]; then
  echo "Node $(node --version) is too old. Set SATELLITECREATOR_NODE_BIN to a newer Node's bin." >&2
  exit 1
fi

for port in "$API_PORT" "$WEB_PORT"; do
  if port_in_use "$port"; then
    echo "Port $port is already in use. Stop the process using it and try again." >&2
    exit 1
  fi
done

if [ ! -d web/node_modules ]; then
  npm --prefix web install
fi

uv run uvicorn api.main:app --host 127.0.0.1 --port "$API_PORT" &
api_pid=$!
trap 'kill "$api_pid" 2>/dev/null' EXIT
wait_for_api
npm --prefix web run dev
