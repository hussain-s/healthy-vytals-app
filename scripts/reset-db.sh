#!/usr/bin/env bash
# HealthyVytals — reset the local database (macOS/Linux).
#
# Drops the local SQLite database file, re-applies migrations, and re-seeds. This
# is the quickest way back to a clean, known state during development.
#
# Only supported for the default SQLite backend; for Postgres, manage the schema
# with migrations directly. Refuses to run against a non-SQLite DATABASE_URL.
#
# Usage:  scripts/reset-db.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"
VENV_PY="${REPO_ROOT}/.venv/bin/python"

if [[ ! -x "${VENV_PY}" ]]; then
  echo "Error: virtual environment not found. Run scripts/setup.sh first." >&2
  exit 1
fi

# Ask the app for the configured DB URL + SQLite file path (single source of
# truth), so this script honors HV_DATABASE_URL / .env.
cd "${BACKEND_DIR}"
read -r IS_SQLITE DB_PATH < <("${VENV_PY}" - <<'PYINFO'
from urllib.parse import urlparse
from app.core.config import get_settings
s = get_settings()
path = ""
if s.is_sqlite:
    # sqlite:///relative.db or sqlite:////absolute.db
    path = urlparse(s.database_url).path.lstrip("/") or urlparse(s.database_url).path
print(str(s.is_sqlite), path)
PYINFO
)

if [[ "${IS_SQLITE}" != "True" ]]; then
  echo "Refusing to reset a non-SQLite database (DATABASE_URL is not SQLite)." >&2
  echo "For Postgres, use migrations to manage the schema." >&2
  exit 1
fi

if [[ -n "${DB_PATH}" && -f "${DB_PATH}" ]]; then
  echo "Removing SQLite database: ${DB_PATH}"
  rm -f "${DB_PATH}" "${DB_PATH}-journal"
fi

"${SCRIPT_DIR}/migrate.sh"
"${SCRIPT_DIR}/seed.sh"
echo "Database reset complete."
