"""TEST-ONLY seed for CHG-20260802-036 WB-2.1 integration manual smoke.

Creates a fresh isolated SQLite with separate books for each structure-stage
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
        "STORYLENS_WB21_SMOKE_ROOT",
        Path(os.environ["TEMP"]) / "storylens-wb21-integration",
    )
)
SMOKE_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = SMOKE_DIR / "wb21_integration.db"
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
from app.narrative_core.services.whole_book_fixture_pipeline_v1_service import (  # noqa: E402
    execute_fixture_minimal_pipeline_v1,
)
from app.narrative_core.services.whole_book_minimal_helpers_v1 import (  # noqa: E402
    set_stage_completed,
)
from app.narrative_core.services.whole_book_minimal_structure_stages_v1_service import (  # noqa: E402
    _persist_structure_assets,
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
    load_structure_checkpoint_envelope,
)
from app.schemas.settings import CloudBudgetUpdate  # noqa: E402
from app.services.whole_book_source_fingerprint import sha256_utf8  # noqa: E402
from tests.whole_book_minimal_test_helpers import seed_three_windows  # noqa: E402

API_URL = os.environ.get("STORYLENS_WB21_API_URL", "http://127.0.0.1:8005")
FE_URL = os.environ.get("STORYLENS_WB21_FE_URL", "http://127.0.0.1:1425")


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


def _wb_url(book_id: int, *, module: str | None = None, run_id: int | None = None) -> str:
    url = f"{FE_URL}/books/{book_id}/whole-book"
    params: list[str] = []
    if module:
        params.append(f"module={module}")
    if run_id is not None:
        params.append(f"run={run_id}")
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
    **extra,
) -> dict:
    return {
        "kind": kind,
        "book_title": book.title,
        "book_id": book.id,
        "whole_book_run_id": run_id,
        "status": status,
        "url": _wb_url(book.id, module=module, run_id=run_id),
        "expected_initial": expected_initial,
        "expected_display": expected_display or expected_initial,
        "result_origin": "fixture",
        **extra,
    }


def _seed_pipeline_entry(
    session,
    *,
    kind: str,
    title: str,
    source_key: str,
    structure_mode: str,
    expected_initial: str,
    expected_display: str | None = None,
    module: str = "structure",
    **extra,
) -> dict:
    run_id, book_id = _prepare_sample_s_run(session, title=title, source_key=source_key)
    result = execute_fixture_minimal_pipeline_v1(session, run_id, structure_mode=structure_mode)
    session.commit()
    book = session.get(Book, book_id)
    assert book is not None
    run = get_run(session, run_id)
    structure_payload = get_run_structure_product_v1(session, run_id)
    product_status = (
        structure_payload.get("result_status") if structure_payload else result["structure"].get("result_status")
    )
    return _wb_entry(
        kind,
        book,
        run_id,
        run.status,
        expected_initial=expected_initial,
        expected_display=expected_display,
        module=module,
        structure_mode=structure_mode,
        product_result_status=product_status,
        coverage_scope=structure_payload.get("coverage_scope") if structure_payload else None,
        stage_count=result["structure"].get("stage_count"),
        limitations=((structure_payload or {}).get("structure") or {}).get("limitations"),
        **extra,
    )


def _seed_canceled(session) -> dict:
    run_id, book_id = _prepare_sample_s_run(
        session,
        title="WB21 F Canceled",
        source_key="wb21-canceled",
    )
    start_whole_book_run_v1(session, run_id)
    request_cancel_whole_book_run_v1(session, run_id)
    session.commit()
    book = session.get(Book, book_id)
    assert book is not None
    run = get_run(session, run_id)
    payload = get_run_structure_product_v1(session, run_id)
    return _wb_entry(
        "canceled",
        book,
        run_id,
        run.status,
        expected_initial="run cancelled; product result_status=canceled; structure view canceled",
        expected_display="data-state=canceled",
        module="structure",
        product_result_status=payload.get("result_status") if payload else "canceled",
    )


def _seed_conflict(session) -> dict:
    run_id, book_id = _prepare_sample_s_run(
        session,
        title="WB21 G Structure Conflict",
        source_key="wb21-conflict",
    )
    execute_fixture_minimal_pipeline_v1(session, run_id, structure_mode="multi_stage")
    session.commit()
    version = session.scalar(
        select(NarrativeAssetVersion)
        .join(NarrativeAsset, NarrativeAssetVersion.asset_id == NarrativeAsset.id)
        .where(
            NarrativeAsset.book_id == book_id,
            NarrativeAssetVersion.asset_type == "structure_stage",
            NarrativeAssetVersion.is_canonical.is_(True),
        )
    )
    assert version is not None
    confirm_narrative_asset_v1(session, version.asset_id)
    session.commit()
    envelope = load_structure_checkpoint_envelope(session, run_id)
    structure = dict(envelope["structure"])
    structure["stages"][0]["title"] = "Conflict-Candidate-Title"
    run = get_run(session, run_id)
    meta = _persist_structure_assets(
        session,
        run_id=run_id,
        book_id=book_id,
        snapshot_id=int(run.snapshot_id),
        structure=structure,
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
    payload = get_run_structure_product_v1(session, run_id)
    return _wb_entry(
        "conflict",
        book,
        run_id,
        run.status,
        expected_initial="confirmed structure + open conflict; data-state=conflict; candidate version present",
        expected_display="data-state=conflict",
        module="structure",
        product_result_status=payload.get("result_status") if payload else "conflict",
        open_conflict_count=len(conflicts),
        conflicts_created=meta["conflicts_created"],
    )


def _seed_snapshot_only_book(
    session,
    *,
    title: str,
    source_key: str,
) -> Book:
    book, _ = _seed_sample_s_book(session, title=title, source_key=source_key)
    session.commit()
    return book


def _seed_cost_consent(session) -> dict:
    book = _seed_snapshot_only_book(
        session,
        title="WB21 J Cost Consent",
        source_key="wb21-cost-consent",
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
    }


async def _amain() -> dict:
    assert "storylens-wb21-integration" in get_settings().database_url.replace("\\", "/")
    create_db()
    SessionLocal = get_session_factory()
    fixtures: dict = {
        "change_id": "CHG-20260802-036",
        "parent_change": "CHG-20260801-035",
        "database": str(DB_PATH),
        "smoke_root": str(SMOKE_DIR),
        "api_url": API_URL,
        "frontend_url": FE_URL,
        "note": (
            "test-only WB-2.1 structure fixtures; result_origin=fixture; "
            "banner/limitations FIXTURE_TEST_DATA; catalog entries required for READY"
        ),
        "regression_note": (
            "Scene/journey V1.1.2 regressions remain in CHG-029 smoke DB "
            "(scripts_seed_chg029_smoke_v2.py). This seed covers whole-book structure + "
            "minimal V1.1.2 whole-book regressions (overview/characters_events/cost_consent)."
        ),
        "seeded_at": datetime.now(timezone.utc).isoformat(),
    }
    with SessionLocal() as session:
        _enable_cloud(session)

        entry_available = _seed_pipeline_entry(
            session,
            kind="structure_available",
            title="WB21 A Multi-Stage Available",
            source_key="wb21-available",
            structure_mode="multi_stage",
            expected_initial=(
                "completed multi-stage; data-state=available; overview 9 claims; "
                "characters_events on same run; evidence deep link; banner=测试数据"
            ),
            expected_display="data-state=available; stages>=2; turning_points present",
        )
        entry_available["v112_regression"] = ["whole_book_overview", "characters_events", "structure_available"]

        entry_non_three_act = _seed_pipeline_entry(
            session,
            kind="non_three_act",
            title="WB21 B Non-Three-Act",
            source_key="wb21-non-three-act",
            structure_mode="non_three_act",
            expected_initial="completed; 4 stages (not forced to 3); no 第一幕 labels",
            expected_display="data-state=available; stage_count=4",
        )

        entry_tp_empty = _seed_pipeline_entry(
            session,
            kind="turning_points_empty",
            title="WB21 C Turning Points Empty",
            source_key="wb21-tp-empty",
            structure_mode="tp_empty",
            expected_initial="completed; stages present; turning_points=[]",
            expected_display="data-state=available; empty turning_points list",
        )

        entry_insufficient = _seed_pipeline_entry(
            session,
            kind="insufficient",
            title="WB21 D Insufficient Coverage",
            source_key="wb21-insufficient",
            structure_mode="insufficient",
            expected_initial="run completed; coverage_scope=insufficient; empty stages",
            expected_display="data-state=insufficient",
        )

        entry_failed = _seed_pipeline_entry(
            session,
            kind="failed",
            title="WB21 E Structure Failed",
            source_key="wb21-failed",
            structure_mode="failed_empty",
            expected_initial="run failed; product result_status=failed; STRUCTURE_* failure_code",
            expected_display="data-state=failed",
        )

        entry_canceled = _seed_canceled(session)
        entry_conflict = _seed_conflict(session)

        entry_evidence = _seed_pipeline_entry(
            session,
            kind="evidence",
            title="WB21 H Evidence Deep Link",
            source_key="wb21-evidence",
            structure_mode="multi_stage",
            expected_initial=(
                "completed multi-stage; citation_evidence_bindings present; "
                "stage evidence drawer + open-in-reader deep link"
            ),
            expected_display="data-state=available; evidence drawer navigates to reader",
        )

        book_absent = _seed_snapshot_only_book(
            session,
            title="WB21 I Structure Absent",
            source_key="wb21-absent",
        )
        entry_absent = {
            "kind": "structure_absent",
            "book_title": book_absent.title,
            "book_id": book_absent.id,
            "whole_book_run_id": None,
            "status": "not_started",
            "url": _wb_url(book_absent.id, module="structure"),
            "expected_initial": "snapshot exists; no whole-book run; structure not_started/absent",
            "expected_display": "data-state=not_started or absent; no READY inference from DB alone",
        }

        entry_cost = _seed_cost_consent(session)
        entry_cost["v112_regression"] = ["cost_consent"]

        fixtures.update(
            {
                "structure_available": entry_available,
                "non_three_act": entry_non_three_act,
                "turning_points_empty": entry_tp_empty,
                "insufficient": entry_insufficient,
                "failed": entry_failed,
                "canceled": entry_canceled,
                "conflict": entry_conflict,
                "evidence": entry_evidence,
                "structure_absent": entry_absent,
                "cost_consent": entry_cost,
            }
        )

    out = SMOKE_DIR / "MANUAL_FIXTURES.json"
    out.write_text(json.dumps(fixtures, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "database": str(DB_PATH), "fixtures": str(out)}, ensure_ascii=False))
    return fixtures


if __name__ == "__main__":
    asyncio.run(_amain())
