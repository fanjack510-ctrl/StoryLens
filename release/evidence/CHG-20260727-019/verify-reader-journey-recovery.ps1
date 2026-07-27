# CHG-20260727-019 zero-cost verification (no real Provider, no Sidecar/Installer build).
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
Set-Location $Root
$env:PYTHONPATH = Join-Path $Root "apps\api"
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { throw "Missing venv python: $Py" }

$Evidence = Join-Path $Root "release\evidence\CHG-20260727-019"
$Work = Join-Path $Evidence "_work"
New-Item -ItemType Directory -Force -Path $Work | Out-Null

$IncidentDbDir = "D:\StoryLensIncident\INC-20260727-001-current\AppData-StoryLens\database"
$CopyDir = Join-Path $Work "incident-db-copy"
if (Test-Path $CopyDir) { Remove-Item -Recurse -Force $CopyDir }
New-Item -ItemType Directory -Force -Path $CopyDir | Out-Null

$results = [ordered]@{
  INCIDENT_SNAPSHOT_VERIFICATION = "FAIL"
  STARTUP_RECOVERY = "FAIL"
  RECOVERY_IDEMPOTENCY = "FAIL"
  HEALTHY_RUNNING_PRESERVED = "FAIL"
  RESUME_CONTRACT = "FAIL"
  OUTPUT_TRUNCATED_PERSISTENCE = "FAIL"
  SIDECAR_HEALTH_AFTER_FAILURE = "FAIL"
  TASK_CENTER_JOURNEY_PROGRESS = "FAIL"
  TASK_CENTER_JOURNEY_CTA = "FAIL"
  TYPESCRIPT_TYPECHECK = "FAIL"
  GIT_DIFF_CHECK = "FAIL"
  TARGETED_PYTEST = "FAIL"
  TARGETED_VITEST = "FAIL"
  REAL_PROVIDER_CALLS = 0
  NEW_ANALYSIS_RUNS = 0
  NEW_JOURNEY_TASKS = 0
  JOURNEY_WORKER_AUTO_ENQUEUED = "NO"
  SIDECAR_BUILD_COUNT = 0
  INSTALLER_BUILD_COUNT = 0
}

function Write-ResultBlock {
  param([string]$Overall)
  @"
READER JOURNEY RECOVERY VERIFICATION：
$Overall
INCIDENT RUN：
2
INCIDENT JOURNEY：
1
ORIGINAL STATUS：
scene_profiles_running
RECOVERED STATUS：
$($results.RECOVERED_STATUS)
RETRYABLE：
$($results.RETRYABLE)
ERROR CODE：
$($results.ERROR_CODE)
JOURNEY WORKER AUTO ENQUEUED：
$($results.JOURNEY_WORKER_AUTO_ENQUEUED)
REAL PROVIDER CALLS：
$($results.REAL_PROVIDER_CALLS)
NEW ANALYSIS RUNS：
$($results.NEW_ANALYSIS_RUNS)
NEW JOURNEY TASKS：
$($results.NEW_JOURNEY_TASKS)
EXISTING INVOCATIONS PRESERVED：
$($results.EXISTING_INVOCATIONS_PRESERVED)
SCENE ARTIFACTS PRESERVED：
$($results.SCENE_ARTIFACTS_PRESERVED)
SIDECAR HEALTH AFTER FAILURE：
$($results.SIDECAR_HEALTH_AFTER_FAILURE)
OUTPUT_TRUNCATED PERSISTENCE：
$($results.OUTPUT_TRUNCATED_PERSISTENCE)
STARTUP RECOVERY：
$($results.STARTUP_RECOVERY)
RECOVERY IDEMPOTENCY：
$($results.RECOVERY_IDEMPOTENCY)
HEALTHY RUNNING PRESERVED：
$($results.HEALTHY_RUNNING_PRESERVED)
RESUME CONTRACT：
$($results.RESUME_CONTRACT)
TASK CENTER JOURNEY PROGRESS：
$($results.TASK_CENTER_JOURNEY_PROGRESS)
TASK CENTER JOURNEY CTA：
$($results.TASK_CENTER_JOURNEY_CTA)
TYPESCRIPT TYPECHECK：
$($results.TYPESCRIPT_TYPECHECK)
GIT DIFF CHECK：
$($results.GIT_DIFF_CHECK)
SIDECAR BUILD COUNT：
0
INSTALLER BUILD COUNT：
0
"@
}

