param(
  [string]$InstallDir='D:\AI\StoryLens\models\Qwen3-14B-Q4_K_M',
  [string]$Proxy='',
  [string]$LoadTestStatus='not_tested'
)
$ErrorActionPreference='Stop'
$Repo='Qwen/Qwen3-14B-GGUF';$File='Qwen3-14B-Q4_K_M.gguf'
$Url="https://huggingface.co/$Repo/resolve/main/$File";$Manifest='D:\AI\StoryLens\models\model-manifest.json'
New-Item -ItemType Directory -Force -Path $InstallDir|Out-Null
$partial=Join-Path $InstallDir ($File+'.partial');$target=Join-Path $InstallDir $File
if(-not(Test-Path $target)){
  $curlArgs=@('--fail','--location','--retry','20','--retry-all-errors','--retry-delay','5','--connect-timeout','30','--speed-limit','65536','--speed-time','60','--continue-at','-','--output',$partial)
  if($Proxy){$curlArgs+=@('--proxy',$Proxy)};$curlArgs+=$Url
  & curl.exe @curlArgs;if($LASTEXITCODE){throw 'Official Hugging Face download failed'}
  Move-Item -LiteralPath $partial -Destination $target -Force
}
$item=Get-Item -LiteralPath $target;if($item.Length -lt 8000000000){throw 'Downloaded model is unexpectedly small'}
$hash=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
$stream=[IO.File]::OpenRead($target);try{$header=New-Object byte[] 4;[void]$stream.Read($header,0,4)}finally{$stream.Dispose()}
$magic=[Text.Encoding]::ASCII.GetString($header);if($magic -ne 'GGUF'){throw 'Invalid GGUF header'}
$record=[ordered]@{model_id=$Repo;file_name=$File;path=$target;size_bytes=$item.Length;sha256=$hash;quantization='Q4_K_M';source=$Url;downloaded_at=(Get-Date).ToUniversalTime().ToString('o');gguf_metadata=@{magic=$magic;architecture='qwen3';parameter_scale='14B'};load_test_status=$LoadTestStatus}
$record|ConvertTo-Json -Depth 5|Set-Content -Encoding utf8 $Manifest
$record|ConvertTo-Json -Depth 5
