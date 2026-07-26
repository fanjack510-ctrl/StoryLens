# FIX-TASK-01 / CHG-20260726-009 — production-like config path verification
# No installer build. Source API only. Temp DB copy. CWD = System32.
$ErrorActionPreference = "Stop"
$Repo = "D:\Dstorylens-wt-narrative-phase2br1-integration"
$Port = 18001
$EvidenceDir = Join-Path $Repo "release\evidence\CHG-20260726-009"
$LogOut = Join-Path $EvidenceDir "verify-api.out.log"
$LogErr = Join-Path $EvidenceDir "verify-api.err.log"
$ResultPath = Join-Path $EvidenceDir "verify-result.json"
New-Item -ItemType Directory -Force $EvidenceDir | Out-Null

function Assert-StoryLensClosed {
  $procs = Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -match '^(?i)storylens(-api|-desktop)?$'
  }
  if ($procs) {
    Write-Host "Stopping installed StoryLens processes: $($procs.Id -join ', ')"
    $procs | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
  }
  $left = Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -match '^(?i)storylens(-api|-desktop)?$'
  }
  if ($left) {
    throw "StoryLens still running after stop attempt: $($left.Id -join ', ')"
  }
  Write-Host "StoryLens closed: OK"
}

function Copy-SqliteSafe([string]$SourceDb, [string]$DestDb) {
  if (-not (Test-Path -LiteralPath $SourceDb)) {
    throw "Formal DB not found: $SourceDb"
  }
  $destDir = Split-Path -Parent $DestDb
  New-Item -ItemType Directory -Force $destDir | Out-Null
  if (Test-Path -LiteralPath $DestDb) { Remove-Item -LiteralPath $DestDb -Force }
  $py = Join-Path $Repo ".venv\Scripts\python.exe"
  $src = $SourceDb.Replace("\", "\\")
  $dst = $DestDb.Replace("\", "\\")
  & $py -c @"
import sqlite3
from pathlib import Path
src = Path(r'''$SourceDb''')
dst = Path(r'''$DestDb''')
dst.parent.mkdir(parents=True, exist_ok=True)
if dst.exists():
    dst.unlink()
s = sqlite3.connect(str(src))
try:
    d = sqlite3.connect(str(dst))
    try:
        s.backup(d)
        d.commit()
    finally:
        d.close()
finally:
    s.close()
print('sqlite_backup_ok', dst)
"@
  if ($LASTEXITCODE -ne 0) { throw "SQLite backup failed" }
  if (-not (Test-Path -LiteralPath $DestDb)) { throw "Backup dest missing" }
  Write-Host "DB backup OK -> $DestDb"
}

Assert-StoryLensClosed

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$TempRoot = Join-Path $env:TEMP "storylens-fix-task01-$stamp"
$TempDb = Join-Path $TempRoot "database\storylens.db"
$FormalDb = Join-Path $env:LOCALAPPDATA "StoryLens\database\storylens.db"
New-Item -ItemType Directory -Force $TempRoot | Out-Null
Copy-SqliteSafe -SourceDb $FormalDb -DestDb $TempDb

# Clear Fake / Live provider switches (list-only; no real Provider)
$clearKeys = @(
  "STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE",
  "STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE_FAIL",
  "STORYLENS_NATIVE_OVERVIEW_SMOKE_FAKE",
  "STORYLENS_USE_FAKE_PROVIDER",
  "STORYLENS_FAKE_PROVIDER",
  "STORYLENS_LIVE_PROVIDER",
  "OPENAI_API_KEY",
  "STORYLENS_OPENAI_API_KEY",
  "ANTHROPIC_API_KEY"
)
foreach ($k in $clearKeys) {
  Remove-Item "Env:$k" -ErrorAction SilentlyContinue
}

$env:STORYLENS_APP_ENV = "production"
$env:STORYLENS_DATABASE_URL = "sqlite:///" + ($TempDb -replace "\\", "/")
$env:STORYLENS_DATA_DIR = $TempRoot
$env:STORYLENS_LOG_DIR = Join-Path $TempRoot "logs"
$env:PYTHONPATH = Join-Path $Repo "apps\api"
# Do NOT set STORYLENS_CONFIG_DIR to a missing path that short-circuits incorrectly;
# leave unset so apply_runtime_path_defaults / resolve logic use StoryLens layout + resource_root.
Remove-Item Env:STORYLENS_CONFIG_DIR -ErrorAction SilentlyContinue

New-Item -ItemType Directory -Force $env:STORYLENS_LOG_DIR | Out-Null
if (Test-Path $LogOut) { Remove-Item $LogOut -Force }
if (Test-Path $LogErr) { Remove-Item $LogErr -Force }

$py = Join-Path $Repo ".venv\Scripts\python.exe"
$cwd = "C:\Windows\System32"
Write-Host "Starting API from $cwd on port $Port ..."
$proc = Start-Process -FilePath $py `
  -WorkingDirectory $cwd `
  -ArgumentList @(
    "-m", "uvicorn", "app.main:app",
    "--app-dir", (Join-Path $Repo "apps\api"),
    "--host", "127.0.0.1",
    "--port", "$Port",
    "--ws", "none"
  ) `
  -RedirectStandardOutput $LogOut `
  -RedirectStandardError $LogErr `
  -WindowStyle Hidden `
  -PassThru

$healthCode = 0
$runsCode = 0
$runsCount = 0
$fnf = $false
try {
  $deadline = (Get-Date).AddSeconds(45)
  $ok = $false
  do {
    try {
      $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 2
      $healthCode = [int]$r.StatusCode
      $ok = ($healthCode -eq 200)
    } catch {
      Start-Sleep -Milliseconds 500
    }
  } until ($ok -or (Get-Date) -gt $deadline)
  if (-not $ok) {
    Write-Host "=== OUT LOG ==="; Get-Content $LogOut -ErrorAction SilentlyContinue | Select-Object -Last 40
    Write-Host "=== ERR LOG ==="; Get-Content $LogErr -ErrorAction SilentlyContinue | Select-Object -Last 40
    throw "Health check failed"
  }
  Write-Host "HEALTH HTTP: $healthCode"

  try {
    $runsResp = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/v1/analysis-runs" -UseBasicParsing -TimeoutSec 30
    $runsCode = [int]$runsResp.StatusCode
    $json = $runsResp.Content | ConvertFrom-Json
    if ($json -is [System.Array]) { $runsCount = $json.Count }
    elseif ($json.PSObject.Properties.Name -contains "items") { $runsCount = @($json.items).Count }
    elseif ($json.PSObject.Properties.Name -contains "runs") { $runsCount = @($json.runs).Count }
    else { $runsCount = 1 }
  } catch {
    if ($_.Exception.Response) {
      $runsCode = [int]$_.Exception.Response.StatusCode.value__
    } else {
      $runsCode = 0
    }
    Write-Host "analysis-runs error: $_"
  }
  Write-Host "ANALYSIS-RUNS HTTP: $runsCode"
  Write-Host "HISTORICAL RUNS COUNT: $runsCount"

  $combined = @()
  if (Test-Path $LogOut) { $combined += Get-Content $LogOut -Raw -ErrorAction SilentlyContinue }
  if (Test-Path $LogErr) { $combined += Get-Content $LogErr -Raw -ErrorAction SilentlyContinue }
  $text = ($combined -join "`n")
  $fnf = ($text -match "FileNotFoundError" -and $text -match "scene_evidence_validation\.json")
  Write-Host "FILE-NOT-FOUND AFTER FIX: $fnf"
}
finally {
  if ($proc -and -not $proc.HasExited) {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
  }
  # Also kill anything still bound to 18001
  $owner = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1 -ExpandProperty OwningProcess
  if ($owner) {
    Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue
  }
  Write-Host "Temp API stopped."
}

$result = [ordered]@{
  health_http = $healthCode
  analysis_runs_http = $runsCode
  historical_runs_count = $runsCount
  file_not_found_after_fix = $fnf
  cwd = $cwd
  database = $TempDb
  port = $Port
  temp_root = $TempRoot
  passed = (($healthCode -eq 200) -and ($runsCode -eq 200) -and ($runsCount -gt 0) -and (-not $fnf))
}
$result | ConvertTo-Json | Set-Content -LiteralPath $ResultPath -Encoding utf8
Write-Host "RESULT: $($result | ConvertTo-Json -Compress)"
if (-not $result.passed) { exit 1 }
exit 0
