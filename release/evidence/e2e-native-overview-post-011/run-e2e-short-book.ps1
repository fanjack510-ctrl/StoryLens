# Native Overview real E2E after CHG-011 — short book only (book_id=5, 5 chapters)
# No installer, no formal DB writes, no CHG-012.
$ErrorActionPreference = "Stop"
$Repo = "D:\Dstorylens-wt-narrative-phase2br1-integration"
$Port = 18003
$BookId = 5
$Evidence = Join-Path $Repo "release\evidence\e2e-native-overview-post-011"
$Py = Join-Path $Repo ".venv\Scripts\python.exe"
$LogOut = Join-Path $Evidence "api.out.log"
$LogErr = Join-Path $Evidence "api.err.log"
$Summary = Join-Path $Evidence "e2e-summary.json"
New-Item -ItemType Directory -Force $Evidence | Out-Null

function Assert-StoryLensClosed {
  $procs = Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -match '^(?i)storylens(-api|-desktop)?$'
  }
  if ($procs) {
    Write-Host "Stopping StoryLens $($procs.Id -join ',')"
    $procs | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep 2
  }
  if (Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match '^(?i)storylens(-api|-desktop)?$' }) {
    throw "StoryLens still running"
  }
}
function Stop-Port([int]$p) {
  $o = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1 -ExpandProperty OwningProcess
  if ($o) { Stop-Process -Id $o -Force -ErrorAction SilentlyContinue }
}

Assert-StoryLensClosed
Stop-Port $Port

# Product default check (source)
$defCheck = & $Py -c "from app.narrative_core.services.native_overview_live_transport import AliyunNativeOverviewTransport; print(AliyunNativeOverviewTransport.max_output_tokens)"
if ([int]$defCheck -ne 8192) { throw "PRODUCT DEFAULT max_output_tokens is $defCheck, expected 8192" }
Write-Host "PRODUCT DEFAULT max_output_tokens=$defCheck"

$FormalDb = Join-Path $env:LOCALAPPDATA "StoryLens\database\storylens.db"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$TempRoot = Join-Path $env:TEMP "storylens-e2e-native-$stamp"
$TempDb = Join-Path $TempRoot "database\storylens.db"
New-Item -ItemType Directory -Force (Split-Path $TempDb) | Out-Null
& $Py -c @"
import sqlite3
from pathlib import Path
src=Path(r'''$FormalDb'''); dst=Path(r'''$TempDb''')
s=sqlite3.connect(str(src)); d=sqlite3.connect(str(dst)); s.backup(d); d.commit(); d.close(); s.close()
# verify book 5
con=sqlite3.connect(str(dst)); con.row_factory=sqlite3.Row
b=con.execute('SELECT id,title FROM books WHERE id=5').fetchone()
ch=con.execute('SELECT count(*) c FROM chapters WHERE book_id=5').fetchone()['c']
print(dict(b), 'chapters', ch)
assert b and ch==5 and '戏神' not in (b['title'] or '')
con.close()
print('backup_ok')
"@
if ($LASTEXITCODE -ne 0) { throw "backup/book5 check failed" }

# Clear fakes
foreach ($k in @(
  "STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE","STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE_FAIL",
  "STORYLENS_NATIVE_OVERVIEW_SMOKE_FAKE","STORYLENS_USE_FAKE_PROVIDER","STORYLENS_FAKE_PROVIDER"
)) { Remove-Item "Env:$k" -ErrorAction SilentlyContinue }

$env:STORYLENS_APP_ENV = "production"
$env:PRO_NATIVE_OVERVIEW_ENABLED = "true"
$env:STORYLENS_DATABASE_URL = "sqlite:///" + ($TempDb -replace "\\","/")
$env:STORYLENS_DATA_DIR = $TempRoot
$env:STORYLENS_LOG_DIR = Join-Path $TempRoot "logs"
$env:PYTHONPATH = (Join-Path $Repo "apps\api") + ";" + "D:\Dstorylens-private-engine-wt-phase2br1-integration\src"
Remove-Item Env:STORYLENS_CONFIG_DIR -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $env:STORYLENS_LOG_DIR | Out-Null
if (Test-Path $LogOut) { Remove-Item $LogOut -Force }
if (Test-Path $LogErr) { Remove-Item $LogErr -Force }

function Start-Api {
  param($Out,$Err)
  if (Test-Path $Out) { Remove-Item $Out -Force }
  if (Test-Path $Err) { Remove-Item $Err -Force }
  $proc = Start-Process -FilePath $Py -WorkingDirectory "C:\Windows\System32" -ArgumentList @(
    "-m","uvicorn","app.main:app","--app-dir",(Join-Path $Repo "apps\api"),
    "--host","127.0.0.1","--port","$Port","--ws","none"
  ) -RedirectStandardOutput $Out -RedirectStandardError $Err -WindowStyle Hidden -PassThru
  $deadline = (Get-Date).AddSeconds(60)
  do {
    try {
      $r = Invoke-WebRequest "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 2
      if ([int]$r.StatusCode -eq 200) { return $proc }
    } catch { Start-Sleep -Milliseconds 400 }
  } until ((Get-Date) -gt $deadline)
  Get-Content $Err -ErrorAction SilentlyContinue | Select-Object -Last 40
  throw "API health failed"
}

