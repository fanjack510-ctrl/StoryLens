# CHG-20260802-036 — WB-2.1 Integration Manual UI Environment

## Runtime slots

| Item | Value |
| --- | --- |
| UI | `http://127.0.0.1:1425` |
| API | `http://127.0.0.1:8005` |
| Database | `C:\Users\msi\AppData\Local\Temp\storylens-wb21-integration\wb21_integration.db` |
| Fixtures | `%TEMP%\storylens-wb21-integration\MANUAL_FIXTURES.json` |
| Real provider | **disabled** |
| Formal AppData DB | **not used** |
| External network | **none** (smoke-fake / fixture pipeline only) |

## Launch (test-only)

```powershell
cd D:\Dstorylens-wt-1.2.0-after-1.1.2
$env:PYTHONPATH = "D:\Dstorylens-private-wt-1.2.0-after-1.1.2\src;apps\api"
D:\Dstorylens\.venv\Scripts\python.exe apps\api\scripts_seed_wb21_integration.py
D:\Dstorylens\.venv\Scripts\python.exe release\evidence\whole-book\CHG-20260802-036\launch_wb21_integration_api.py

cd apps\desktop
$env:VITE_API_BASE_URL = "http://127.0.0.1:8005"
$env:VITE_WHOLE_BOOK_FREE_PRODUCT_ENABLED = "true"
npx vite --host 127.0.0.1 --port 1425 --strictPort
```

**READY rule:** catalog entries in `MANUAL_FIXTURES.json` are required — do not infer READY from DB alone.

## Entry catalog (seeded 2026-08-02)

| Kind | Book title | book_id | run_id | status | URL | Expected display |
| --- | --- | --- | --- | --- | --- | --- |
| structure_available | WB21 A Multi-Stage Available | 1 | 1 | completed | http://127.0.0.1:1425/books/1/whole-book?module=structure&run=1 | data-state=available; stages≥2 |
| non_three_act | WB21 B Non-Three-Act | 2 | 2 | completed | http://127.0.0.1:1425/books/2/whole-book?module=structure&run=2 | 4 stages; not forced 3-act |
| turning_points_empty | WB21 C Turning Points Empty | 3 | 3 | completed | http://127.0.0.1:1425/books/3/whole-book?module=structure&run=3 | stages OK; turning_points=[] message |
| insufficient | WB21 D Insufficient Coverage | 4 | 4 | completed | http://127.0.0.1:1425/books/4/whole-book?module=structure&run=4 | data-state=insufficient |
| failed | WB21 E Structure Failed | 5 | 5 | failed | http://127.0.0.1:1425/books/5/whole-book?module=structure&run=5 | data-state=failed |
| canceled | WB21 F Canceled | 6 | 6 | cancelled | http://127.0.0.1:1425/books/6/whole-book?module=structure&run=6 | data-state=canceled |
| conflict | WB21 G Structure Conflict | 7 | 7 | completed | http://127.0.0.1:1425/books/7/whole-book?module=structure&run=7 | data-state=conflict |
| evidence | WB21 H Evidence Deep Link | 8 | 8 | completed | http://127.0.0.1:1425/books/8/whole-book?module=structure&run=8 | evidence buttons; stay on structure |
| structure_absent | WB21 I Structure Absent | 9 | — | not_started | http://127.0.0.1:1425/books/9/whole-book?module=structure | data-state=not_started/absent |
| cost_consent | WB21 J Cost Consent | 10 | — | not_started | http://127.0.0.1:1425/books/10/whole-book | prepare + consent |

Also on available run: 全书总览 / 主要人物与关键事件 modules.

V1.1.2 scene/journey regressions: CHG-029 smoke DB (`scripts_seed_chg029_smoke_v2.py`, ports 1423/8003).

## Browser DOM verified (automated)

See `DOM_VERIFY_RESULTS.json` — page_ok_all=true; purchase_ui ABSENT; structure data-states matched catalog.
