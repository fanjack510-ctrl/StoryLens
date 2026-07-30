# CHG-20260730-017 Manual UI Environment

## Live stack

| Item | Value |
|------|-------|
| DATABASE | `C:\Users\msi\AppData\Local\Temp\storylens-mg-chg017\storylens.db` |
| API URL | http://127.0.0.1:18080 |
| FRONTEND URL | http://127.0.0.1:1420 |
| Provider | Fake |
| REAL PROVIDER CALLS | 0 |
| FORMAL DATABASE WRITES | 0 |

## Start

```powershell
cd apps/api
$env:PYTHONPATH = (Get-Location).Path
D:\Dstorylens\.venv\Scripts\python.exe scripts_seed_chg017_mg.py

$mgRoot = Join-Path $env:TEMP "storylens-mg-chg017"
$db = Join-Path $mgRoot "storylens.db"
$env:STORYLENS_DATABASE_URL = "sqlite:///$($db -replace '\\','/')"
$env:STORYLENS_PROVIDER = "fake"
$env:STORYLENS_ALLOW_FAKE_PROVIDER = "1"
D:\Dstorylens\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 18080 --ws none

# Post-start patch: restore Fixture A scene_analysis_running; keep Fixture C journey starting
D:\Dstorylens\.venv\Scripts\python.exe -c "import sqlite3; db=r'$db'; c=sqlite3.connect(db); c.execute(\"update analysis_runs set status='scene_analysis_running', error_code=null, error_message=null, failed_stage=null, completed_at=null, progress_current=1, progress_total=3 where id=1\"); c.execute(\"update reader_journey_runs set status='starting', current_stage='starting', root_error_code='WAITING_SCENE_ANALYSIS', root_error_message='waiting scene analysis', retryable=1, failure_details_json='{}', completed_at=null where id=1\"); c.execute(\"update analysis_runs set status='succeeded', progress_current=3, progress_total=3 where id=3\"); c.execute(\"update reader_journey_runs set status='starting', current_stage='starting', root_error_code=null, root_error_message=null, retryable=0, failure_details_json='{}', completed_at=null where analysis_run_id=3\"); c.commit()"

cd ../desktop
$env:VITE_API_BASE_URL = "http://127.0.0.1:18080"
npx vite --host 127.0.0.1 --port 1420
```

## Direct URLs

**SCENE ANALYSIS RUNNING URL**
http://127.0.0.1:1420/books/1?chapter=1&analysisRun=1&view=progress

Journey deep link (expect redirect to progress):
http://127.0.0.1:1420/books/1?chapter=1&analysisRun=1&view=result&tab=reader-journey&journeyRun=1

**AWAITING CONFIRMATION URL**
http://127.0.0.1:1420/books/2?chapter=2&analysisRun=2&view=scene-boundary-review

Journey deep link (expect redirect to confirm):
http://127.0.0.1:1420/books/2?chapter=2&analysisRun=2&view=result&tab=reader-journey

**JOURNEY RUNNING URL**
http://127.0.0.1:1420/books/3?chapter=3&analysisRun=3&view=progress&journeyRun=2

**JOURNEY SUCCEEDED PROGRESS URL** (Fixture D)
http://127.0.0.1:1420/books/4?chapter=4&analysisRun=4&view=progress&journeyRun=3

Expect: 「阅读旅程已生成」; toolbar 「阅读旅程」green primary; 「查看分析进度」secondary; panel CTA 「查看阅读旅程」.

**JOURNEY SUCCEEDED RESULT URL** (Fixture D)
http://127.0.0.1:1420/books/4?chapter=4&analysisRun=4&view=result&tab=reader-journey&journeyRun=3

Expect: 「阅读旅程」green selected; 「查看分析进度」secondary; no dual green primary in toolbar.

Fixtures: `MANUAL_FIXTURES.json`

## Manual gate note

MG-017 Completed Journey CTA amendment is ready for acceptance.
Do **not** mark CHG-017 `verified` until MG PASS.
Do **not** build RC.5 / create CHG-019 from this gate.
