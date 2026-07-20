# Read-only release artifact gates for dist/release/
param(
    [string]$ReleaseDir = ""
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
if (-not $ReleaseDir) {
    $ReleaseDir = Join-Path $Root "dist\release"
}

function Fail([string]$Message) {
    Write-Host "RELEASE GATE FAILED: $Message" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $ReleaseDir)) {
    Fail "Release directory missing: $ReleaseDir"
}

$SummaryPath = Join-Path $ReleaseDir "build-summary.json"
if (-not (Test-Path $SummaryPath)) {
    Fail "build-summary.json missing under $ReleaseDir"
}

$Sidecar = Join-Path $ReleaseDir "storylens-api.exe"
if (-not (Test-Path $Sidecar)) {
    Fail "storylens-api.exe missing in release dir"
}
if ((Get-Item $Sidecar).Length -le 0) {
    Fail "storylens-api.exe is empty"
}

$Installers = @(
    Get-ChildItem -Path $ReleaseDir -Filter "*.exe" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ne "storylens-api.exe" -and ($_.Name -match "setup|StoryLens") }
)
if (-not $Installers) {
    Fail "NSIS installer not found in $ReleaseDir"
}
foreach ($inst in $Installers) {
    if ($inst.Length -le 0) {
        Fail "Installer is empty: $($inst.FullName)"
    }
}

$SecretPatterns = @(
    "BEGIN RSA PRIVATE KEY",
    "BEGIN PRIVATE KEY",
    "TAURI_SIGNING_PRIVATE_KEY="
)
Get-ChildItem -Path $ReleaseDir -Recurse -File | ForEach-Object {
    $text = Get-Content -LiteralPath $_.FullName -Raw -ErrorAction SilentlyContinue
    if (-not $text) { return }
    foreach ($pat in $SecretPatterns) {
        if ($text -match [regex]::Escape($pat)) {
            Fail "Possible secret material in release artifact: $($_.FullName)"
        }
    }
}

$TrackedSidecar = git -C $Root ls-files -- "apps/desktop/src-tauri/binaries/*.exe" 2>$null
if ($TrackedSidecar) {
    Fail "Sidecar EXE must not be tracked by Git: $TrackedSidecar"
}

$StagedSidecar = git -C $Root diff --cached --name-only -- "apps/desktop/src-tauri/binaries/*.exe" 2>$null
if ($StagedSidecar) {
    Fail "Sidecar EXE must not be staged for commit: $StagedSidecar"
}

Write-Host "Release artifact gates passed: $ReleaseDir" -ForegroundColor Green
