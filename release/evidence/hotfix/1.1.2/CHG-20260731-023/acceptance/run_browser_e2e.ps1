# CHG-20260731-023 final browser acceptance 鈥?seed, API launcher, vite preview, Playwright.
$ErrorActionPreference = "Stop"

$Repo = "D:\Dstorylens-wt-chg023-final-state-fix"
$Acceptance = Join-Path $Repo "release\evidence\hotfix\1.1.2\CHG-20260731-023\acceptance"
$MgRoot = Join-Path $env:TEMP "storylens-mg-chg023-final"
$DbPath = Join-Path $MgRoot "storylens.db"
$ApiPort = 18067
$FePort = 1467
$ApiUrl = "http://127.0.0.1:$ApiPort"
$FeUrl = "http://127.0.0.1:$FePort"

$Py = "D:\Dstorylens-wt-hotfix-1.1.2-integration\.venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = Join-Path $Repo ".venv\Scripts\python.exe" }
if (-not (Test-Path $Py)) { $Py = "python" }

$apiProc = $null
$feProc = $null

function Stop-ProcSafe([System.Diagnostics.Process]$p) {
    if ($null -eq $p) { return }
    if ($p.HasExited) { return }
    try {
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    } catch { }
}

function Wait-HttpOk([string]$Url, [int]$Seconds = 90) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400) { return }
        } catch { Start-Sleep -Seconds 1 }
    }
    throw "Timeout waiting for $Url"
}

function Invoke-Seed {
    Write-Host "=== Seed CHG-023 final fixtures ==="
    $env:STORYLENS_MG_ROOT = $MgRoot
    $env:STORYLENS_MG_API_URL = $ApiUrl
    $env:STORYLENS_MG_FE_URL = $FeUrl
    & $Py (Join-Path $Repo "apps\api\scripts_seed_chg023_final_mg.py")
    if ($LASTEXITCODE -ne 0) { throw "Seed failed" }
    if (-not (Test-Path $DbPath)) { throw "DB missing after seed: $DbPath" }
}

