# Private Whole-Book Live Smoke (default dry-run)
# Real Live requires -Live AND WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE=1
# Integration CI must not pass -Live.
param(
    [Parameter(Mandatory = $true)][int]$BookId,
    [Parameter(Mandatory = $true)][int]$SnapshotId,
    [string]$Modules = "book_overview",
    [switch]$Live,
    [switch]$Yes,
    [switch]$Cancel,
    [switch]$CheckResults
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    $py = "python"
}
$script = Join-Path $PSScriptRoot "private_whole_book_live_smoke.py"
$argsList = @(
    $script,
    "--book-id", $BookId,
    "--snapshot-id", $SnapshotId,
    "--modules", $Modules
)
if ($Live) { $argsList += "--live" }
if ($Yes) { $argsList += "--yes" }
if ($Cancel) { $argsList += "--cancel" }
if ($CheckResults) { $argsList += "--check-results" }

& $py @argsList
exit $LASTEXITCODE
