# CHG-20260730-017 Manual UI Environment

## Constraints
- Fake Provider only
- Temp / isolated DB only (no formal AppData writes)
- Do not build RC / push / tag / release

## Suggested local start (operator)

```powershell
$env:STORYLENS_DATABASE_URL = "sqlite:///$env:TEMP/storylens-mg-chg017/storylens.db"
$env:STORYLENS_PROVIDER = "fake"
# API (example port)
D:\Dstorylens\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 18080
# Desktop
cd apps/desktop; npm run dev -- --port 1420
```

## Fixture intent
1. Confirm scenes → enter Scene Analysis with progress `< N/N`
2. Assert top nav: 正文阅读 · 查看分析进度 · 更多 — no 阅读旅程
3. Open old Journey URL → redirects to progress
4. Wait until Scene N/N and journey starting → 阅读旅程 appears

## URLs (fill after start)
- API: http://127.0.0.1:18080
- Frontend: http://127.0.0.1:1420
- Scene analysis chapter: (operator)
- Journey starting chapter: (operator)
