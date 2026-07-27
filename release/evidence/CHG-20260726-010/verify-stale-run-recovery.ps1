# FIX-RUN-01 / CHG-20260726-010 — stale run recovery verification
# Does NOT modify formal DB. Seeds stale Run #10 into a SQLite backup copy.
$ErrorActionPreference = "Stop"
$Repo = "D:\Dstorylens-wt-narrative-phase2br1-integration"
$Port = 18002
$EvidenceDir = Join-Path $Repo "release\evidence\CHG-20260726-010"
$LogOut = Join-Path $EvidenceDir "verify-api.out.log"
$LogErr = Join-Path $EvidenceDir "verify-api.err.log"
$ResultPath = Join-Path $EvidenceDir "verify-result.json"
New-Item -ItemType Directory -Force $EvidenceDir | Out-Null

function Assert-StoryLensClosed {
  $procs = Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -match '^(?i)storylens(-api|-desktop)?$'
  }
  if ($procs) {
    Write-Host "Stopping StoryLens: $($procs.Id -join ', ')"
    $procs | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
  }
  $left = Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -match '^(?i)storylens(-api|-desktop)?$'
  }
  if ($left) { throw "StoryLens still running: $($left.Id -join ', ')" }
  Write-Host "StoryLens closed: OK"
}

function Stop-PortOwner([int]$ListenPort) {
  $owner = Get-NetTCPConnection -LocalPort $ListenPort -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1 -ExpandProperty OwningProcess
  if ($owner) { Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue }
}

