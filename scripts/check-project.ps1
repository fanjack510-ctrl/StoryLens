# Thin wrapper: run project acceptance checks via local venv.
$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python venv missing. Run .\scripts\bootstrap.ps1 first."
}
& $python (Join-Path $PSScriptRoot "check_project.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python -m pytest
exit $LASTEXITCODE
