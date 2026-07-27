# CHG-20260726-012 — Full short-book Native Overview real E2E
# Book: #5 《十日前4章》 via temp DB + source API (no formal DB writes, no installer).
#
# Usage:
#   # Preflight only (no whole-book Provider window calls)
#   powershell -NoProfile -ExecutionPolicy Bypass -File "...\verify-shortbook-native-overview-e2e.ps1"
#
#   # After reviewing preflight values:
#   powershell -NoProfile -ExecutionPolicy Bypass -File "...\verify-shortbook-native-overview-e2e.ps1" -ConfirmLive
#
# Does NOT modify source. Does NOT build installer. Does NOT auto-kill leftover processes.
param(
  [switch]$ConfirmLive
)

$ErrorActionPreference = "Stop"
$Repo = "D:\Dstorylens-wt-narrative-phase2br1-integration"
$PrivateSrc = "D:\Dstorylens-private-engine-wt-phase2br1-integration\src"
$Evidence = Join-Path $Repo "release\evidence\CHG-20260726-012"
$LiveDir = Join-Path $Evidence "shortbook-e2e-live"
$Py = Join-Path $Repo ".venv\Scripts\python.exe"
$Runner = Join-Path $Evidence "verify_shortbook_native_overview_e2e.py"
$ApiPort = 18002
$WatchPorts = @(8000, 1420, 1421, 18000, $ApiPort)

New-Item -ItemType Directory -Force $LiveDir | Out-Null

function Get-ProcessCommandLine {
  param([int]$ProcessId)
  try {
    $p = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if ($p) { return [string]$p.CommandLine }
  } catch {}
  return ""
}

function Get-ProcessPathSafe {
  param($Proc)
  try { return [string]$Proc.Path } catch { return "" }
}

function Test-LeftoverEnvironment {
  $blockers = @()

  # Named StoryLens installer / desktop / api processes
  $named = Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -match '^(?i)storylens(-api|-desktop)?$'
  }
  foreach ($p in $named) {
    $blockers += [pscustomobject]@{
      Kind = "process"
      Name = $p.ProcessName
      PID = $p.Id
      Path = (Get-ProcessPathSafe $p)
      CommandLine = (Get-ProcessCommandLine -ProcessId $p.Id)
    }
  }

  # Explicit exe name checks
  foreach ($exe in @("storylens-desktop", "storylens-api")) {
    $hit = Get-Process -Name $exe -ErrorAction SilentlyContinue
    foreach ($p in $hit) {
      $blockers += [pscustomobject]@{
        Kind = "process"
        Name = $p.ProcessName
        PID = $p.Id
        Path = (Get-ProcessPathSafe $p)
        CommandLine = (Get-ProcessCommandLine -ProcessId $p.Id)
      }
    }
  }

  # Port listeners (installer / Vite / prior API)
  foreach ($port in $WatchPorts) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
      $pid = [int]$c.OwningProcess
      if ($pid -le 0) { continue }
      $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
      $name = if ($proc) { $proc.ProcessName } else { "?" }
      $path = if ($proc) { Get-ProcessPathSafe $proc } else { "" }
      $cmd = Get-ProcessCommandLine -ProcessId $pid
      $blockers += [pscustomobject]@{
        Kind = "port"
        Name = "$name :$port"
        PID = $pid
        Path = $path
        CommandLine = $cmd
      }
    }
  }

  # Dev Vite / Uvicorn heuristics (without killing)
  $suspects = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $cmd = [string]$_.CommandLine
    if (-not $cmd) { return $false }
    if ($cmd -match '(?i)vite.*(storylens|Dstorylens)|storylens.*vite') { return $true }
    if ($cmd -match '(?i)uvicorn\s+app\.main:app') { return $true }
    if ($cmd -match '(?i)storylens-desktop|StoryLens\\desktop') { return $true }
    return $false
  }
  foreach ($s in $suspects) {
    # Skip the current PowerShell / this verification python runner itself later
    $blockers += [pscustomobject]@{
      Kind = "suspect"
      Name = $s.Name
      PID = [int]$s.ProcessId
      Path = [string]$s.ExecutablePath
      CommandLine = [string]$s.CommandLine
    }
  }

  # Deduplicate by PID+Kind+Name
  $uniq = @{}
  $list = @()
  foreach ($b in $blockers) {
    $key = "$($b.Kind)|$($b.PID)|$($b.Name)"
    if ($uniq.ContainsKey($key)) { continue }
    $uniq[$key] = $true
    $list += $b
  }
  return $list
}

