# Unify StoryLens version across package manifests via the Python version manager.
# Usage: ./scripts/set_version.ps1 1.0.1
# Prefer: python scripts/version_manager.py set <version>
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidatePattern('^\d+\.\d+\.\d+([.-][A-Za-z0-9.-]+)?$')]
    [string]$Version,
    [switch]$AllowDowngrade,
    [switch]$AllowSame
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    $py = "python"
}

$args = @((Join-Path $PSScriptRoot "version_manager.py"), "set", $Version)
if ($AllowDowngrade) { $args += "--allow-downgrade" }
if ($AllowSame) { $args += "--allow-same" }

& $py @args
exit $LASTEXITCODE
