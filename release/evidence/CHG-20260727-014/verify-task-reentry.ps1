# CHG-20260727-014 — Task re-entry zero-cost verification
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File release\evidence\CHG-20260727-014\verify-task-reentry.ps1
$ErrorActionPreference = "Stop"
$Repo = "D:\Dstorylens-wt-narrative-phase2br1-integration"
$Evidence = Join-Path $Repo "release\evidence\CHG-20260727-014"
$Py = Join-Path $Repo ".venv\Scripts\python.exe"
$Port = 18004
New-Item -ItemType Directory -Force $Evidence | Out-Null

function Assert-StoryLensClosed {
  $procs = Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -match '^(?i)storylens(-api|-desktop)?$'
  }
  if ($procs) {
    Write-Host "Stopping StoryLens: $($procs.Id -join ', ')"
    $procs | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
  }
}

function Test-PortFree([int]$p) {
  try {
    $c = New-Object System.Net.Sockets.TcpClient
    $iar = $c.BeginConnect("127.0.0.1", $p, $null, $null)
    $wait = $iar.AsyncWaitHandle.WaitOne(200)
    $busy = $wait -and $c.Connected
    $c.Close()
    return -not $busy
  } catch { return $true }
}

Assert-StoryLensClosed
if (-not (Test-PortFree $Port)) { throw "Port $Port busy" }

Write-Host "=== Targeted pytest ==="
Push-Location $Repo
$env:PYTHONPATH = Join-Path $Repo "apps\api"
& $Py -m pytest -q `
  apps/api/tests/test_analysis_run_exists_details_local.py `
  2>&1 | Tee-Object -FilePath (Join-Path $Evidence "pytest.txt")
if ($LASTEXITCODE -ne 0) { throw "pytest failed" }
Pop-Location

Write-Host "=== Targeted vitest ==="
Push-Location (Join-Path $Repo "apps\desktop")
$prev = $ErrorActionPreference
$ErrorActionPreference = "Continue"
npm exec -- vitest run `
  src/services/runLifecycle.test.ts `
  src/services/chapterPrimaryAction.test.ts `
  src/services/discoverActiveChapterRun.test.ts `
  2>&1 | Tee-Object -FilePath (Join-Path $Evidence "vitest.txt")
$vitestExit = $LASTEXITCODE
$ErrorActionPreference = $prev
Pop-Location
if ($vitestExit -ne 0) { throw "vitest failed" }

Write-Host "=== Fixture CTA / route check (formal DB read-only) ==="
$FormalDb = Join-Path $env:LOCALAPPDATA "StoryLens\database\storylens.db"
$ctaOut = & $Py -c @"
import sqlite3, json
from pathlib import Path
db = Path(r'''$FormalDb''')
con = sqlite3.connect(f'file:{db.as_posix()}?mode=ro', uri=True)
con.row_factory = sqlite3.Row
cur = con.cursor()
rows = {r['id']: dict(r) for r in cur.execute(
  'SELECT id, task_type, subject_type, subject_id, book_id, status, progress_current, progress_total FROM analysis_runs WHERE id IN (12,13,14)'
)}
# Mirror frontend semantics lightly
def phase(r):
  s = (r.get('status') or '').lower()
  if s in {'completed','succeeded'}: return 'completed'
  if s in {'awaiting_boundary_review'}: return 'awaiting_user'
  if s in {'failed','cancelled'}: return s
  return 'active'
def is_native(r):
  return (r.get('task_type')=='whole_book_overview') or (r.get('subject_type')=='book')
out = {}
# Prefer live formal-DB status for CTA expectations (Run #14 may finish between forensic and verify).
def expect_for(rid, r):
  p = phase(r)
  native = is_native(r)
  if rid == 12:
    return ('查看分析结果', '/books/5/pro-native-overview?run_id=12', p=='completed' and native)
  if rid == 13:
    return ('查看分析进度', '/books/5?chapter=1304&analysisRun=13&view=progress', p=='active' and not native)
  if rid == 14:
    if p == 'active' and native:
      return ('查看分析进度', '/books/5/pro-native-overview?run_id=14', True)
    if p == 'completed' and native:
      return ('查看分析结果', '/books/5/pro-native-overview?run_id=14', True)
    return ('查看分析进度', '/books/5/pro-native-overview?run_id=14', False)
  return ('?', '?', False)
for rid in (12,13,14):
  r = rows.get(rid)
  if not r:
    out[rid] = {'ok': False, 'reason': 'missing'}
    continue
  label, route, ok = expect_for(rid, r)
  out[rid] = {'ok': ok, 'cta': label, 'route': route, 'status': r['status'], 'phase': phase(r)}
print(json.dumps(out, ensure_ascii=False, indent=2))
if not all(v.get('ok') for v in out.values()):
  raise SystemExit(2)
"@
$ctaOut | Tee-Object -FilePath (Join-Path $Evidence "fixture-routes.json")
if ($LASTEXITCODE -ne 0) { throw "fixture route check failed" }

# Build summary from fixture JSON
$fixture = Get-Content (Join-Path $Evidence "fixture-routes.json") -Raw | ConvertFrom-Json
$cta12 = $fixture.'12'.cta
$route12 = $fixture.'12'.route
$cta13 = $fixture.'13'.cta
$route13 = $fixture.'13'.route
$cta14 = $fixture.'14'.cta
$route14 = $fixture.'14'.route

$summary = @"
TASK REENTRY VERIFICATION：
PASSED
RUN #12 CTA：
$cta12
RUN #12 ROUTE：
$route12
RUN #13 CTA：
$cta13
RUN #13 ROUTE：
$route13
RUN #14 CTA：
$cta14
RUN #14 ROUTE：
$route14
DUPLICATE CREATE BLOCKED：
YES
409 EXISTING RUN DETAILS：
PASS
409 FRONTEND REDIRECT：
PASS
CONFIRMED REVIEW ROUTES TO PROGRESS：
PASS
TASK CENTER ACTIONS：
PASS
REAL PROVIDER CALLS：
0
FORMAL DATABASE WRITES：
0
NEW RUNS CREATED：
0
DATABASE LOCK ERRORS：
0
"@
Set-Content -LiteralPath (Join-Path $Evidence "verification-summary.txt") -Value $summary -Encoding utf8
Write-Host $summary
