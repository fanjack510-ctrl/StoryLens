# Build FastAPI sidecar with PyInstaller → apps/desktop/src-tauri/binaries/
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Missing .venv. Run .\scripts\bootstrap.ps1 first."
}

$OutDir = Join-Path $Root "apps\api\dist-sidecar"
$WorkDir = Join-Path $Root "apps\api\build\pyinstaller"
$Spec = Join-Path $Root "apps\api\storylens-api.spec"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

Write-Host "==> Ensuring PyInstaller"
# Native tools often write progress to stderr; do not treat that as terminating under Stop.
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    & $Python -m pip install -q "pyinstaller>=6.3"
    if ($LASTEXITCODE) { exit $LASTEXITCODE }

    Write-Host "==> PyInstaller sidecar"
    & $Python -m PyInstaller --noconfirm --clean --distpath $OutDir --workpath $WorkDir $Spec
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
} finally {
    $ErrorActionPreference = $prevEap
}

$Built = Join-Path $OutDir "storylens-api.exe"
if (-not (Test-Path $Built)) {
    throw "Sidecar binary missing: $Built"
}

$Triple = "x86_64-pc-windows-msvc"
$BinDir = Join-Path $Root "apps\desktop\src-tauri\binaries"
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
$Target = Join-Path $BinDir "storylens-api-$Triple.exe"
Copy-Item -Force $Built $Target
Write-Host "Sidecar ready: $Target"
Get-Item $Target | Format-List Name, Length, FullName
