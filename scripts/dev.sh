#!/usr/bin/env bash
# HealthyVytals — run the development server (macOS/Linux).
#
# Starts the single Uvicorn process that serves BOTH the server-rendered web UI
# and the JSON API on http://localhost:8000, with autoreload for local dev.
#
# Usage:  scripts/dev.sh            (defaults to port 8000)
#         PORT=9000 scripts/dev.sh  (override the port)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"
VENV_PY="${REPO_ROOT}/.venv/bin/python"
PORT="${PORT:-8000}"

if [[ ! -x "${VENV_PY}" ]]; then
  echo "Error: virtual environment not found. Run scripts/setup.sh first." >&2
  exit 1
fi

# Run from backend/ so 'app.main:app' and relative paths (SQLite file, templates)
# resolve correctly.
cd "${BACKEND_DIR}"
echo "Starting HealthyVytals on http://localhost:${PORT}  (Ctrl+C to stop)"
exec "${VENV_PY}" -m uvicorn app.main:app --reload --port "${PORT}"
