# Thin wrapper: production frontend build for StoryLens.
# Notes:
# - Does NOT publish to GitHub.
# - Does NOT choose or write a LICENSE file.
# - Does NOT send real model requests.
# - App version comes from repository-root VERSION (synced via scripts/version_manager.py).
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
& $py (Join-Path $Root "scripts\version_manager.py") check
if ($LASTEXITCODE) { exit $LASTEXITCODE }
$version = (Get-Content -LiteralPath (Join-Path $Root "VERSION") -Raw -Encoding UTF8).Trim()
Write-Host "Building StoryLens $version (desktop production bundle)..."
& "$PSScriptRoot\build_desktop.ps1"
exit $LASTEXITCODE
