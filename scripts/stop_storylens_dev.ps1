$ErrorActionPreference='Stop'
$runtime='data/runtime/dev'
function Get-PortOwner([int]$ListenPort){
  $conn=Get-NetTCPConnection -LocalPort $ListenPort -State Listen -ErrorAction SilentlyContinue|Select-Object -First 1
  if(-not $conn){return $null}
  return [int]$conn.OwningProcess
}
function Stop-StoryLensPid([int]$ProcessId,[string]$Role){
  if(-not $ProcessId){return}
  $p=Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
  if(-not $p){Write-Host "No running ${Role} PID=${ProcessId}";return}
  $identity="$($p.Name) $($p.CommandLine)"
  $cmd=[string]$p.CommandLine
  if($Role -eq 'backend'){
    $isUvicorn=($cmd -match 'uvicorn' -and $cmd -match 'app\.main:app')
    # Windows may hide CommandLine; fall back to python + port-8000 ownership.
    $ownsPort=((Get-PortOwner 8000) -eq $ProcessId) -and ($p.Name -match '(?i)^python(\.exe)?$')
    if(-not $isUvicorn -and -not $ownsPort){
      throw "Refusing to stop non-StoryLens backend PID=${ProcessId}"
    }
  }
  if($Role -eq 'desktop'){
    $isNode=($cmd -match '(npm|node|cmd)')
    $ownsPort=((Get-PortOwner 1420) -eq $ProcessId) -and ($p.Name -match '(?i)^(node|npm)(\.exe)?$')
    if(-not $isNode -and -not $ownsPort){
      throw "Refusing to stop non-StoryLens desktop PID=${ProcessId}"
    }
  }
  try{
    Stop-Process -Id $ProcessId -Force -ErrorAction Stop
    Write-Host "Stopped ${Role} PID=${ProcessId}"
  }catch{
    Write-Warning "Could not stop ${Role} PID=${ProcessId}: $($_.Exception.Message). Try elevated shell."
  }
}
function Find-StoryLensBackend{
  $owner=Get-PortOwner 8000
  if(-not $owner){return $null}
  $p=Get-CimInstance Win32_Process -Filter "ProcessId=$owner" -ErrorAction SilentlyContinue
  if(-not $p){return $null}
  $cmd=[string]$p.CommandLine
  if(($cmd -match 'uvicorn' -and $cmd -match 'app\.main:app') -or ($p.Name -match '(?i)^python(\.exe)?$')){return $owner}
  return $null
}
function Find-StoryLensDesktop{
  $owner=Get-PortOwner 1420
  if(-not $owner){return $null}
  $p=Get-CimInstance Win32_Process -Filter "ProcessId=$owner" -ErrorAction SilentlyContinue
  if(-not $p){return $null}
  $cmd=[string]$p.CommandLine
  if(($cmd -match '(vite|node)') -or ($p.Name -match '(?i)^node(\.exe)?$')){return $owner}
  return $null
}

$desktopMeta=$null;$backendMeta=$null
if(Test-Path "$runtime/desktop.json"){$desktopMeta=Get-Content -Raw "$runtime/desktop.json"|ConvertFrom-Json}
if(Test-Path "$runtime/backend.json"){$backendMeta=Get-Content -Raw "$runtime/backend.json"|ConvertFrom-Json}

if($desktopMeta){
  foreach($childId in @($desktopMeta.child_pids)){
    try{if(Get-Process -Id $childId -ErrorAction SilentlyContinue){Stop-Process -Id $childId -Force -ErrorAction SilentlyContinue}}catch{}
  }
  $desktopPid=[int]($desktopMeta.frontend_pid)
  if(-not $desktopPid -and $desktopMeta.listen_pid){$desktopPid=[int]$desktopMeta.listen_pid}
  if(-not $desktopPid -and $desktopMeta.pid){$desktopPid=[int]$desktopMeta.pid}
  Stop-StoryLensPid $desktopPid 'desktop'
  Remove-Item -LiteralPath "$runtime/desktop.json" -Force -ErrorAction SilentlyContinue
}else{
  $found=Find-StoryLensDesktop
  if($found){Stop-StoryLensPid $found 'desktop'}
}

if($backendMeta){
  $backendPid=[int]($backendMeta.backend_pid)
  if(-not $backendPid -and $backendMeta.pid){$backendPid=[int]$backendMeta.pid}
  Stop-StoryLensPid $backendPid 'backend'
  Remove-Item -LiteralPath "$runtime/backend.json" -Force -ErrorAction SilentlyContinue
}else{
  $found=Find-StoryLensBackend
  if($found){Stop-StoryLensPid $found 'backend'}
}

$deadline=(Get-Date).AddSeconds(15)
do{
  $busy=@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue|Where-Object{$_.LocalPort -in @(8000,1420)})
  if($busy){Start-Sleep -Milliseconds 250}
}until(-not $busy -or (Get-Date)-gt $deadline)
if($busy){
  $owners=$busy|ForEach-Object{"$($_.LocalPort):$($_.OwningProcess)"}
  throw "StoryLens ports were not released: $($owners -join ', '). Retry with elevated permissions if access is denied."
}
Write-Host 'StoryLens ports 8000 and 1420 are free.'
