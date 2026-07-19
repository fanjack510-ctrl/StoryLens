$ErrorActionPreference='Stop'; $PidFile='data/runtime/local_llama/process.json'
if(-not (Test-Path $PidFile)){Write-Host 'No StoryLens local model PID record.';exit 0}
$Meta=Get-Content $PidFile -Raw|ConvertFrom-Json; $Process=Get-CimInstance Win32_Process -Filter "ProcessId=$($Meta.pid)" -ErrorAction SilentlyContinue
if($Process){if($Process.ExecutablePath -notmatch 'llama-server\.exe$'){throw "Recorded PID $($Meta.pid) is not llama-server; refusing to stop."};Stop-Process -Id $Meta.pid -Force;Write-Host "Stopped StoryLens llama-server PID=$($Meta.pid)."}else{Write-Host 'Recorded process is no longer running.'}
Remove-Item -LiteralPath $PidFile -Force
