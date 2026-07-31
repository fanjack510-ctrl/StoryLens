# CHG-20260731-023 Manual UI Environment

## Live stack

| Item | Value |
|------|-------|
| DATABASE | `C:\Users\msi\AppData\Local\Temp\storylens-mg-chg023\storylens.db`（隔离；正式 AppData 写入 = 0） |
| API URL | http://127.0.0.1:18057 |
| FRONTEND URL | http://127.0.0.1:1436 |
| Provider | Fake |
| REAL PROVIDER CALLS | 0 |
| FORMAL DATABASE WRITES | 0 |
| PUBLIC BASE HEAD | `61d16e0627d3f15fa3de60160a9a1f0d3fe6e441` |
| BRANCH | `fix/1.1.2-recovery-ui-sync-chg023` |

## Start

```powershell
# 1) Seed
cd D:\Dstorylens-wt-hotfix-1.1.2-integration\apps\api
$env:STORYLENS_MG_ROOT = Join-Path $env:TEMP "storylens-mg-chg023"
$env:STORYLENS_MG_API_URL = "http://127.0.0.1:18057"
$env:STORYLENS_MG_FE_URL = "http://127.0.0.1:1436"
$env:PYTHONPATH = (Get-Location).Path
..\..\.venv\Scripts\python.exe scripts_seed_chg023_mg.py

# 2) API
$db = Join-Path $env:STORYLENS_MG_ROOT "storylens.db"
$env:STORYLENS_DATABASE_URL = "sqlite:///$($db -replace '\\','/')"
$env:STORYLENS_PROVIDER = "fake"
$env:STORYLENS_ALLOW_FAKE_PROVIDER = "1"
$env:STORYLENS_DISABLE_INSTANCE_LOCK = "1"
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 18057 --ws none

# 3) Frontend
cd ..\desktop
$env:VITE_API_BASE_URL = "http://127.0.0.1:18057"
npx vite --host 127.0.0.1 --port 1436
```

## Direct URLs

**SUCCEEDED FIXTURE URL（Fixture A）**  
http://127.0.0.1:1436/books/1?chapter=1&analysisRun=1&journeyRun=1&view=result&tab=reader-journey  

预期：显示最终阅读旅程结果；不显示「阅读旅程已中断」；不显示「继续分析」。

**RECOVERABLE FIXTURE URL（Fixture B）**  
http://127.0.0.1:1436/books/2?chapter=2&analysisRun=2&journeyRun=2&view=progress&tab=reader-journey  

预期：阅读旅程已中断；点击一次「继续分析」→ 仅 `POST /reader-journey-runs/2/resume`（无 `/analysis-runs/*/recover`）；恢复卡立即消失；显示「正在恢复阅读旅程」；最终自动显示结果；不新建 Analysis/Journey Run。

Fixtures JSON: `release/evidence/hotfix/1.1.2/CHG-20260731-023/MANUAL_FIXTURES.json`
