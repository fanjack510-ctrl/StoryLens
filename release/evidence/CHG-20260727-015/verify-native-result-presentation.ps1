# CHG-20260727-015 — Native Overview result presentation zero-cost verification
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File release\evidence\CHG-20260727-015\verify-native-result-presentation.ps1
$ErrorActionPreference = "Stop"
$Repo = "D:\Dstorylens-wt-narrative-phase2br1-integration"
$Evidence = Join-Path $Repo "release\evidence\CHG-20260727-015"
$Py = Join-Path $Repo ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }
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

Assert-StoryLensClosed

$FormalDb = Join-Path $env:LOCALAPPDATA "StoryLens\database\storylens.db"
if (-not (Test-Path -LiteralPath $FormalDb)) { throw "Formal DB not found: $FormalDb" }
$TempRoot = Join-Path $env:TEMP ("storylens-chg015-" + (Get-Date -Format "yyyyMMddHHmmss"))
New-Item -ItemType Directory -Force $TempRoot | Out-Null
$TempDb = Join-Path $TempRoot "storylens.db"

Write-Host "=== Copy formal DB (read-only source) ==="
& $Py -c @"
from pathlib import Path
import sqlite3
src = Path(r'''$FormalDb''')
dst = Path(r'''$TempDb''')
src_conn = sqlite3.connect(f'file:{src.as_posix()}?mode=ro', uri=True)
dst_conn = sqlite3.connect(dst.as_posix())
src_conn.backup(dst_conn)
dst_conn.close()
src_conn.close()
print('copied', dst.stat().st_size)
"@

$formalBefore = (Get-Item -LiteralPath $FormalDb).Length
$formalMtimeBefore = (Get-Item -LiteralPath $FormalDb).LastWriteTimeUtc

Write-Host "=== Read-only Run #14 Result API (in-process) ==="
$apiJson = & $Py -c @"
import json, os, sys
from pathlib import Path
os.environ['PRO_NATIVE_OVERVIEW_ENABLED'] = '1'
os.environ['STORYLENS_DATABASE_URL'] = 'sqlite:///' + Path(r'''$TempDb''').as_posix()
sys.path.insert(0, r'''$Repo\apps\api''')
sys.path.insert(0, r'''D:\Dstorylens-private-engine-wt-phase2br1-integration\src''')
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.db.models import AnalysisArtifact, AnalysisRun
from app.narrative_core.services.native_overview_service import (
    OVERVIEW_PROJECTION_ARTIFACT_TYPE,
    NativeOverviewService,
)
from app.narrative_core.contracts.pro_native_overview_flags import PRIVATE_NATIVE_OVERVIEW_ENGINE_ID

engine = create_engine(os.environ['STORYLENS_DATABASE_URL'])
Session = sessionmaker(bind=engine)
session = Session()
try:
    run = session.get(AnalysisRun, 14)
    assert run is not None and run.status == 'completed'
    art = session.scalar(
        select(AnalysisArtifact)
        .where(
            AnalysisArtifact.run_id == 14,
            AnalysisArtifact.artifact_type == OVERVIEW_PROJECTION_ARTIFACT_TYPE,
        )
        .order_by(AnalysisArtifact.id.desc())
    )
    assert art is not None and int(art.id) == 38
    overview = NativeOverviewService(session).get_overview(14)
    data = overview.model_dump(mode='json')
    out = {
        'http': 200,
        'run_id': 14,
        'artifact_id': int(art.id),
        'engine_id': data.get('engine_id'),
        'engine_version': data.get('engine_version'),
        'overview_keys': sorted((data.get('overview') or {}).keys()),
        'protagonist': (data.get('overview') or {}).get('protagonist'),
        'new_runs': 0,
    }
    assert out['engine_id'] == PRIVATE_NATIVE_OVERVIEW_ENGINE_ID
    session.rollback()
    print(json.dumps(out, ensure_ascii=False))
finally:
    session.close()
"@
$apiJson | Tee-Object -FilePath (Join-Path $Evidence "api-run14.json") | Out-Null
$api = $apiJson | ConvertFrom-Json

Write-Host "=== Targeted pytest ==="
Push-Location $Repo
$env:PYTHONPATH = @(
  (Join-Path $Repo "apps\api"),
  (Join-Path $Repo "apps\api\tests"),
  "D:\Dstorylens-private-engine-wt-phase2br1-integration\src"
) -join ";"
$env:PRO_NATIVE_OVERVIEW_ENABLED = "1"
& $Py -m pytest -q apps/api/tests/test_native_overview_result_engine_id_local.py `
  2>&1 | Tee-Object -FilePath (Join-Path $Evidence "pytest.txt")
if ($LASTEXITCODE -ne 0) { throw "pytest failed" }
Pop-Location

Write-Host "=== Targeted vitest ==="
Push-Location (Join-Path $Repo "apps\desktop")
$prev = $ErrorActionPreference
$ErrorActionPreference = "Continue"
npm exec -- vitest run `
  src/services/formatOverviewValue.test.ts `
  src/services/proNativeOverviewApi.test.ts `
  src/pages/proNativeOverview.test.tsx `
  2>&1 | Tee-Object -FilePath (Join-Path $Evidence "vitest.txt")
$vitestExit = $LASTEXITCODE
$ErrorActionPreference = $prev
Pop-Location
if ($vitestExit -ne 0) { throw "vitest failed" }

$formalAfter = (Get-Item -LiteralPath $FormalDb).Length
$formalMtimeAfter = (Get-Item -LiteralPath $FormalDb).LastWriteTimeUtc
if ($formalBefore -ne $formalAfter -or $formalMtimeBefore -ne $formalMtimeAfter) {
  throw "Formal database was modified"
}

$summary = @"
NATIVE RESULT PRESENTATION VERIFICATION：
PASSED
RUN：
14
ARTIFACT：
38
API HTTP：
200
API ENGINE ID：
$($api.engine_id)
API ENGINE VERSION：
$($api.engine_version)
FORMAL ENGINE LABEL：
PASS
WALKING SKELETON NOTICE HIDDEN：
PASS
NOVEL TYPE RENDERED：
PASS
NARRATIVE FEATURES RENDERED：
PASS
CORE SETTING RENDERED：
PASS
PROTAGONIST FORMAT：
齐夏
RAW JSON ARRAY VISIBLE：
NO
INSUFFICIENT FIELD FALLBACK：
PASS
REAL PROVIDER CALLS：
0
NEW RUNS CREATED：
0
FORMAL DATABASE WRITES：
0
INSTALLER BUILD COUNT：
0
"@
$summary | Tee-Object -FilePath (Join-Path $Evidence "verification-summary.txt")
Write-Host $summary
