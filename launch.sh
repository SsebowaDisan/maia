#!/bin/bash
set -euo pipefail

MAIA_SERVER_NAME="${MAIA_SERVER_NAME:-0.0.0.0}"
MAIA_SERVER_PORT="${MAIA_SERVER_PORT:-8000}"

if [ "${MAIA_START_OLLAMA:-false}" = "true" ]; then
    echo "[maia] Starting optional ollama sidecar..."
    ollama serve &
fi

echo "[maia] Launching FastAPI + React static app on ${MAIA_SERVER_NAME}:${MAIA_SERVER_PORT}"
uvicorn api.main:app --host "$MAIA_SERVER_NAME" --port "$MAIA_SERVER_PORT"
