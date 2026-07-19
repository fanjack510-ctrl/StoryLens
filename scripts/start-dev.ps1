# Thin wrapper: start StoryLens API + desktop dev servers.
param(
    [switch]$Tauri,
    [switch]$StartLocalModel
)
$ErrorActionPreference = "Stop"
& "$PSScriptRoot\start_storylens_dev.ps1" -Tauri:$Tauri -StartLocalModel:$StartLocalModel
exit $LASTEXITCODE
