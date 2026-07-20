# Windows desktop release smoke checks (no full GUI automation).
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Missing .venv. Run .\scripts\bootstrap.ps1 first."
}

Write-Host "==> Python release smoke tests"
& $Python -m pytest apps/api/tests/test_sidecar_entry.py apps/api/tests/test_windows_release_smoke.py -q
if ($LASTEXITCODE) { exit $LASTEXITCODE }

$SidecarCandidates = @(
    (Join-Path $Root "apps\desktop\src-tauri\binaries\storylens-api-x86_64-pc-windows-msvc.exe"),
    (Join-Path $Root "dist\release\storylens-api.exe")
)
$Sidecar = $SidecarCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($Sidecar) {
    Write-Host "==> Sidecar process smoke: $Sidecar"
    $SmokeData = Join-Path $env:TEMP ("storylens-smoke-" + [guid]::NewGuid().ToString("n"))
    New-Item -ItemType Directory -Force -Path $SmokeData | Out-Null
    try {
        $Port = 0
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
        $listener.Start()
        try { $Port = ($listener.LocalEndpoint).Port } finally { $listener.Stop() }

        $env:STORYLENS_DATA_DIR = $SmokeData
        $env:STORYLENS_APP_ENV = "production"
        $env:STORYLENS_APP_HOST = "127.0.0.1"
        $env:STORYLENS_APP_PORT = "$Port"

        $proc = $null
        try {
            $proc = Start-Process -FilePath $Sidecar -PassThru -WindowStyle Hidden
            $deadline = (Get-Date).AddSeconds(120)
            $healthy = $false
            while ((Get-Date) -lt $deadline) {
                if ($proc.HasExited) {
                    $logHint = ""
                    $logPath = Join-Path $SmokeData "logs\sidecar.log"
                    if (Test-Path $logPath) {
                        $logHint = (Get-Content $logPath -Tail 8) -join " | "
                    }
                    throw "Sidecar exited early with code $($proc.ExitCode). $logHint"
                }
                try {
                    $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 5
                    if ($resp.StatusCode -eq 200) {
                        $healthy = $true
                        break
                    }
                } catch {
                    Start-Sleep -Milliseconds 500
                }
            }
            if (-not $healthy) {
                throw "Sidecar /health not reachable on port $Port within timeout"
            }
            Write-Host "Sidecar /health OK (data_dir=$SmokeData)"
        } finally {
            if ($proc -and -not $proc.HasExited) {
                Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
                $proc.WaitForExit(5000)
            }
        }
    } finally {
        Remove-Item -Recurse -Force $SmokeData -ErrorAction SilentlyContinue
        Remove-Item Env:STORYLENS_DATA_DIR -ErrorAction SilentlyContinue
        Remove-Item Env:STORYLENS_APP_ENV -ErrorAction SilentlyContinue
        Remove-Item Env:STORYLENS_APP_HOST -ErrorAction SilentlyContinue
        Remove-Item Env:STORYLENS_APP_PORT -ErrorAction SilentlyContinue
    }
} else {
    Write-Host "SKIP sidecar EXE smoke (binary not built yet)" -ForegroundColor Yellow
}

$ReleaseDir = Join-Path $Root "dist\release"
if (Test-Path $ReleaseDir) {
    Write-Host "==> Release artifact gates"
    & (Join-Path $Root "scripts\check_release_artifacts.ps1") -ReleaseDir $ReleaseDir
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
} else {
    Write-Host "SKIP release artifact gates (dist/release not present)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "MANUAL ACCEPTANCE (not automated):" -ForegroundColor Cyan
Write-Host "  - Install NSIS package and confirm StoryLens starts backend automatically"
Write-Host "  - Close app and confirm sidecar process exits"
Write-Host "  - Confirm user database lives under %LOCALAPPDATA%\\StoryLens\\"
Write-Host "  - Manual updater check against a real GitHub Release latest.json"
Write-Host ""
Write-Host "SMOKE OK" -ForegroundColor Green
