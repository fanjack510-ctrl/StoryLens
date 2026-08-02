# -*- coding: utf-8 -*-
"""TEST-ONLY API launcher for CHG-20260802-036 WB-2.1 integration smoke. Not product code.

- Binds 127.0.0.1:8005 only
- Uses wb21_integration.db (isolated temp DB)
- Real provider OFF; smoke-fake ON (no external network)
- Formal AppData DB not used

PYTHONPATH: if narrative private-engine imports fail, set STORYLENS_PRIVATE_ENGINE_SRC
(default D:\\Dstorylens-private-wt-1.2.0-after-1.1.2\\src) so launcher prepends that src tree.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SMOKE_ROOT = Path(
    os.environ.get(
        "STORYLENS_WB21_SMOKE_ROOT",
        Path(os.environ["TEMP"]) / "storylens-wb21-integration",
    )
)
DB = SMOKE_ROOT / "wb21_integration.db"
FIXTURES = SMOKE_ROOT / "MANUAL_FIXTURES.json"
PORT = int(os.environ.get("STORYLENS_WB21_API_PORT", "8005"))
FE_PORT = int(os.environ.get("STORYLENS_WB21_FE_PORT", "1425"))
PUBLIC_ROOT = Path(
    os.environ.get("STORYLENS_WB21_PUBLIC_ROOT", r"D:\Dstorylens-wt-1.2.0-after-1.1.2")
)
PRIVATE_ENGINE_SRC = Path(
    os.environ.get(
        "STORYLENS_PRIVATE_ENGINE_SRC",
        r"D:\Dstorylens-private-wt-1.2.0-after-1.1.2\src",
    )
)

if not DB.is_file():
    raise SystemExit(f"Smoke DB missing: {DB} — run apps/api/scripts_seed_wb21_integration.py first")

if PRIVATE_ENGINE_SRC.is_dir():
    sys.path.insert(0, str(PRIVATE_ENGINE_SRC))
else:
    print(
        f"WB21_SMOKE_WARN private_engine_src_missing path={PRIVATE_ENGINE_SRC} "
        "(set STORYLENS_PRIVATE_ENGINE_SRC if imports fail)",
        flush=True,
    )

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
    fixtures_note = str(FIXTURES) if FIXTURES.is_file() else "missing (seed not run?)"
    print(
        f"WB21_SMOKE_API port={PORT} db={DB} fixtures={fixtures_note} "
        f"smoke_fake=ON real_provider=OFF localhost-only",
        flush=True,
    )
    uvicorn.run("app.main:app", host="127.0.0.1", port=PORT, log_level="info", ws="none")
