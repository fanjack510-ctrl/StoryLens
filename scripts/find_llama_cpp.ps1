param([switch]$Json)

$ErrorActionPreference = "Stop"
$Roots = @(
    'D:\AI', 'D:\Dstorylens', 'D:\llama.cpp', 'D:\llama',
    (Join-Path $env:USERPROFILE 'Downloads'),
    (Join-Path $env:USERPROFILE 'Desktop')
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -Unique

$PathRoots = $env:PATH -split ';' | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
$Candidates = @()
foreach ($Root in @($Roots + $PathRoots | Select-Object -Unique)) {
    Get-ChildItem -LiteralPath $Root -Filter 'llama-server.exe' -File -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
        $Directory = $_.DirectoryName
        $CudaFiles = @(Get-ChildItem -LiteralPath $Directory -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^(cudart|cublas|ggml-cuda).*\.dll$' })
        $Version = $_.VersionInfo.FileVersion
        $LooksCuda = $CudaFiles.Count -gt 0 -or $Directory -match 'cuda'
        $LooksOfficial = $Directory -match 'llama|ggml'
        $Candidates += [pscustomobject]@{
            path = $_.FullName
            directory = $Directory
            file_version = $Version
            has_cuda_dependencies = $CudaFiles.Count -gt 0
            cuda_dll_count = $CudaFiles.Count
            looks_cuda_x64 = $LooksCuda -and [Environment]::Is64BitOperatingSystem
            source_requires_verification = -not $LooksOfficial
            priority = if ($LooksCuda -and $CudaFiles.Count -gt 0) { 1 } elseif ($LooksCuda) { 2 } else { 9 }
            modified_utc = $_.LastWriteTimeUtc.ToString('o')
        }
    }
}
$Candidates = @($Candidates | Sort-Object priority, @{Expression='modified_utc';Descending=$true}, path -Unique)
if ($Json) { $Candidates | ConvertTo-Json -Depth 4 } else { $Candidates | Format-Table -AutoSize }
if ($Candidates.Count -eq 0) {
    Write-Error 'No llama-server.exe candidate found in the approved search roots or PATH.'
    exit 1
}
exit 0
