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

$VersionFile = Join-Path $Root "VERSION"
if (-not (Test-Path $VersionFile)) {
    Fail "VERSION file missing at repo root"
}
$ExpectedVersion = (Get-Content -LiteralPath $VersionFile -Raw -Encoding UTF8).Trim()
if (-not $ExpectedVersion) {
    Fail "VERSION file is empty"
}

$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
& $py (Join-Path $Root "scripts\version_manager.py") check
if ($LASTEXITCODE) {
    Fail "version_manager.py check failed"
}
$IsRcCandidate = ($env:STORYLENS_RC_CANDIDATE -eq "1")
if ($IsRcCandidate) {
    Write-Host "STORYLENS_RC_CANDIDATE=1: skip change_registry --release and release-guard for local RC artifact gates."
} else {
    & $py (Join-Path $Root "scripts\change_registry.py") check --release
    if ($LASTEXITCODE) {
        Fail "change_registry.py check --release failed"
    }
    & $py (Join-Path $Root "scripts\version_manager.py") release-guard --artifacts-dir $ReleaseDir
    if ($LASTEXITCODE) {
        Fail "version_manager.py release-guard failed"
    }
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
    if ($inst.Name -notlike "*${ExpectedVersion}*") {
        Fail "Installer name missing VERSION ${ExpectedVersion}: $($inst.Name)"
    }
}

$LatestJson = Join-Path $ReleaseDir "latest.json"
if (Test-Path $LatestJson) {
    $latestRaw = Get-Content -LiteralPath $LatestJson -Raw -Encoding UTF8
    if ($latestRaw -notmatch '"version"\s*:\s*"' + [regex]::Escape($ExpectedVersion) + '"') {
        Fail "latest.json version does not match VERSION $ExpectedVersion"
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
