param(
  [int]$Port = 8765,
  [switch]$SkipBuild,
  [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$runtimeDir = Join-Path $env:LOCALAPPDATA 'StoryLens\runtime'
New-Item -ItemType Directory -Force $runtimeDir | Out-Null
$stateFile = Join-Path $runtimeDir 'web_server.json'
$outLog = Join-Path $runtimeDir 'web_server.out.log'
$errLog = Join-Path $runtimeDir 'web_server.err.log'
$url = "http://127.0.0.1:$Port"

function Get-PortOwner([int]$ListenPort) {
  $conn = Get-NetTCPConnection -LocalPort $ListenPort -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
  if (-not $conn) { return $null }
  return [int]$conn.OwningProcess
}

function Test-StoryLensHealth([string]$BaseUrl) {
  try {
    $h = Invoke-RestMethod "$BaseUrl/health" -TimeoutSec 2
    return ($h.status -eq 'ok')
  } catch {
    return $false
  }
}

function Open-StoryLensBrowser([string]$Target) {
  if ($NoBrowser) { return }
  try {
    Start-Process $Target | Out-Null
  } catch {
    Write-Warning "Could not open browser automatically. Please visit $Target"
  }
}

# Idempotent reuse: healthy existing web server
if (Test-StoryLensHealth $url) {
  try {
    $rt = Invoke-RestMethod "$url/api/v1/runtime" -TimeoutSec 3
    Write-Host "StoryLens local web already running."
    Write-Host "URL: $url"
    Write-Host "Runtime: $($rt.runtime_mode) | data: $($rt.data_directory)"
  } catch {
    Write-Host "StoryLens already healthy at $url"
  }
  Open-StoryLensBrowser $url
  exit 0
}

$owner = Get-PortOwner $Port
if ($owner) {
  throw "Port $Port is already in use by PID $owner, but /health is not a StoryLens service. Stop that process or choose another port."
}

$python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
  throw "Missing $python — create the project venv first."
}

$dist = Join-Path $Root 'apps\desktop\dist'
$index = Join-Path $dist 'index.html'
if (-not $SkipBuild -or -not (Test-Path $index)) {
  Write-Host 'Building frontend production assets...'
  Push-Location (Join-Path $Root 'apps\desktop')
  try {
    $env:VITE_API_BASE_URL = ''
    npm run build
  } finally {
    Pop-Location
  }
}
if (-not (Test-Path $index)) {
  throw "Frontend dist missing: $index"
}

$env:STORYLENS_WEB_MODE = '1'
$env:STORYLENS_APP_ENV = 'production'
$env:STORYLENS_SERVE_FRONTEND = '1'
$env:STORYLENS_WEB_PORT = "$Port"
$env:STORYLENS_FRONTEND_DIST = $dist
$env:STORYLENS_FRONTEND_ORIGIN = $url
# Do not set STORYLENS_DATA_DIR — use %LOCALAPPDATA%\StoryLens

$launcher = Start-Process $python -ArgumentList @(
  '-m', 'uvicorn', 'app.main:app',
  '--app-dir', 'apps/api',
  '--host', '127.0.0.1',
  '--port', "$Port"
) -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru

$deadline = (Get-Date).AddSeconds(45)
$ok = $false
do {
  if (Test-StoryLensHealth $url) { $ok = $true; break }
  Start-Sleep -Milliseconds 500
} until ((Get-Date) -gt $deadline)

if (-not $ok) {
  if (Get-Process -Id $launcher.Id -ErrorAction SilentlyContinue) {
    Stop-Process -Id $launcher.Id -Force -ErrorAction SilentlyContinue
  }
  throw "StoryLens web failed health check. See logs:`n  $outLog`n  $errLog"
}

$listenPid = Get-PortOwner $Port
if (-not $listenPid) { $listenPid = [int]$launcher.Id }

@{
  schema = 'storylens-web-1'
  pid = $listenPid
  launcher_pid = [int]$launcher.Id
  port = $Port
  url = $url
  started_at = (Get-Date).ToString('o')
  frontend_dist = $dist
} | ConvertTo-Json | Set-Content $stateFile -Encoding utf8

Write-Host "StoryLens local web started."
Write-Host "URL: $url"
Write-Host "Data: $env:LOCALAPPDATA\StoryLens"
Write-Host "State: $stateFile"
Open-StoryLensBrowser $url
