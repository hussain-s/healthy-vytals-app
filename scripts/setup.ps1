# HealthyVytals - one-command setup (Windows PowerShell).
#
# Creates the Python virtual environment, installs dependencies, applies database
# migrations, and seeds demo data. After this, run scripts\dev.ps1 to start the app.
#
# Prerequisite: Python 3.11+ only (no Node, no Docker).
# Usage:  ./scripts/setup.ps1
$ErrorActionPreference = "Stop"

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot   = Split-Path -Parent $ScriptDir
$BackendDir = Join-Path $RepoRoot "backend"
$VenvDir    = Join-Path $RepoRoot ".venv"

# --- Locate a suitable Python (3.11+) ---
$PythonBin = if ($env:PYTHON) { $env:PYTHON } else { "python" }
if (-not (Get-Command $PythonBin -ErrorAction SilentlyContinue)) {
    Write-Error "'$PythonBin' not found. Install Python 3.11+ and retry."
    exit 1
}
& $PythonBin -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Python 3.11+ required."
    exit 1
}

# --- Create the virtual environment (idempotent) ---
if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating virtual environment at $VenvDir..."
    & $PythonBin -m venv $VenvDir
}
$VenvPy = Join-Path $VenvDir "Scripts\python.exe"

# --- Install dependencies ---
Write-Host "Installing dependencies..."
& $VenvPy -m pip install --quiet --upgrade pip
& $VenvPy -m pip install --quiet -r (Join-Path $BackendDir "requirements.txt")

# --- Migrate + seed ---
& (Join-Path $ScriptDir "migrate.ps1")
& (Join-Path $ScriptDir "seed.ps1")

Write-Host ""
Write-Host "Setup complete. Start the app with:  ./scripts/dev.ps1"
Write-Host "Then open http://localhost:8000/ (UI) and http://localhost:8000/docs (API)."