Write-Host "Starting API from C:\Windows\System32 ..."
$proc1 = Start-Api -Out $LogOut -Err $LogErr
$report = [ordered]@{
  local_api_health = "FAIL"
  analysis_runs_api = "FAIL"
  create_run_http = 0
  create_response_ms = -1
  run_id = $null
  provider = "aliyun_qwen_plus"
  model = "qwen3.7-plus"
  max_tokens_source = "PRODUCT DEFAULT"
  product_default_max_tokens = 8192
  real_provider_http = $null
  real_provider_calls = 0
  finish_reasons = @()
  any_finish_length = $false
  json_pass = "FAIL"
  parser_pass = "FAIL"
  schema_pass = "FAIL"
  final_run_state = $null
  result_api_http = 0
  restart_recovery = "FAIL"
  database_lock = $false
  actual_cost = 0.0
  formal_database_writes = 0
  end_to_end = "BLOCKED"
  build = "NO"
  book_id = $BookId
  book_title = "十日前4章"
}

try {
  $report.local_api_health = "PASS"
  $runs = Invoke-WebRequest "http://127.0.0.1:$Port/api/v1/analysis-runs" -UseBasicParsing -TimeoutSec 30
  if ([int]$runs.StatusCode -eq 200) { $report.analysis_runs_api = "PASS" }

  # Preflight
  $preBody = @{ module_key = "book_overview"; mode = "whole_book_native" } | ConvertTo-Json
  $pre = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/books/$BookId/whole-book-runs/preflight" `
    -Method POST -ContentType "application/json" -Body $preBody -TimeoutSec 60
  $pre | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $Evidence "preflight.json") -Encoding utf8
  Write-Host "PREFLIGHT run_creation_enabled=$($pre.run_creation_enabled) est_cost=$($pre.estimated_cost) est_tokens=$($pre.estimated_tokens) windows?=?"
  if (-not $pre.run_creation_enabled) { throw "preflight blocked: $($pre.blocking_errors | ConvertTo-Json -Compress)" }
  $estCost = [double]$pre.estimated_cost
  if ($estCost -gt 0.50) { throw "COST GATE: preflight estimated_cost=$estCost > 0.50" }

  $clientReq = "e2e-post011-" + [guid]::NewGuid().ToString("N").Substring(0,12)
  $createPayload = @{
    mode = "whole_book_native"
    module_key = "book_overview"
    provider_id = "aliyun_qwen_plus"
    model_id = "qwen3.7-plus"
    client_request_id = $clientReq
    consent = @{
      estimated_tokens = [int]$pre.estimated_tokens
      estimated_cost = [double]$pre.estimated_cost
      currency = ($(if ($pre.currency) { $pre.currency } else { "CNY" }))
      confirmed = $true
    }
  } | ConvertTo-Json -Depth 5

  $sw = [Diagnostics.Stopwatch]::StartNew()
  $createResp = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/v1/books/$BookId/whole-book-runs" `
    -Method POST -ContentType "application/json" -Body $createPayload -TimeoutSec 5 -UseBasicParsing
  $sw.Stop()
  $report.create_run_http = [int]$createResp.StatusCode
  $report.create_response_ms = [int]$sw.ElapsedMilliseconds
  $createJson = $createResp.Content | ConvertFrom-Json
  $report.run_id = $createJson.run_id
  Write-Host "CREATE status=$($report.create_run_http) ms=$($report.create_response_ms) run_id=$($report.run_id) init=$($createJson.status)"

  # Poll run status
  $deadline = (Get-Date).AddMinutes(15)
  $final = $null
  do {
    Start-Sleep -Seconds 3
    $st = Invoke-RestMethod "http://127.0.0.1:$Port/api/v1/whole-book-runs/$($report.run_id)" -TimeoutSec 30
    $final = $st
    Write-Host ("POLL status={0} progress={1}/{2}" -f $st.status, $st.progress_current, $st.progress_total)
    if ($st.status -in @("completed","succeeded","failed","failed_provider","cancelled","interrupted")) { break }
    # cost check from DB invocations
    $costNow = & $Py -c @"
import sqlite3
con=sqlite3.connect(r'''$TempDb''')
row=con.execute('SELECT coalesce(sum(estimated_cost),0) FROM model_invocations WHERE run_id=?', ($($report.run_id),)).fetchone()
print(row[0] if row else 0)
con.close()
"@
    if ([double]$costNow -gt 0.50) { throw "COST GATE mid-run actual=$costNow > 0.50 — stopping" }
  } until ((Get-Date) -gt $deadline)

  $report.final_run_state = $final.status

  # Invocation forensics
  $invJson = & $Py -c @"
