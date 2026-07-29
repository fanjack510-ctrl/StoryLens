# MANUAL_UI_ENV — CHG-20260729-011

## Status

Ready for MG-CHG-20260729-011 MANUAL UI ACCEPTANCE

## Isolated runtime

| Item | Value |
|------|--------|
| Worktree | `D:\Dstorylens-wt-hotfix-1.1.2-chapter-workflow-consistency` |
| Branch | `fix/1.1.2-chapter-workflow-consistency` |
| Start HEAD | `e59da1238eb2c509b4a05d7a401a6b5a1b2002ee` |
| Data dir | `%TEMP%\storylens-mg-chg011-workflow-consistency` |
| DATABASE | `%TEMP%\storylens-mg-chg011-workflow-consistency\database\storylens-mg-chg011.db` |
| API | `http://127.0.0.1:18047` |
| FRONTEND | `http://127.0.0.1:1426` |
| TASK CENTER | `http://127.0.0.1:1426/tasks` |

## Case URLs

| Case | URL |
|------|-----|
| REVISION 22-TO-6 | http://127.0.0.1:1426/books/1?chapter=1&analysisRun=2&view=result |
| INTERRUPTED | http://127.0.0.1:1426/books/1?chapter=2&analysisRun=3&journeyRun=2 |
| AWAITING CONFIRMATION | http://127.0.0.1:1426/books/1?chapter=3&analysisRun=4&view=scene-boundary-review |
| RUNNING | http://127.0.0.1:1426/books/1?chapter=4&analysisRun=5&journeyRun=3 |
| SUCCEEDED | http://127.0.0.1:1426/books/1?chapter=5&analysisRun=6&journeyRun=4&view=result |
| HOOK EMPTY | http://127.0.0.1:1426/books/1?chapter=5&journeyRun=4&lens=hook_payoff |
| HOOK RICH | vitest only — see FIXTURES.md Fixture D |

## Suggested start (PowerShell)

```powershell
# From repo root
$Evidence = "release\evidence\hotfix\1.1.2\CHG-20260729-011"
$env:PYTHONPATH = "apps\api"
python $Evidence\seed_mg_chg011_fixtures.py

$DataDir = "$env:TEMP\storylens-mg-chg011-workflow-consistency"
$Db = "$DataDir\database\storylens-mg-chg011.db"
$env:STORYLENS_DATABASE_URL = "sqlite:///" + ($Db -replace "\\", "/")
$env:STORYLENS_DATA_DIR = $DataDir
$env:STORYLENS_APP_PORT = "18047"
$env:STORYLENS_REAL_PROVIDER_ENABLED = "0"
$env:STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE = "1"
$env:STORYLENS_JOURNEY_FAKE_MODE = "success"
$env:STORYLENS_ALLOWED_ORIGINS = "http://127.0.0.1:1426"

# API (new terminal)
Set-Location apps\api
python -m uvicorn app.main:app --host 127.0.0.1 --port 18047

# After API boot — restore interrupted/running fixtures
python $Evidence\refresh_mg_after_api_boot.py

# Frontend (new terminal)
$env:VITE_API_BASE_URL = "http://127.0.0.1:18047"
Set-Location apps\desktop
npx vite --host 127.0.0.1 --port 1426 --strictPort
```

Or one-shot: `powershell -File release\evidence\hotfix\1.1.2\CHG-20260729-011\launch_mg_chg011.ps1`

## Fake / safety

- Real Provider OFF (`STORYLENS_REAL_PROVIDER_ENABLED=0`, Smoke Fake ON)
- FakeCredentialStore readiness via smoke-fake override (no Keyring / formal credentials)
- Formal AppData DB not used
- REAL PROVIDER CALLS: **0**

## Manual focus

1. **Fixture A:** Result/scene list shows **6** scenes, not 22; no duplicate S01 labels
2. **Fixture B:** Main area **阅读旅程已中断** (not “正在生成”); progress **1/6**; resume CTA available
3. **Fixture C:** Scene boundary review shows **17→6** draft; confirm starts new revision-bound journey
4. **Running:** Progress panel **2/6**, status running (not interrupted)
5. **Succeeded:** Unified presentation — view results, journey nav, no stale running banner
6. **Hook empty:** Hook lens shows uncertain/none copy (not failure); no raw smoke-fake strings
7. **Hook rich:** Validate via vitest Fixture B (no live URL)
8. Top nav: no ordinary「场景分析」tab; confirm/journey nav follows presentation stage

## Post-boot refresh

Sidecar startup recovery interrupts orphan `scene_profiles_running` rows. Run `refresh_mg_after_api_boot.py` once after each API restart before manual acceptance of Fixtures B and Running.
