$ErrorActionPreference="Continue"
$root="D:\Dstorylens-wt-1.2.0-after-1.1.2"
$ev="D:\Dstorylens-wt-1.2.0-after-1.1.2\release\evidence\whole-book\CHG-20260803-049"
Set-Location "$root\apps\desktop"
$start=Get-Date
npx tsc -b --pretty false *>&1 | Out-File "$ev\TYPECHECK.txt" -Encoding utf8
Add-Content "$ev\TYPECHECK.txt" ("TYPECHECK_EXIT=$LASTEXITCODE")
npx vite build *>&1 | Out-File "$ev\DESKTOP_PRODUCTION_BUILD.txt" -Encoding utf8
Add-Content "$ev\DESKTOP_PRODUCTION_BUILD.txt" ("BUILD_EXIT=$LASTEXITCODE")
Add-Content "$ev\DESKTOP_PRODUCTION_BUILD.txt" ("DURATION_SEC=$([int]((Get-Date)-$start).TotalSeconds)")
