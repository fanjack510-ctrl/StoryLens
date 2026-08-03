# -*- coding: utf-8 -*-
"""TEST-ONLY API launcher for CHG-20260803-048 V1.2.0 E2E smoke. Not product code.

- Binds 127.0.0.1:8007 only
- Uses storylens_v120_e2e.db (isolated temp DB)
- Real provider OFF; smoke-fake ON (no external network)
- Formal AppData DB not used
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SMOKE_ROOT = Path(
    os.environ.get(
        "STORYLENS_V120_E2E_SMOKE_ROOT",
        Path(os.environ["TEMP"]) / "storylens-v120-e2e",
    )
)
DB = SMOKE_ROOT / "storylens_v120_e2e.db"
if not DB.is_file():
    alt = SMOKE_ROOT / "wb22_integration.db"
    if alt.is_file():
        DB = alt
FIXTURES = SMOKE_ROOT / "MANUAL_FIXTURES.json"
PORT = int(os.environ.get("STORYLENS_V120_E2E_API_PORT", "8007"))
FE_PORT = int(os.environ.get("STORYLENS_V120_E2E_FE_PORT", "1427"))
PUBLIC_ROOT = Path(
    os.environ.get("STORYLENS_V120_E2E_PUBLIC_ROOT", r"D:\Dstorylens-wt-1.2.0-after-1.1.2")
)
PRIVATE_ENGINE_SRC = Path(
    os.environ.get(
        "STORYLENS_PRIVATE_ENGINE_SRC",
        r"D:\Dstorylens-private-wt-1.2.0-after-1.1.2\src",
    )
)

if not DB.is_file():
    raise SystemExit(f"Smoke DB missing: {DB}")

if PRIVATE_ENGINE_SRC.is_dir():
    sys.path.insert(0, str(PRIVATE_ENGINE_SRC))

os.environ["STORYLENS_DATABASE_URL"] = "sqlite:///" + DB.as_posix()
os.environ["STORYLENS_APP_ENV"] = "development"
os.environ["STORYLENS_APP_HOST"] = "127.0.0.1"
os.environ["STORYLENS_APP_PORT"] = str(PORT)
os.environ["STORYLENS_PROVIDER"] = "aliyun_qwen_plus"
os.environ["STORYLENS_REAL_PROVIDER_ENABLED"] = "0"
os.environ["STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED"] = "false"
os.environ["STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED"] = "true"
os.environ["STORYLENS_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED"] = "true"
os.environ["STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE"] = "1"
os.environ["STORYLENS_JOURNEY_FAKE_MODE"] = "success"
os.environ["STORYLENS_ALLOWED_ORIGINS"] = f"http://127.0.0.1:{FE_PORT}"
os.environ["STORYLENS_DISABLE_INSTANCE_LOCK"] = "1"
os.environ.pop("STORYLENS_WEB_PORT", None)
os.environ.pop("STORYLENS_SETTINGS_CACHE", None)
os.environ.pop("STORYLENS_ALLOW_FAKE_PROVIDER", None)

api_root = PUBLIC_ROOT / "apps" / "api"
sys.path.insert(0, str(api_root))
os.chdir(api_root)

import uvicorn  # noqa: E402

if __name__ == "__main__":
    print(
        f"V120_E2E_SMOKE api=http://127.0.0.1:{PORT} db={DB} fixtures={FIXTURES.is_file()}",
        flush=True,
    )
    uvicorn.run("app.main:app", host="127.0.0.1", port=PORT, log_level="info", ws="none")
