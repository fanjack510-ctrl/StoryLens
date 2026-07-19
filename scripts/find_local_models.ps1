param([string[]]$Roots=@('D:\AI',"$env:USERPROFILE\Downloads","$env:USERPROFILE\.cache\huggingface","$env:USERPROFILE\.cache\modelscope"))
$ErrorActionPreference='Stop'
$rows=@();$seen=@{}
foreach($root in $Roots|Select-Object -Unique){
  if(-not(Test-Path -LiteralPath $root)){continue}
  Get-ChildItem -LiteralPath $root -Recurse -File -Filter '*.gguf' -ErrorAction SilentlyContinue|
    Where-Object{$_.Name -match 'Qwen3.*14B.*Q4_K_M'}|ForEach-Object{
      if($seen.ContainsKey($_.FullName)){return};$seen[$_.FullName]=$true
      $hash=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
      $stream=[IO.File]::OpenRead($_.FullName);try{$bytes=New-Object byte[] 4;[void]$stream.Read($bytes,0,4)}finally{$stream.Dispose()};$header=[Text.Encoding]::ASCII.GetString($bytes)
      $rows+=[pscustomobject]@{path=$_.FullName;size_bytes=$_.Length;sha256=$hash;split=$_.Name -match '-\d+-of-\d+';gguf_magic=$header;architecture='qwen3';parameter_scale='14B';quantization='Q4_K_M';source_hint=if($_.FullName -match 'huggingface|Qwen'){ 'Qwen official/cache' }else{'unknown'}}
    }
}
$rows|ConvertTo-Json -Depth 3
