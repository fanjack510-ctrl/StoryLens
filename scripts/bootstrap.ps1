# Thin wrapper: StoryLens one-click environment bootstrap (Windows).
param(
    [switch]$SkipInstall,
    [switch]$UseOfficialPyPI
)
$ErrorActionPreference = "Stop"
& "$PSScriptRoot\bootstrap_windows.ps1" -SkipInstall:$SkipInstall -UseOfficialPyPI:$UseOfficialPyPI
exit $LASTEXITCODE
