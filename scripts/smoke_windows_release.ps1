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

function Get-PortListenOwner([int]$ListenPort) {
    if ($ListenPort -le 0) { return $null }
    $conn = Get-NetTCPConnection -LocalPort $ListenPort -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $conn) { return $null }
    return [int]$conn.OwningProcess
}

function Get-PidsByExecutablePath([string]$ExePath) {
    if (-not $ExePath) { return @() }
    $resolved = $null
    try { $resolved = [System.IO.Path]::GetFullPath($ExePath) } catch { $resolved = $ExePath }
    $normalized = $resolved.TrimEnd('\', '/').ToLowerInvariant()
    $pids = New-Object System.Collections.Generic.List[int]
    foreach ($row in @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)) {
        if (-not $row.ExecutablePath) { continue }
        $ep = $null
        try { $ep = [System.IO.Path]::GetFullPath([string]$row.ExecutablePath) } catch { $ep = [string]$row.ExecutablePath }
        if ($ep.TrimEnd('\', '/').ToLowerInvariant() -eq $normalized) {
            $pids.Add([int]$row.ProcessId)
        }
    }
    return @($pids | Select-Object -Unique)
}

function Get-NewPidsByPath([string]$ExePath, [int[]]$BaselinePids) {
    $baseline = @{}
    foreach ($b in @($BaselinePids)) { if ($b -gt 0) { $baseline[[int]$b] = $true } }
    $current = @(Get-PidsByExecutablePath -ExePath $ExePath)
    $added = New-Object System.Collections.Generic.List[int]
    foreach ($pidNow in $current) {
        if (-not $baseline.ContainsKey([int]$pidNow)) {
            $added.Add([int]$pidNow)
        }
    }
    return @($added)
}

$SidecarCandidates = @(
    (Join-Path $Root "apps\desktop\src-tauri\binaries\storylens-api-x86_64-pc-windows-msvc.exe"),
    (Join-Path $Root "dist\release\storylens-api.exe")
)
$Sidecar = $SidecarCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($Sidecar) {
    Write-Host "==> Sidecar process smoke: $Sidecar"
    $SmokeData = Join-Path $env:TEMP ("storylens-smoke-" + [guid]::NewGuid().ToString("n"))
    New-Item -ItemType Directory -Force -Path $SmokeData | Out-Null
    $StopTree = Join-Path $Root "scripts\stop_owned_process_tree.ps1"
    $smokeFailed = $false
    $smokeError = $null
    try {
        $Port = 0
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
        $listener.Start()
        try { $Port = ($listener.LocalEndpoint).Port } finally { $listener.Stop() }

        $env:STORYLENS_DATA_DIR = $SmokeData
        $env:STORYLENS_APP_ENV = "production"
        $env:STORYLENS_APP_HOST = "127.0.0.1"
        $env:STORYLENS_APP_PORT = "$Port"
        $env:STORYLENS_SHUTDOWN_TOKEN = [guid]::NewGuid().ToString("n")

        # Path-based ownership: never rely solely on Start-Process root / parent tree.
        $baselinePathPids = @(Get-PidsByExecutablePath -ExePath $Sidecar)
        Write-Host ("Baseline same-path PIDs before smoke: " + (@($baselinePathPids) -join ', '))

        $proc = $null
        $listenOwner = $null
        $ownedNewPids = @()
        try {
            $proc = Start-Process -FilePath $Sidecar -PassThru -WindowStyle Hidden
            $deadline = (Get-Date).AddSeconds(120)
            $healthy = $false
            while ((Get-Date) -lt $deadline) {
                # Re-scan path PIDs every loop — PyInstaller onefile may spawn a sibling/orphan.
                $ownedNewPids = @(Get-NewPidsByPath -ExePath $Sidecar -BaselinePids $baselinePathPids)
                if ($proc -and $proc.Id -gt 0 -and ($ownedNewPids -notcontains [int]$proc.Id)) {
                    # Root may already have exited; still keep it in the owned set if it was ours.
                    if (-not (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue)) {
                        # exited — path scan is source of truth
                    } else {
                        $ownedNewPids = @($ownedNewPids + [int]$proc.Id | Select-Object -Unique)
                    }
                }
                try {
                    $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 5
                    if ($resp.StatusCode -eq 200) {
                        $listenOwner = Get-PortListenOwner -ListenPort $Port
                        $ownedNewPids = @(Get-NewPidsByPath -ExePath $Sidecar -BaselinePids $baselinePathPids)
                        if ($listenOwner) {
                            $ownedNewPids = @($ownedNewPids + [int]$listenOwner | Select-Object -Unique)
                        }
                        if ($proc -and -not $proc.HasExited) {
                            $ownedNewPids = @($ownedNewPids + [int]$proc.Id | Select-Object -Unique)
                        }
                        $healthy = $true
                        break
                    }
                } catch {
                    # Prefer path ownership over "root still alive" — wrapper may exit early.
                    $anyOwnedAlive = $false
                    foreach ($oid in @($ownedNewPids)) {
                        if (Get-Process -Id $oid -ErrorAction SilentlyContinue) {
                            $anyOwnedAlive = $true
                            break
                        }
                    }
                    if ($proc) {
                        $proc.Refresh()
                        if (-not $proc.HasExited) { $anyOwnedAlive = $true }
                    }
                    if (-not $anyOwnedAlive -and $ownedNewPids.Count -eq 0 -and $proc -and $proc.HasExited) {
                        $logHint = ""
                        $logPath = Join-Path $SmokeData "logs\sidecar.log"
                        if (Test-Path $logPath) {
                            $logHint = (Get-Content $logPath -Tail 8) -join " | "
                        }
                        throw "Sidecar exited early with code $($proc.ExitCode). $logHint"
                    }
                    Start-Sleep -Milliseconds 500
                }
            }
            if (-not $healthy) {
                throw "Sidecar /health not reachable on port $Port within timeout"
            }
            # A clean packaged runtime must receive the public material seed without
            # inheriting any local books or database rows from the build machine.
            $seedSummary = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/material-lab/library/summary" -TimeoutSec 10
            $seedState = "$($seedSummary.knowledge_count),$($seedSummary.imported_knowledge_count),$($seedSummary.source_book_count)"
            if ($seedState -ne "798,798,0") {
                throw "Packaged material seed mismatch (all,imported,books=$seedState; expected 798,798,0)"
            }
            Write-Host "Packaged material seed OK (materials=798, imported=798, books=0)"
            Write-Host ("Sidecar /health OK (data_dir=$SmokeData, start_pid=$($proc.Id), listen_pid=$listenOwner, owned_new=$($ownedNewPids -join ','))")
        } catch {
            $smokeFailed = $true
            $smokeError = $_
        } finally {
            # Exact cleanup of this smoke run's path-delta PIDs (never baseline / other instances).
            $ownedNewPids = @(Get-NewPidsByPath -ExePath $Sidecar -BaselinePids $baselinePathPids)
            if ($listenOwner) {
                $ownedNewPids = @($ownedNewPids + [int]$listenOwner | Select-Object -Unique)
            }
            $ownerNow = Get-PortListenOwner -ListenPort $Port
            if ($ownerNow) {
                # Only claim listen owner if it appeared as a new same-path PID or was already owned.
                $pathNow = @(Get-PidsByExecutablePath -ExePath $Sidecar)
                if (($ownedNewPids -contains [int]$ownerNow) -or ($pathNow -contains [int]$ownerNow -and ($baselinePathPids -notcontains [int]$ownerNow))) {
                    $ownedNewPids = @($ownedNewPids + [int]$ownerNow | Select-Object -Unique)
                }
            }
            if ($proc -and $proc.Id -gt 0 -and ($baselinePathPids -notcontains [int]$proc.Id)) {
                $ownedNewPids = @($ownedNewPids + [int]$proc.Id | Select-Object -Unique)
            }

            Write-Host ("Cleaning owned new PIDs: " + (@($ownedNewPids) -join ', '))
            if ($ownedNewPids.Count -gt 0) {
                try {
                    $null = & $StopTree -ExactProcessIds $ownedNewPids -WaitMs 10000
                } catch {
                    $smokeFailed = $true
                    if (-not $smokeError) { $smokeError = $_ }
                }
            }

            $residual = @()
            foreach ($targetPid in @($ownedNewPids | Select-Object -Unique)) {
                if ($targetPid -and (Get-Process -Id $targetPid -ErrorAction SilentlyContinue)) {
                    $residual += [int]$targetPid
                }
            }
            # Also fail if any new same-path PID remains after cleanup.
            $stillNew = @(Get-NewPidsByPath -ExePath $Sidecar -BaselinePids $baselinePathPids)
            foreach ($p in $stillNew) {
                if ($residual -notcontains [int]$p) { $residual += [int]$p }
            }
            if ($residual.Count -gt 0) {
                $smokeFailed = $true
                $msg = "Residual sidecar PID(s) after smoke cleanup: $($residual -join ', ')"
                if (-not $smokeError) { $smokeError = $msg } else { Write-Host $msg -ForegroundColor Red }
            } else {
                Write-Host "No residual sidecar from this smoke run (owned new PIDs: $($ownedNewPids -join ', '))"
            }

            # Must not disturb baseline PIDs that existed before this smoke.
            foreach ($b in @($baselinePathPids)) {
                if ($b -and -not (Get-Process -Id $b -ErrorAction SilentlyContinue)) {
                    # Baseline may exit on its own; that is not a smoke failure.
                }
            }
        }

        if ($smokeFailed) {
            if ($smokeError -is [System.Management.Automation.ErrorRecord]) {
                throw $smokeError
            }
            throw "$smokeError"
        }
    } finally {
        Remove-Item -Recurse -Force $SmokeData -ErrorAction SilentlyContinue
        Remove-Item Env:STORYLENS_DATA_DIR -ErrorAction SilentlyContinue
        Remove-Item Env:STORYLENS_APP_ENV -ErrorAction SilentlyContinue
        Remove-Item Env:STORYLENS_APP_HOST -ErrorAction SilentlyContinue
        Remove-Item Env:STORYLENS_APP_PORT -ErrorAction SilentlyContinue
        Remove-Item Env:STORYLENS_SHUTDOWN_TOKEN -ErrorAction SilentlyContinue
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
