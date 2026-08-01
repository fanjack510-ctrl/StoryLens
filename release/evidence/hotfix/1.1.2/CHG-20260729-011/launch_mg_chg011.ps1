# CHG-20260729-011 Manual Gate launcher — isolated Fake Provider, ports 18047 / 1426
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)))
$Evidence = $PSScriptRoot
$DataDir = Join-Path $env:TEMP "storylens-mg-chg011-workflow-consistency"
$DbPath = Join-Path $DataDir "database\storylens-mg-chg011.db"
$ApiPort = 18047
$FePort = 1426
$Py = Join-Path $Repo ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }

Write-Host "=== CHG-011 Manual Gate seed ==="
& $Py (Join-Path $Evidence "seed_mg_chg011_fixtures.py") --data-dir $DataDir --db-path $DbPath
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$env:STORYLENS_DATABASE_URL = "sqlite:///" + ($DbPath -replace "\\", "/")
$env:STORYLENS_DATA_DIR = $DataDir
$env:STORYLENS_APP_ENV = "development"
$env:STORYLENS_APP_PORT = "$ApiPort"
$env:STORYLENS_REAL_PROVIDER_ENABLED = "0"
$env:STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE = "1"
$env:STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE_FAIL = "0"
$env:STORYLENS_JOURNEY_FAKE_MODE = "success"
$env:STORYLENS_ALLOWED_ORIGINS = "http://127.0.0.1:$FePort"

Write-Host "=== Starting API on :$ApiPort ==="
$apiJob = Start-Job -ScriptBlock {
    param($Repo, $ApiPort)
    Set-Location (Join-Path $Repo "apps\api")
    $env:STORYLENS_APP_PORT = "$ApiPort"
    & (Join-Path $Repo ".venv\Scripts\python.exe") -m uvicorn app.main:app --host 127.0.0.1 --port $ApiPort
} -ArgumentList $Repo, $ApiPort

Start-Sleep -Seconds 3
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/health" -TimeoutSec 10
    Write-Host "API health: $($health.status)"
} catch {
    Write-Warning "API health check pending: $_"
}

Write-Host "=== Starting Frontend on :$FePort ==="
$feJob = Start-Job -ScriptBlock {
    param($Repo, $FePort, $ApiPort)
    Set-Location (Join-Path $Repo "apps\desktop")
    $env:VITE_API_BASE_URL = "http://127.0.0.1:$ApiPort"
    npx vite --host 127.0.0.1 --port $FePort --strictPort
} -ArgumentList $Repo, $FePort, $ApiPort

Start-Sleep -Seconds 8
Write-Host "=== Refresh fixtures after API orphan recovery ==="
& $Py (Join-Path $Evidence "refresh_mg_after_api_boot.py")
Write-Host "=== HTTP E2E ==="
$env:MG_API_BASE = "http://127.0.0.1:$ApiPort"
& $Py (Join-Path $Evidence "run_http_e2e_chg011.py")
$e2eExit = $LASTEXITCODE

Write-Host ""
Write-Host "Manual Gate ready:"
Write-Host "  DATABASE: $DbPath"
Write-Host "  API:      http://127.0.0.1:$ApiPort"
Write-Host "  FRONTEND: http://127.0.0.1:$FePort"
Write-Host "  Manifest: $(Join-Path $Evidence 'FIXTURE_MANIFEST.json')"
Write-Host ""
Write-Host "Jobs: API=$($apiJob.Id) FE=$($feJob.Id) — Stop-Job -Id $($apiJob.Id),$($feJob.Id); Remove-Job -Id $($apiJob.Id),$($feJob.Id)"

exit $e2eExit
