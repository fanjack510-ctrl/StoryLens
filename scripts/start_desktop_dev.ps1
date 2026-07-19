param([switch]$Tauri)
$ErrorActionPreference='Stop'
$runtime='data/runtime/dev'
New-Item -ItemType Directory -Force $runtime|Out-Null
function Get-PortOwner([int]$ListenPort){
  $conn=Get-NetTCPConnection -LocalPort $ListenPort -State Listen -ErrorAction SilentlyContinue|Select-Object -First 1
  if(-not $conn){return $null}
  return [int]$conn.OwningProcess
}
$npmArgs=if($Tauri){@('run','tauri','dev')}else{@('run','dev')}
$out="$runtime/desktop.out.log";$err="$runtime/desktop.err.log"
$p=Start-Process npm.cmd -ArgumentList $npmArgs -WorkingDirectory apps/desktop -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden -PassThru
if(-not $Tauri){
  $deadline=(Get-Date).AddSeconds(45);$ok=$false
  do{try{Invoke-WebRequest 'http://127.0.0.1:1420' -UseBasicParsing -TimeoutSec 2|Out-Null;$ok=$true}catch{Start-Sleep 1}}until($ok -or (Get-Date)-gt $deadline)
  if(-not $ok){
    if(Get-Process -Id $p.Id -ErrorAction SilentlyContinue){Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue}
    throw 'Vite failed to start'
  }
}
$owner=Get-PortOwner 1420
if(-not $Tauri -and -not $owner){throw 'Desktop started but port 1420 owner could not be resolved.'}
$allProcesses=@(Get-CimInstance Win32_Process)
$children=@();$frontier=@($p.Id)
while($frontier.Count){
  $next=@($allProcesses|Where-Object{$frontier -contains $_.ParentProcessId}|Select-Object -ExpandProperty ProcessId)
  $children+=@($next);$frontier=@($next)
}
$frontendPid=if($owner){$owner}else{$p.Id}
@{
  runtime_schema_version='1c-a-4'
  backend_pid=$null
  frontend_pid=$frontendPid
  backend_port=8000
  frontend_port=1420
  capability_schema_version='1c-a-2'
  pid=$p.Id
  child_pids=$children
  listen_pid=$frontendPid
  executable=(Get-Command npm.cmd).Source
  tauri=[bool]$Tauri
}|ConvertTo-Json|Set-Content "$runtime/desktop.json" -Encoding utf8
Write-Host 'Desktop dev: http://127.0.0.1:1420'