function Start-VerifyApi([string]$DbPath, [string]$TempRoot, [string]$OutLog, [string]$ErrLog) {
  foreach ($k in @(
    "STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE",
    "STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE_FAIL",
    "STORYLENS_NATIVE_OVERVIEW_SMOKE_FAKE",
    "STORYLENS_USE_FAKE_PROVIDER",
    "STORYLENS_FAKE_PROVIDER",
    "STORYLENS_LIVE_PROVIDER",
    "OPENAI_API_KEY",
    "STORYLENS_OPENAI_API_KEY",
    "ANTHROPIC_API_KEY"
  )) { Remove-Item "Env:$k" -ErrorAction SilentlyContinue }

  $env:STORYLENS_APP_ENV = "production"
  $env:STORYLENS_DATABASE_URL = "sqlite:///" + ($DbPath -replace "\\", "/")
  $env:STORYLENS_DATA_DIR = $TempRoot
  $env:STORYLENS_LOG_DIR = Join-Path $TempRoot "logs"
  $env:PYTHONPATH = Join-Path $Repo "apps\api"
  Remove-Item Env:STORYLENS_CONFIG_DIR -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Force $env:STORYLENS_LOG_DIR | Out-Null
  if (Test-Path $OutLog) { Remove-Item $OutLog -Force }
  if (Test-Path $ErrLog) { Remove-Item $ErrLog -Force }

  $py = Join-Path $Repo ".venv\Scripts\python.exe"
  $proc = Start-Process -FilePath $py `
    -WorkingDirectory "C:\Windows\System32" `
    -ArgumentList @(
      "-m", "uvicorn", "app.main:app",
      "--app-dir", (Join-Path $Repo "apps\api"),
      "--host", "127.0.0.1",
      "--port", "$Port",
      "--ws", "none"
    ) `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog `
    -WindowStyle Hidden `
    -PassThru
  $deadline = (Get-Date).AddSeconds(45)
  $ok = $false
  do {
    try {
      $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 2
      if ([int]$r.StatusCode -eq 200) { $ok = $true }
    } catch { Start-Sleep -Milliseconds 400 }
  } until ($ok -or (Get-Date) -gt $deadline)
  if (-not $ok) {
    Get-Content $OutLog -ErrorAction SilentlyContinue | Select-Object -Last 30
    Get-Content $ErrLog -ErrorAction SilentlyContinue | Select-Object -Last 30
    throw "API health failed on port $Port"
  }
  return $proc
}

Assert-StoryLensClosed
Stop-PortOwner $Port

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$TempRoot = Join-Path $env:TEMP "storylens-fix-run01-$stamp"
$TempDb = Join-Path $TempRoot "database\storylens.db"
$FormalDb = Join-Path $env:LOCALAPPDATA "StoryLens\database\storylens.db"
New-Item -ItemType Directory -Force (Split-Path $TempDb) | Out-Null

$py = Join-Path $Repo ".venv\Scripts\python.exe"
& $py -c @"
import sqlite3
from pathlib import Path
src = Path(r'''$FormalDb''')
dst = Path(r'''$TempDb''')
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
print('backup_ok')
"@
if ($LASTEXITCODE -ne 0) { throw "SQLite backup failed" }

# Seed stale Run #10 + active reservation into TEMP copy only
& $py -c @"
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
db = Path(r'''$TempDb''')
con = sqlite3.connect(str(db))
con.row_factory = sqlite3.Row
cur = con.cursor()
row = cur.execute('SELECT id, status, error_code FROM analysis_runs WHERE id=10').fetchone()
if row is None:
    raise SystemExit('Run #10 missing from backup')
print('BEFORE_SEED', dict(row))
# Reset Run #10 to worker-bound stale state
cur.execute('''
UPDATE analysis_runs
SET status='boundary_candidates_running',
    error_code=NULL,
    error_message=NULL,
    completed_at=NULL,
    retryable=0
WHERE id=10
''')
# Ensure an active reservation for run 10
existing = cur.execute(
    \"SELECT id FROM cloud_budget_reservations WHERE run_id=10 AND status='active'\"
).fetchone()
if existing is None:
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')
    exp = (datetime.now(timezone.utc) + timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S.%f')
    cur.execute('''
    INSERT INTO cloud_budget_reservations (
      run_id, stage,
      reserved_requests, reserved_tokens, reserved_cost,
      remaining_requests, consumed_requests, released_requests,
      remaining_tokens, consumed_tokens, released_tokens,
      remaining_cost, consumed_cost, released_cost,
      expected_requests, worst_case_requests,
      status, expires_at, released_at, created_at
    ) VALUES (
      10, 'boundary_review_generation',
      15, 10000, 0.1,
      15, 0, 0,
      10000, 0, 0,
      0.1, 0.0, 0.0,
      15, 30,
      'active', ?, NULL, ?
    )
    ''', (exp, now))
print('ACTIVE_BEFORE', [dict(r) for r in cur.execute(
  \"SELECT id,status,error_code FROM analysis_runs WHERE status NOT IN ('succeeded','failed','failed_provider','failed_structural','cancelled','review_cancelled','completed')\"
).fetchall()])
print('RES10_BEFORE', [dict(r) for r in cur.execute(
  \"SELECT id,run_id,status,remaining_cost,consumed_cost FROM cloud_budget_reservations WHERE run_id=10\"
).fetchall()])
con.commit()
con.close()
print('seed_ok')
"@
if ($LASTEXITCODE -ne 0) { throw "Seed stale run failed" }

# First API start triggers lifespan recovery
$proc1 = Start-VerifyApi -DbPath $TempDb -TempRoot $TempRoot -OutLog $LogOut -ErrLog $LogErr
$health1 = 200
$runs1 = 0
$run10After = $null
$res10After = $null
try {
  $runsResp = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/v1/analysis-runs" -UseBasicParsing -TimeoutSec 30
  $runs1 = [int]$runsResp.StatusCode
  & $py -c @"
import sqlite3, json
from pathlib import Path
db = Path(r'''$TempDb''')
con = sqlite3.connect(str(db))
con.row_factory = sqlite3.Row
cur = con.cursor()
print('RUN10_AFTER', json.dumps(dict(cur.execute('SELECT id,status,error_code,error_message,completed_at FROM analysis_runs WHERE id=10').fetchone()), ensure_ascii=False))
print('RES10_AFTER', json.dumps([dict(r) for r in cur.execute('SELECT id,run_id,status,remaining_cost,consumed_cost,released_cost FROM cloud_budget_reservations WHERE run_id=10').fetchall()], ensure_ascii=False))
con.close()
"@
} finally {
  if ($proc1 -and -not $proc1.HasExited) { Stop-Process -Id $proc1.Id -Force -ErrorAction SilentlyContinue }
  Stop-PortOwner $Port
  Start-Sleep -Seconds 1
}

# Capture after first recovery
$snap1 = & $py -c @"
import sqlite3, json
from pathlib import Path
db = Path(r'''$TempDb''')
con = sqlite3.connect(str(db)); con.row_factory = sqlite3.Row; cur = con.cursor()
run = dict(cur.execute('SELECT id,status,error_code,completed_at FROM analysis_runs WHERE id=10').fetchone())
res = [dict(r) for r in cur.execute('SELECT id,status,remaining_cost,consumed_cost,released_cost,released_at FROM cloud_budget_reservations WHERE run_id=10 ORDER BY id').fetchall()]
print(json.dumps({'run': run, 'reservations': res}, ensure_ascii=False))
con.close()
"@
$state1 = $snap1 | ConvertFrom-Json
Write-Host "AFTER_FIRST_RECOVERY run=$($state1.run | ConvertTo-Json -Compress)"

# Second start — idempotency
$proc2 = Start-VerifyApi -DbPath $TempDb -TempRoot $TempRoot -OutLog $LogOut -ErrLog ($LogErr + ".2")
$health2 = 200
$runs2 = 0
$createMs = -1
$newRunId = $null
$lockHits = 0
try {
  $runsResp2 = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/v1/analysis-runs" -UseBasicParsing -TimeoutSec 30
  $runs2 = [int]$runsResp2.StatusCode

  $snap2 = & $py -c @"
import sqlite3, json
from pathlib import Path
db = Path(r'''$TempDb''')
con = sqlite3.connect(str(db)); con.row_factory = sqlite3.Row; cur = con.cursor()
run = dict(cur.execute('SELECT id,status,error_code,completed_at FROM analysis_runs WHERE id=10').fetchone())
res = [dict(r) for r in cur.execute('SELECT id,status,remaining_cost,consumed_cost,released_cost,released_at FROM cloud_budget_reservations WHERE run_id=10 ORDER BY id').fetchall()]
print(json.dumps({'run': run, 'reservations': res}, ensure_ascii=False))
con.close()
"@
  $state2 = $snap2 | ConvertFrom-Json

  $combined = ""
  foreach ($f in @($LogOut, $LogErr, ($LogErr + ".2"))) {
    if (Test-Path $f) { $combined += (Get-Content $f -Raw -ErrorAction SilentlyContinue) }
  }
  if ($combined -match "database is locked") {
    $lockHits = ([regex]::Matches($combined, "database is locked")).Count
  }
}
finally {
  if ($proc2 -and -not $proc2.HasExited) { Stop-Process -Id $proc2.Id -Force -ErrorAction SilentlyContinue }
  Stop-PortOwner $Port
  Start-Sleep -Seconds 1
}

# Fake Create Run via TestClient + FakeProvider (0 real Provider calls).
# Production gateway has no "fake" name; unit FakeTransport is the approved zero-network path.
$createOut = & $py -c @"
import os, sys, time, json, sqlite3
from pathlib import Path
os.environ['STORYLENS_APP_ENV'] = 'development'
os.environ['STORYLENS_DATABASE_URL'] = 'sqlite:///' + Path(r'''$TempDb''').as_posix()
os.environ['STORYLENS_DATA_DIR'] = r'''$TempRoot'''
os.environ['PYTHONPATH'] = r'''$Repo''' + r'\apps\api'
sys.path.insert(0, os.environ['PYTHONPATH'])
# clear smoke/live flags
for k in list(os.environ):
    if 'FAKE' in k or 'LIVE_PROVIDER' in k or k.endswith('_API_KEY'):
        if k.startswith('STORYLENS_') or k in {'OPENAI_API_KEY','ANTHROPIC_API_KEY'}:
            os.environ.pop(k, None)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app.db.session import get_db, get_session_factory
from app.main import create_app
from app.model_gateway.gateway import ModelGateway
from app.model_gateway.registry import get_model_gateway
from tests.fakes import FakeProvider

db_path = Path(r'''$TempDb''')
con = sqlite3.connect(str(db_path))
row = con.execute('SELECT subject_id FROM analysis_runs WHERE id=10').fetchone()
chapter_id = int(row[0]) if row and str(row[0]).isdigit() else None
if chapter_id is None:
    row2 = con.execute(\"SELECT id FROM chapters WHERE COALESCE(section_type,'') != 'front_matter' ORDER BY id LIMIT 1\").fetchone()
    chapter_id = int(row2[0]) if row2 else None
con.close()
if not chapter_id:
    raise SystemExit('no chapter for fake create')

engine = create_engine(f'sqlite:///{db_path.as_posix()}', connect_args={'check_same_thread': False})
factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
app = create_app()
def _db():
    with factory() as s:
        yield s
app.dependency_overrides[get_db] = _db
app.dependency_overrides[get_session_factory] = lambda: factory
app.dependency_overrides[get_model_gateway] = lambda: ModelGateway([FakeProvider()])
t0 = time.perf_counter()
try:
    with TestClient(app) as client:
        resp = client.post(f'/api/v1/chapters/{chapter_id}/analysis-runs', json={'provider_name':'fake','force':True})
    ms = int((time.perf_counter() - t0) * 1000)
    body = resp.json() if resp.content else {}
    print(json.dumps({'status_code': resp.status_code, 'ms': ms, 'body': body, 'text': resp.text[:500]}, ensure_ascii=False))
    if resp.status_code >= 400:
        sys.exit(2)
except Exception as e:
    ms = int((time.perf_counter() - t0) * 1000)
    print(json.dumps({'status_code': 0, 'ms': ms, 'error': str(e)}, ensure_ascii=False))
    if 'database is locked' in str(e):
        sys.exit(3)
    sys.exit(1)
finally:
    engine.dispose()
"@
if ($LASTEXITCODE -eq 3) { $lockHits++ }
if ($createOut) {
  Write-Host "CREATE_OUT: $createOut"
  try {
    $createJson = $createOut | ConvertFrom-Json
    $createMs = [int]$createJson.ms
    if ($createJson.body -and $createJson.body.run_id) { $newRunId = $createJson.body.run_id }
  } catch {
    Write-Host "CREATE_PARSE_ERROR: $_"
  }
}

$idempotent = (
  ($state1.run.status -eq $state2.run.status) -and
  ($state1.run.error_code -eq $state2.run.error_code) -and
  ($state1.run.completed_at -eq $state2.run.completed_at)
)

$result = [ordered]@{
  health_http = $health2
  analysis_runs_http = $runs2
  run10_after_status = $state1.run.status
  run10_after_error = $state1.run.error_code
  reservation_after = $state1.reservations
  recovery_idempotent = $idempotent
  new_run_id = $newRunId
  create_ms = $createMs
  database_lock_errors = $lockHits
  temp_db = $TempDb
  passed = (
    ($health2 -eq 200) -and ($runs2 -eq 200) -and
    ($state1.run.status -eq "failed") -and
    ($state1.run.error_code -eq "PROCESS_INTERRUPTED") -and
    $idempotent -and
    ($null -ne $newRunId) -and ($createMs -ge 0) -and ($createMs -lt 5000) -and
    ($lockHits -eq 0)
  )
}
$result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ResultPath -Encoding utf8
Write-Host "RESULT: $($result | ConvertTo-Json -Compress -Depth 6)"
if (-not $result.passed) { exit 1 }
exit 0

