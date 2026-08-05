$ErrorActionPreference="Continue"
$root="D:\Dstorylens-wt-1.2.0-after-1.1.2"
$ev="D:\Dstorylens-wt-1.2.0-after-1.1.2\release\evidence\whole-book\CHG-20260803-049"
$py="D:\Dstorylens\.venv\Scripts\python.exe"
Set-Location $root
$sw=[Diagnostics.Stopwatch]::StartNew()
$out="$ev\CHECK_PROJECT.txt"
function Log($m){ Add-Content $out ("[{0:N1}s] {1}" -f $sw.Elapsed.TotalSeconds, $m) }
Set-Content $out "CHECK_PROJECT INSTRUMENTED START"
Log "STEP2 rglob *.gguf"
& $py -c "from pathlib import Path; import time; r=Path(r'D:\Dstorylens-wt-1.2.0-after-1.1.2'); t=time.time(); xs=list(r.rglob('*.gguf')); print('gguf_count', len(xs), 'sec', round(time.time()-t,2))" 2>&1 | ForEach-Object { Log "$_" }
Log "STEP3 version_manager check"
& $py scripts\version_manager.py check *>&1 | Tee-Object -FilePath "$ev\VERSION_MANAGER_CHECK.txt" | ForEach-Object { Log "$_" }
Log "STEP3 exit=$LASTEXITCODE"
Log "STEP4 change_registry check START"
$regJob = Start-Process -FilePath $py -ArgumentList 'scripts\change_registry.py','check' -WorkingDirectory $root -RedirectStandardOutput "$ev\CHANGE_REGISTRY_CHECK.txt" -RedirectStandardError "$ev\CHANGE_REGISTRY_CHECK.err.txt" -PassThru -NoNewWindow
$deadline = (Get-Date).AddMinutes(18)
while (-not $regJob.HasExited -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 5; Log ("STEP4 still running pid=$($regJob.Id) elapsed={0:N1}s" -f $sw.Elapsed.TotalSeconds) }
if (-not $regJob.HasExited) { Log "STEP4 TIMEOUT after 18m — killing change_registry"; Stop-Process -Id $regJob.Id -Force; Log "STEP4 exit=TIMEOUT" } else { Log "STEP4 exit=$($regJob.ExitCode)" }
Log "STEP5 check_project.py START"
$cp = Start-Process -FilePath $py -ArgumentList 'scripts\check_project.py' -WorkingDirectory $root -RedirectStandardOutput "$ev\CHECK_PROJECT_RAW.txt" -RedirectStandardError "$ev\CHECK_PROJECT_RAW.err.txt" -PassThru -NoNewWindow
$deadline2 = (Get-Date).AddMinutes(18)
while (-not $cp.HasExited -and (Get-Date) -lt $deadline2) { Start-Sleep -Seconds 5; Log ("STEP5 still running pid=$($cp.Id) elapsed={0:N1}s" -f $sw.Elapsed.TotalSeconds) }
if (-not $cp.HasExited) { Log "STEP5 TIMEOUT — killing check_project"; Stop-Process -Id $cp.Id -Force; Log "STEP5 exit=TIMEOUT" } else { Get-Content "$ev\CHECK_PROJECT_RAW.txt" -ErrorAction SilentlyContinue | ForEach-Object { Log $_ }; Log "STEP5 exit=$($cp.ExitCode)" }
Log "DONE"
