# CHG-20260730-017 Manual UI Environment

## Live MG stack (this machine)

| Item | Value |
|------|-------|
| DATABASE | `%TEMP%\storylens-mg-chg017\storylens.db` (`sqlite:///C:/Users/msi/AppData/Local/Temp/storylens-mg-chg017/storylens.db`) |
| API URL | http://127.0.0.1:18080 |
| FRONTEND URL | http://127.0.0.1:1420 |
| Health | `GET /health` → ok (temp DB) |
| Provider | Fake / no formal AppData writes |
| Formal DB writes | 0 |

## Start commands used

```powershell
$mgRoot = Join-Path $env:TEMP "storylens-mg-chg017"
$db = Join-Path $mgRoot "storylens.db"
$env:STORYLENS_DATABASE_URL = "sqlite:///$($db -replace '\\','/')"
$env:STORYLENS_PROVIDER = "fake"
$env:STORYLENS_ALLOW_FAKE_PROVIDER = "1"
cd apps/api
D:\Dstorylens\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 18080 --ws none

cd apps/desktop
npx vite --host 127.0.0.1 --port 1420
```

## Acceptance steps
1. Import/start chapter analysis → confirm scenes → enter Scene Analysis with progress `< N/N`
2. Top nav: 正文阅读 · 查看分析进度 · 更多 — **no** 阅读旅程 / 确认场景 / 场景分析 / 查看分析结果
3. Open Journey deep link with `tab=reader-journey` → redirects to progress
4. After Scene `N/N` and journey starting → 阅读旅程 appears

## Chapter URLs
Fill after creating fixture chapter in this temp DB:

- SCENE ANALYSIS URL: http://127.0.0.1:1420/books/{bookId}?chapter={chapterId}&analysisRun={runId}&view=progress
- JOURNEY STARTING URL: same shell after Scene N/N (`journey_starting` / `journey_running`)
