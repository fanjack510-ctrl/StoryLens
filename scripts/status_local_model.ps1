$ErrorActionPreference='Stop'; $PidFile='data/runtime/local_llama/process.json'
if(-not (Test-Path $PidFile)){Write-Host 'status=stopped';exit 1}
$Meta=Get-Content $PidFile -Raw|ConvertFrom-Json; $Process=Get-Process -Id $Meta.pid -ErrorAction SilentlyContinue
$Health='unavailable'; if($Process){try{$Models=Invoke-RestMethod "http://$($Meta.host):$($Meta.port)/v1/models" -TimeoutSec 5;$Health='healthy'}catch{$Health='starting_or_unhealthy'}}
$Gpu=& nvidia-smi --query-gpu=name,memory.used --format=csv,noheader 2>$null
[pscustomobject]@{running=[bool]$Process;pid=$Meta.pid;port=$Meta.port;health=$Health;model=$Meta.model_name;log=$Meta.log_path;error_log=$Meta.error_log_path;gpu=$Gpu}|ConvertTo-Json -Depth 3
if(-not $Process){exit 1}
