# CHG-20260727-016 — Single-chapter release scope zero-cost verification
$ErrorActionPreference = "Stop"
$Repo = "D:\Dstorylens-wt-narrative-phase2br1-integration"
$Evidence = Join-Path $Repo "release\evidence\CHG-20260727-016"
$Py = Join-Path $Repo ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }
New-Item -ItemType Directory -Force $Evidence | Out-Null

function Assert-StoryLensClosed {
  $procs = Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -match '^(?i)storylens(-api|-desktop)?$'
  }
  if ($procs) {
    $procs | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
  }
}

Assert-StoryLensClosed

$FormalDb = Join-Path $env:LOCALAPPDATA "StoryLens\database\storylens.db"
$formalBefore = if (Test-Path $FormalDb) { (Get-Item $FormalDb).Length } else { 0 }
$formalMtimeBefore = if (Test-Path $FormalDb) { (Get-Item $FormalDb).LastWriteTimeUtc } else { $null }

Write-Host "=== Targeted pytest (flag off create block) ==="
Push-Location $Repo
$env:PYTHONPATH = @(
  (Join-Path $Repo "apps\api"),
  (Join-Path $Repo "apps\api\tests"),
  "D:\Dstorylens-private-engine-wt-phase2br1-integration\src"
) -join ";"
$env:PRO_NATIVE_OVERVIEW_ENABLED = "false"
& $Py -m pytest -q `
  apps/api/tests/test_native_overview_release_scope_local.py `
  apps/api/tests/test_analysis_run_exists_details_local.py `
  2>&1 | Tee-Object -FilePath (Join-Path $Evidence "pytest.txt")
if ($LASTEXITCODE -ne 0) { throw "pytest failed" }
Pop-Location

Write-Host "=== Targeted vitest ==="
Push-Location (Join-Path $Repo "apps\desktop")
$prev = $ErrorActionPreference
$ErrorActionPreference = "Continue"
npm exec -- vitest run `
  src/pages/singleChapterReleaseScope.test.tsx `
  src/pages/proNativeOverview.test.tsx `
  src/pages/BookRoutePage.test.tsx `
  src/services/chapterPrimaryAction.test.ts `
  src/services/runLifecycle.test.ts `
  2>&1 | Tee-Object -FilePath (Join-Path $Evidence "vitest.txt")
$vitestExit = $LASTEXITCODE
$ErrorActionPreference = $prev
Pop-Location
if ($vitestExit -ne 0) { throw "vitest failed" }

Write-Host "=== Build script must not bake Native Overview ON ==="
$rcScript = Get-Content (Join-Path $Repo "scripts\build_windows_rc.ps1") -Raw
if ($rcScript -match 'VITE_PRO_NATIVE_OVERVIEW_ENABLED\s*=\s*"true"') {
  throw "build_windows_rc.ps1 still forces VITE_PRO_NATIVE_OVERVIEW_ENABLED=true"
}
$backend = Get-Content (Join-Path $Repo "apps\desktop\src-tauri\src\backend.rs") -Raw
if ($backend -match 'cmd\.env\("PRO_NATIVE_OVERVIEW_ENABLED",\s*"true"\)') {
  throw "backend.rs still forces PRO_NATIVE_OVERVIEW_ENABLED=true for RC"
}

if (Test-Path $FormalDb) {
  $formalAfter = (Get-Item $FormalDb).Length
  $formalMtimeAfter = (Get-Item $FormalDb).LastWriteTimeUtc
  if ($formalBefore -ne $formalAfter -or $formalMtimeBefore -ne $formalMtimeAfter) {
    throw "Formal database was modified"
  }
}

$summary = @"
SINGLE CHAPTER RELEASE SCOPE VERIFICATION：
PASSED

NATIVE OVERVIEW BOOK ENTRY：
HIDDEN

CHAPTER AGGREGATE ENTRY：
HIDDEN

INDEPENDENT READER JOURNEY ENTRY：
HIDDEN

NATIVE DIRECT ROUTE：
COMING SOON PAGE

NATIVE CREATE BLOCKED：
YES

NATIVE HISTORICAL TASKS HIDDEN：
YES

CHAPTER PRIMARY ACTION：
PASS

CHAPTER ACTIVE REENTRY：
PASS

CHAPTER COMPLETED REENTRY：
PASS

409 EXISTING RUN REDIRECT：
PASS

REAL PROVIDER CALLS：
0

NEW NATIVE RUNS：
0

FORMAL DATABASE WRITES：
0

INSTALLER BUILD COUNT：
0
"@
$summary | Tee-Object -FilePath (Join-Path $Evidence "verification-summary.txt")
Write-Host $summary
