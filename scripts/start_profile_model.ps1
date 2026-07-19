param(
  [Parameter(Mandatory=$true)][string]$ModelProfile,
  [ValidateSet(16,24,32)][int]$GpuLayers=16,
  [string]$ProfilesPath='config/local_model_profiles.yaml'
)
$ErrorActionPreference='Stop'
$profiles=Get-Content -Raw -Encoding utf8 $ProfilesPath|ConvertFrom-Json
$profile=$profiles.$ModelProfile;if(-not $profile){throw "Unknown model profile: $ModelProfile"}
if($profile.manual_only -and $ModelProfile -ne 'qwen36_27b_manual'){throw 'Invalid manual-only profile'}
$server=(Get-Content .env -Encoding utf8|Where-Object{$_ -match '^STORYLENS_LLAMA_SERVER_PATH='}|Select-Object -First 1)-replace '^[^=]+=',''
if(-not(Test-Path -LiteralPath $server)){throw 'llama-server missing'}
if(-not(Test-Path -LiteralPath $profile.model_path)){throw 'profile model file missing'}
if(Test-Path 'data/runtime/local_llama/process.json'){throw 'StoryLens model PID record already exists'}
$runtime='data/runtime/local_llama';New-Item -ItemType Directory -Force $runtime|Out-Null
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss';$log=Join-Path $runtime "server-$stamp.log";$err=Join-Path $runtime "server-$stamp.err.log"
$args=@('-m',$profile.model_path,'-c',$profile.context_size,'-ngl',$GpuLayers,'-np',$profile.parallel,'-a',$profile.provider_name,'--host','127.0.0.1','--port','8080','--batch-size',$profile.batch_size,'--ubatch-size',$profile.ubatch_size,'--reasoning','off')
$process=Start-Process -FilePath $server -ArgumentList $args -RedirectStandardOutput $log -RedirectStandardError $err -WindowStyle Hidden -PassThru
[ordered]@{pid=$process.Id;started_at=(Get-Date).ToUniversalTime().ToString('o');profile=$ModelProfile;model_name=$profile.provider_name;model_file=[IO.Path]::GetFileName($profile.model_path);host='127.0.0.1';port=8080;context_size=$profile.context_size;gpu_layers=$GpuLayers;parallel=$profile.parallel;thinking_enabled=$false;thinking_control_method='llama-server --reasoning off';log_path=(Resolve-Path $log).Path;error_log_path=(Resolve-Path $err).Path;arguments=$args}|ConvertTo-Json -Depth 4|Set-Content 'data/runtime/local_llama/process.json' -Encoding utf8
Write-Host "Started $ModelProfile PID=$($process.Id) with thinking disabled."
