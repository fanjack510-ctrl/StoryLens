# MANUAL_UI_ENV — CHG-20260803-048

## Endpoints
| Item | Value |
|---|---|
| UI | http://127.0.0.1:1427 |
| API | http://127.0.0.1:8007 |
| Database | `C:\Users\msi\AppData\Local\Temp\storylens-v120-e2e\storylens_v120_e2e.db` |
| Fixtures | `%TEMP%\storylens-v120-e2e\MANUAL_FIXTURES.json` |
| `VITE_WHOLE_BOOK_FREE_PRODUCT_ENABLED` | `true` |
| Real provider | **disabled** |
| Formal AppData DB | **not used** |
| Browser DOM verified | **YES** (`DOM_VERIFY_RESULTS.json`, `page_ok_all=true`) |

## Launch
```powershell
cd D:\Dstorylens-wt-1.2.0-after-1.1.2
$env:STORYLENS_WB22_SMOKE_ROOT = "$env:TEMP\storylens-wb22-integration-v120-e2e"
D:\Dstorylens\.venv\Scripts\python.exe apps\api\scripts_seed_wb22_integration.py
# Checkpoint WAL into isolated smoke DB (do not copy .db alone):
D:\Dstorylens\.venv\Scripts\python.exe -c "import sqlite3,json; from pathlib import Path; src=Path(r'$env:TEMP')/'storylens-wb22-integration-v120-e2e'/'wb22_integration.db'; dst=Path(r'$env:TEMP')/'storylens-v120-e2e'; dst.mkdir(exist_ok=True); db=dst/'storylens_v120_e2e.db'; s=sqlite3.connect(str(src)); d=sqlite3.connect(str(db)); s.backup(d); d.close(); s.close()"

$env:PYTHONPATH = "D:\Dstorylens-private-wt-1.2.0-after-1.1.2\src;apps\api"
D:\Dstorylens\.venv\Scripts\python.exe release\evidence\whole-book\CHG-20260803-048\launch_v120_e2e_api.py

cd apps\desktop
$env:VITE_API_BASE_URL = "http://127.0.0.1:8007"
$env:VITE_WHOLE_BOOK_FREE_PRODUCT_ENABLED = "true"
npx vite --host 127.0.0.1 --port 1427 --strictPort
```

## Helpers
- API launcher: `release/evidence/whole-book/CHG-20260803-048/launch_v120_e2e_api.py`
- DOM verify: `release/evidence/whole-book/CHG-20260803-048/dom_verify_v120_e2e.mjs`

READY requires catalog URLs + DOM verify — not DB alone.