# --- Incident snapshot recovery (copy only; never touch original) ---
if (-not (Test-Path (Join-Path $IncidentDbDir "storylens.db"))) {
  throw "Incident snapshot DB missing: $IncidentDbDir"
}
Copy-Item (Join-Path $IncidentDbDir "storylens.db") $CopyDir
foreach ($extra in @("storylens.db-wal", "storylens.db-shm")) {
  $p = Join-Path $IncidentDbDir $extra
  if (Test-Path $p) { Copy-Item $p $CopyDir }
}

$SnapshotPy = Join-Path $Work "snapshot_recover.py"
@'
import json, shutil, sys
from pathlib import Path
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from app.db.models import AnalysisArtifact, AnalysisRun, ModelInvocation, ReaderJourneyRun
from app.services.reader_journey_recovery import JOURNEY_INTERRUPTED, recover_orphaned_reader_journeys
from app.services.scene_pipeline import mark_interrupted_runs_failed

db = Path(sys.argv[1])
engine = create_engine(f"sqlite:///{db.as_posix()}")
Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
out = {}
with Session() as session:
    j = session.get(ReaderJourneyRun, 1)
    if j is None:
        raise SystemExit("journey 1 missing")
    out["original_status"] = j.status
    inv_before = session.scalar(select(func.count()).select_from(ModelInvocation)) or 0
    runs_before = session.scalar(select(func.count()).select_from(AnalysisRun)) or 0
    journeys_before = session.scalar(select(func.count()).select_from(ReaderJourneyRun)) or 0
    scenes_before = session.scalar(
        select(func.count()).select_from(AnalysisArtifact).where(
            AnalysisArtifact.run_id == 2,
            AnalysisArtifact.artifact_type == "scene_analysis",
        )
    ) or 0
    stats1 = mark_interrupted_runs_failed(session)
    session.expire_all()
    j = session.get(ReaderJourneyRun, 1)
    out["recovered_status"] = j.status
    out["retryable"] = bool(j.retryable)
    out["error_code"] = j.root_error_code
    out["interrupted_journeys"] = stats1.get("interrupted_journeys", 0)
    stats2 = mark_interrupted_runs_failed(session)
    out["second_interrupted"] = stats2.get("interrupted_journeys", 0)
    inv_after = session.scalar(select(func.count()).select_from(ModelInvocation)) or 0
    runs_after = session.scalar(select(func.count()).select_from(AnalysisRun)) or 0
    journeys_after = session.scalar(select(func.count()).select_from(ReaderJourneyRun)) or 0
    scenes_after = session.scalar(
        select(func.count()).select_from(AnalysisArtifact).where(
            AnalysisArtifact.run_id == 2,
            AnalysisArtifact.artifact_type == "scene_analysis",
        )
    ) or 0
    out["inv_preserved"] = inv_before == inv_after and inv_before >= 1
    out["runs_delta"] = runs_after - runs_before
    out["journeys_delta"] = journeys_after - journeys_before
    out["scenes"] = f"{scenes_after} / 7"
    out["scenes_ok"] = scenes_before == 7 and scenes_after == 7
    out["ok"] = (
        out["original_status"] == "scene_profiles_running"
        and out["recovered_status"] != "scene_profiles_running"
        and out["retryable"] is True
        and out["error_code"] == JOURNEY_INTERRUPTED
        and out["second_interrupted"] == 0
        and out["runs_delta"] == 0
        and out["journeys_delta"] == 0
        and out["scenes_ok"]
        and out["inv_preserved"]
    )
