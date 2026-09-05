#!/usr/bin/env bash
# HealthyVytals — apply database migrations (macOS/Linux).
#
# One-command wrapper so beginners never type raw Alembic (decision §12.5). Runs
# `alembic upgrade head` against the configured database (SQLite by default),
# using the project's virtual environment.
#
# Usage:  scripts/migrate.sh
set -euo pipefail

# Resolve repo root from this script's location so it works from any CWD.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"
VENV_PY="${REPO_ROOT}/.venv/bin/python"

if [[ ! -x "${VENV_PY}" ]]; then
  echo "Error: virtual environment not found at ${REPO_ROOT}/.venv" >&2
  echo "Run scripts/setup.sh first." >&2
  exit 1
fi

# Alembic must run from backend/ (where alembic.ini lives) and needs app/ on the
# path (prepend_sys_path=. in alembic.ini handles that once CWD is backend/).
cd "${BACKEND_DIR}"
echo "Applying migrations (alembic upgrade head)..."
"${VENV_PY}" -m alembic upgrade head
echo "Database is up to date."
