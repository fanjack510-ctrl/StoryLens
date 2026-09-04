[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateSet('web', 'app')][string]$Mode,
    [Parameter(Mandatory = $true)][string]$Server,
    [Parameter(Mandatory = $true)][string]$IdentityFile,
    [Parameter(Mandatory = $true)][string]$BaselineCommit,
    [string]$Domain = 'app.dstorylens.com',
    [switch]$DryRun,
    [switch]$KeepPackage,
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$taskPackageDirectory = $null
$taskExitCode = 1
$taskStatus = 'DEPLOY_FAILED_SAFELY'

# Native output is captured and never forwarded, including ssh/scp diagnostics.
# SSH passphrase interaction uses its terminal/ssh-agent, not script parameters.
function Invoke-CheckedNative {
    param([string]$Executable, [string[]]$Arguments)
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $captured = & $Executable @Arguments 2>&1
        $nativeCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($nativeCode -ne 0) {
        $fixedCodes = @('FULL_DEPLOYMENT_REQUIRED', 'WORKTREE_NOT_CLEAN', 'DOCUMENTATION_ONLY',
            'MODE_MISMATCH', 'INVALID_BASELINE', 'INVALID_PATH', 'HEAD_CHANGED',
            'DEPLOY_FAILED_ROLLED_BACK', 'ROLLBACK_FAILED_MANUAL_RECOVERY_REQUIRED',
            'MANUAL_RECOVERY_REQUIRED', 'SHA256_MISMATCH', 'BASELINE_MISMATCH',
            'DEPLOYED_SOURCE_DRIFT', 'RELEASE_ALREADY_EXISTS', 'PROTOCOL_MISMATCH')
        $safeCode = 'COMMAND_FAILED_SAFELY'
        foreach ($line in @($captured)) {
            if ($fixedCodes -contains [string]$line) { $safeCode = [string]$line }
        }
        throw $safeCode
    }
    return (@($captured) -join "`n")
}

