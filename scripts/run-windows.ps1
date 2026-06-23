# run-windows.ps1 — set up and launch the PQA desktop app on Windows.
#
# Usage (from the repo root):
#   .\scripts\run-windows.ps1            # build the web UI (if needed) and launch
#   .\scripts\run-windows.ps1 -Build     # force a fresh web build, then launch
#   .\scripts\run-windows.ps1 -NoBuild   # skip the web build, just launch
#
# Prerequisites (Windows 11 usually ships the last two):
#   - Git, Python 3.11+, Node.js + npm
#   - WebView2 Runtime (Evergreen) and .NET Framework 4.8
#
# The shell auto-sets PYTHONNET_RUNTIME=netfx and uses the WebView2 (Edge
# Chromium) backend on Windows, so no manual env vars are needed.

[CmdletBinding()]
param(
    [switch]$Build,    # force rebuild of the web bundle
    [switch]$NoBuild   # never rebuild (fastest relaunch)
)

$ErrorActionPreference = "Stop"

# Always operate from the repo root (parent of this script's folder).
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

# --- Python host environment -------------------------------------------------
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment (.venv)..." -ForegroundColor Cyan
    py -3.11 -m venv .venv
    & ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
    & ".\.venv\Scripts\python.exe" -m pip install -r "desktop\requirements.txt"
}

$Python = ".\.venv\Scripts\python.exe"

# --- Web UI bundle -----------------------------------------------------------
$DistIndex = "web\dist\index.html"
$NeedBuild = $Build -or (-not (Test-Path $DistIndex))

if ($NoBuild) { $NeedBuild = $false }

if ($NeedBuild) {
    Write-Host "Building web UI..." -ForegroundColor Cyan
    Push-Location "web"
    if (-not (Test-Path "node_modules")) { npm install }
    npm run build
    Pop-Location
} else {
    Write-Host "Skipping web build (use -Build to force)." -ForegroundColor DarkGray
}

# --- Launch ------------------------------------------------------------------
Write-Host "Launching PQA desktop app..." -ForegroundColor Green
& $Python -m desktop.shell
