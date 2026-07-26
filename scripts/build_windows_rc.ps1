# Local Windows RC candidate build (STEP 2.7).
# - Temporarily sets VERSION to 1.1.0-rc.1 (or -RcVersion)
# - Installs Private Engine into the build venv (editable)
# - Builds via build_windows_release.ps1 with STORYLENS_RC_CANDIDATE=1
# - Restores formal VERSION files so Integration stays at 1.0.5
#
# Does NOT Push / Tag / Release / permanently bump VERSION.
param(
    [string]$RcVersion = "1.1.0-rc.1",
    [string]$PrivateEnginePath = "D:\Dstorylens-private-engine-wt-phase2br1-integration",
    [string]$BuildLog = ""
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

if (-not $BuildLog) {
    $BuildLog = Join-Path $Root "release\evidence\CHG-20260725-003\night-run\windows-build-log.md"
}

$FormalVersion = (Get-Content -LiteralPath (Join-Path $Root "VERSION") -Raw -Encoding UTF8).Trim()
if ($FormalVersion -ne "1.0.5") {
    throw "Refusing RC build: formal VERSION must be 1.0.5 before override (got $FormalVersion)"
}

$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Missing .venv at $py" }

$started = (Get-Date).ToString("o")
$logLines = New-Object System.Collections.Generic.List[string]
function Log([string]$Message) {
    $line = "$(Get-Date -Format o)  $Message"
    Write-Host $line
    $logLines.Add($line) | Out-Null
}

function Restore-FormalVersion {
    Log "Restoring formal VERSION files via git checkout"
    & git -C $Root checkout -- `
        VERSION `
        apps/desktop/package.json `
        apps/desktop/package-lock.json `
        apps/desktop/src-tauri/tauri.conf.json `
        apps/desktop/src-tauri/Cargo.toml `
        apps/desktop/src-tauri/Cargo.lock `
        pyproject.toml `
        apps/api/app/__init__.py `
        2>&1 | ForEach-Object { Log "$_" }
    $restored = (Get-Content -LiteralPath (Join-Path $Root "VERSION") -Raw -Encoding UTF8).Trim()
    if ($restored -ne "1.0.5") {
        throw "VERSION restore failed; got $restored"
    }
}

try {
    Log "STEP 2.7 RC build start"
    Log "Formal VERSION=$FormalVersion RC=$RcVersion"
    Log "PrivateEnginePath=$PrivateEnginePath"

    if (-not (Test-Path $PrivateEnginePath)) {
        throw "Private engine path missing: $PrivateEnginePath"
    }

    Log "Install Private Engine editable into build venv"
    & $py -m pip install -e $PrivateEnginePath
    if ($LASTEXITCODE) { throw "pip install private engine failed" }
    & $py -c "import storylens_private_engine; print('private_engine_ok', storylens_private_engine.__file__)"
    if ($LASTEXITCODE) { throw "private engine import failed after install" }

    Log "Temporary version override -> $RcVersion"
    & $py (Join-Path $Root "scripts\version_manager.py") set $RcVersion
    if ($LASTEXITCODE) { throw "version_manager set $RcVersion failed" }

    $env:STORYLENS_RC_CANDIDATE = "1"
    # Do not force updater signing for local RC.
    Remove-Item Env:STORYLENS_SIGN_UPDATER -ErrorAction SilentlyContinue
    Remove-Item Env:TAURI_SIGNING_PRIVATE_KEY -ErrorAction SilentlyContinue

    Log "Invoke build_windows_release.ps1 (RC candidate mode)"
    & (Join-Path $Root "scripts\build_windows_release.ps1")
    if ($LASTEXITCODE) { throw "build_windows_release.ps1 failed" }

    $summaryPath = Join-Path $Root "dist\release\build-summary.json"
    if (Test-Path $summaryPath) {
        Log "build-summary.json present"
        Get-Content $summaryPath | ForEach-Object { Log $_ }
    }

    Log "RC build finished OK"
} catch {
    Log "RC BUILD FAILED: $($_.Exception.Message)"
    throw
} finally {
    try { Restore-FormalVersion } catch { Log "RESTORE WARNING: $_" }
    $env:STORYLENS_RC_CANDIDATE = $null
    $finished = (Get-Date).ToString("o")
    $md = @(
        "# Windows RC Build Log",
        "",
        "Started: $started",
        "Finished: $finished",
        "RC Version: $RcVersion",
        "Formal VERSION restored to: 1.0.5",
        "Private Engine: $PrivateEnginePath",
        "STORYLENS_RC_CANDIDATE: 1",
        "Live Provider: NO",
        "",
        "## Log",
        ""
    ) + ($logLines | ForEach-Object { "- $_" })
    $utf8 = New-Object System.Text.UTF8Encoding $false
    New-Item -ItemType Directory -Force -Path (Split-Path $BuildLog) | Out-Null
    [System.IO.File]::WriteAllLines($BuildLog, $md, $utf8)
    Log "Wrote $BuildLog"
}
