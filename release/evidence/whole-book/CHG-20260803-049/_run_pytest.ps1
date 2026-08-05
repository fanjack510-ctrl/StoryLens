$ErrorActionPreference="Continue"
$root="D:\Dstorylens-wt-1.2.0-after-1.1.2"
$ev="D:\Dstorylens-wt-1.2.0-after-1.1.2\release\evidence\whole-book\CHG-20260803-049"
$py="D:\Dstorylens\.venv\Scripts\python.exe"
$priv="D:\Dstorylens-private-wt-1.2.0-after-1.1.2\src"
Set-Location $root
$env:PYTHONPATH="$priv;$root\apps\api"
$start=Get-Date
& $py -m pytest --continue-on-collection-errors -q --tb=line *>&1 | Out-File -FilePath "$ev\PUBLIC_FULL_PYTEST.txt" -Encoding utf8
Add-Content "$ev\PUBLIC_FULL_PYTEST.txt" ("EXIT=$LASTEXITCODE")
Add-Content "$ev\PUBLIC_FULL_PYTEST.txt" ("DURATION_SEC=$([int]((Get-Date)-$start).TotalSeconds)")
