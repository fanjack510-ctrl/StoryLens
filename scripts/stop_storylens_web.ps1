param(
  [int]$Port = 8765
)
$ErrorActionPreference = 'Stop'
$runtimeDir = Join-Path $env:LOCALAPPDATA 'StoryLens\runtime'
$stateFile = Join-Path $runtimeDir 'web_server.json'
$lockFile = Join-Path $runtimeDir 'storylens_instance.lock'

function Get-PortOwner([int]$ListenPort) {
  $conn = Get-NetTCPConnection -LocalPort $ListenPort -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
  if (-not $conn) { return $null }
  return [int]$conn.OwningProcess
}

function Stop-StoryLensWebPid([int]$ProcessId) {
  if (-not $ProcessId) { return }
  $p = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
  if (-not $p) {
    Write-Host "No process PID=$ProcessId"
    return
  }
  $cmd = [string]$p.CommandLine
  $ownsPort = ((Get-PortOwner $Port) -eq $ProcessId)
  $isUvicorn = ($cmd -match 'uvicorn' -and $cmd -match 'app\.main:app')
  $isPython = $p.Name -match '(?i)^python(\.exe)?$'
  if (-not $isUvicorn -and -not ($ownsPort -and $isPython)) {
    throw "Refusing to stop non-StoryLens process PID=$ProcessId"
  }
  Stop-Process -Id $ProcessId -Force -ErrorAction Stop
  Write-Host "Stopped StoryLens web PID=$ProcessId"
}

$stopped = $false
if (Test-Path $stateFile) {
  $meta = Get-Content -Raw $stateFile | ConvertFrom-Json
  $pidToStop = [int]($meta.pid)
  if (-not $pidToStop -and $meta.launcher_pid) { $pidToStop = [int]$meta.launcher_pid }
  if ($meta.port) { $Port = [int]$meta.port }
  if ($pidToStop) {
    try {
      Stop-StoryLensWebPid $pidToStop
      $stopped = $true
    } catch {
      Write-Warning $_.Exception.Message
    }
  }
  Remove-Item -LiteralPath $stateFile -Force -ErrorAction SilentlyContinue
}

$owner = Get-PortOwner $Port
if ($owner) {
  try {
    Stop-StoryLensWebPid $owner
    $stopped = $true
  } catch {
    throw
  }
}

if (Test-Path $lockFile) {
  Remove-Item -LiteralPath $lockFile -Force -ErrorAction SilentlyContinue
}

$deadline = (Get-Date).AddSeconds(15)
do {
  $busy = Get-PortOwner $Port
  if ($busy) { Start-Sleep -Milliseconds 250 }
} until (-not $busy -or (Get-Date) -gt $deadline)

if ($busy) {
  throw "Port $Port still held by PID $busy"
}

if ($stopped) {
  Write-Host "StoryLens local web stopped. Port $Port is free."
} else {
  Write-Host "No StoryLens local web process found on port $Port."
}
