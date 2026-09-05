# HealthyVytals - load demo seed data (Windows PowerShell).
#
# Idempotent: safe to run repeatedly. Populates representative demo data so the
# app is explorable on first run. (No-op until Phase 1 adds models.)
#
# Usage:  ./scripts/seed.ps1
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
Write-Host "Seeding demo data..."
& $VenvPy -m app.db.seed