try {
    if ($Server -cnotmatch '^[a-z_][a-z0-9_-]*@[a-z0-9][a-z0-9.-]*$' -or
        $Domain -cnotmatch '^[a-z0-9][a-z0-9.-]*[a-z0-9]$' -or $Domain.Contains('..') -or
        -not $Domain.Contains('.') -or $Domain.Length -gt 253 -or
        $BaselineCommit -cnotmatch '^[0-9a-f]{7,40}$') { throw 'INVALID_ARGUMENTS' }
    $root = Split-Path -Parent $PSScriptRoot
    $pythonPath = Join-Path $root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        $pythonPath = (Get-Command python -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    }
    $helper = Join-Path $root 'infra\online\deploy_package.py'
    $baseArguments = @('--root', $root, '--mode', $Mode, '--baseline', $BaselineCommit)
    $preflight = Invoke-CheckedNative $pythonPath (@('-B', $helper, 'preflight') + $baseArguments)
    $metadata = $preflight | ConvertFrom-Json
    if ($metadata.tool_protocol -ne 2 -or $metadata.tool_version -cnotmatch '^[0-9a-f]{64}$') {
        throw 'PROTOCOL_MISMATCH'
    }
    # Always fail scope/dirty checks before tests, packaging, or any remote call.
    if ($SkipTests) { Write-Warning 'SKIP_TESTS_EXPLICIT: local test gate skipped.' }
    if ($DryRun) {
        $taskStatus = "DRY_RUN_OK mode=$Mode commit=$($metadata.commit) classification=$Mode"
        $taskExitCode = 0
    } else {
        if (-not (Test-Path -LiteralPath $IdentityFile -PathType Leaf)) {
            throw 'IDENTITY_FILE_UNAVAILABLE'
        }
        $keyPath = (Resolve-Path -LiteralPath $IdentityFile).Path
        $ssh = (Get-Command ssh -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
        $scp = (Get-Command scp -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
        Push-Location -LiteralPath $root
        try {
            if (-not $SkipTests) {
                if ($Mode -eq 'app') {
                    $null = Invoke-CheckedNative $pythonPath @('-m', 'pytest', 'apps/online_api/tests', '-q')
                    $null = Invoke-CheckedNative $pythonPath @('-m', 'compileall', '-q', 'apps/online_api')
                } else {
                    $npm = (Get-Command npm.cmd -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
                    $null = Invoke-CheckedNative $npm @('--prefix', 'apps/online_web', 'ci', '--no-audit')
                    foreach ($task in @('typecheck', 'test', 'build')) {
                        $null = Invoke-CheckedNative $npm @('--prefix', 'apps/online_web', 'run', $task)
                    }
                }
            }
            $taskPackageDirectory = Join-Path ([IO.Path]::GetTempPath()) ('storylens-deploy-' + [guid]::NewGuid().ToString('N'))
            $null = New-Item -ItemType Directory -Path $taskPackageDirectory
            $filename = 'storylens-deploy-' + [guid]::NewGuid().ToString('N') + '.tar.gz'
            $packagePath = Join-Path $taskPackageDirectory $filename
            $result = Invoke-CheckedNative $pythonPath (@('-B', $helper, 'package') + $baseArguments +
                @('--output', $packagePath, '--expected-head', $metadata.commit))
            $bundle = $result | ConvertFrom-Json
            $hashAlgorithm = [Security.Cryptography.SHA256]::Create()
            $packageStream = [IO.File]::OpenRead($packagePath)
            try {
                $localDigest = [BitConverter]::ToString($hashAlgorithm.ComputeHash($packageStream)).Replace('-', '').ToLowerInvariant()
            } finally {
                $packageStream.Dispose()
                $hashAlgorithm.Dispose()
            }
            if ($localDigest -cne $bundle.sha256) {
                throw 'SHA256_MISMATCH'
            }
            # Only validated alphanumeric tokens enter the remote shell command.
            # Force pinned known_hosts validation; never silently trust a new host.
            $sshOptions = @('-i', $keyPath, '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=15')
            $null = Invoke-CheckedNative $scp ($sshOptions + @($packagePath, "${Server}:/tmp/$filename"))
            $remote = "sudo -n /opt/storylens/bin/storylens-online-deploy-lightweight production --protocol 2 --tool-version '$($metadata.tool_version)' '$Mode' '$($bundle.commit)' '$filename' '$($bundle.sha256)' '$($metadata.baseline)' '$Domain'"
            $response = Invoke-CheckedNative $ssh ($sshOptions + @($Server, $remote))
            if ($response.Trim() -cne 'DEPLOY_SUCCEEDED') { throw 'REMOTE_STATUS_INVALID' }
            $taskStatus = "DEPLOY_SUCCEEDED mode=$Mode commit=$($bundle.commit)"
            $taskExitCode = 0
        } finally { Pop-Location }
    }
} catch {
    # Never print exception objects or attacker-controlled/native output.
    $safe = @('FULL_DEPLOYMENT_REQUIRED', 'WORKTREE_NOT_CLEAN', 'DOCUMENTATION_ONLY',
        'MODE_MISMATCH', 'INVALID_BASELINE', 'INVALID_PATH', 'HEAD_CHANGED',
        'DEPLOY_FAILED_ROLLED_BACK', 'ROLLBACK_FAILED_MANUAL_RECOVERY_REQUIRED',
        'MANUAL_RECOVERY_REQUIRED', 'SHA256_MISMATCH', 'BASELINE_MISMATCH',
        'DEPLOYED_SOURCE_DRIFT', 'RELEASE_ALREADY_EXISTS', 'COMMAND_FAILED_SAFELY',
        'INVALID_ARGUMENTS', 'IDENTITY_FILE_UNAVAILABLE', 'REMOTE_STATUS_INVALID', 'PROTOCOL_MISMATCH')
    if ($safe -contains $_.Exception.Message) { $taskStatus = $_.Exception.Message }
} finally {
    if ($null -ne $taskPackageDirectory -and (Test-Path -LiteralPath $taskPackageDirectory)) {
        if ($KeepPackage) {
            Write-Output "PACKAGE_KEPT directory=$taskPackageDirectory"
        } else {
            # Exact task-created directory, validated before recursive cleanup.
            $resolved = (Resolve-Path -LiteralPath $taskPackageDirectory).Path
            $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
            if ($resolved.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -and
                (Split-Path -Leaf $resolved) -match '^storylens-deploy-[0-9a-f]{32}$') {
                try {
                    if ((Get-Item -LiteralPath $resolved).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                        throw 'UNSAFE_TEMP_PATH'
                    }
                    Remove-Item -LiteralPath $resolved -Recurse -Force
                } catch {
                    $taskStatus = 'LOCAL_PACKAGE_CLEANUP_FAILED'
                    $taskExitCode = 1
                }
            }
        }
    }
}
Write-Output $taskStatus
exit $taskExitCode
