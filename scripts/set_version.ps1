# Unify StoryLens version across package manifests.
# Usage: ./scripts/set_version.ps1 0.1.0
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidatePattern('^\d+\.\d+\.\d+([.-][A-Za-z0-9.-]+)?$')]
    [string]$Version
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false

function Write-TextNoBom([string]$Path, [string]$Content) {
    [System.IO.File]::WriteAllText($Path, $Content, $Utf8NoBom)
}

function Set-JsonVersion([string]$Path, [string]$NewVersion) {
    $raw = [System.IO.File]::ReadAllText($Path)
    if ($raw -match '"version"\s*:\s*"' + [regex]::Escape($NewVersion) + '"') {
        Write-Host "unchanged $Path ($NewVersion)"
        return
    }
    $updated = [regex]::Replace($raw, '"version"\s*:\s*"[^"]+"', "`"version`": `"$NewVersion`"", 1)
    if ($updated -eq $raw) { throw "Failed to update version in $Path" }
    Write-TextNoBom $Path $updated
    Write-Host "updated $Path"
}

function Set-TomlPackageVersion([string]$Path, [string]$NewVersion) {
    $raw = [System.IO.File]::ReadAllText($Path)
    if ($raw -match '(?m)^version\s*=\s*"' + [regex]::Escape($NewVersion) + '"') {
        Write-Host "unchanged $Path ($NewVersion)"
        return
    }
    $lines = $raw -split "`r?`n", -1
    $inPackage = $false
    $done = $false
    $out = foreach ($line in $lines) {
        if ($line -match '^\s*\[package\]\s*$') { $inPackage = $true }
        elseif ($line -match '^\s*\[') { $inPackage = $false }
        if (-not $done -and $inPackage -and $line -match '^\s*version\s*=') {
            $done = $true
            "version = `"$NewVersion`""
        } else {
            $line
        }
    }
    if (-not $done) { throw "Failed to update [package].version in $Path" }
    Write-TextNoBom $Path (($out -join "`n").TrimEnd() + "`n")
    Write-Host "updated $Path"
}

function Set-PyprojectVersion([string]$Path, [string]$NewVersion) {
    $raw = [System.IO.File]::ReadAllText($Path)
    if ($raw -match '(?m)^version\s*=\s*"' + [regex]::Escape($NewVersion) + '"') {
        Write-Host "unchanged $Path ($NewVersion)"
        return
    }
    $updated = [regex]::Replace($raw, '(?m)^version\s*=\s*"[^"]+"', "version = `"$NewVersion`"", 1)
    if ($updated -eq $raw) { throw "Failed to update version in $Path" }
    Write-TextNoBom $Path $updated
    Write-Host "updated $Path"
}

function Set-FastapiVersion([string]$Path, [string]$NewVersion) {
    $raw = [System.IO.File]::ReadAllText($Path)
    if ($raw -match 'FastAPI\(title="StoryLens API", version="' + [regex]::Escape($NewVersion) + '"') {
        Write-Host "unchanged $Path ($NewVersion)"
        return
    }
    $updated = [regex]::Replace(
        $raw,
        'FastAPI\(title="StoryLens API", version="[^"]+"',
        "FastAPI(title=`"StoryLens API`", version=`"$NewVersion`""
    )
    if ($updated -eq $raw) { throw "Failed to update FastAPI version in $Path" }
    Write-TextNoBom $Path $updated
    Write-Host "updated $Path"
}

Set-JsonVersion (Join-Path $Root "apps/desktop/package.json") $Version
Set-JsonVersion (Join-Path $Root "apps/desktop/src-tauri/tauri.conf.json") $Version
Set-TomlPackageVersion (Join-Path $Root "apps/desktop/src-tauri/Cargo.toml") $Version
Set-PyprojectVersion (Join-Path $Root "pyproject.toml") $Version
Set-FastapiVersion (Join-Path $Root "apps/api/app/main.py") $Version

Write-Host "Version set to $Version"
