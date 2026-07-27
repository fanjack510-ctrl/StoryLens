param([int]$Port=8000)
$ErrorActionPreference='Stop'
$runtime='data/runtime/dev'
New-Item -ItemType Directory -Force $runtime|Out-Null
function Get-PortOwner([int]$ListenPort){
  $conn=Get-NetTCPConnection -LocalPort $ListenPort -State Listen -ErrorAction SilentlyContinue|Select-Object -First 1
  if(-not $conn){return $null}
  return [int]$conn.OwningProcess
}
function Assert-StoryLensBackend([int]$ProcessId){
  $proc=Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
  if(-not $proc){throw "Backend PID ${ProcessId} is not running."}
  $cmd=[string]$proc.CommandLine
  $isUvicorn=($cmd -match 'uvicorn' -and $cmd -match 'app\.main:app')
  $isPython=$proc.Name -match '(?i)^python(\.exe)?$'
  # CommandLine may be empty under restricted ACLs; health check already passed.
  if(-not $isUvicorn -and -not $isPython){
    throw "Port owner PID ${ProcessId} is not a StoryLens FastAPI process."
  }
  return $proc
}
if(Test-Path "$runtime/backend.json"){
  $record=Get-Content -Raw "$runtime/backend.json"|ConvertFrom-Json
  $recordedPid=[int]$record.backend_pid
  if(-not $recordedPid -and $record.pid){$recordedPid=[int]$record.pid}
  if($recordedPid -and (Get-Process -Id $recordedPid -ErrorAction SilentlyContinue)){
    throw 'Recorded StoryLens backend already exists.'
  }
  Remove-Item -LiteralPath "$runtime/backend.json" -Force
}
$existing=Get-PortOwner $Port
if($existing){throw "Port $Port is already in use by PID $existing."}
$out="$runtime/backend.out.log";$err="$runtime/backend.err.log"
# --ws none: StoryLens uses HTTP polling for tasks/progress; do not require websockets.
$launcher=Start-Process .\.venv\Scripts\python.exe -ArgumentList @('-m','uvicorn','app.main:app','--app-dir','apps/api','--host','127.0.0.1','--port',"$Port",'--ws','none') -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden -PassThru
$deadline=(Get-Date).AddSeconds(30);$ok=$false
do{
  try{Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 2|Out-Null;$ok=$true}
  catch{Start-Sleep 1}
}until($ok -or (Get-Date)-gt $deadline)
if(-not $ok){
  if(Get-Process -Id $launcher.Id -ErrorAction SilentlyContinue){Stop-Process -Id $launcher.Id -Force -ErrorAction SilentlyContinue}
  throw 'Backend failed health check'
}
$owner=Get-PortOwner $Port
if(-not $owner){
  Stop-Process -Id $launcher.Id -Force -ErrorAction SilentlyContinue
  throw 'Backend started but port owner could not be resolved.'
}
try{$proc=Assert-StoryLensBackend $owner}catch{
  Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue
  throw
}
$contract=Invoke-RestMethod "http://127.0.0.1:$Port/api/v1/system/capabilities" -TimeoutSec 3
if($contract.capability_schema_version -ne '1c-a-2'){
  Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue
  throw 'Backend capability contract mismatch'
}
@{
  runtime_schema_version='1c-a-4'
  backend_pid=$owner
  frontend_pid=$null
  backend_port=$Port
  frontend_port=1420
  capability_schema_version='1c-a-2'
  pid=$owner
  executable=$proc.ExecutablePath
  port=$Port
}|ConvertTo-Json|Set-Content "$runtime/backend.json" -Encoding utf8
Write-Host "FastAPI: http://127.0.0.1:$Port | capability schema 1c-a-2 | pid $owner"