Write-Host "=== Environment leftover check (report-only, no auto-kill) ==="
$leftovers = Test-LeftoverEnvironment
# Filter out this shell and harmless noise: keep anything on watch ports or storylens-named
$reported = @()
foreach ($b in $leftovers) {
  $cmd = [string]$b.CommandLine
  $name = [string]$b.Name
  # Ignore current verification script's parent references only if clearly this file
  if ($cmd -match 'verify-shortbook-native-overview-e2e\.ps1') { continue }
  if ($cmd -match 'verify_shortbook_native_overview_e2e\.py') { continue }
  $reported += $b
}

if ($reported.Count -gt 0) {
  Write-Host "BLOCKED: leftover processes/ports detected. Close them manually, then re-run."
  Write-Host ""
  Write-Host ("{0,-10} {1,-8} {2,-28} {3}" -f "KIND", "PID", "NAME", "PATH / COMMAND")
  foreach ($b in $reported) {
    Write-Host ("{0,-10} {1,-8} {2,-28} {3}" -f $b.Kind, $b.PID, $b.Name, $b.Path)
    if ($b.CommandLine) {
      Write-Host ("{0,-10} {1,-8} {2,-28} {3}" -f "", "", "", $b.CommandLine)
    }
  }
  $reportPath = Join-Path $LiveDir "environment-blockers.json"
  $reported | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 $reportPath
  Write-Host ""
  Write-Host "Saved: $reportPath"
  Write-Host "Script stopped without killing processes and without calling Provider."
  exit 2
}
Write-Host "Environment check PASS (no StoryLens / watched-port leftovers)."

# Clear Fake env for this session only (does not kill processes)
Get-ChildItem Env: | Where-Object {
  $_.Name -like 'STORYLENS_*' -and $_.Name -match 'FAKE'
} | ForEach-Object { Remove-Item "Env:$($_.Name)" -ErrorAction SilentlyContinue }
Remove-Item Env:STORYLENS_NATIVE_OVERVIEW_SMOKE_FAKE -ErrorAction SilentlyContinue
Remove-Item Env:STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE -ErrorAction SilentlyContinue

$env:PYTHONPATH = (Join-Path $Repo "apps\api") + ";" + $PrivateSrc
$env:STORYLENS_APP_ENV = "production"
$env:PRO_NATIVE_OVERVIEW_ENABLED = "true"

if (-not (Test-Path $Py)) { throw "venv python missing: $Py" }
if (-not (Test-Path $Runner)) { throw "runner missing: $Runner" }

$argList = @()
if ($ConfirmLive) {
  Write-Host ""
  Write-Host "ConfirmLive set — will create ONE full Native Overview run on book_id=5 (temp DB)."
  Write-Host "Cost gate: <= ¥0.50 ; product defaults timeout=180 / max_tokens=8192 (not script overrides)."
  $argList += "--confirm"
} else {
  Write-Host ""
  Write-Host "Preflight mode — no whole-book run / no window Provider calls."
}

& $Py $Runner @argList
$code = $LASTEXITCODE

if (-not $ConfirmLive) {
  Write-Host ""
  Write-Host "Manual next step after reviewing preflight values:"
  Write-Host ('powershell -NoProfile -ExecutionPolicy Bypass -File "{0}" -ConfirmLive' -f $PSCommandPath)
}

exit $code
