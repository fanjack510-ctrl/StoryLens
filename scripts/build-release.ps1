# Thin wrapper: production frontend build for StoryLens Community 1.0.0-rc1.
# Notes:
# - Does NOT publish to GitHub.
# - Does NOT choose or write a LICENSE file.
# - Does NOT send real model requests.
# - Package manifests may still declare 0.1.0; RC marketing version is 1.0.0-rc1.
# - After build, place reproducible artifacts under artifacts/release-candidate/storylens-community-v1.0-rc1/
$ErrorActionPreference = "Stop"
Write-Host "Building StoryLens Community 1.0.0-rc1 (desktop production bundle)..."
& "$PSScriptRoot\build_desktop.ps1"
exit $LASTEXITCODE
