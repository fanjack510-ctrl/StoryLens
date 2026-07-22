param(
  [int]$Port = 8765,
  [switch]$SkipBuild,
  [switch]$NoBrowser
)
# StoryLens local web: HTTP + static SPA only.
# Product progress uses HTTP polling (not WebSocket/SSE). Pass --ws none so Uvicorn
# does not import optional websockets.* (broken/incomplete installs must not block boot).
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

function Clear-WebRuntimeState {
  Remove-Item -LiteralPath $stateFile -Force -ErrorAction SilentlyContinue
}

function Get-LogTail([string]$Path, [int]$Lines = 12) {
  if (-not (Test-Path $Path)) { return '' }
  try {
    return ((Get-Content -LiteralPath $Path -Tail $Lines -ErrorAction SilentlyContinue) -join "`n")
  } catch {
    return ''
  }
}

function Assert-PythonBootModules([string]$PythonExe) {
  # Web mode does not require websockets; verify uvicorn is importable.
  & $PythonExe -c "import uvicorn; print(uvicorn.__version__)" | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "StoryLens local service failed to start: uvicorn is missing from .venv."
  }
}

function Fail-WebStart([string]$UserMessage, [System.Diagnostics.Process]$Proc = $null) {
  if ($Proc -and -not $Proc.HasExited) {
    try { Stop-Process -Id $Proc.Id -Force -ErrorAction SilentlyContinue } catch {}
  }
  Clear-WebRuntimeState
  $tail = Get-LogTail $errLog
  Write-Host $UserMessage
  Write-Host "开发者日志: $errLog"
  if ($tail) {
    Write-Host "---- stderr (tail) ----"
    Write-Host $tail
  }
  throw $UserMessage
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
  throw "Missing $python - create the project venv first."
}

Assert-PythonBootModules $python

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
# Do not set STORYLENS_DATA_DIR - use %LOCALAPPDATA%\StoryLens

# --ws none: StoryLens does not use WebSocket; avoid importing broken optional websockets package.
$launcher = Start-Process $python -ArgumentList @(
  '-m', 'uvicorn', 'app.main:app',
  '--app-dir', 'apps/api',
  '--host', '127.0.0.1',
  '--port', "$Port",
  '--ws', 'none'
) -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru

$deadline = (Get-Date).AddSeconds(45)
$ok = $false
do {
  $launcher.Refresh()
  if ($launcher.HasExited) {
    $exitCode = $launcher.ExitCode
    $errText = Get-LogTail $errLog 40
    if ($errText -match 'websockets|WebSocket') {
      Fail-WebStart "StoryLens 本地服务启动失败：Uvicorn WebSocket依赖不可用。" $launcher
    }
    Fail-WebStart "StoryLens 本地服务启动失败：后端进程已提前退出 (exit=$exitCode)。" $launcher
  }
  if (Test-StoryLensHealth $url) { $ok = $true; break }
  Start-Sleep -Milliseconds 400
} until ((Get-Date) -gt $deadline)

if (-not $ok) {
  Fail-WebStart "StoryLens 本地服务启动失败：健康检查超时。" $launcher
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
  ws = 'none'
} | ConvertTo-Json | Set-Content $stateFile -Encoding utf8

Write-Host "StoryLens local web started."
Write-Host "URL: $url"
Write-Host "Data: $env:LOCALAPPDATA\StoryLens"
Write-Host "State: $stateFile"
Open-StoryLensBrowser $url