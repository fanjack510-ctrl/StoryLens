param([string]$OutputPath = ".\StoryLens-source.zip")

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path ".").Path
$OutputFull = [System.IO.Path]::GetFullPath((Join-Path $Root $OutputPath))
$Stage = Join-Path ([System.IO.Path]::GetTempPath()) ("storylens-package-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $Stage | Out-Null
try {
    $ExcludedDirectories = @('.venv','__pycache__','.pytest_cache','.ruff_cache','.mypy_cache','.git','node_modules','target','dist','raw','processed','exports','runtime','models','storylens_project_scaffold')
    $ExcludedFiles = @('.env','.env.backup-*','local_model_profiles.yaml','cloud_pricing.json','*.pyc','*.pyo','*.key','*.gguf','*.db','*.sqlite3','*.zip','llama-server.exe','cudart*.dll','cublas*.dll','ggml-cuda*.dll')
    $arguments = @($Root,$Stage,'/E','/NFL','/NDL','/NJH','/NJS','/NP','/XD') + $ExcludedDirectories + @('/XF') + $ExcludedFiles
    & robocopy @arguments | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed with exit code $LASTEXITCODE" }
    if (Test-Path -LiteralPath $OutputFull) { Remove-Item -LiteralPath $OutputFull -Force }
    Compress-Archive -Path (Join-Path $Stage '*') -DestinationPath $OutputFull -CompressionLevel Optimal
    Write-Host "Created safe source package: $OutputFull"
} finally {
    $ResolvedStage = [System.IO.Path]::GetFullPath($Stage)
    if ($ResolvedStage.StartsWith([System.IO.Path]::GetTempPath()) -and (Test-Path -LiteralPath $ResolvedStage)) {
        Remove-Item -LiteralPath $ResolvedStage -Recurse -Force
    }
}
