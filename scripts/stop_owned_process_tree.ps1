# Stop processes by recorded PIDs only (never by process name).
# Intended for test/smoke cleanup of processes this session started.
param(
    [int]$RootProcessId = 0,
    [int[]]$AlsoStop = @(),
    # Accept int[] from PowerShell callers, or a comma-separated string via -File.
    [Parameter(ValueFromRemainingArguments = $false)]
    $ExactProcessIds = @(),
    [int]$WaitMs = 8000
)

$ErrorActionPreference = "Stop"

function Convert-ToPidList($Value) {
    $out = New-Object System.Collections.Generic.List[int]
    if ($null -eq $Value) { return @() }
    if ($Value -is [string]) {
        foreach ($part in @($Value -split ',')) {
            $t = $part.Trim()
            if ($t -match '^\d+$') { $out.Add([int]$t) }
        }
        return @($out)
    }
    foreach ($item in @($Value)) {
        if ($null -eq $item) { continue }
        if ($item -is [string] -and $item -match ',') {
            foreach ($part in @($item -split ',')) {
                $t = $part.Trim()
                if ($t -match '^\d+$') { $out.Add([int]$t) }
            }
        } elseif ("$item" -match '^\d+$') {
            $out.Add([int]$item)
        }
    }
    return @($out)
}

function Get-DescendantProcessIds([int]$RootId) {
    $all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    $found = New-Object System.Collections.Generic.List[int]
    $frontier = New-Object System.Collections.Generic.Queue[int]
    $seen = @{}
    $frontier.Enqueue($RootId)
    while ($frontier.Count -gt 0) {
        $current = $frontier.Dequeue()
        if ($seen.ContainsKey($current)) { continue }
        $seen[$current] = $true
        foreach ($child in @($all | Where-Object { $_.ParentProcessId -eq $current })) {
            $cid = [int]$child.ProcessId
            if (-not $seen.ContainsKey($cid)) {
                $found.Add($cid)
                $frontier.Enqueue($cid)
            }
        }
    }
    return @($found)
}

$tracked = New-Object System.Collections.Generic.List[int]
foreach ($exact in @(Convert-ToPidList $ExactProcessIds)) {
    if ($exact -gt 0 -and -not $tracked.Contains($exact)) {
        $tracked.Add($exact)
    }
}
if ($RootProcessId -gt 0) {
    if (-not $tracked.Contains($RootProcessId)) {
        $tracked.Add($RootProcessId)
    }
    foreach ($d in @(Get-DescendantProcessIds -RootId $RootProcessId)) {
        if (-not $tracked.Contains($d)) { $tracked.Add($d) }
    }
}
foreach ($extra in @(Convert-ToPidList $AlsoStop)) {
    if ($extra -gt 0 -and -not $tracked.Contains($extra)) {
        $tracked.Add($extra)
    }
}

if ($tracked.Count -eq 0) {
    , @()
    return
}

# Prefer stopping non-root first when a root was supplied.
$ordered = New-Object System.Collections.Generic.List[int]
foreach ($id in @($tracked)) {
    if ($RootProcessId -le 0 -or $id -ne $RootProcessId) { $ordered.Add($id) }
}
if ($RootProcessId -gt 0 -and -not $ordered.Contains($RootProcessId)) {
    $ordered.Add($RootProcessId)
}

foreach ($targetPid in @($ordered)) {
    if (Get-Process -Id $targetPid -ErrorAction SilentlyContinue) {
        Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue
    }
}

$deadline = (Get-Date).AddMilliseconds($WaitMs)
$alive = @()
do {
    $alive = @($tracked | Where-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue })
    if ($alive.Count -gt 0) { Start-Sleep -Milliseconds 150 }
} while ($alive.Count -gt 0 -and (Get-Date) -lt $deadline)

if ($alive.Count -gt 0) {
    throw "Owned process tree still alive after stop (PIDs only): $($alive -join ', ')"
}

# Emit tracked PIDs for callers that want to assert residual absence.
, @($tracked)
