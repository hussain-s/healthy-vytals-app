#!/usr/bin/env bash
# HealthyVytals — load demo seed data (macOS/Linux).
#
# Idempotent: safe to run repeatedly. Populates representative demo data so the
# app is explorable on first run. (No-op until Phase 1 adds models.)
#
# Usage:  scripts/seed.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"
VENV_PY="${REPO_ROOT}/.venv/bin/python"

if [[ ! -x "${VENV_PY}" ]]; then
  echo "Error: virtual environment not found. Run scripts/setup.sh first." >&2
  exit 1
fi

cd "${BACKEND_DIR}"
echo "Seeding demo data..."
"${VENV_PY}" -m app.db.seed
