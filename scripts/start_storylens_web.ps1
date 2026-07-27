param(
  [int]$Port = 8765,
  [switch]$SkipBuild,
  [switch]$NoBrowser,
  [string]$ProjectRoot = ''
)
# StoryLens local web: HTTP + static SPA only.
# Product progress uses HTTP polling (not WebSocket/SSE). Pass --ws none so Uvicorn
# does not import optional websockets.* (broken/incomplete installs must not block boot).
$ErrorActionPreference = 'Stop'
$Root = if ($ProjectRoot) { (Resolve-Path -LiteralPath $ProjectRoot).Path } else { Split-Path -Parent $PSScriptRoot }
Set-Location $Root

$runtimeDir = Join-Path $env:LOCALAPPDATA 'StoryLens\runtime'
New-Item -ItemType Directory -Force $runtimeDir | Out-Null
$stateFile = Join-Path $runtimeDir 'web_server.json'
$outLog = Join-Path $runtimeDir 'web_server.out.log'
$errLog = Join-Path $runtimeDir 'web_server.err.log'
$url = "http://127.0.0.1:$Port"
$frontendBuildMetaName = 'storylens-frontend-build.json'

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

function Get-GitHead([string]$RepoRoot) {
  try {
    $head = (& git -C $RepoRoot rev-parse HEAD 2>$null)
    if ($LASTEXITCODE -ne 0) { return $null }
    return ([string]$head).Trim()
  } catch {
    return $null
  }
}

function Read-FrontendBuildMeta([string]$DistDir) {
  $metaPath = Join-Path $DistDir $frontendBuildMetaName
  if (-not (Test-Path -LiteralPath $metaPath)) { return $null }
  try {
    return (Get-Content -LiteralPath $metaPath -Raw -Encoding utf8 | ConvertFrom-Json)
  } catch {
    return $null
  }
}

function Assert-FrontendDistFresh([string]$DistDir, [string]$IndexPath) {
  if (-not (Test-Path -LiteralPath $IndexPath)) {
    throw "Frontend dist missing: $IndexPath"
  }
  $indexItem = Get-Item -LiteralPath $IndexPath
  Write-Host ("Frontend dist/index.html last write: {0:o}" -f $indexItem.LastWriteTimeUtc)

  $assetsDir = Join-Path $DistDir 'assets'
  if (Test-Path -LiteralPath $assetsDir) {
    $asset = Get-ChildItem -LiteralPath $assetsDir -File -ErrorAction SilentlyContinue |
      Sort-Object LastWriteTimeUtc -Descending |
      Select-Object -First 1
    if ($asset) {
      Write-Host ("Frontend assets latest: {0} @ {1:o}" -f $asset.Name, $asset.LastWriteTimeUtc)
    }
  }

  $head = Get-GitHead $Root
  $meta = Read-FrontendBuildMeta $DistDir
  if (-not $meta -or -not $meta.source_commit) {
    throw "前端 dist 缺少构建身份 ($frontendBuildMetaName)。请重新执行前端构建后再启动，未启动 StoryLens。"
  }
  if ($head -and ($meta.source_commit -ne $head)) {
    throw ("前端 dist 不是当前源码（dist={0} HEAD={1}）。请重新构建后再启动，未启动 StoryLens。" -f $meta.source_commit, $head)
  }
  Write-Host ("Frontend source_commit: {0}" -f $meta.source_commit)
  if ($meta.build_time) { Write-Host ("Frontend build_time: {0}" -f $meta.build_time) }
  if ($meta.application_version) { Write-Host ("Frontend application_version: {0}" -f $meta.application_version) }
}

# Idempotent reuse: healthy existing web server
if (Test-StoryLensHealth $url) {
  try {
    $rt = Invoke-RestMethod "$url/api/v1/runtime" -TimeoutSec 3
    Write-Host "StoryLens local web already running."
    Write-Host "URL: $url"
    Write-Host "Runtime: $($rt.runtime_mode) | data: $($rt.data_directory)"
    if ($rt.frontend_source_commit) {
      Write-Host "Frontend source_commit: $($rt.frontend_source_commit)"
    }
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
$mustBuild = (-not $SkipBuild) -or (-not (Test-Path -LiteralPath $index))
if ($mustBuild) {
  Write-Host 'Building frontend production assets...'
  Push-Location (Join-Path $Root 'apps\desktop')
  $buildExit = 0
  try {
    $env:VITE_API_BASE_URL = ''
    npm run build
    $buildExit = $LASTEXITCODE
  } finally {
    Pop-Location
  }
  if ($buildExit -ne 0) {
    Clear-WebRuntimeState
    Write-Host '前端构建失败，未启动StoryLens'
    exit $buildExit
  }
}

Assert-FrontendDistFresh $dist $index

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

$meta = Read-FrontendBuildMeta $dist
@{
  schema = 'storylens-web-1'
  pid = $listenPid
  launcher_pid = [int]$launcher.Id
  port = $Port
  url = $url
  started_at = (Get-Date).ToString('o')
  frontend_dist = $dist
  frontend_source_commit = $(if ($meta) { [string]$meta.source_commit } else { $null })
  frontend_build_time = $(if ($meta) { [string]$meta.build_time } else { $null })
  ws = 'none'
} | ConvertTo-Json | Set-Content $stateFile -Encoding utf8

Write-Host "StoryLens local web started."
Write-Host "URL: $url"
Write-Host "Data: $env:LOCALAPPDATA\StoryLens"
Write-Host "State: $stateFile"
Open-StoryLensBrowser $url
