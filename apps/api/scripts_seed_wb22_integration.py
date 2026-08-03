"""TEST-ONLY seed for CHG-20260803-042 WB-2.2 integration manual smoke.

Creates a fresh isolated SQLite with separate books for each chapter-functions
acceptance entry. Not packaged; not a product Fake Provider registration.
Catalog entries in MANUAL_FIXTURES.json are required — do not infer READY from DB alone.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

API_ROOT = Path(__file__).resolve().parent
REPO_ROOT = API_ROOT.parents[1]
sys.path.insert(0, str(API_ROOT))

SMOKE_DIR = Path(
    os.environ.get(
        "STORYLENS_WB22_SMOKE_ROOT",
        Path(os.environ["TEMP"]) / "storylens-wb22-integration",
    )
)
SMOKE_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = SMOKE_DIR / "wb22_integration.db"
if DB_PATH.exists():
    DB_PATH.unlink()
for suffix in ("-wal", "-shm"):
    side = Path(str(DB_PATH) + suffix)
    if side.exists():
        side.unlink()

os.environ["STORYLENS_DATABASE_URL"] = f"sqlite:///{DB_PATH.as_posix()}"
os.environ["STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED"] = "true"
os.environ["STORYLENS_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED"] = "true"
os.environ["STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED"] = "false"
os.environ.setdefault("STORYLENS_PROVIDER", "aliyun_qwen_plus")
os.environ.pop("STORYLENS_ALLOW_FAKE_PROVIDER", None)
os.environ.pop("STORYLENS_SETTINGS_CACHE", None)

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.db.models import (  # noqa: E402
    AnalysisConflict,
    ApplicationSetting,
    Book,
    Chapter,
    NarrativeAsset,
    NarrativeAssetVersion,
    Paragraph,
    ProviderConfiguration,
)
from app.db.session import create_db, get_session_factory  # noqa: E402
from app.narrative_core.services.fixture_window_analysis_sample_s import (  # noqa: E402
    SAMPLE_S_PARAGRAPH_TEXTS,
)
from app.narrative_core.services.whole_book_confirm_protection_v1_service import (  # noqa: E402
    confirm_narrative_asset_v1,
)
from app.narrative_core.services.whole_book_consent_service import (  # noqa: E402
    create_whole_book_consent,
)
from app.narrative_core.services.whole_book_cost_estimate_service import (  # noqa: E402
    estimate_whole_book_analysis,
)
from app.narrative_core.services.whole_book_chapter_functions_product_v1_service import (  # noqa: E402
    get_run_chapter_functions_product_v1,
    load_chapter_functions_checkpoint_envelope,
)
from app.narrative_core.services.whole_book_fixture_pipeline_v1_service import (  # noqa: E402
    execute_fixture_minimal_pipeline_v1,
)
from app.narrative_core.services.whole_book_minimal_chapter_functions_v1_service import (  # noqa: E402
    _persist_chapter_function_assets,
    synthesize_minimal_chapter_functions_v1,
)
from app.narrative_core.services.whole_book_minimal_extraction_v1_service import (  # noqa: E402
    FixtureWindowAnalysisTransport,
    execute_minimal_entity_event_extraction_v1,
)
from app.narrative_core.services.whole_book_minimal_helpers_v1 import (  # noqa: E402
    set_stage_completed,
)
from app.narrative_core.services.whole_book_minimal_materialization_v1_service import (  # noqa: E402
    materialize_minimal_narrative_assets_v1,
)
from app.narrative_core.services.whole_book_minimal_overview_v1_service import (  # noqa: E402
    synthesize_minimal_book_overview_v1,
)
from app.narrative_core.services.whole_book_run_v1_service import (  # noqa: E402
    create_whole_book_run_v1,
    get_run,
    start_whole_book_run_v1,
)
from app.narrative_core.services.whole_book_runtime_control_v1_service import (  # noqa: E402
    request_cancel_whole_book_run_v1,
)
from app.narrative_core.services.whole_book_snapshot_v1_service import (  # noqa: E402
    create_or_reuse_book_snapshot_v1,
)
from app.narrative_core.services.whole_book_structure_product_v1_service import (  # noqa: E402
    get_run_structure_product_v1,
)
from app.schemas.settings import CloudBudgetUpdate  # noqa: E402
from app.services.whole_book_source_fingerprint import sha256_utf8  # noqa: E402
from tests.whole_book_minimal_test_helpers import seed_three_windows  # noqa: E402

API_URL = os.environ.get("STORYLENS_WB22_API_URL", "http://127.0.0.1:8006")
FE_URL = os.environ.get("STORYLENS_WB22_FE_URL", "http://127.0.0.1:1426")


def _enable_cloud(session) -> None:
    session.merge(ApplicationSetting(key="cloud_enabled", value_json=json.dumps(True)))
    payload = CloudBudgetUpdate().model_dump()
    payload.update(
        {
            "daily_request_limit": 500,
            "daily_token_limit": 2_000_000,
            "daily_cost_limit": 50.0,
            "cloud_daily_request_limit": 500,
            "cloud_daily_token_limit": 2_000_000,
            "cloud_daily_estimated_cost_limit": 50.0,
        }
    )
    session.merge(ApplicationSetting(key="cloud_budget_settings", value_json=json.dumps(payload)))
    session.commit()


def _seed_sample_s_book(session, *, title: str, source_key: str) -> tuple[Book, int]:
    book = Book(
        title=title,
        source_file_name=f"{source_key}.txt",
        source_file_hash=sha256_utf8(source_key),
    )
    session.add(book)
    session.flush()
    chapters: list[Chapter] = []
    for idx in range(3):
        ch = Chapter(book_id=book.id, chapter_index=idx, title=f"第{idx + 1}章")
        session.add(ch)
        session.flush()
        chapters.append(ch)
    global_idx = 0
    for ch_idx, ch in enumerate(chapters):
        for para_idx, text in enumerate(SAMPLE_S_PARAGRAPH_TEXTS[ch_idx * 3 : ch_idx * 3 + 3]):
            session.add(
                Paragraph(
                    id=f"p-{source_key}-{global_idx}",
                    book_id=book.id,
                    chapter_id=ch.id,
                    paragraph_index=para_idx,
                    raw_text=text,
                    normalized_text=text,
                    char_start=0,
                    char_end=len(text),
                    content_hash=sha256_utf8(text),
                )
            )
            global_idx += 1
    session.flush()
    snap = create_or_reuse_book_snapshot_v1(session, book.id)["snapshot"]
    return book, snap.id


def _ensure_consent(session, book_id: int) -> int:
    provider = session.scalar(
        select(ProviderConfiguration).where(ProviderConfiguration.provider_name == "fixture")
    )
    if provider is None:
        provider = ProviderConfiguration(provider_name="fixture", plus_model="fixture-model")
        session.add(provider)
        session.flush()
    est = estimate_whole_book_analysis(session, book_id, "whole_book_native", provider.id)
    est.pricing_status = "unavailable"
    session.flush()
    consent = create_whole_book_consent(
        session,
        book_id=book_id,
        estimate_id=est.id,
        user_budget_limit_cny="1000",
        max_provider_calls=100,
        max_input_tokens=10_000_000,
        max_output_tokens=10_000_000,
        auto_retry_enabled=False,
        max_retries_per_unit=0,
    )
    return consent.id


def _prepare_sample_s_run(session, *, title: str, source_key: str) -> tuple[int, int]:
    book, snapshot_id = _seed_sample_s_book(session, title=title, source_key=source_key)
    run = create_whole_book_run_v1(
        session,
        book.id,
        snapshot_id,
        "whole_book_native",
        str(uuid.uuid4()),
        "fixture",
    )
    consent_id = _ensure_consent(session, book.id)
    run.consent_id = consent_id
    set_stage_completed(session, run.id, "windowing", progress_total=3)
    seed_three_windows(session, run.id, snapshot_id)
    session.flush()
    return run.id, book.id


def _wb_url(
    book_id: int,
    *,
    module: str | None = None,
    run_id: int | None = None,
    extra_qs: dict[str, str] | None = None,
) -> str:
    url = f"{FE_URL}/books/{book_id}/whole-book"
    params: list[str] = []
    if module:
        params.append(f"module={module}")
    if run_id is not None:
        params.append(f"run={run_id}")
    if extra_qs:
        for k, v in extra_qs.items():
            params.append(f"{k}={v}")
    if params:
        url += "?" + "&".join(params)
    return url


def _wb_entry(
    kind: str,
    book: Book,
    run_id: int | None,
    status: str,
    *,
    expected_initial: str,
    expected_display: str | None = None,
    module: str | None = None,
    seeded: bool = True,
    extra_qs: dict[str, str] | None = None,
    **extra,
) -> dict:
    return {
        "kind": kind,
        "book_title": book.title,
        "book_id": book.id,
        "whole_book_run_id": run_id,
        "status": status,
        "url": _wb_url(book.id, module=module, run_id=run_id, extra_qs=extra_qs),
        "expected_initial": expected_initial,
        "expected_display": expected_display or expected_initial,
        "result_origin": "fixture",
        "seeded": seeded,
        **extra,
    }


def _seed_pipeline_entry(
    session,
    *,
    kind: str,
    title: str,
    source_key: str,
    chapter_functions_mode: str,
    expected_initial: str,
    expected_display: str | None = None,
    module: str = "chapter_functions",
    structure_mode: str = "multi_stage",
    extra_qs: dict[str, str] | None = None,
    **extra,
) -> dict:
    run_id, book_id = _prepare_sample_s_run(session, title=title, source_key=source_key)
    result = execute_fixture_minimal_pipeline_v1(
        session,
        run_id,
        structure_mode=structure_mode,
        chapter_functions_mode=chapter_functions_mode,
    )
    session.commit()
    book = session.get(Book, book_id)
    assert book is not None
    run = get_run(session, run_id)
    cf_payload = get_run_chapter_functions_product_v1(session, run_id)
    product_status = None
    if cf_payload:
        product_status = cf_payload.get("product_result_status") or cf_payload.get("result_status")
    elif result.get("chapter_functions"):
        product_status = result["chapter_functions"].get("product_result_status") or result[
            "chapter_functions"
        ].get("result_status")
    return _wb_entry(
        kind,
        book,
        run_id,
        run.status,
        expected_initial=expected_initial,
        expected_display=expected_display,
        module=module,
        chapter_functions_mode=chapter_functions_mode,
        structure_mode=structure_mode,
        product_result_status=product_status,
        coverage_scope=cf_payload.get("coverage_scope") if cf_payload else None,
        total_chapters=cf_payload.get("total_chapters") if cf_payload else None,
        failure_code=cf_payload.get("failure_code") if cf_payload else result.get("chapter_functions", {}).get(
            "failure_code"
        ),
        extra_qs=extra_qs,
        **extra,
    )


def _seed_canceled(session) -> dict:
    run_id, book_id = _prepare_sample_s_run(
        session,
        title="WB22 F Canceled",
        source_key="wb22-canceled",
    )
    start_whole_book_run_v1(session, run_id)
    request_cancel_whole_book_run_v1(session, run_id)
    session.commit()
    book = session.get(Book, book_id)
    assert book is not None
    run = get_run(session, run_id)
    payload = get_run_chapter_functions_product_v1(session, run_id)
    return _wb_entry(
        "canceled",
        book,
        run_id,
        run.status,
        expected_initial="run cancelled; product result_status=canceled; chapter_functions view canceled",
        expected_display="data-state=canceled",
        module="chapter_functions",
        product_result_status=payload.get("result_status") if payload else "canceled",
    )


def _seed_conflict(session) -> dict:
    run_id, book_id = _prepare_sample_s_run(
        session,
        title="WB22 G Chapter Functions Conflict",
        source_key="wb22-conflict",
    )
    execute_fixture_minimal_pipeline_v1(session, run_id, chapter_functions_mode="available")
    session.commit()
    version = session.scalar(
        select(NarrativeAssetVersion)
        .join(NarrativeAsset, NarrativeAssetVersion.asset_id == NarrativeAsset.id)
        .where(
            NarrativeAsset.book_id == book_id,
            NarrativeAssetVersion.asset_type == "chapter_function",
            NarrativeAssetVersion.is_canonical.is_(True),
        )
    )
    assert version is not None
    confirm_narrative_asset_v1(session, version.asset_id)
    session.commit()
    envelope = load_chapter_functions_checkpoint_envelope(session, run_id)
    assert envelope is not None
    cf = dict(envelope["chapter_functions"])
    cf["chapters"] = [dict(c) for c in cf["chapters"]]
    cf["chapters"][0]["primary_function"] = "flashback"
    run = get_run(session, run_id)
    meta = _persist_chapter_function_assets(
        session,
        run_id=run_id,
        book_id=book_id,
        snapshot_id=int(run.snapshot_id),
        result=cf,
        catalog=None,
    )
    session.commit()
    conflicts = list(
        session.scalars(
            select(AnalysisConflict).where(
                AnalysisConflict.book_id == book_id,
                AnalysisConflict.status == "open",
            )
        ).all()
    )
    assert conflicts and meta["conflicts_created"] >= 1
    book = session.get(Book, book_id)
    assert book is not None
    payload = get_run_chapter_functions_product_v1(session, run_id)
    return _wb_entry(
        "conflict",
        book,
        run_id,
        run.status,
        expected_initial="confirmed chapter_function + open conflict; data-state=conflict; candidate version present",
        expected_display="data-state=conflict",
        module="chapter_functions",
        product_result_status=(payload or {}).get("product_result_status")
        or (payload or {}).get("result_status")
        or "conflict",
        open_conflict_count=len(conflicts),
        conflicts_created=meta["conflicts_created"],
    )


def _seed_structure_context_absent(session) -> dict:
    """CF completes without WB-2.1 structure stage (context absent)."""
    run_id, book_id = _prepare_sample_s_run(
        session,
        title="WB22 Structure Context Absent",
        source_key="wb22-ctx-absent",
    )
    start_whole_book_run_v1(session, run_id)
    execute_minimal_entity_event_extraction_v1(
        session, run_id, transport=FixtureWindowAnalysisTransport()
    )
    materialize_minimal_narrative_assets_v1(session, run_id)
    synthesize_minimal_book_overview_v1(session, run_id, finalize_run=False)
    cf = synthesize_minimal_chapter_functions_v1(
        session, run_id, mode="structure_context_absent", finalize_run=True
    )
    session.commit()
    book = session.get(Book, book_id)
    assert book is not None
    run = get_run(session, run_id)
    payload = get_run_chapter_functions_product_v1(session, run_id)
    caps = ((payload or {}).get("chapter_functions") or {}).get("context_capabilities") or {}
    return _wb_entry(
        "wb21_context_absent",
        book,
        run_id,
        run.status,
        expected_initial="CF completed without structure stage; structure_derived_context.present=false",
        expected_display="data-state=available; WB-2.1 context absent",
        module="chapter_functions",
        chapter_functions_mode="structure_context_absent",
        product_result_status=cf.get("product_result_status") or cf.get("result_status"),
        structure_derived_context=caps.get("structure_derived_context"),
    )


def _seed_snapshot_only_book(session, *, title: str, source_key: str) -> Book:
    book, _ = _seed_sample_s_book(session, title=title, source_key=source_key)
    session.commit()
    return book


def _seed_cost_consent(session) -> dict:
    book = _seed_snapshot_only_book(
        session,
        title="WB22 Cost Consent",
        source_key="wb22-cost-consent",
    )
    return {
        "kind": "cost_consent",
        "book_title": book.title,
        "book_id": book.id,
        "whole_book_run_id": None,
        "status": "not_started",
        "url": _wb_url(book.id),
        "expected_initial": "prepare 200; estimate+consent UI; real_provider=false; fixture preview clickable",
        "expected_display": "prepare + consent; no whole-book run yet",
        "seeded": True,
    }


def _url_variant(base_entry: dict, *, kind: str, extra_qs: dict[str, str], expected: str) -> dict:
    book_id = base_entry["book_id"]
    run_id = base_entry["whole_book_run_id"]
    return {
        "kind": kind,
        "book_title": base_entry["book_title"],
        "book_id": book_id,
        "whole_book_run_id": run_id,
        "status": base_entry["status"],
        "url": _wb_url(book_id, module="chapter_functions", run_id=run_id, extra_qs=extra_qs),
        "expected_initial": expected,
        "expected_display": expected,
        "result_origin": "fixture",
        "seeded": True,
        "shares_run_with": base_entry["kind"],
        "extra_qs": extra_qs,
    }


async def _amain() -> dict:
    assert "storylens-wb22-integration" in get_settings().database_url.replace("\\", "/")
    create_db()
    SessionLocal = get_session_factory()
    fixtures: dict = {
        "change_id": "CHG-20260803-042",
        "parent_change": "CHG-20260802-036",
        "database": str(DB_PATH),
        "smoke_root": str(SMOKE_DIR),
        "api_url": API_URL,
        "frontend_url": FE_URL,
        "note": (
            "test-only WB-2.2 chapter_functions fixtures; result_origin=fixture; "
            "banner/limitations FIXTURE_TEST_DATA; catalog entries required for READY"
        ),
        "regression_note": (
            "Overview / characters_events / structure regressions reuse available run modules. "
            "Scene/journey V1.1.2 remain in CHG-029 smoke DB."
        ),
        "seeded_at": datetime.now(timezone.utc).isoformat(),
    }
    with SessionLocal() as session:
        _enable_cloud(session)

        entry_available = _seed_pipeline_entry(
            session,
            kind="cf_available",
            title="WB22 A Available",
            source_key="wb22-available",
            chapter_functions_mode="available",
            expected_initial=(
                "completed; data-state=available; primary+optional secondary; "
                "evidence bindings; banner=测试数据; overview/characters/structure on same run"
            ),
            expected_display="data-state=available; chapters>=1",
        )
        entry_available["v112_regression"] = [
            "whole_book_overview",
            "characters_events",
            "structure_available",
            "chapter_functions_available",
        ]

        entry_primary_secondary = _seed_pipeline_entry(
            session,
            kind="cf_primary_secondary",
            title="WB22 B Primary+Secondary",
            source_key="wb22-multi-fn",
            chapter_functions_mode="multi_function",
            expected_initial="completed; at least one chapter with primary + secondary_functions",
            expected_display="data-state=available; primary+secondary present",
        )

        entry_primary_null = _seed_pipeline_entry(
            session,
            kind="cf_primary_null",
            title="WB22 C Primary Null",
            source_key="wb22-primary-null",
            chapter_functions_mode="primary_null",
            expected_initial="completed; primary_function=null legal; secondary present",
            expected_display="data-state=available; primary null allowed",
        )

        entry_secondary_empty = _seed_pipeline_entry(
            session,
            kind="cf_secondary_empty",
            title="WB22 D Secondary Empty",
            source_key="wb22-secondary-empty",
            chapter_functions_mode="secondary_empty",
            expected_initial="completed; primary present; secondary_functions=[]",
            expected_display="data-state=available; empty secondary list",
        )

        entry_partial = _seed_pipeline_entry(
            session,
            kind="cf_partial",
            title="WB22 E Partial Span",
            source_key="wb22-partial",
            chapter_functions_mode="partial",
            expected_initial="completed; coverage_scope=partial_span; partial banner allowed",
            expected_display="data-state=available or partial; coverage=partial_span",
        )

        entry_insufficient = _seed_pipeline_entry(
            session,
            kind="cf_insufficient",
            title="WB22 F Insufficient",
            source_key="wb22-insufficient",
            chapter_functions_mode="insufficient",
            expected_initial="run completed; coverage_scope=insufficient; empty chapters",
            expected_display="data-state=insufficient",
        )

        entry_failed = _seed_pipeline_entry(
            session,
            kind="cf_failed",
            title="WB22 G Failed",
            source_key="wb22-failed",
            chapter_functions_mode="failed_empty",
            expected_initial="run failed; product result_status=failed; CHAPTER_FN_* failure_code",
            expected_display="data-state=failed",
        )

        entry_canceled = _seed_canceled(session)
        entry_conflict = _seed_conflict(session)

        entry_evidence = _seed_pipeline_entry(
            session,
            kind="cf_evidence",
            title="WB22 H Evidence Deep Link",
            source_key="wb22-evidence",
            chapter_functions_mode="available",
            expected_initial=(
                "completed; citation_evidence_bindings present; "
                "evidence button + open-in-reader deep link"
            ),
            expected_display="data-state=available; evidence clickable",
        )

        book_absent = _seed_snapshot_only_book(
            session,
            title="WB22 I Chapter Functions Absent",
            source_key="wb22-absent",
        )
        entry_absent = {
            "kind": "cf_absent",
            "book_title": book_absent.title,
            "book_id": book_absent.id,
            "whole_book_run_id": None,
            "status": "not_started",
            "url": _wb_url(book_absent.id, module="chapter_functions"),
            "expected_initial": "snapshot exists; no whole-book run; chapter_functions not_started/absent",
            "expected_display": "data-state=not_started or absent; no READY inference from DB alone",
            "seeded": True,
        }

        entry_long_book = _seed_pipeline_entry(
            session,
            kind="cf_long_book_pagination",
            title="WB22 J Long Book / Pagination",
            source_key="wb22-long-book",
            chapter_functions_mode="long_book",
            expected_initial=(
                "completed long_book mode on Sample S (3 ch); "
                "UI pagination/load-more + API cursor; mark full 9+ ch as optional heavier seed"
            ),
            expected_display="data-state=available; pagination controls or cursor API",
            note="Sample S 3 chapters; long_book fixture mode; cursor pagination verified via API",
        )

        chapter_id_for_detail = None
        if entry_available.get("whole_book_run_id") is not None:
            avail_payload = get_run_chapter_functions_product_v1(
                session, entry_available["whole_book_run_id"], limit=1
            )
            if avail_payload and avail_payload.get("items"):
                chapter_id_for_detail = str(avail_payload["items"][0].get("chapter_id") or "1")

        entry_function_filter = _url_variant(
            entry_available,
            kind="cf_function_filter",
            extra_qs={"cfFunction": "setup"},
            expected="data-state=available; function filter=setup applied",
        )
        entry_status_filter = _url_variant(
            entry_available,
            kind="cf_status_filter",
            extra_qs={"cfStatus": "observed"},
            expected="data-state=available; status filter=observed applied",
        )
        entry_chapter_detail = _url_variant(
            entry_available,
            kind="cf_chapter_detail",
            extra_qs={"cfChapter": chapter_id_for_detail or "1"},
            expected="data-state=available; chapter detail drawer/selection",
        )

        entry_ctx_available = _seed_pipeline_entry(
            session,
            kind="wb21_context_available",
            title="WB22 K WB-2.1 Context Available",
            source_key="wb22-ctx-available",
            chapter_functions_mode="structure_context_available",
            expected_initial="CF + structure present; structure_derived_context marker=DERIVED_CONTEXT_NOT_FACT",
            expected_display="data-state=available; WB-2.1 context available (derived, not fact)",
        )

        entry_ctx_absent = _seed_structure_context_absent(session)

        entry_ctx_insufficient = _seed_pipeline_entry(
            session,
            kind="wb21_context_insufficient",
            title="WB22 M WB-2.1 Context Insufficient",
            source_key="wb22-ctx-insufficient",
            chapter_functions_mode="structure_context_insufficient",
            structure_mode="insufficient",
            expected_initial="structure coverage insufficient; CF may still complete; derived context insufficient",
            expected_display="CF available/insufficient; WB-2.1 context insufficient",
        )

        entry_cost = _seed_cost_consent(session)
        entry_cost["v112_regression"] = ["cost_consent"]

        # Regression module URLs on the available run (same book/run).
        entry_reg_overview = {
            "kind": "regression_overview",
            "book_title": entry_available["book_title"],
            "book_id": entry_available["book_id"],
            "whole_book_run_id": entry_available["whole_book_run_id"],
            "status": entry_available["status"],
            "url": _wb_url(
                entry_available["book_id"],
                module="overview",
                run_id=entry_available["whole_book_run_id"],
            ),
            "expected_initial": "overview module still loads on CF-available run",
            "expected_display": "overview regression OK",
            "seeded": True,
            "shares_run_with": "cf_available",
        }
        entry_reg_characters = {
            "kind": "regression_characters",
            "book_title": entry_available["book_title"],
            "book_id": entry_available["book_id"],
            "whole_book_run_id": entry_available["whole_book_run_id"],
            "status": entry_available["status"],
            "url": _wb_url(
                entry_available["book_id"],
                module="characters_events",
                run_id=entry_available["whole_book_run_id"],
            ),
            "expected_initial": "characters_events module still loads on CF-available run",
            "expected_display": "characters_events regression OK",
            "seeded": True,
            "shares_run_with": "cf_available",
        }
        structure_payload = get_run_structure_product_v1(
            session, entry_available["whole_book_run_id"]
        )
        entry_reg_structure = {
            "kind": "regression_structure",
            "book_title": entry_available["book_title"],
            "book_id": entry_available["book_id"],
            "whole_book_run_id": entry_available["whole_book_run_id"],
            "status": entry_available["status"],
            "url": _wb_url(
                entry_available["book_id"],
                module="structure",
                run_id=entry_available["whole_book_run_id"],
            ),
            "expected_initial": "structure module still available; WB-2.1 regression",
            "expected_display": "data-state=available; structure regression OK",
            "seeded": True,
            "shares_run_with": "cf_available",
            "structure_result_status": (structure_payload or {}).get("result_status"),
        }

        fixtures.update(
            {
                "cf_available": entry_available,
                "cf_primary_secondary": entry_primary_secondary,
                "cf_primary_null": entry_primary_null,
                "cf_secondary_empty": entry_secondary_empty,
                "cf_partial": entry_partial,
                "cf_insufficient": entry_insufficient,
                "cf_failed": entry_failed,
                "canceled": entry_canceled,
                "conflict": entry_conflict,
                "cf_evidence": entry_evidence,
                "cf_absent": entry_absent,
                "cf_long_book_pagination": entry_long_book,
                "cf_function_filter": entry_function_filter,
                "cf_status_filter": entry_status_filter,
                "cf_chapter_detail": entry_chapter_detail,
                "wb21_context_available": entry_ctx_available,
                "wb21_context_absent": entry_ctx_absent,
                "wb21_context_insufficient": entry_ctx_insufficient,
                "cost_consent": entry_cost,
                "regression_overview": entry_reg_overview,
                "regression_characters": entry_reg_characters,
                "regression_structure": entry_reg_structure,
            }
        )

    out = SMOKE_DIR / "MANUAL_FIXTURES.json"
    out.write_text(json.dumps(fixtures, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    catalog_keys = [
        k
        for k, v in fixtures.items()
        if isinstance(v, dict) and v.get("book_id") is not None
    ]
    print(
        json.dumps(
            {
                "ok": True,
                "database": str(DB_PATH),
                "fixtures": str(out),
                "catalog_count": len(catalog_keys),
                "catalog_keys": catalog_keys,
            },
            ensure_ascii=False,
        )
    )
    return fixtures


if __name__ == "__main__":
    asyncio.run(_amain())
