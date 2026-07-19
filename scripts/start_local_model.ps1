param(
    [ValidateSet('safe','balanced','full')][string]$Profile = 'safe',
    [int]$ContextSize = 0,
    [int]$GpuLayers = -1,
    [int]$Parallel = 1
)
$ErrorActionPreference = 'Stop'
function Get-Setting([string]$Name) {
    $Value=[Environment]::GetEnvironmentVariable($Name)
    if($Value){return $Value}
    if(Test-Path .env){$Line=Get-Content .env -Encoding utf8|Where-Object{$_ -match "^$Name="}|Select-Object -First 1;if($Line){return ($Line -split '=',2)[1].Trim()}}
    return $null
}
$Server=Get-Setting 'STORYLENS_LLAMA_SERVER_PATH'; $Model=Get-Setting 'STORYLENS_LOCAL_MODEL_PATH'
$HostAddress=Get-Setting 'STORYLENS_LOCAL_LLAMA_HOST'; if(-not $HostAddress){$HostAddress='127.0.0.1'}
$Port=[int](Get-Setting 'STORYLENS_LOCAL_LLAMA_PORT'); if($Port -le 0){$Port=8080}
$Alias=Get-Setting 'STORYLENS_LOCAL_LLAMA_MODEL'; if(-not $Alias){$Alias=[IO.Path]::GetFileNameWithoutExtension($Model)}
$Profiles=@{safe=@{context=4096;layers=16};balanced=@{context=4096;layers=24};full=@{context=4096;layers=32}}
if($ContextSize -le 0){$ContextSize=$Profiles[$Profile].context};if($GpuLayers -lt 0){$GpuLayers=$Profiles[$Profile].layers}
if($Profile -eq 'safe' -and $GpuLayers -gt 16){throw 'Safe profile cannot exceed 16 GPU layers.'}
$Batch=[int](Get-Setting 'STORYLENS_LOCAL_LLAMA_BATCH_SIZE');if($Batch -le 0){$Batch=128}
$Ubatch=[int](Get-Setting 'STORYLENS_LOCAL_LLAMA_UBATCH_SIZE');if($Ubatch -le 0){$Ubatch=64}
if(-not (Test-Path -LiteralPath $Server -PathType Leaf)){throw 'Configured llama-server is missing.'}
if(-not (Test-Path -LiteralPath $Model -PathType Leaf)){throw 'Configured GGUF model is missing.'}
if(-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)){throw 'nvidia-smi is unavailable.'}
if(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue){throw "Port $Port is already in use."}
$Runtime='data/runtime/local_llama'; New-Item -ItemType Directory -Force -Path $Runtime|Out-Null
$PidFile=Join-Path $Runtime 'process.json'
if(Test-Path $PidFile){$Old=Get-Content $PidFile -Raw|ConvertFrom-Json;if(Get-Process -Id $Old.pid -ErrorAction SilentlyContinue){throw "Recorded local model process $($Old.pid) is still running."}}
$HelpInfo=New-Object System.Diagnostics.ProcessStartInfo;$HelpInfo.FileName=$Server;$HelpInfo.Arguments='--help';$HelpInfo.UseShellExecute=$false;$HelpInfo.RedirectStandardOutput=$true;$HelpInfo.RedirectStandardError=$true
$HelpProcess=[System.Diagnostics.Process]::Start($HelpInfo);$Help=$HelpProcess.StandardOutput.ReadToEnd()+$HelpProcess.StandardError.ReadToEnd();$HelpProcess.WaitForExit();if($HelpProcess.ExitCode -ne 0){throw 'llama-server --help failed.'}
foreach($Required in @('--ctx-size','--gpu-layers','--parallel','--alias','--host','--port')){if($Help -notmatch [regex]::Escape($Required)){throw "Current llama-server does not support $Required"}}
$Timestamp=Get-Date -Format 'yyyyMMdd-HHmmss'; $Log=Join-Path $Runtime "server-$Timestamp.log"; $Err=Join-Path $Runtime "server-$Timestamp.err.log"
$Args=@('-m',$Model,'-c',$ContextSize,'-ngl',$GpuLayers,'-np',$Parallel,'-a',$Alias,'--host',$HostAddress,'--port',$Port)
$BatchSupported=$Help -match [regex]::Escape('--batch-size');$UbatchSupported=$Help -match [regex]::Escape('--ubatch-size')
if($BatchSupported){$Args += @('--batch-size',$Batch)};if($UbatchSupported){$Args += @('--ubatch-size',$Ubatch)}
$Before=& nvidia-smi --query-gpu=name,driver_version,memory.used --format=csv,noheader
$Process=Start-Process -FilePath $Server -ArgumentList $Args -RedirectStandardOutput $Log -RedirectStandardError $Err -WindowStyle Hidden -PassThru
$VersionInfo=New-Object System.Diagnostics.ProcessStartInfo;$VersionInfo.FileName=$Server;$VersionInfo.Arguments='--version';$VersionInfo.UseShellExecute=$false;$VersionInfo.RedirectStandardOutput=$true;$VersionInfo.RedirectStandardError=$true
$VersionProcess=[System.Diagnostics.Process]::Start($VersionInfo);$Version=($VersionProcess.StandardOutput.ReadToEnd()+$VersionProcess.StandardError.ReadToEnd()).Trim();$VersionProcess.WaitForExit()
[ordered]@{pid=$Process.Id;started_at=(Get-Date).ToUniversalTime().ToString('o');log_path=(Resolve-Path $Log).Path;error_log_path=(Resolve-Path $Err).Path;version=$Version;model_name=$Alias;model_file=[IO.Path]::GetFileName($Model);profile=$Profile;host=$HostAddress;port=$Port;context_size=$ContextSize;gpu_layers=$GpuLayers;parallel=$Parallel;batch_size=if($BatchSupported){$Batch}else{$null};ubatch_size=if($UbatchSupported){$Ubatch}else{$null};gpu_before=$Before;arguments=$Args}|ConvertTo-Json -Depth 4|Set-Content $PidFile -Encoding utf8
Write-Host "Started StoryLens llama-server PID=$($Process.Id). Logs: $Log and $Err"
