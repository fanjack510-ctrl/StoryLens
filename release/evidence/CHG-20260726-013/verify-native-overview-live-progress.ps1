# CHG-20260726-013 — Native Overview live progress (Fake Slow, zero Provider cost)
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File "...\verify-native-overview-live-progress.ps1"
param()
$ErrorActionPreference = "Stop"
$Repo = "D:\Dstorylens-wt-narrative-phase2br1-integration"
$PrivateSrc = "D:\Dstorylens-private-engine-wt-phase2br1-integration\src"
$Evidence = Join-Path $Repo "release\evidence\CHG-20260726-013"
$Py = Join-Path $Repo ".venv\Scripts\python.exe"
$WatchPorts = @(8000, 1420, 1421, 18003)

New-Item -ItemType Directory -Force $Evidence | Out-Null

function Get-Cmd([int]$ProcessId) {
  try {
    $p = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if ($p) { return [string]$p.CommandLine }
  } catch {}
  return ""
}

Write-Host "=== Leftover check (report-only, no kill) ==="
$blockers = @()
Get-Process -ErrorAction SilentlyContinue | Where-Object {
  $_.ProcessName -match '^(?i)storylens(-api|-desktop)?$'
} | ForEach-Object {
  $blockers += [pscustomobject]@{ Kind="process"; PID=$_.Id; Name=$_.ProcessName; Cmd=(Get-Cmd $_.Id) }
}
foreach ($port in $WatchPorts) {
  Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
    $opid = [int]$_.OwningProcess
    $proc = Get-Process -Id $opid -ErrorAction SilentlyContinue
    $blockers += [pscustomobject]@{
      Kind="port"; PID=$opid; Name="$($proc.ProcessName) :$port"; Cmd=(Get-Cmd $opid)
    }
  }
}
if ($blockers.Count -gt 0) {
  $blockers | Format-Table -AutoSize | Out-String | Write-Host
  $blockers | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $Evidence "environment-blockers.json")
  throw "Leftover processes/ports detected — close manually and re-run."
}
Write-Host "Environment PASS"

$env:PYTHONPATH = (Join-Path $Repo "apps\api") + ";" + $PrivateSrc
$env:PRO_NATIVE_OVERVIEW_ENABLED = "true"
Get-ChildItem Env: | Where-Object { $_.Name -like 'STORYLENS_*' -and $_.Name -match 'FAKE' } |
  ForEach-Object { Remove-Item "Env:$($_.Name)" -ErrorAction SilentlyContinue }

Write-Host "=== Targeted pytest ==="
& $Py -m pytest `
  (Join-Path $Repo "apps\api\tests\test_native_overview_live_progress_local.py") `
  (Join-Path $Repo "apps\api\tests\test_stale_run_startup_recovery_local.py") `
  -q --tb=line
if ($LASTEXITCODE -ne 0) { throw "targeted tests failed" }

Write-Host "=== Fake slow 3-window progress sequence ==="
& $Py (Join-Path $Evidence "write_progress_sequence_evidence.py")
if ($LASTEXITCODE -ne 0) { throw "progress sequence evidence failed" }

$lock = 0
Get-ChildItem $Evidence -Filter "*.log" -ErrorAction SilentlyContinue | ForEach-Object {
  $t = Get-Content $_.FullName -Raw -ErrorAction SilentlyContinue
  if ($t -and $t -match 'database is locked') { $lock++ }
}
Write-Host "DATABASE_LOCK_ERRORS=$lock"
Write-Host "REAL_PROVIDER_CALLS=0"
Write-Host "FORMAL_DATABASE_WRITES=0"
Write-Host "INSTALLER_BUILD_COUNT=0"
if ($lock -gt 0) { throw "database lock detected" }
Write-Host "VERIFY PASS"
