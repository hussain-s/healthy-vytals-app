#!/usr/bin/env bash
# HealthyVytals — one-command setup (macOS/Linux).
#
# Creates the Python virtual environment, installs dependencies, applies database
# migrations, and seeds demo data. After this, run scripts/dev.sh to start the app.
#
# Prerequisite: Python 3.11+ only (no Node, no Docker).
# Usage:  scripts/setup.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"
VENV_DIR="${REPO_ROOT}/.venv"

# --- Locate a suitable Python (3.11+) ---
PYTHON_BIN="${PYTHON:-python3}"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Error: '${PYTHON_BIN}' not found. Install Python 3.11+ and retry." >&2
  exit 1
fi
"${PYTHON_BIN}" - <<'PYCHECK'
import sys
if sys.version_info < (3, 11):
    sys.exit(f"Python 3.11+ required, found {sys.version.split()[0]}")
PYCHECK

# --- Create the virtual environment (idempotent) ---
if [[ ! -d "${VENV_DIR}" ]]; then
  echo "Creating virtual environment at ${VENV_DIR}..."
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi
VENV_PY="${VENV_DIR}/bin/python"

# --- Install dependencies ---
echo "Installing dependencies..."
"${VENV_PY}" -m pip install --quiet --upgrade pip
"${VENV_PY}" -m pip install --quiet -r "${BACKEND_DIR}/requirements.txt"

# --- Migrate + seed ---
"${SCRIPT_DIR}/migrate.sh"
"${SCRIPT_DIR}/seed.sh"

echo ""
echo "Setup complete. Start the app with:  scripts/dev.sh"
echo "Then open http://localhost:8000/ (UI) and http://localhost:8000/docs (API)."