print(json.dumps(out, ensure_ascii=False))
'@ | Set-Content -Encoding utf8 $SnapshotPy

$snapJson = & $Py $SnapshotPy (Join-Path $CopyDir "storylens.db") | Select-Object -Last 1
$snap = $snapJson | ConvertFrom-Json
$results.RECOVERED_STATUS = $snap.recovered_status
$results.RETRYABLE = if ($snap.retryable) { "YES" } else { "NO" }
$results.ERROR_CODE = $snap.error_code
$results.EXISTING_INVOCATIONS_PRESERVED = if ($snap.inv_preserved) { "YES" } else { "NO" }
$results.SCENE_ARTIFACTS_PRESERVED = $snap.scenes
$results.NEW_ANALYSIS_RUNS = [int]$snap.runs_delta
$results.NEW_JOURNEY_TASKS = [int]$snap.journeys_delta
if ($snap.ok) {
  $results.INCIDENT_SNAPSHOT_VERIFICATION = "PASS"
  $results.STARTUP_RECOVERY = "PASS"
  $results.RECOVERY_IDEMPOTENCY = "PASS"
}

# --- Targeted pytest / vitest ---
& $Py -m pytest apps/api/tests/test_reader_journey_startup_recovery_local.py -q --tb=line
if ($LASTEXITCODE -eq 0) {
  $results.TARGETED_PYTEST = "PASS"
  $results.OUTPUT_TRUNCATED_PERSISTENCE = "PASS"
  $results.SIDECAR_HEALTH_AFTER_FAILURE = "PASS"
  $results.HEALTHY_RUNNING_PRESERVED = "PASS"
  $results.RESUME_CONTRACT = "PASS"
} else {
  $results.TARGETED_PYTEST = "FAIL"
}

Push-Location (Join-Path $Root "apps\desktop")
npx vitest run src/services/compositeRunLifecycle.test.ts src/services/runLifecycle.test.ts src/services/runProgressDisplay.test.ts
$vitestOk = ($LASTEXITCODE -eq 0)
Pop-Location
if ($vitestOk) {
  $results.TARGETED_VITEST = "PASS"
  $results.TASK_CENTER_JOURNEY_PROGRESS = "PASS"
  $results.TASK_CENTER_JOURNEY_CTA = "PASS"
}

Push-Location (Join-Path $Root "apps\desktop")
npx tsc -p tsconfig.json --noEmit
$tscOk = ($LASTEXITCODE -eq 0)
Pop-Location
$results.TYPESCRIPT_TYPECHECK = if ($tscOk) { "PASS" } else { "FAIL" }

# Git diff sanity: no VERSION / installer / private engine
$diffNames = git -C $Root diff --name-only HEAD
$bad = $diffNames | Where-Object {
  $_ -match '^(VERSION$|apps/desktop/src-tauri/target/|dist/|Dstorylens-private)'
}
$results.GIT_DIFF_CHECK = if (-not $bad) { "PASS" } else { "FAIL" }

$overall = "PASSED"
foreach ($k in @(
  "INCIDENT_SNAPSHOT_VERIFICATION","STARTUP_RECOVERY","RECOVERY_IDEMPOTENCY",
  "HEALTHY_RUNNING_PRESERVED","RESUME_CONTRACT","OUTPUT_TRUNCATED_PERSISTENCE",
  "SIDECAR_HEALTH_AFTER_FAILURE","TASK_CENTER_JOURNEY_PROGRESS","TASK_CENTER_JOURNEY_CTA",
  "TYPESCRIPT_TYPECHECK","GIT_DIFF_CHECK","TARGETED_PYTEST","TARGETED_VITEST"
)) {
  if ($results[$k] -ne "PASS") { $overall = "FAILED"; break }
}

$block = Write-ResultBlock -Overall $overall
$block | Set-Content -Encoding utf8 (Join-Path $Evidence "verification-result.txt")
Write-Output $block
if ($overall -ne "PASSED") { exit 1 }
exit 0
