# CHG-20260730-018 Manual UI Environment

## Live stack

| Item | Value |
|------|-------|
| DATABASE | `C:\Users\msi\AppData\Local\Temp\storylens-mg-chg018\storylens.db`（隔离；正式 AppData 写入 = 0） |
| API URL | http://127.0.0.1:18080 |
| FRONTEND URL | http://127.0.0.1:1420 |
| Provider | Fake |
| REAL PROVIDER CALLS | 0 |
| FORMAL DATABASE WRITES | 0 |

## Start

```powershell
# 1) Seed
cd apps/api
$env:PYTHONPATH = (Get-Location).Path
D:\Dstorylens\.venv\Scripts\python.exe scripts_seed_chg018_mg.py

# 2) API
$mgRoot = Join-Path $env:TEMP "storylens-mg-chg018"
$db = Join-Path $mgRoot "storylens.db"
$env:STORYLENS_DATABASE_URL = "sqlite:///$($db -replace '\\','/')"
$env:STORYLENS_PROVIDER = "fake"
$env:STORYLENS_ALLOW_FAKE_PROVIDER = "1"
D:\Dstorylens\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 18080 --ws none

# 3) Post-start patch（startup orphan recovery 会把无 worker 的 running Journey 标为 interrupted；MG Active 需在 API 启动后再写回 running）
D:\Dstorylens\.venv\Scripts\python.exe -c "import sqlite3; db=r'$db'; c=sqlite3.connect(db); c.execute(\"update reader_journey_runs set status='running', current_stage='running', root_error_code=null, root_error_message=null, retryable=0, failure_details_json='{}' where id=1\"); c.commit()"

# 4) Frontend（必须指向 18080）
cd ../desktop
$env:VITE_API_BASE_URL = "http://127.0.0.1:18080"
npx vite --host 127.0.0.1 --port 1420
```

## Direct URLs

**ACTIVE JOURNEY URL**  
http://127.0.0.1:1420/books/1?chapter=1&analysisRun=1&view=progress&journeyRun=1  

预期：正在生成阅读旅程；不显示「分析已暂停」；不显示「修复并继续」/「继续分析」；刷新后保持。

**REAL INTERRUPTED URL**  
http://127.0.0.1:1420/books/2?chapter=2&analysisRun=2&view=progress&journeyRun=2  

预期：阅读旅程已中断；显示继续分析；点击一次恢复后 Recovery Card 立即消失。

Fixtures JSON: `release/evidence/hotfix/1.1.2/CHG-20260730-018/MANUAL_FIXTURES.json`
