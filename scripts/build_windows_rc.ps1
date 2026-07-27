# Local Windows RC candidate build.
# - Temporarily sets VERSION to -RcVersion (e.g. 1.1.0-rc.8)
# - Installs Private Engine into the build venv (editable)
# - Builds via build_windows_release.ps1 with STORYLENS_RC_CANDIDATE=1
# - Restores formal VERSION files so Integration stays at the pre-override formal version
#
# Does NOT Push / Tag / Release / permanently bump VERSION.
param(
    [string]$RcVersion = "1.1.0-rc.8",
    [string]$PrivateEnginePath = "D:\Dstorylens-private-engine-wt-phase2br1-integration",
    [string]$BuildLog = ""
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

if (-not $BuildLog) {
    # Do not overwrite prior RC build logs when building a later RC.
    $safeRc = ($RcVersion -replace "[^\w\.-]", "_")
    $BuildLog = Join-Path $Root "release\evidence\RC8\windows-build-log-$safeRc.md"
}

$FormalVersion = (Get-Content -LiteralPath (Join-Path $Root "VERSION") -Raw -Encoding UTF8).Trim()
# Allow RC packaging from current formal lines (1.0.5 historical, 1.1.0 release branch).
$AllowedFormal = @("1.0.5", "1.1.0")
if ($AllowedFormal -notcontains $FormalVersion) {
    throw "Refusing RC build: formal VERSION must be one of $($AllowedFormal -join ', ') before override (got $FormalVersion)"
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
    if ($restored -ne $FormalVersion) {
        throw "VERSION restore failed; expected $FormalVersion got $restored"
    }
}

try {
    Log "RC build start"
    Log "Formal VERSION=$FormalVersion RC=$RcVersion"
    Log "PrivateEnginePath=$PrivateEnginePath"

    if (-not (Test-Path $PrivateEnginePath)) {
        throw "Private engine path missing: $PrivateEnginePath"
    }

    Log "Install Private Engine editable into build venv"
    # --no-build-isolation: avoid flaky mirror fetches of setuptools during PEP517 isolation
    & $py -m pip install -e $PrivateEnginePath --no-build-isolation
    if ($LASTEXITCODE) { throw "pip install private engine failed" }
    & $py -c "import storylens_private_engine; print('private_engine_ok', storylens_private_engine.__file__)"
    if ($LASTEXITCODE) { throw "private engine import failed after install" }

    Log "Temporary version override -> $RcVersion"
    # Formal 1.1.0 → 1.1.0-rc.N is a SemVer 'downgrade'; allow only for RC packaging override.
    & $py (Join-Path $Root "scripts\version_manager.py") set $RcVersion --allow-downgrade
    if ($LASTEXITCODE) { throw "version_manager set $RcVersion failed" }

    $env:STORYLENS_RC_CANDIDATE = "1"
    # CHG-20260727-016: single-chapter scope — do NOT bake Native Overview on.
    Remove-Item Env:VITE_PRO_NATIVE_OVERVIEW_ENABLED -ErrorAction SilentlyContinue
    Remove-Item Env:PRO_NATIVE_OVERVIEW_ENABLED -ErrorAction SilentlyContinue
    # Do not force updater signing for local RC.
    Remove-Item Env:STORYLENS_SIGN_UPDATER -ErrorAction SilentlyContinue
    Remove-Item Env:TAURI_SIGNING_PRIVATE_KEY -ErrorAction SilentlyContinue

    # Preserve prior RC installers (do not overwrite older RCs).
    $releaseDir = Join-Path $Root "dist\release"
    $archiveDir = Join-Path $releaseDir "archive"
    if (Test-Path $releaseDir) {
        New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
        Get-ChildItem -Path $releaseDir -Filter "StoryLens_*-setup.exe" -File -ErrorAction SilentlyContinue |
            ForEach-Object {
                $dest = Join-Path $archiveDir $_.Name
                if (-not (Test-Path $dest)) {
                    Log "Archiving prior installer $($_.Name)"
                    Copy-Item -Force $_.FullName $dest
                } else {
                    Log "Archive already has $($_.Name); leave untouched"
                }
            }
    }

    Log "Invoke build_windows_release.ps1 (RC candidate mode; Native Overview UI baked OFF)"
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
    Remove-Item Env:VITE_PRO_NATIVE_OVERVIEW_ENABLED -ErrorAction SilentlyContinue
    Remove-Item Env:PRO_NATIVE_OVERVIEW_ENABLED -ErrorAction SilentlyContinue
    $finished = (Get-Date).ToString("o")
    $md = @(
        "# Windows RC Build Log",
        "",
        "Started: $started",
        "Finished: $finished",
        "RC Version: $RcVersion",
        "Formal VERSION restored to: $FormalVersion",
        "Private Engine: $PrivateEnginePath",
        "STORYLENS_RC_CANDIDATE: 1",
        "VITE_PRO_NATIVE_OVERVIEW_ENABLED (RC bake): false",
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
