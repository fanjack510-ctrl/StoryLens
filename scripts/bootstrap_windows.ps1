param([switch]$SkipInstall,[switch]$UseOfficialPyPI)
$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param([scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE"
    }
}

if (-not (Test-Path ".venv")) {
    $PythonVersion = "3.11"
    $PreviousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & py -3.11 -c "import ssl" 2>$null
    $SslExitCode = $LASTEXITCODE
    $ErrorActionPreference = $PreviousErrorActionPreference
    if ($SslExitCode -ne 0) {
        Write-Warning "Python 3.11 is unavailable or its SSL module is broken; using compatible Python 3.12."
        $PythonVersion = "3.12"
    }
    Invoke-Checked { py "-$PythonVersion" -m venv .venv }
}

Invoke-Checked { & .\.venv\Scripts\python.exe -c "import ssl" }
if (-not $SkipInstall) {
    $IndexArgs = @()
    if ($UseOfficialPyPI) { $IndexArgs = @('--index-url','https://pypi.org/simple') }
    try {
        Invoke-Checked { & .\.venv\Scripts\python.exe -m pip install @IndexArgs --upgrade pip }
        Invoke-Checked { & .\.venv\Scripts\python.exe -m pip install @IndexArgs -e ".[dev]" }
    } catch {
        Write-Warning "Package index failed. Retry explicitly with -UseOfficialPyPI, or use -SkipInstall when the venv is already complete."
        throw
    }
} else {
    Write-Host "Skipping package installation; validating the existing virtual environment only."
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
} else {
    $Legacy = Get-Content .env -Encoding utf8 | Where-Object { $_ -match '^(APP_|DATABASE_URL=|DEFAULT_MODEL_PROVIDER=|LOCAL_LLAMA_)' }
    if ($Legacy) {
        Write-Warning "Existing .env contains legacy variable names. It was not overwritten. Back it up and add the STORYLENS_ prefix; run scripts/check_env.py for names."
    }
}

Write-Host "StoryLens environment is ready."
