# One-shot Windows release build:
# frontend → FastAPI sidecar → Tauri NSIS installer → dist/release/
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$Summary = [ordered]@{
    started_at = (Get-Date).ToString("o")
    version = $null
    frontend = "pending"
    sidecar = "pending"
    tauri = "pending"
    updater_artifacts = "skipped"
    outputs = @()
    errors = @()
}

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==== $Message ====" -ForegroundColor Cyan
}

$TauriConf = Join-Path $Root "apps\desktop\src-tauri\tauri.conf.json"
$TauriConfBackup = $null

try {
    $confRaw = Get-Content -LiteralPath $TauriConf -Raw -Encoding UTF8
    if ($confRaw -match '"version"\s*:\s*"([^"]+)"') {
        $Summary.version = $Matches[1]
    }

    # Opt-in signing only. Lingering shell env keys must not enable signing or hang on password prompts.
    $HasSigningKey = ($env:STORYLENS_SIGN_UPDATER -eq "1") -and [bool]$env:TAURI_SIGNING_PRIVATE_KEY
    if (
        ($env:STORYLENS_SIGN_UPDATER -eq "1") -and
        -not $HasSigningKey -and
        $env:TAURI_SIGNING_PRIVATE_KEY_PATH -and
        (Test-Path $env:TAURI_SIGNING_PRIVATE_KEY_PATH)
    ) {
        $env:TAURI_SIGNING_PRIVATE_KEY = [System.IO.File]::ReadAllText($env:TAURI_SIGNING_PRIVATE_KEY_PATH).Trim()
        if ($null -eq $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD) {
            $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = ""
        }
        $HasSigningKey = [bool]$env:TAURI_SIGNING_PRIVATE_KEY
        Write-Host "Loaded updater private key from TAURI_SIGNING_PRIVATE_KEY_PATH (value not logged)."
    }

    # Patch conf for this build only; restore afterwards so the working tree stays clean.
    $TauriConfBackup = $confRaw
    $patched = $confRaw
    if ($env:TAURI_UPDATER_PUBKEY) {
        Write-Step "Inject updater pubkey from TAURI_UPDATER_PUBKEY"
        $pk = $env:TAURI_UPDATER_PUBKEY.Trim()
        $patched = [regex]::Replace(
            $patched,
            '"pubkey"\s*:\s*"[^"]*"',
            "`"pubkey`": `"$pk`"",
            1
        )
    }
    $artifactFlag = if ($HasSigningKey) { "true" } else { "false" }
    $patched = [regex]::Replace(
        $patched,
        '"createUpdaterArtifacts"\s*:\s*(true|false)',
        "`"createUpdaterArtifacts`": $artifactFlag",
        1
    )
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($TauriConf, $patched, $utf8)
    if ($HasSigningKey) {
        $Summary.updater_artifacts = "enabled"
    } else {
        Write-Host "No updater signing key; building installer without updater signatures."
        $Summary.updater_artifacts = "skipped_no_secret"
    }

    Write-Step "Frontend dependency check"
    Push-Location (Join-Path $Root "apps\desktop")
    try {
        if (-not (Test-Path "node_modules")) {
            & npm.cmd ci
            if ($LASTEXITCODE) { throw "npm ci failed" }
        } else {
            & npm.cmd install
            if ($LASTEXITCODE) { throw "npm install failed" }
        }
        Write-Step "Frontend build (vite)"
        # Use vite directly: full `tsc -b` is covered by npm run typecheck / typecheck:e2e.
        # Vite may write chunk-size warnings to stderr; with ErrorActionPreference=Stop that
        # becomes a terminating NativeCommandError even when exit code is 0.
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            & npx.cmd vite build
            if ($LASTEXITCODE) { throw "frontend build failed" }
        } finally {
            $ErrorActionPreference = $prevEap
        }
        $Summary.frontend = "ok"
    } finally {
        Pop-Location
    }

    Write-Step "FastAPI sidecar build"
    & (Join-Path $Root "scripts\build_sidecar.ps1")
    if ($LASTEXITCODE) { throw "sidecar build failed" }
    $Summary.sidecar = "ok"

    $Sidecar = Join-Path $Root "apps\desktop\src-tauri\binaries\storylens-api-x86_64-pc-windows-msvc.exe"
    if (-not (Test-Path $Sidecar)) {
        throw "Sidecar missing after build: $Sidecar"
    }

    Write-Step "Tauri Windows installer"
    Push-Location (Join-Path $Root "apps\desktop")
    try {
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            & npm.cmd run tauri -- build --bundles nsis
            if ($LASTEXITCODE) { throw "tauri build failed" }
        } finally {
            $ErrorActionPreference = $prevEap
        }
        $Summary.tauri = "ok"
    } finally {
        Pop-Location
    }

    Write-Step "Collect release artifacts"
    $ReleaseDir = Join-Path $Root "dist\release"
    New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
    Get-ChildItem $ReleaseDir -Force | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    $BundleDir = Join-Path $Root "apps\desktop\src-tauri\target\release\bundle"
    $copied = @()
    Get-ChildItem -Path $BundleDir -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in ".exe", ".msi", ".sig", ".json", ".zip" -or $_.Name -like "*.nsis.zip" } |
        ForEach-Object {
            $dest = Join-Path $ReleaseDir $_.Name
            Copy-Item -Force $_.FullName $dest
            $copied += $dest
        }

    Copy-Item -Force $Sidecar (Join-Path $ReleaseDir "storylens-api.exe")
    $copied += (Join-Path $ReleaseDir "storylens-api.exe")

    $nsis = Get-ChildItem $ReleaseDir -Filter "*.exe" | Where-Object { $_.Name -match "StoryLens|nsis|setup" -and $_.Name -ne "storylens-api.exe" }
    if (-not $nsis) {
        # Tauri NSIS typically: StoryLens_0.1.0_x64-setup.exe
        $nsis = Get-ChildItem $ReleaseDir -Filter "*setup*.exe" -ErrorAction SilentlyContinue
    }
    if (-not $nsis) {
        throw "NSIS installer not found under dist/release"
    }

    $Summary.outputs = $copied
    $Summary.installer = $nsis[0].FullName
    $Summary.sidecar_in_release = (Test-Path (Join-Path $ReleaseDir "storylens-api.exe"))
    $Summary.finished_at = (Get-Date).ToString("o")

    $SummaryPath = Join-Path $ReleaseDir "build-summary.json"
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($SummaryPath, ($Summary | ConvertTo-Json -Depth 6), $utf8)

    Write-Step "Release artifact gates"
    & (Join-Path $Root "scripts\check_release_artifacts.ps1") -ReleaseDir $ReleaseDir
    if ($LASTEXITCODE) { throw "release artifact gates failed" }

    Write-Host ""
    Write-Host "BUILD OK" -ForegroundColor Green
    Write-Host "Version: $($Summary.version)"
    Write-Host "Installer: $($Summary.installer)"
    Write-Host "Sidecar bundled for Tauri externalBin: $Sidecar"
    Write-Host "Release dir: $ReleaseDir"
    Write-Host "Updater artifacts: $($Summary.updater_artifacts)"
    Write-Host "Summary: $SummaryPath"
} catch {
    $Summary.errors += $_.Exception.Message
    $Summary.finished_at = (Get-Date).ToString("o")
    $ReleaseDir = Join-Path $Root "dist\release"
    New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
    $Summary | ConvertTo-Json -Depth 6 | ForEach-Object {
        $utf8 = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText((Join-Path $ReleaseDir "build-summary.json"), $_, $utf8)
    }
    Write-Host "BUILD FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    if ($null -ne $TauriConfBackup) {
        $utf8 = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText($TauriConf, $TauriConfBackup, $utf8)
    }
}
