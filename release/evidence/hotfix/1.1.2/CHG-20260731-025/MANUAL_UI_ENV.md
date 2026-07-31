# CHG-20260731-025 Manual UI Environment

## Mode

Source build preview only — **no new RC installer**.

## Services (kept running)

| Role | URL / Path | Notes |
|------|------------|-------|
| Frontend preview | http://127.0.0.1:1480 | `vite preview` of desktop `dist` built with fix |
| API | http://127.0.0.1:18057 | source uvicorn, isolated DATA_DIR |
| Database | `%TEMP%\storylens-chg025-right-rail-cta\data\database\storylens.db` | succeeded Journey + Result |

## MANUAL URL

http://127.0.0.1:1480/books/1?chapter=1&analysisRun=1&journeyRun=1&view=progress

Expected:

- Right-rail success card「查看阅读旅程」
- Top nav「阅读旅程」
- Journey status=succeeded, result exists

## Acceptance steps

1. Open MANUAL URL
2. Click right-rail「查看阅读旅程」once → result view
3. Click「查看分析进度」secondary to return
4. Click top「阅读旅程」→ same Journey Result
5. Refresh → result still OK

## Formal isolation

Formal DB fingerprint before: see `formal_db_before.sha256`  
No formal install overwrite. No new RC.
