"""Phase 1C Integration tests — Engine + Capability + Preflight E2E.

Does not call models, does not enable production run creation, does not
register a production Engine. Uses project .venv Python when available.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AnalysisArtifact,
    AnalysisRun,
    Base,
    Book,
    BookSnapshot,
    Chapter,
    Paragraph,
)
from app.narrative_core.capability_registry import get_capability_metadata
from app.narrative_core.contracts.api_dto import WHOLE_BOOK_RUNS_ENDPOINT_DISABLED
from app.narrative_core.contracts.capability import CapabilityDecision, QuotaPolicy
from app.narrative_core.contracts.stage import WholeBookStageContext
from app.narrative_core.contracts.whole_book_artifact import (
    WHOLE_BOOK_STAGE_ARTIFACT_SCHEMA,
    WHOLE_BOOK_STAGE_ARTIFACT_TYPE,
    WHOLE_BOOK_STAGE_ARTIFACT_VERSION,
)
from app.narrative_core.enums import (
    CapabilityAvailability,
    CapabilityKey,
    CapabilityReasonCode,
    QuotaPolicyKind,
    SnapshotStatus,
    StageStatus,
    WholeBookAnalysisMode,
    WholeBookStageKey,
)
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.migrations.runner import (
    apply_narrative_phase1bp_migrations,
    apply_narrative_phase1p_migrations,
)
from app.narrative_core.services.capability_api_payloads import (
    build_capabilities_list_response,
    build_capability_detail_response,
)
from app.narrative_core.services.capability_service import DefaultCapabilityService
from app.narrative_core.services.mock_whole_book_engine import (
    MOCK_ENGINE_ID,
    MockWholeBookAnalysisEngine,
)
from app.narrative_core.services.quota_service import (
    InMemoryQuotaService,
    extract_reservation_id,
)
from app.narrative_core.services.run_permission_guard import require_whole_book_run_permission
from app.narrative_core.services.whole_book_engine_adapters import (
    ArtifactWriterAdapter,
    NarrativeAssetWriterAdapter,
)
from app.narrative_core.services.whole_book_engine_registry import (
    DefaultWholeBookEngineFactory,
    PRODUCTION_DEFAULT_ENGINE_ID,
)
from app.narrative_core.services.whole_book_preflight import (
    build_whole_book_preflight,
    preflight_response_dict,
)
from app.narrative_core.services.whole_book_request_chain import (
    create_whole_book_analysis_request_for_test,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _fk_engine(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


@pytest.fixture()
def session(tmp_path) -> Session:
    db = _fk_engine(f"sqlite:///{tmp_path / 'phase1c-integration.db'}")
    Base.metadata.create_all(db)
    apply_narrative_phase1p_migrations(db)
    apply_narrative_phase1bp_migrations(db)
    SessionLocal = sessionmaker(bind=db, autoflush=False, expire_on_commit=False)
    s = SessionLocal()
    yield s
    s.close()
    db.dispose()


def _seed_book(session: Session) -> Book:
    book = Book(
        title="Integration Book",
        source_file_name="integration.txt",
        source_file_hash="i" * 64,
        created_at=datetime.now(timezone.utc),
    )
    session.add(book)
    session.flush()
    chapter = Chapter(
        book_id=book.id,
        chapter_index=1,
        title="第一章",
        display_title="第一章",
        chapter_title="第一章",
        source_title_line="第一章",
        word_count=11,
    )
    session.add(chapter)
    session.flush()
    session.add(
        Paragraph(
            id=f"B{book.id:04d}-C0001-P0001",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=1,
            raw_text="hello world",
            normalized_text="hello world",
            char_start=0,
            char_end=11,
        )
    )
    session.commit()
    return book


def _allowed_decision() -> CapabilityDecision:
    meta = get_capability_metadata(CapabilityKey.WHOLE_BOOK_ANALYSIS)
    return CapabilityDecision(
        capability_key=CapabilityKey.WHOLE_BOOK_ANALYSIS,
        allowed=True,
        reason_code=CapabilityReasonCode.CAPABILITY_AVAILABLE,
        availability=CapabilityAvailability.AVAILABLE,
        display_message="test override allowed",
        supported_modes=meta.supported_modes,
        metadata=meta,
    )


def test_01_capability_not_shipped_preview_visible() -> None:
    meta = get_capability_metadata(CapabilityKey.WHOLE_BOOK_ANALYSIS)
    assert meta.shipped is False
    assert meta.preview_visible is True
    assert meta.availability == CapabilityAvailability.PREVIEW
    assert meta.requires_license is True
    svc = DefaultCapabilityService()
    decision = svc.evaluate_capability(CapabilityKey.WHOLE_BOOK_ANALYSIS)
    assert decision.allowed is False
    assert decision.reason_code == CapabilityReasonCode.CAPABILITY_NOT_SHIPPED
    assert decision.preview_only is True


def test_02_mode_not_supported() -> None:
    svc = DefaultCapabilityService()
    decision = svc.evaluate_mode(CapabilityKey.WHOLE_BOOK_ANALYSIS, "chapter_only")
    assert decision.allowed is False
    assert decision.reason_code == CapabilityReasonCode.CAPABILITY_MODE_NOT_SUPPORTED
    assert "不受支持" in decision.display_message


def test_03_unknown_capability() -> None:
    svc = DefaultCapabilityService()
    decision = svc.evaluate_capability("not_a_real_key")
    assert decision.reason_code == CapabilityReasonCode.CAPABILITY_UNKNOWN
    assert decision.allowed is False


def test_04_guard_denied_no_engine_no_run(session: Session) -> None:
    book = _seed_book(session)
    before = session.scalar(select(func.count()).select_from(AnalysisRun)) or 0
    engine_calls: list[str] = []

    def engine_invoker(*_a, **_k):
        engine_calls.append("called")

    svc = DefaultCapabilityService(session)
    result = require_whole_book_run_permission(
        svc,
        analysis_mode=WholeBookAnalysisMode.NATIVE,
        book_id=book.id,
        book_snapshot_id=1,
        snapshot_status=SnapshotStatus.COMPLETED,
        engine_invoker=engine_invoker,
    )
    assert result.allowed is False
    assert result.reason_code == "WHOLE_BOOK_RUNS_ENDPOINT_DISABLED"
    assert engine_calls == []
    after = session.scalar(select(func.count()).select_from(AnalysisRun)) or 0
    assert after == before


def test_05_guard_denied_no_quota_reserve() -> None:
    quota = InMemoryQuotaService(
        policy_overrides={
            CapabilityKey.WHOLE_BOOK_ANALYSIS.value: (
                QuotaPolicy(kind=QuotaPolicyKind.PER_BOOK, policy_key="wb", limit=1),
            )
        }
    )
    svc = DefaultCapabilityService(quota=quota)
    before = quota.evaluate_quota(
        CapabilityKey.WHOLE_BOOK_ANALYSIS, context={"book_id": 9}
    )
    result = require_whole_book_run_permission(
        svc,
        analysis_mode=WholeBookAnalysisMode.NATIVE,
        book_id=9,
        book_snapshot_id=1,
    )
    assert result.allowed is False
    after = quota.evaluate_quota(
        CapabilityKey.WHOLE_BOOK_ANALYSIS, context={"book_id": 9}
    )
    assert (after.reserved or 0) == (before.reserved or 0)


def test_06_test_allowed_decision_builds_request() -> None:
    svc = DefaultCapabilityService()
    engine = MockWholeBookAnalysisEngine()
    request, plan = create_whole_book_analysis_request_for_test(
        svc,
        book_id=1,
        book_snapshot_id=1,
        analysis_mode=WholeBookAnalysisMode.NATIVE,
        run_id=42,
        decision_override=_allowed_decision(),
        client_allowed=True,
        engine=engine,
    )
    assert request.capability_context.allowed is True
    assert request.capability_context.display_message == "test override allowed"
    assert len(plan.stages) > 0
    engine.validate_request(request)


def test_07_denied_without_override() -> None:
    svc = DefaultCapabilityService()
    engine = MockWholeBookAnalysisEngine()
    with pytest.raises(NarrativeCoreError) as exc:
        create_whole_book_analysis_request_for_test(
            svc,
            book_id=1,
            book_snapshot_id=1,
            analysis_mode=WholeBookAnalysisMode.NATIVE,
            client_allowed=True,
            engine=engine,
            skip_guard=True,
        )
    assert exc.value.code == NarrativeCoreErrorCode.WHOLE_BOOK_CAPABILITY_DENIED


def test_08_stage_context_relation_writer_field() -> None:
    class _Rel:
        def write_relation_candidate(self, payload):  # noqa: ANN001
            return 7

    ctx = WholeBookStageContext(
        run_id=1,
        book_id=1,
        book_snapshot_id=1,
        analysis_mode=WholeBookAnalysisMode.NATIVE,
        stage_key=WholeBookStageKey.BUILD_FULLTEXT_INDEX,
        capability_context=_allowed_decision(),
        relation_writer=_Rel(),
        extra={"note": "non-core"},
    )
    assert ctx.relation_writer is not None
    assert "relation_writer" not in ctx.extra


def test_09_stage_artifact_envelope(session: Session) -> None:
    book = _seed_book(session)
    run = AnalysisRun(
        task_type="whole_book",
        subject_type="book",
        subject_id=str(book.id),
        provider="mock",
        model="mock",
        prompt_version="none",
        schema_version="1",
        input_hash="a" * 64,
        status="pending",
    )
    session.add(run)
    session.commit()
    writer = ArtifactWriterAdapter(session)
    engine = MockWholeBookAnalysisEngine()
    ctx = WholeBookStageContext(
        run_id=run.id,
        book_id=book.id,
        book_snapshot_id=1,
        analysis_mode=WholeBookAnalysisMode.NATIVE,
        stage_key=WholeBookStageKey.BUILD_FULLTEXT_INDEX,
        capability_context=_allowed_decision(),
        run_stage_id=99,
        artifact_writer=writer,
    )
    result = engine.execute_stage(ctx)
    assert result.status == StageStatus.COMPLETED
    assert result.output_artifact_ids
    row = session.get(AnalysisArtifact, result.output_artifact_ids[0])
    assert row is not None
    assert row.artifact_type == WHOLE_BOOK_STAGE_ARTIFACT_TYPE
    payload = json.loads(row.payload_json)
    assert payload["schema"] == WHOLE_BOOK_STAGE_ARTIFACT_SCHEMA
    assert payload["version"] == WHOLE_BOOK_STAGE_ARTIFACT_VERSION
    assert payload["mock"] is True
    assert payload["synthetic"] is True
    assert payload["non_production"] is True
    assert payload["stage_key"] == WholeBookStageKey.BUILD_FULLTEXT_INDEX.value
    assert "full_text" not in payload


def test_10_mock_not_production() -> None:
    assert PRODUCTION_DEFAULT_ENGINE_ID is None
    factory = DefaultWholeBookEngineFactory(production_mode=True)
    with pytest.raises(NarrativeCoreError) as exc:
        factory.create_engine(MOCK_ENGINE_ID)
    assert exc.value.code == NarrativeCoreErrorCode.WHOLE_BOOK_ENGINE_UNAVAILABLE


def test_11_preflight_no_side_effects(session: Session) -> None:
    book = _seed_book(session)
    before_runs = session.scalar(select(func.count()).select_from(AnalysisRun)) or 0
    before_snaps = session.scalar(select(func.count()).select_from(BookSnapshot)) or 0
    before_arts = session.scalar(select(func.count()).select_from(AnalysisArtifact)) or 0

    svc = DefaultCapabilityService(session)
    dto = build_whole_book_preflight(
        session,
        svc,
        book_id=book.id,
        request={
            "analysis_mode": WholeBookAnalysisMode.NATIVE.value,
            "requested_modules": ["book_overview"],
            "book_snapshot_id": None,
        },
    )
    body = preflight_response_dict(dto)
    assert body["run_creation_enabled"] is False
    assert "WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=true" in body["blocking_reasons"]
    assert "whole_book_analysis shipped=false" in body["blocking_reasons"]
    assert "no production Engine" in body["blocking_reasons"]
    assert body["engine_status"]["production_engine_available"] is False
    assert body["engine_status"]["mock_reported_as_production"] is False
    assert body["chapter_count"] >= 1
    assert body["character_count"] >= 1

    after_runs = session.scalar(select(func.count()).select_from(AnalysisRun)) or 0
    after_snaps = session.scalar(select(func.count()).select_from(BookSnapshot)) or 0
    after_arts = session.scalar(select(func.count()).select_from(AnalysisArtifact)) or 0
    assert after_runs == before_runs
    assert after_snaps == before_snaps
    assert after_arts == before_arts


def test_12_quota_reserve_commit_release() -> None:
    quota = InMemoryQuotaService(
        policy_overrides={
            CapabilityKey.WHOLE_BOOK_ANALYSIS.value: (
                QuotaPolicy(kind=QuotaPolicyKind.PER_BOOK, policy_key="wb", limit=1),
            )
        }
    )
    assert quota.backend == "memory_non_production"
    ctx = {"book_id": 3}
    reserved = quota.reserve_usage(CapabilityKey.WHOLE_BOOK_ANALYSIS, context=ctx)
    assert reserved.allowed is True
    rid = extract_reservation_id(reserved)
    assert rid
    quota.commit_usage(CapabilityKey.WHOLE_BOOK_ANALYSIS, reservation_id=rid, context=ctx)
    quota.commit_usage(CapabilityKey.WHOLE_BOOK_ANALYSIS, reservation_id=rid, context=ctx)

    mid = quota.reserve_usage("whole_book_analysis", context={"book_id": 4})
    assert mid.allowed is True
    rid2 = extract_reservation_id(mid)
    assert rid2
    quota.release_usage("whole_book_analysis", reservation_id=rid2, context={"book_id": 4})
    quota.release_usage("whole_book_analysis", reservation_id=rid2, context={"book_id": 4})


def test_13_budget_denied_no_asset_write(session: Session) -> None:
    book = _seed_book(session)
    asset_writer = NarrativeAssetWriterAdapter(session)
    artifact_writer = ArtifactWriterAdapter(session)
    before_arts = len(artifact_writer.calls)
    svc = DefaultCapabilityService(session)

    def cloud_budget_checker():
        return False, "budget denied"

    result = require_whole_book_run_permission(
        svc,
        analysis_mode=WholeBookAnalysisMode.NATIVE,
        book_id=book.id,
        book_snapshot_id=1,
        snapshot_status=SnapshotStatus.COMPLETED,
        context={"allow_endpoint_for_test": True},
        cloud_budget_checker=cloud_budget_checker,
    )
    assert result.allowed is False
    assert len(artifact_writer.calls) == before_arts
    assert list(getattr(asset_writer, "created_asset_ids", []) or []) == []


def test_14_capability_api_dto() -> None:
    body = build_capabilities_list_response(DefaultCapabilityService())
    whole = next(i for i in body["items"] if i["key"] == "whole_book_analysis")
    assert whole["preview_visible"] is True
    assert whole["shipped"] is False
    assert whole["decision"]["allowed"] is False
    detail = build_capability_detail_response(
        DefaultCapabilityService(), "whole_book_analysis"
    )
    assert detail["decision"]["capability_key"] == "whole_book_analysis"
    assert detail["decision"]["allowed"] is False
    assert set(detail["decision"].keys()) >= {
        "capability_key",
        "allowed",
        "availability",
        "reason_code",
        "display_message",
        "supported_modes",
        "quota",
        "usage",
        "remaining",
        "offline_status",
        "license_status",
        "evaluated_at",
    }
    lib = build_capability_detail_response(
        DefaultCapabilityService(), "narrative_asset_library"
    )
    assert lib.get("foundation_note")


def test_15_capability_keys_script() -> None:
    import subprocess
    import sys

    script = REPO_ROOT / "scripts" / "check_capability_keys.py"
    py = Path(r"D:\Dstorylens\.venv\Scripts\python.exe")
    exe = str(py) if py.exists() else sys.executable
    proc = subprocess.run(
        [exe, str(script)], cwd=str(REPO_ROOT), capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_16_flags_unchanged() -> None:
    assert WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is True
    text = (REPO_ROOT / "apps/desktop/src/services/productEdition.ts").read_text(
        encoding="utf-8"
    )
    assert "PRO_CAPABILITIES_SHIPPED = false" in text
    assert PRODUCTION_DEFAULT_ENGINE_ID is None


def test_17_openapi_routes_registered() -> None:
    from app.main import app

    paths = {route.path for route in app.routes}
    assert "/api/v1/capabilities" in paths
    assert "/api/v1/capabilities/{capability_key}" in paths
    assert "/api/v1/books/{book_id}/whole-book-runs/preflight" in paths
    schema = app.openapi()
    assert "/api/v1/capabilities" in schema["paths"]
    assert "/api/v1/books/{book_id}/whole-book-runs/preflight" in schema["paths"]