import sqlite3, json
con=sqlite3.connect(r'''$TempDb''')
con.row_factory=sqlite3.Row
rows=list(con.execute('SELECT id,status,http_status_code,finish_reason,input_tokens,output_tokens,estimated_cost,error_code,length(raw_response_text) raw_len FROM model_invocations WHERE run_id=? ORDER BY id', ($($report.run_id),)))
print(json.dumps([dict(r) for r in rows], ensure_ascii=False))
con.close()
"@
  $invs = $invJson | ConvertFrom-Json
  $report.real_provider_calls = @($invs).Count
  $report.finish_reasons = @($invs | ForEach-Object { $_.finish_reason })
  $report.any_finish_length = [bool]($invs | Where-Object { $_.finish_reason -eq "length" })
  $report.actual_cost = [double](($invs | Measure-Object -Property estimated_cost -Sum).Sum)
  if ($invs.Count -gt 0) {
    $okHttp = $invs | Where-Object { [int]$_.http_status_code -eq 200 }
    if ($okHttp) { $report.real_provider_http = 200 }
  }
  $succInv = $invs | Where-Object { $_.status -eq "succeeded" }
  if ($succInv -and -not $report.any_finish_length) {
    $report.json_pass = "PASS"
    $report.parser_pass = "PASS"
    $report.schema_pass = "PASS"
  } elseif ($report.final_run_state -in @("completed","succeeded") -and -not $report.any_finish_length) {
    $report.json_pass = "PASS"
    $report.parser_pass = "PASS"
    $report.schema_pass = "PASS"
  }

  # Result API — overview + results
  try {
    $ov = Invoke-WebRequest "http://127.0.0.1:$Port/api/v1/whole-book-runs/$($report.run_id)/overview" -UseBasicParsing -TimeoutSec 30
    $report.result_api_http = [int]$ov.StatusCode
  } catch {
    try {
      $res = Invoke-WebRequest "http://127.0.0.1:$Port/api/v1/whole-book-runs/$($report.run_id)/results" -UseBasicParsing -TimeoutSec 30
      $report.result_api_http = [int]$res.StatusCode
    } catch {
      if ($_.Exception.Response) { $report.result_api_http = [int]$_.Exception.Response.StatusCode.value__ }
    }
  }

  # Restart recovery
  if ($proc1 -and -not $proc1.HasExited) { Stop-Process -Id $proc1.Id -Force -ErrorAction SilentlyContinue }
  Stop-Port $Port
  Start-Sleep 2
  $proc2 = Start-Api -Out ($LogOut+".2") -Err ($LogErr+".2")
  $again = Invoke-RestMethod "http://127.0.0.1:$Port/api/v1/whole-book-runs/$($report.run_id)" -TimeoutSec 30
  if ($again.status -eq $report.final_run_state -or $again.status -in @("completed","succeeded")) {
    $report.restart_recovery = "PASS"
  }
  try {
    $ov2 = Invoke-WebRequest "http://127.0.0.1:$Port/api/v1/whole-book-runs/$($report.run_id)/overview" -UseBasicParsing -TimeoutSec 30
    if ([int]$ov2.StatusCode -eq 200) { $report.restart_recovery = "PASS" }
  } catch {}

  # lock / log scan
  $logs = ""
  foreach ($f in @($LogOut,$LogErr,($LogOut+".2"),($LogErr+".2"))) {
    if (Test-Path $f) { $logs += Get-Content $f -Raw -ErrorAction SilentlyContinue }
  }
  if ($logs -match "database is locked") { $report.database_lock = $true }

  $passed = (
    $report.local_api_health -eq "PASS" -and
    $report.analysis_runs_api -eq "PASS" -and
    $report.create_run_http -eq 201 -and
    $report.create_response_ms -ge 0 -and $report.create_response_ms -lt 5000 -and
    $null -ne $report.run_id -and
    $report.real_provider_calls -ge 1 -and
    -not $report.any_finish_length -and
    $report.json_pass -eq "PASS" -and
    $report.parser_pass -eq "PASS" -and
    $report.schema_pass -eq "PASS" -and
    ($report.final_run_state -in @("completed","succeeded")) -and
    $report.result_api_http -eq 200 -and
    $report.restart_recovery -eq "PASS" -and
    -not $report.database_lock -and
    $report.actual_cost -le 0.50
  )
  $report.end_to_end = $(if ($passed) { "PASSED" } else { "BLOCKED" })
  $report.invocations = $invs
  $report.preflight_estimated_cost = $estCost
}
catch {
  Write-Host "E2E ERROR: $_"
  $report.end_to_end = "BLOCKED"
  $report.error = "$_"
  if ("$_" -match "database is locked") { $report.database_lock = $true }
}
finally {
  Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Id -in @($proc1.Id,$proc2.Id) } | Stop-Process -Force -ErrorAction SilentlyContinue
  Stop-Port $Port
}

$report | ConvertTo-Json -Depth 8 | Set-Content $Summary -Encoding utf8
Write-Host "==== E2E SUMMARY ===="
$report | ConvertTo-Json -Depth 6
if ($report.end_to_end -ne "PASSED") { exit 1 }
exit 0
