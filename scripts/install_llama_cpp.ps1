param(
    [string]$Version = 'b9982',
    [string]$InstallRoot = 'D:\AI\llama.cpp'
)

$ErrorActionPreference = 'Stop'
if (-not [Environment]::Is64BitOperatingSystem) { throw 'Windows x64 is required.' }
if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) { throw 'nvidia-smi is unavailable; CUDA installation is not permitted.' }
$Gpu = & nvidia-smi --query-gpu=name,driver_version,compute_cap --format=csv,noheader
if ($LASTEXITCODE -ne 0) { throw 'nvidia-smi failed.' }

$Headers = @{'User-Agent'='StoryLens-llama.cpp-installer'}
$Release = Invoke-RestMethod -Uri "https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/$Version" -Headers $Headers -TimeoutSec 30
$Names = @("llama-$Version-bin-win-cuda-12.4-x64.zip", 'cudart-llama-bin-win-cuda-12.4-x64.zip')
$Assets = @($Release.assets | Where-Object { $_.name -in $Names })
if ($Assets.Count -ne 2) { throw "Official release $Version does not contain both required CUDA 12.4 assets." }

$Destination = Join-Path $InstallRoot $Version
$Downloads = Join-Path $Destination 'downloads'
$Bin = Join-Path $Destination 'bin'
New-Item -ItemType Directory -Force -Path $Downloads,$Bin | Out-Null
$ManifestAssets = @()
foreach ($Asset in $Assets) {
    $Archive = Join-Path $Downloads $Asset.name
    if (-not (Test-Path -LiteralPath $Archive)) {
        Invoke-WebRequest -Uri $Asset.browser_download_url -Headers $Headers -OutFile $Archive -TimeoutSec 1800
    }
    $Actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Archive).Hash.ToLowerInvariant()
    $Expected = ([string]$Asset.digest -replace '^sha256:','').ToLowerInvariant()
    if (-not $Expected -or $Actual -ne $Expected) { throw "SHA256 mismatch for $($Asset.name)." }
    $Extract = Join-Path $Destination ("extract-" + [IO.Path]::GetFileNameWithoutExtension($Asset.name))
    if (Test-Path $Extract) { Remove-Item -LiteralPath $Extract -Recurse -Force }
    Expand-Archive -LiteralPath $Archive -DestinationPath $Extract -Force
    Get-ChildItem -LiteralPath $Extract -File -Recurse | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $Bin $_.Name) -Force }
    $ManifestAssets += [ordered]@{name=$Asset.name;url=$Asset.browser_download_url;size=$Asset.size;sha256=$Actual}
}
$Server = Join-Path $Bin 'llama-server.exe'
if (-not (Test-Path -LiteralPath $Server)) { throw 'llama-server.exe missing after extraction.' }
$CudaDlls = @(Get-ChildItem -LiteralPath $Bin -File | Where-Object {$_.Name -match '^(cudart|cublas|ggml-cuda).*\.dll$'})
if ($CudaDlls.Count -lt 4) { throw 'Required CUDA DLL set is incomplete.' }
$ProcessInfo = New-Object System.Diagnostics.ProcessStartInfo
$ProcessInfo.FileName = $Server
$ProcessInfo.Arguments = '--version'
$ProcessInfo.UseShellExecute = $false
$ProcessInfo.RedirectStandardOutput = $true
$ProcessInfo.RedirectStandardError = $true
$Process = [System.Diagnostics.Process]::Start($ProcessInfo)
$VersionText = (($Process.StandardOutput.ReadToEnd() + $Process.StandardError.ReadToEnd()).Trim())
$Process.WaitForExit()
$VersionExitCode = $Process.ExitCode
if ($VersionExitCode -ne 0) { throw 'llama-server.exe --version failed.' }
$Manifest = [ordered]@{
    source='https://github.com/ggml-org/llama.cpp/releases'
    release_url=$Release.html_url
    tag=$Release.tag_name
    commit=$Release.target_commitish
    published_at=$Release.published_at
    installed_at=(Get-Date).ToUniversalTime().ToString('o')
    install_directory=$Destination
    server_path=$Server
    server_sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $Server).Hash.ToLowerInvariant()
    version_output=$VersionText
    cuda_dll_count=$CudaDlls.Count
    gpu_detection=$Gpu
    assets=$ManifestAssets
}
$Manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $InstallRoot 'installation-manifest.json') -Encoding utf8
Write-Host "Installed official llama.cpp $Version to $Destination"
Write-Host $VersionText