function Stop-PortListener([int]$Port) {
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        if ($c.OwningProcess) {
            Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
}

function Start-ApiLauncher {
    param([int]$FailJourneyId = 2)
    Stop-ProcSafe $script:apiProc
    Stop-PortListener -Port $ApiPort
    Start-Sleep -Seconds 1
    $launcher = Join-Path $MgRoot "launch_api_accept.py"
    if (-not (Test-Path $launcher)) { throw "Launcher missing: $launcher" }
    $env:STORYLENS_CHG023_FAIL_JOURNEY_ID = "$FailJourneyId"
    $env:STORYLENS_MG_API_PORT = "$ApiPort"
    $env:STORYLENS_MG_FE_PORT = "$FePort"
    $apiLogOut = Join-Path $MgRoot "api_launch.out.log"
    $apiLogErr = Join-Path $MgRoot "api_launch.err.log"
    Remove-Item $apiLogOut, $apiLogErr -ErrorAction SilentlyContinue
    Write-Host "=== Start API launcher (fail_journey_id=$FailJourneyId) ==="
    $script:apiProc = Start-Process -FilePath $Py -ArgumentList @($launcher) `
        -WorkingDirectory (Join-Path $Repo "apps\api") `
        -RedirectStandardOutput $apiLogOut `
        -RedirectStandardError $apiLogErr `
        -PassThru -WindowStyle Hidden
    try {
        Wait-HttpOk "$ApiUrl/api/v1/analysis-runs"
    } catch {
        Write-Host "--- api_launch.out.log (tail) ---"
        if (Test-Path $apiLogOut) { Get-Content $apiLogOut -Tail 40 | Write-Host }
        Write-Host "--- api_launch.err.log (tail) ---"
        if (Test-Path $apiLogErr) { Get-Content $apiLogErr -Tail 40 | Write-Host }
        throw
    }
    Write-Host "API ready: $ApiUrl"
}

function Start-FePreview {
    Stop-ProcSafe $script:feProc
    Stop-PortListener -Port $FePort
    Start-Sleep -Seconds 1
    $desktop = Join-Path $Repo "apps\desktop"
    $env:VITE_API_BASE_URL = $ApiUrl
    $env:VITE_PUBLIC_GIT_HEAD = (git -C $Repo rev-parse HEAD).Trim()
    Push-Location $desktop
    try {
        Write-Host "=== Build desktop (VITE_API_BASE_URL=$ApiUrl HEAD=$($env:VITE_PUBLIC_GIT_HEAD)) ==="
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
        Write-Host "=== vite preview :$FePort ==="
        $feLogOut = Join-Path $MgRoot "fe_preview.out.log"
        $feLogErr = Join-Path $MgRoot "fe_preview.err.log"
        Remove-Item $feLogOut, $feLogErr -ErrorAction SilentlyContinue
        $npxCmd = Get-Command npx.cmd -ErrorAction SilentlyContinue
        $npx = if ($npxCmd) { $npxCmd.Source } else { "npx.cmd" }
        $script:feProc = Start-Process -FilePath $npx `
            -ArgumentList @("vite", "preview", "--host", "127.0.0.1", "--port", "$FePort", "--strictPort") `
            -WorkingDirectory $desktop `
            -RedirectStandardOutput $feLogOut `
            -RedirectStandardError $feLogErr `
            -PassThru -WindowStyle Hidden
    } finally {
        Pop-Location
    }
    Wait-HttpOk $FeUrl
    Write-Host "Frontend ready: $FeUrl"
}

function Invoke-Playwright {
    param(
        [string]$Order = "fail-first",
        [string]$ExtraEnv = @{}
    )
    $desktop = Join-Path $Repo "apps\desktop"
    Push-Location $desktop
    try {
        $env:PLAYWRIGHT_BASE_URL = $FeUrl
        $env:CHG023_FIXTURES_JSON = Join-Path $Acceptance "MANUAL_FIXTURES.json"
        $env:CHG023_TEST_ORDER = $Order
        $env:CHG023_RUN_SUCCESS_ONLY = "0"
        foreach ($k in $ExtraEnv.Keys) { Set-Item -Path "env:$k" -Value $ExtraEnv[$k] }
        Write-Host "=== Playwright (order=$Order) ==="
        npx playwright test --config playwright.chg023-final.config.ts
        if ($LASTEXITCODE -ne 0) { throw "Playwright failed (order=$Order)" }
    } finally {
        Pop-Location
    }
}

function Invoke-PlaywrightSuccessOnly {
    $desktop = Join-Path $Repo "apps\desktop"
    Push-Location $desktop
    try {
        $env:PLAYWRIGHT_BASE_URL = $FeUrl
        $env:CHG023_FIXTURES_JSON = Join-Path $Acceptance "MANUAL_FIXTURES.json"
        $env:CHG023_RUN_SUCCESS_ONLY = "1"
        Remove-Item Env:CHG023_TEST_ORDER -ErrorAction SilentlyContinue
        Write-Host "=== Playwright case B only (post API restart) ==="
        npx playwright test --config playwright.chg023-final.config.ts --grep "@success-only"
        if ($LASTEXITCODE -ne 0) { throw "Playwright success-only failed" }
    } finally {
        Pop-Location
    }
}

try {
    Stop-PortListener -Port $ApiPort
    Stop-PortListener -Port $FePort
    Start-Sleep -Seconds 2
    Invoke-Seed
    Start-ApiLauncher
    Start-FePreview

    Write-Host "`n=== Round 1: fail then success ==="
    Invoke-Playwright -Order "fail-first"

    Write-Host "`n=== Reseed + Round 2: success then fail ==="
    Stop-ProcSafe $apiProc
    Stop-PortListener -Port $ApiPort
    Start-Sleep -Seconds 2
    Invoke-Seed
    Start-ApiLauncher
    Invoke-Playwright -Order "success-first"

    Write-Host "`n=== Restart API + brief case B ==="
    Start-ApiLauncher
    Invoke-PlaywrightSuccessOnly

    Write-Host "`n=== CHG-023 browser E2E PASSED ==="
    Write-Host "  DB:       $DbPath"
    Write-Host "  Fixtures: $(Join-Path $Acceptance 'MANUAL_FIXTURES.json')"
    Write-Host "  Spec:     $(Join-Path $Repo 'apps\desktop\e2e\chg023_final_resume_state.spec.ts')"
    exit 0
} catch {
    Write-Error $_
    exit 1
} finally {
    Stop-ProcSafe $apiProc
    Stop-ProcSafe $feProc
}


