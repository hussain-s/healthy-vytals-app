# HealthyVytals - run the development server (Windows PowerShell).
#
# Starts the single Uvicorn process that serves BOTH the server-rendered web UI
# and the JSON API on http://localhost:8000, with autoreload for local dev.
#
# Usage:  ./scripts/dev.ps1              (defaults to port 8000)
#         $env:PORT=9000; ./scripts/dev.ps1  (override the port)
$ErrorActionPreference = "Stop"

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot   = Split-Path -Parent $ScriptDir
$BackendDir = Join-Path $RepoRoot "backend"
$VenvPy     = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Port       = if ($env:PORT) { $env:PORT } else { "8000" }

if (-not (Test-Path $VenvPy)) {
    Write-Error "Virtual environment not found. Run scripts\setup.ps1 first."
    exit 1
}

Set-Location $BackendDir
Write-Host "Starting HealthyVytals on http://localhost:$Port  (Ctrl+C to stop)"
& $VenvPy -m uvicorn app.main:app --reload --port $Port
