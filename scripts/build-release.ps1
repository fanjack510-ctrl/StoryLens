# Thin wrapper: production frontend build for StoryLens.
# Notes:
# - Does NOT publish to GitHub.
# - Does NOT choose or write a LICENSE file.
# - Does NOT send real model requests.
# - App version comes from apps/desktop/package.json (synced via scripts/set_version.ps1).
$ErrorActionPreference = "Stop"
$pkg = Get-Content -LiteralPath (Join-Path $PSScriptRoot "..\apps\desktop\package.json") -Raw -Encoding UTF8
$version = if ($pkg -match '"version"\s*:\s*"([^"]+)"') { $Matches[1] } else { "unknown" }
Write-Host "Building StoryLens $version (desktop production bundle)..."
& "$PSScriptRoot\build_desktop.ps1"
exit $LASTEXITCODE
