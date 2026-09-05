# HealthyVytals - reset the local database (Windows PowerShell).
#
# Drops the local SQLite database file, re-applies migrations, and re-seeds. This
# is the quickest way back to a clean, known state during development.
#
# Only supported for the default SQLite backend; refuses to run against a
# non-SQLite DATABASE_URL.
#
# Usage:  ./scripts/reset-db.ps1
$ErrorActionPreference = "Stop"

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot   = Split-Path -Parent $ScriptDir
$BackendDir = Join-Path $RepoRoot "backend"
$VenvPy     = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPy)) {
    Write-Error "Virtual environment not found. Run scripts\setup.ps1 first."
    exit 1
}

Set-Location $BackendDir

# Ask the app for the configured DB URL + SQLite file path (single source of truth).
$info = & $VenvPy -c @"
from urllib.parse import urlparse
from app.core.config import get_settings
s = get_settings()
path = ''
if s.is_sqlite:
    path = urlparse(s.database_url).path.lstrip('/') or urlparse(s.database_url).path
print(str(s.is_sqlite))
print(path)
"@
$isSqlite = ($info[0]).Trim()
$dbPath   = ($info[1]).Trim()

if ($isSqlite -ne "True") {
    Write-Error "Refusing to reset a non-SQLite database. For Postgres, use migrations."
    exit 1
}

if ($dbPath -and (Test-Path $dbPath)) {
    Write-Host "Removing SQLite database: $dbPath"
    Remove-Item -Force $dbPath -ErrorAction SilentlyContinue
    Remove-Item -Force "$dbPath-journal" -ErrorAction SilentlyContinue
}

& (Join-Path $ScriptDir "migrate.ps1")
& (Join-Path $ScriptDir "seed.ps1")
Write-Host "Database reset complete."
