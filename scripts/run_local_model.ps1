param(
    [string]$LlamaServer,
    [string]$ModelPath,
    [int]$ContextSize = 0,
    [int]$GpuLayers = -1,
    [string]$HostAddress,
    [int]$Port = 0,
    [int]$Parallel = 1,
    [string]$ModelAlias
)

$ErrorActionPreference = "Stop"
function Get-Setting([string]$Name) {
    $Value = [Environment]::GetEnvironmentVariable($Name)
    if ($Value) { return $Value }
    if (Test-Path .env) {
        $Line = Get-Content .env -Encoding utf8 | Where-Object { $_ -match "^$Name=" } | Select-Object -First 1
        if ($Line) { return ($Line -split '=',2)[1].Trim() }
    }
    return $null
}
function Get-OrDefault($Value, $Default) { if ($null -eq $Value -or $Value -eq '') { return $Default }; return $Value }

if (-not $LlamaServer) { $LlamaServer = Get-Setting 'STORYLENS_LLAMA_SERVER_PATH' }
if (-not $ModelPath) { $ModelPath = Get-Setting 'STORYLENS_LOCAL_MODEL_PATH' }
if ($ContextSize -le 0) { $ContextSize = [int](Get-OrDefault (Get-Setting 'STORYLENS_LOCAL_LLAMA_CONTEXT_SIZE') '16384') }
if ($GpuLayers -lt 0) { $GpuLayers = [int](Get-OrDefault (Get-Setting 'STORYLENS_LOCAL_LLAMA_GPU_LAYERS') '999') }
if (-not $HostAddress) { $HostAddress = Get-OrDefault (Get-Setting 'STORYLENS_LOCAL_LLAMA_HOST') '127.0.0.1' }
if ($Port -le 0) { $Port = [int](Get-OrDefault (Get-Setting 'STORYLENS_LOCAL_LLAMA_PORT') '8080') }
if (-not $ModelAlias) { $ModelAlias = Get-OrDefault (Get-Setting 'STORYLENS_LOCAL_LLAMA_MODEL') ([IO.Path]::GetFileNameWithoutExtension($ModelPath)) }

if (-not $LlamaServer -or -not (Test-Path -LiteralPath $LlamaServer -PathType Leaf)) { throw "llama-server executable not found. Configure STORYLENS_LLAMA_SERVER_PATH." }
if (-not $ModelPath -or -not (Test-Path -LiteralPath $ModelPath -PathType Leaf)) { throw "GGUF model not found. Configure STORYLENS_LOCAL_MODEL_PATH." }
if ($ContextSize -le 0 -or $GpuLayers -lt 0 -or $Port -lt 1 -or $Port -gt 65535 -or $Parallel -lt 1) { throw "Invalid context, GPU layer, parallel, or port setting." }
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { throw "Port $Port is already in use." }

$HelpInfo=New-Object System.Diagnostics.ProcessStartInfo;$HelpInfo.FileName=$LlamaServer;$HelpInfo.Arguments='--help';$HelpInfo.UseShellExecute=$false;$HelpInfo.RedirectStandardOutput=$true;$HelpInfo.RedirectStandardError=$true
$HelpProcess=[System.Diagnostics.Process]::Start($HelpInfo);$null=$HelpProcess.StandardOutput.ReadToEnd();$null=$HelpProcess.StandardError.ReadToEnd();$HelpProcess.WaitForExit()
if ($HelpProcess.ExitCode -ne 0) { throw "llama-server --help failed." }
Write-Host "Starting llama-server: model=$([IO.Path]::GetFileName($ModelPath)) alias=$ModelAlias context=$ContextSize gpu_layers=$GpuLayers parallel=$Parallel host=$HostAddress port=$Port"
& $LlamaServer -m $ModelPath -c $ContextSize -ngl $GpuLayers -np $Parallel -a $ModelAlias --host $HostAddress --port $Port
exit $LASTEXITCODE
