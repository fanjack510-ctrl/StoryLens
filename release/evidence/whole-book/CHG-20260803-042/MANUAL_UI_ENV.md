# MANUAL_UI_ENV — CHG-20260803-042

| Item | Value |
|---|---|
| UI | http://127.0.0.1:1426 |
| API | http://127.0.0.1:8006 |
| Database | C:\Users\msi\AppData\Local\Temp\storylens-wb22-integration\wb22_integration.db |
| Fixtures | %TEMP%\storylens-wb22-integration\MANUAL_FIXTURES.json |
| Real provider | disabled |
| Formal AppData DB | not used |

## Launch
```powershell
cd D:\Dstorylens-wt-1.2.0-after-1.1.2
$env:PYTHONPATH = "D:\Dstorylens-private-wt-1.2.0-after-1.1.2\src;apps\api"
D:\Dstorylens\.venv\Scripts\python.exe apps\api\scripts_seed_wb22_integration.py
D:\Dstorylens\.venv\Scripts\python.exe release\evidence\whole-book\CHG-20260803-042\launch_wb22_integration_api.py

cd apps\desktop
$env:VITE_API_BASE_URL = "http://127.0.0.1:8006"
$env:VITE_WHOLE_BOOK_FREE_PRODUCT_ENABLED = "true"
npx vite --host 127.0.0.1 --port 1426 --strictPort
```

READY requires catalog URLs + DOM verify — not DB alone.
Browser DOM verified: DOM_VERIFY_RESULTS.json page_ok_all=true; purchase_ui ABSENT.
