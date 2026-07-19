param([int]$MaxSeconds = 300, [int]$IntervalSeconds = 2, [int]$MaxTempC = 80, [int]$MaxVramMB = 14336)
$ErrorActionPreference='Stop';$PidFile='data/runtime/local_llama/process.json';if(-not(Test-Path $PidFile)){throw 'StoryLens PID record missing.'}
$Meta=Get-Content $PidFile -Raw|ConvertFrom-Json;$Runtime='data/runtime/local_llama';$Csv=Join-Path $Runtime ("metrics-"+(Get-Date -Format 'yyyyMMdd-HHmmss')+'.csv')
'timestamp,pid,temperature_c,gpu_util_percent,vram_mb,power_w'|Set-Content $Csv -Encoding utf8;$Started=Get-Date;$Failures=0;$Triggered=$null
while(((Get-Date)-$Started).TotalSeconds -lt $MaxSeconds){
    if(-not(Get-Process -Id $Meta.pid -ErrorAction SilentlyContinue)){$Triggered='process_exited';break}
    $Line=& nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,memory.used,power.draw --format=csv,noheader,nounits 2>$null
    if($LASTEXITCODE -ne 0 -or -not $Line){$Failures++;if($Failures -ge 3){$Triggered='nvidia_smi_failed';break};Start-Sleep $IntervalSeconds;continue};$Failures=0
    $Values=$Line -split ','|ForEach-Object{$_.Trim()};$Temp=[double]$Values[0];$Util=[double]$Values[1];$Vram=[double]$Values[2];$Power=[double]$Values[3]
    "$(Get-Date -Format o),$($Meta.pid),$Temp,$Util,$Vram,$Power"|Add-Content $Csv -Encoding utf8
    if($Temp -ge $MaxTempC){$Triggered='temperature_threshold';break};if($Vram -ge $MaxVramMB){$Triggered='vram_threshold';break};Start-Sleep $IntervalSeconds
}
if(-not $Triggered -and ((Get-Date)-$Started).TotalSeconds -ge $MaxSeconds){$Triggered='request_timeout'}
if($Triggered){Write-Error "Safety stop triggered: $Triggered. Metrics: $Csv";powershell -ExecutionPolicy Bypass -File .\scripts\stop_local_model.ps1;Start-Sleep -Seconds 2;exit 1}
