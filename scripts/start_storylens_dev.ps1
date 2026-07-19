param([switch]$Tauri,[switch]$StartLocalModel)
$ErrorActionPreference='Stop'
if(-not(Test-Path .\.venv\Scripts\python.exe)){throw 'Python environment missing'}
if(-not(Get-Command npm.cmd -ErrorAction SilentlyContinue)){throw 'npm missing'}
try{
  & .\scripts\start_backend.ps1
  & .\scripts\start_desktop_dev.ps1 -Tauri:$Tauri
  if($StartLocalModel){
    Write-Warning 'Starting the safe local model profile may use significant GPU resources.'
    & .\scripts\start_profile_model.ps1 -Profile safe
  }
  $backend=Get-Content -Raw data/runtime/dev/backend.json|ConvertFrom-Json
  $desktop=Get-Content -Raw data/runtime/dev/desktop.json|ConvertFrom-Json
  $merged=@{
    runtime_schema_version='1c-a-4'
    backend_pid=[int]$backend.backend_pid
    frontend_pid=[int]$desktop.frontend_pid
    backend_port=8000
    frontend_port=1420
    capability_schema_version='1c-a-2'
  }
  $merged|ConvertTo-Json|Set-Content data/runtime/dev/runtime.json -Encoding utf8
  Write-Host "StoryLens is ready. Backend http://127.0.0.1:8000 | Desktop http://127.0.0.1:1420 | backend_pid=$($merged.backend_pid) frontend_pid=$($merged.frontend_pid)"
}catch{
  Write-Error "StoryLens failed to start: $($_.Exception.Message)"
  try{& .\scripts\stop_storylens_dev.ps1}catch{}
  throw
}
