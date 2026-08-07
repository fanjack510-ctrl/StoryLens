#!/usr/bin/env python3
"""CHG-20260807-053 minimal Bailian smoke (authorized L3).

Does not print API keys, prompts, or full responses.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[3]
if len(sys.argv) > 1 and sys.argv[1] == "--root":
    ROOT = Path(sys.argv[2])
sys.path.insert(0, str(ROOT / "apps" / "api"))
PRIVATE = Path(r"D:\Dstorylens-private-wt-1.2.0-after-1.1.2\src")
if PRIVATE.is_dir():
    sys.path.insert(0, str(PRIVATE))

PROVIDER = "aliyun_qwen_plus"
MODEL_DEFAULT = "qwen3.7-plus"


class MinimalResult(BaseModel):
    status: str


async def main() -> int:
    l3 = Path(os.environ.get("STORYLENS_L3_DIR", r"C:\Users\msi\AppData\Local\Temp\storylens-v120-l3-provider"))
    l3.mkdir(parents=True, exist_ok=True)
    db = l3 / "storylens_l3_smoke.db"
    if db.exists():
        db.unlink()
    os.environ["STORYLENS_DATABASE_URL"] = "sqlite:///" + db.as_posix()
    os.environ.setdefault("STORYLENS_APP_ENV", "development")
    os.environ["STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED"] = "true"
    os.environ["STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED"] = "true"
    os.environ["STORYLENS_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED"] = "false"
    os.environ["STORYLENS_RUN_ALIYUN_TESTS"] = "1"

    from app.db.session import SessionLocal, create_db
    from app.db.models import ProviderConfiguration
    from app.model_gateway.base import ModelRequest
    from app.model_gateway.registry import get_model_gateway
    from app.services.credentials.keyring_store import KeyringCredentialStore
    from app.services.provider_bootstrap import ensure_aliyun_provider_configuration
    from app.services.structured_output import extract_json_object
    from app.narrative_core.services.whole_book_foundation_errors import WholeBookFoundationError
    from app.narrative_core.services.whole_book_free_product_v1_service import (
        create_free_whole_book_analysis_v1,
    )
    from app.narrative_core.services.whole_book_minimal_helpers_v1 import real_provider_enabled
    from sqlalchemy import select

    store = KeyringCredentialStore()
    key = store.get(PROVIDER) or os.environ.get("STORYLENS_ALIYUN_API_KEY", "").strip()
    api_key_configured = bool(key and len(key) > 8)
    print(f"API_KEY_CONFIGURED: {'YES' if api_key_configured else 'NO'}")
    if not api_key_configured:
        print("REAL_PROVIDER_SMOKE: FAIL")
        print("ERROR: authentication — API key missing (keyring/env)")
        return 2

    # Bind into process settings for gateway without echoing key
    os.environ["STORYLENS_ALIYUN_ENABLED"] = "true"
    os.environ["STORYLENS_ALIYUN_API_KEY"] = key
    os.environ.setdefault("STORYLENS_DEFAULT_MODEL_PROVIDER", PROVIDER)

    create_db()
    with SessionLocal() as session:
        ensure_aliyun_provider_configuration(session, PROVIDER, create_if_missing=True)
        row = session.scalar(
            select(ProviderConfiguration).where(ProviderConfiguration.provider_name == PROVIDER)
        )
        assert row is not None
        row.enabled = True
        row.disconnected = False
        row.credential_reference = f"keyring:{PROVIDER}"
        session.commit()
        model = row.plus_model or MODEL_DEFAULT
        print(f"PROVIDER: {PROVIDER}")
        print(f"MODEL: {model}")
        print(f"PROVIDER_ENABLED: YES")
        print(f"ENDPOINT: configured_or_default")

    gateway = get_model_gateway()
    started = time.perf_counter()
    try:
        response = await gateway.generate(
            PROVIDER,
            ModelRequest(
                messages=[
                    {
                        "role": "user",
                        "content": 'Return exactly {"status":"ok"} as JSON object.',
                    }
                ],
                temperature=0,
                max_output_tokens=32,
                response_schema=MinimalResult.model_json_schema(),
                response_format_mode="json_object",
                enable_thinking=False,
            ),
        )
        parsed = MinimalResult.model_validate_json(extract_json_object(response.text))
        latency_ms = int((time.perf_counter() - started) * 1000)
        print(
            "SMOKE_META:",
            json.dumps(
                {
                    "ok": True,
                    "http_status": response.http_status_code,
                    "response_model": response.model,
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                    "latency_ms": latency_ms,
                    "parsed_status": parsed.status,
                },
                ensure_ascii=False,
            ),
        )
        print("REAL_PROVIDER_SMOKE: PASS")
        smoke_ok = True
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
        # redact accidental key fragments
        if key and key in err:
            err = err.replace(key, "***")
        print(
            "SMOKE_META:",
            json.dumps(
                {
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "error": err[:240],
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                },
                ensure_ascii=False,
            ),
        )
        print("REAL_PROVIDER_SMOKE: FAIL")
        smoke_ok = False

    print(f"REAL_PROVIDER_FLAG: {real_provider_enabled()}")
    with SessionLocal() as session:
        try:
            create_free_whole_book_analysis_v1(
                session,
                book_id=1,
                estimate_id=1,
                consent_id=1,
                client_request_id="l3-probe",
            )
            print("FREE_CREATE: UNEXPECTED_SUCCESS")
            free_blocked = False
        except WholeBookFoundationError as exc:
            print(f"FREE_CREATE_ERROR_CODE: {exc.code}")
            print("FREE_CREATE_BLOCKED: YES")
            free_blocked = True
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if key and key in msg:
                msg = msg.replace(key, "***")
            print(f"FREE_CREATE_OTHER: {type(exc).__name__}: {msg[:160]}")
            free_blocked = True

    print(f"FREE_REAL_PATH_OPEN: {'NO' if free_blocked else 'YES'}")
    return 0 if smoke_ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
