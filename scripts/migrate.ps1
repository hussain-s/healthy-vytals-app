# HealthyVytals - apply database migrations (Windows PowerShell).
#
# One-command wrapper so beginners never type raw Alembic (decision 12.5). Runs
# `alembic upgrade head` against the configured database (SQLite by default),
# using the project's virtual environment.
#
# Usage:  ./scripts/migrate.ps1
$ErrorActionPreference = "Stop"

# Resolve repo root from this script's location so it works from any CWD.
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Split-Path -Parent $ScriptDir
$BackendDir = Join-Path $RepoRoot "backend"
$VenvPy = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPy)) {
    Write-Error "Virtual environment not found at $RepoRoot\.venv. Run scripts\setup.ps1 first."
    exit 1
}

# Alembic must run from backend\ (where alembic.ini lives).
Set-Location $BackendDir
Write-Host "Applying migrations (alembic upgrade head)..."
& $VenvPy -m alembic upgrade head
Write-Host "Database is up to date."
