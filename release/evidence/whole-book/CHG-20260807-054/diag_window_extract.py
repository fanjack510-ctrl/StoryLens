#!/usr/bin/env python3
"""Quick diag: formal window extraction after adapter."""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import select

L3 = Path(r"C:\Users\msi\AppData\Local\Temp\storylens-v120-l3-provider-fix")
db = L3 / "diag_window3.db"
if db.exists():
    db.unlink()
os.environ["STORYLENS_DATABASE_URL"] = "sqlite:///" + db.as_posix()
os.environ["STORYLENS_APP_ENV"] = "development"
os.environ["STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED"] = "true"
os.environ["STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED"] = "true"
os.environ["STORYLENS_ALIYUN_ENABLED"] = "true"
os.environ["STORYLENS_DEFAULT_MODEL_PROVIDER"] = "aliyun_qwen_plus"

from app.db.models import (  # noqa: E402
    ApplicationSetting,
    ProviderConfiguration,
    WholeBookProviderAttempt,
    WholeBookProviderUnit,
    WholeBookWindowAnalysisResult,
)
from app.db.session import SessionLocal, create_db  # noqa: E402
from app.narrative_core.contracts.whole_book_contract_v1 import ResultOrigin, WholeBookMode  # noqa: E402
from app.narrative_core.services.whole_book_consent_service import create_whole_book_consent  # noqa: E402
from app.narrative_core.services.whole_book_cost_estimate_service import (  # noqa: E402
    estimate_whole_book_analysis,
)
from app.narrative_core.services.whole_book_minimal_extraction_v1_service import (  # noqa: E402
    execute_minimal_entity_event_extraction_v1,
)
from app.narrative_core.services.whole_book_minimal_pipeline_v1_service import (  # noqa: E402
    build_formal_gateway_transports,
)
from app.narrative_core.services.whole_book_native_input_audit_v1 import (  # noqa: E402
    assert_native_input_independence_v1,
    persist_native_input_audit_v1,
)
from app.narrative_core.services.whole_book_run_v1_service import (  # noqa: E402
    create_whole_book_run_v1,
    start_whole_book_run_v1,
)
from app.narrative_core.services.whole_book_snapshot_v1_service import (  # noqa: E402
    create_or_reuse_book_snapshot_v1,
)
from app.narrative_core.services.whole_book_windowing_v1_service import (  # noqa: E402
    generate_whole_book_windows_v1,
)
from app.services.book_service import import_book  # noqa: E402
from app.services.credentials.keyring_store import KeyringCredentialStore  # noqa: E402
from app.services.provider_bootstrap import ensure_aliyun_provider_configuration  # noqa: E402

sample = (L3 / "diag_2ch.txt").read_text(encoding="utf-8")
store = KeyringCredentialStore()
os.environ["STORYLENS_ALIYUN_API_KEY"] = store.get("aliyun_qwen_plus") or ""
create_db()
with SessionLocal() as session:
    ensure_aliyun_provider_configuration(session, "aliyun_qwen_plus", create_if_missing=True)
    row = session.scalar(
        select(ProviderConfiguration).where(ProviderConfiguration.provider_name == "aliyun_qwen_plus")
    )
    assert row is not None
    row.enabled = True
    row.disconnected = False
    row.plus_model = "qwen3.7-plus"
    row.credential_reference = "keyring:aliyun_qwen_plus"
    if session.get(ApplicationSetting, "cloud_enabled") is None:
        session.add(ApplicationSetting(key="cloud_enabled", value_json="true"))
    session.commit()
    book = import_book(session, "diag_2ch_c.txt", sample.encode("utf-8"))
    snap = create_or_reuse_book_snapshot_v1(session, book.id)["snapshot"]
    est = estimate_whole_book_analysis(session, book.id, "whole_book_native", row.id)
    est.pricing_status = "unavailable"
    session.flush()
    consent = create_whole_book_consent(
        session,
        book_id=book.id,
        estimate_id=est.id,
        user_budget_limit_cny="50",
        max_provider_calls=20,
        max_input_tokens=200000,
        max_output_tokens=100000,
    )
    run = create_whole_book_run_v1(
        session,
        book.id,
        snap.id,
        WholeBookMode.whole_book_native.value,
        "d3",
        ResultOrigin.formal.value,
    )
    run.consent_id = consent.id
    session.flush()
    persist_native_input_audit_v1(session, assert_native_input_independence_v1(session, run.id))
    generate_whole_book_windows_v1(session, run.id)
    start_whole_book_run_v1(session, run.id)
    session.commit()
    transports = build_formal_gateway_transports(session)
    extraction = execute_minimal_entity_event_extraction_v1(
        session, run.id, transport=transports.window
    )
    session.commit()
    print("extraction", extraction)
    results = list(
        session.scalars(
            select(WholeBookWindowAnalysisResult).where(WholeBookWindowAnalysisResult.run_id == run.id)
        )
    )
    print("results", [(r.window_id, r.validation_status) for r in results])
    attempts = list(
        session.scalars(
            select(WholeBookProviderAttempt)
            .join(WholeBookProviderUnit)
            .where(WholeBookProviderUnit.run_id == run.id)
        )
    )
    for a in attempts:
        print(
            "attempt",
            a.status,
            a.error_code,
            a.input_tokens,
            a.output_tokens,
            (a.error_message_safe or "")[:240],
        )
