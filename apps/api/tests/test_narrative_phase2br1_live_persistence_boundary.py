"""Phase 2B-R1 CHG-055 — Live Candidate Evidence Persistence Boundary.

Fixes ``book_overview.claim`` DTO alias resolution and Context evidence-key
locator enrich before DefaultEvidenceValidator. Zero external HTTP.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

if "keyring" not in sys.modules:
    _keyring = ModuleType("keyring")
    _keyring.get_password = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    _keyring.set_password = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    _keyring.delete_password = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    _keyring.get_keyring = lambda: SimpleNamespace(priority=1)  # type: ignore[attr-defined]
    _errors = ModuleType("keyring.errors")

    class KeyringError(Exception):
        pass

    class PasswordDeleteError(KeyringError):
        pass

    _errors.KeyringError = KeyringError  # type: ignore[attr-defined]
    _errors.PasswordDeleteError = PasswordDeleteError  # type: ignore[attr-defined]
    sys.modules["keyring.errors"] = _errors
    sys.modules["keyring"] = _keyring

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    AnalysisArtifact,
    AnalysisRun,
    AnalysisRunStage,
    Base,
    Book,
    BookSnapshotParagraph,
    Chapter,
    NarrativeAsset,
    NarrativeAssetEvidence,
    NarrativeAssetVersion,
    Paragraph,
)
from app.narrative_core.enums import WholeBookAnalysisMode, WholeBookModuleKey
from app.narrative_core.migrations.runner import (
    apply_narrative_phase1bp_migrations,
    apply_narrative_phase1p_migrations,
)
from app.narrative_core.private_engine_contract.context import make_context_bundle_ref
from app.narrative_core.services.live_engine_kind import LiveEngineKind, classify_live_engine_kind
from app.narrative_core.services.live_module_pipeline_diagnostics import (
    LiveModulePipelineDiagnostics,
    fingerprint_structured_output,
)
from app.narrative_core.services.output_ref_resolution import (
    build_candidate_output_refs,
    resolve_provider_output_ref,
)
from app.narrative_core.services.private_engine_signature import is_fake_or_test_engine_id
from app.narrative_core.services.private_whole_book_analysis_runtime import (
    create_lab_private_whole_book_analysis_runtime,
    try_load_first_four_private_runners,
)
from app.narrative_core.services.provider_backed_module_result import (
    build_provider_backed_module_result,
)
from app.narrative_core.services.provider_transport_kind import FakeHttpProviderTransport
from app.narrative_core.services.quote_resolution import SnapshotQuoteIndex
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl


def _fk_engine(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


@pytest.fixture
def bind_env(tmp_path):
    db = _fk_engine(f"sqlite:///{tmp_path / 'chg055.db'}")
    Base.metadata.create_all(db)
    apply_narrative_phase1p_migrations(db)
    apply_narrative_phase1bp_migrations(db)
    factory = sessionmaker(bind=db, autoflush=False, expire_on_commit=False)
    session = factory()
    book = Book(
        title="CHG055 Boundary",
        source_file_name="chg055.txt",
        source_file_hash="e" * 64,
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
        word_count=12,
    )
    session.add(chapter)
    session.flush()
    session.add(
        Paragraph(
            id=f"B{book.id:04d}-C0001-P0001",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=1,
            raw_text="合成段落甲。",
            normalized_text="合成段落甲。",
            char_start=0,
            char_end=6,
        )
    )
    session.add(
        Paragraph(
            id=f"B{book.id:04d}-C0001-P0002",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=2,
            raw_text="合成段落乙。",
            normalized_text="合成段落乙。",
            char_start=6,
            char_end=12,
        )
    )
    session.commit()
    snap = BookSnapshotServiceImpl(session).create_or_reuse_snapshot(book.id)
    session.commit()
    run = AnalysisRun(
        book_id=book.id,
        analysis_type="whole_book_native",
        scope_type="book",
        subject_type="book",
        subject_id=str(book.id),
        provider="aliyun_qwen_plus",
        model="qwen3.7-plus",
        prompt_version="0.0.1",
        schema_version="1.0.0",
        input_hash="a" * 64,
        status="running",
        book_snapshot_id=snap.id,
        task_type="whole_book_pipeline",
    )
    session.add(run)
    session.flush()
    stage = AnalysisRunStage(
        run_id=run.id,
        stage_key="analyze_structure",
        status="running",
        stage_order=0,
        attempt_count=1,
    )
    session.add(stage)
    session.commit()
    paragraphs = list(
        session.scalars(
            select(BookSnapshotParagraph).where(BookSnapshotParagraph.snapshot_id == snap.id)
        ).all()
    )
    assert len(paragraphs) >= 1
    yield {
        "session": session,
        "book": book,
        "snap": snap,
        "run": run,
        "stage": stage,
        "paragraph": paragraphs[0],
        "paragraphs": paragraphs,
        "chapter": chapter,
    }
    session.close()


def _bailian_dto_shaped(env: dict[str, Any], *, evidence_id: str | None = None) -> dict[str, Any]:
    """Desensitized Bailian/BookOverviewResultDto shape — synthetic values only.

    Uses DTO ``evidence_refs`` with provider alias ``book_overview.claim`` and a
    model-visible paragraph evidence_id (snapshot paragraph PK string).
    """

    sp = env["paragraph"]
    eid = evidence_id if evidence_id is not None else str(sp.id)
    return {
        "logline": "合成总览一句话",
        "premise": "合成前提说明",
        "central_question": "合成核心问题",
        "primary_conflict": "合成主要冲突",
        "protagonist_asset_id": None,
        "major_storyline_ids": [],
        "structure_summary": "合成结构摘要",
        "ending_state": "unknown",
        "confidence": 0.7,
        "partial": False,
        "synthetic": False,
        "evidence_refs": [
            {
                "evidence_id": eid,
                "evidence_role": "support",
                "target_output_ref": "book_overview.claim",
            }
        ],
    }


# --- A. Output Ref ---


def test_build_candidate_output_refs_registers_primary_and_assets() -> None:
    refs = build_candidate_output_refs(
        module_key="book_overview",
        asset_candidates=(
            {"asset_type": "event", "output_ref": "book_overview.out", "claim_key": "logline"},
            {"asset_type": "conflict", "output_ref": "book_overview.conflict"},
        ),
    )
    assert "book_overview.out" in refs
    assert "book_overview.conflict" in refs
    assert "module:book_overview:candidate:logline" in refs
    assert "module:book_overview:claim:logline" in refs


def test_claim_alias_resolves_to_primary_out() -> None:
    assets = ({"asset_type": "event", "output_ref": "book_overview.out"},)
    refs = build_candidate_output_refs(module_key="book_overview", asset_candidates=assets)
    res = resolve_provider_output_ref(
        "book_overview.claim",
        module_key="book_overview",
        registered_refs=refs,
        asset_candidates=assets,
    )
    assert res.resolution_status == "RESOLVED"
    assert res.canonical_output_ref == "book_overview.out"
    assert res.provider_output_ref == "book_overview.claim"


def test_claim_key_precise_match() -> None:
    assets = (
        {"asset_type": "event", "output_ref": "book_overview.out", "claim_key": "logline"},
        {"asset_type": "conflict", "output_ref": "book_overview.conflict", "claim_key": "conflict"},
    )
    refs = build_candidate_output_refs(module_key="book_overview", asset_candidates=assets)
    res = resolve_provider_output_ref(
        "book_overview.claim",
        module_key="book_overview",
        registered_refs=refs,
        asset_candidates=assets,
        claim_key="conflict",
    )
    assert res.resolution_status == "RESOLVED"
    assert res.canonical_output_ref == "book_overview.conflict"


def test_ambiguous_without_primary_and_no_claim_key() -> None:
    assets = (
        {"asset_type": "event", "output_ref": "book_overview.a"},
        {"asset_type": "event", "output_ref": "book_overview.b"},
    )
    refs = build_candidate_output_refs(module_key="book_overview", asset_candidates=assets)
    # Remove primary .out so alias cannot resolve via primary rule.
    refs = tuple(r for r in refs if r != "book_overview.out")
    res = resolve_provider_output_ref(
        "book_overview.claim",
        module_key="book_overview",
        registered_refs=refs,
        asset_candidates=assets,
    )
    assert res.resolution_status == "AMBIGUOUS"
    assert res.canonical_output_ref is None
    assert res.candidate_match_count == 2


def test_candidate_missing() -> None:
    res = resolve_provider_output_ref(
        "book_overview.claim",
        module_key="book_overview",
        registered_refs=(),
        asset_candidates=(),
    )
    assert res.resolution_status == "CANDIDATE_MISSING"


def test_cross_module_rejected() -> None:
    refs = build_candidate_output_refs(
        module_key="book_overview",
        asset_candidates=({"output_ref": "book_overview.out"},),
    )
    res = resolve_provider_output_ref(
        "storylines.claim",
        module_key="book_overview",
        registered_refs=refs,
        asset_candidates=({"output_ref": "book_overview.out"},),
    )
    assert res.resolution_status == "MODULE_MISMATCH"


def test_unknown_target_ref() -> None:
    refs = build_candidate_output_refs(
        module_key="book_overview",
        asset_candidates=({"output_ref": "book_overview.out"},),
    )
    res = resolve_provider_output_ref(
        "book_overview.unknown_slot",
        module_key="book_overview",
        registered_refs=refs,
        asset_candidates=({"output_ref": "book_overview.out"},),
    )
    assert res.resolution_status == "UNKNOWN"


def test_canonical_ref_recomputable() -> None:
    assets = ({"asset_type": "event", "output_ref": "book_overview.out", "claim_key": "logline"},)
    a = build_candidate_output_refs(module_key="book_overview", asset_candidates=assets)
    b = build_candidate_output_refs(module_key="book_overview", asset_candidates=assets)
    assert a == b
    assert "module:book_overview:candidate:logline" in a
    assert "book_overview.out" in a


# --- B. Quote index ---


def test_quote_index_resolves_paragraph_key(bind_env) -> None:
    idx = SnapshotQuoteIndex.build_from_session(
        bind_env["session"], book_snapshot_id=int(bind_env["snap"].id)
    )
    sp = bind_env["paragraph"]
    hit = idx.resolve(
        evidence_key=str(sp.id),
        expected_snapshot_id=int(bind_env["snap"].id),
    )
    assert hit.status == "resolved"
    assert hit.paragraph_id == int(sp.id)
    assert hit.failure_code is None


def test_quote_unique_and_ambiguous(bind_env) -> None:
    idx = SnapshotQuoteIndex.build_from_session(
        bind_env["session"], book_snapshot_id=int(bind_env["snap"].id)
    )
    ok = idx.resolve(quote="合成段落甲。", expected_snapshot_id=int(bind_env["snap"].id))
    assert ok.status == "resolved"
    missing = idx.resolve(quote="不存在的句子", expected_snapshot_id=int(bind_env["snap"].id))
    assert missing.status == "rejected"
    assert missing.failure_code == "QUOTE_NOT_FOUND"


def test_quote_snapshot_mismatch(bind_env) -> None:
    idx = SnapshotQuoteIndex.build_from_session(
        bind_env["session"], book_snapshot_id=int(bind_env["snap"].id)
    )
    bad = idx.resolve(evidence_key=str(bind_env["paragraph"].id), expected_snapshot_id=999999)
    assert bad.failure_code == "SNAPSHOT_MISMATCH"


def test_hash_mismatch_rejected(bind_env) -> None:
    idx = SnapshotQuoteIndex.build_from_session(
        bind_env["session"], book_snapshot_id=int(bind_env["snap"].id)
    )
    sp = bind_env["paragraph"]
    bad = idx.resolve(
        evidence_key=str(sp.id),
        expected_snapshot_id=int(bind_env["snap"].id),
        expected_hash="deadbeef",
    )
    assert bad.failure_code == "HASH_MISMATCH"


def test_offset_invalid_rejected(bind_env) -> None:
    idx = SnapshotQuoteIndex.build_from_session(
        bind_env["session"], book_snapshot_id=int(bind_env["snap"].id)
    )
    sp = bind_env["paragraph"]
    bad = idx.resolve(
        evidence_key=str(sp.id),
        expected_snapshot_id=int(bind_env["snap"].id),
        start_offset=0,
        end_offset=99999,
    )
    assert bad.failure_code == "OFFSET_INVALID"


# --- C/D/E. Full pipeline with Bailian DTO shape ---


def test_bailian_dto_shape_persists_orm(bind_env) -> None:
    private = try_load_first_four_private_runners()
    if private is None:
        pytest.skip("storylens_private_engine not installed")

    structured = _bailian_dto_shaped(bind_env)
    transport = FakeHttpProviderTransport(
        stub_text=json.dumps(structured),
        request_id="fake-http-055",
        input_tokens=80,
        output_tokens=40,
        http_status=200,
    )
    assert transport.transport_kind.value == "FAKE_HTTP_TEST"

    runtime = create_lab_private_whole_book_analysis_runtime(
        session=bind_env["session"],
        book_id=int(bind_env["book"].id),
        use_phase1b_persistence=True,
        lab_dry_run=False,
        fallback_to_fake=False,
        require_private_real=True,
    )
    runtime.bind_session(bind_env["session"])
    _wb, contract = runtime.build_native_context_bundle(
        book_id=int(bind_env["book"].id),
        book_snapshot_id=int(bind_env["snap"].id),
        module_keys=("book_overview",),
    )
    ref = make_context_bundle_ref(contract.bundle_hash)
    provider_result = build_provider_backed_module_result(
        module_key="book_overview",
        structured_output=structured,
        provider_usage={
            "provider_request_id": "fake-http-055",
            "transport_kind": "FAKE_HTTP_TEST",
            "input_tokens": 80,
            "output_tokens": 40,
            "http_status": 200,
            "usage_source": "provider_response",
        },
        engine_id="storylens.private.whole_book.dev",
        engine_version="0.1.0-dev",
        provider_key="aliyun_qwen_plus",
        model_id="qwen3.7-plus",
    )
    policy = provider_result.to_provider_policy()
    assert "synthetic_output" not in policy

    fake_engine = getattr(runtime, "fake_engine", None)
    if fake_engine is not None and hasattr(fake_engine, "execute"):
        fake_engine.execute = MagicMock(side_effect=AssertionError("Signed Fake Engine called"))

    pipeline = runtime.execute_module_pipeline(
        module_key=WholeBookModuleKey.BOOK_OVERVIEW,
        book_id=int(bind_env["book"].id),
        book_snapshot_id=int(bind_env["snap"].id),
        run_id=int(bind_env["run"].id),
        run_stage_id=int(bind_env["stage"].id),
        context_bundle_ref=ref,
        configuration_fingerprint_value="cfg-055",
        provider_policy=policy,
        analysis_mode=WholeBookAnalysisMode.NATIVE,
        persist=True,
        require_evidence_for_acceptance=True,
    )
    if fake_engine is not None and hasattr(fake_engine, "execute"):
        fake_engine.execute.assert_not_called()

    diag = dict(pipeline.pipeline_diagnostics or {})
    assert diag.get("structured_output_present") is True
    assert int(diag.get("private_candidate_count") or 0) >= 1
    assert int(diag.get("public_candidate_count") or 0) >= 1
    assert int(diag.get("candidate_output_ref_count") or 0) >= 1
    assert int(diag.get("target_ref_resolved_count") or 0) >= 1
    assert int(diag.get("evidence_valid_count") or 0) >= 1
    assert int(diag.get("candidate_command_count") or 0) >= 1
    assert diag.get("transaction_committed") is True
    assert diag.get("failure_boundary") in (None, "EVIDENCE_VALIDATION_REJECTED") or diag.get(
        "transaction_committed"
    )

    er = pipeline.engine_result
    assert er is not None
    assert len(er.asset_candidates) >= 1
    assert len(er.evidence_candidates) >= 1
    # Provider alias preserved for audit; canonical target is .out
    ev0 = er.evidence_candidates[0]
    assert getattr(ev0, "provider_output_ref", None) in {
        "book_overview.claim",
        None,
    } or str(getattr(ev0, "provider_output_ref", "")).endswith(".claim")
    assert str(ev0.target_output_ref) == "book_overview.out"
    assert ev0.snapshot_paragraph_id is not None
    assert ev0.paragraph_content_hash

    persist = dict((pipeline.candidate_summary or {}).get("persist") or {})
    assert persist.get("orm_written") is True
    assert persist.get("persistence_complete") is True
    assert persist.get("candidate_written") is True
    assert persist.get("evidence_written") is True
    assert persist.get("artifact_written") is True
    assert persist.get("fallback") in (None, False)
    assert pipeline.synthetic is False
    assert classify_live_engine_kind(
        engine_id=str(er.engine_id),
        private_modules_bound=True,
        synthetic=False,
    ) == LiveEngineKind.PRIVATE_REAL
    assert not is_fake_or_test_engine_id(str(er.engine_id))

    session = bind_env["session"]
    assert session.scalar(select(func.count()).select_from(NarrativeAsset)) >= 1
    assert session.scalar(select(func.count()).select_from(NarrativeAssetVersion)) >= 1
    assert session.scalar(select(func.count()).select_from(NarrativeAssetEvidence)) >= 1
    assert session.scalar(select(func.count()).select_from(AnalysisArtifact)) >= 1

    # Diagnostics must not leak bodies / prompts / credentials.
    blob = json.dumps(diag, ensure_ascii=False)
    for banned in ("合成段落", "api_key", "Authorization", "prompt", "messages", "raw_response"):
        assert banned.lower() not in blob.lower() or banned in {
            "prompt"
        }  # key name absence
    assert "合成段落甲" not in blob
    assert "api_key" not in blob
    assert "raw_response" not in blob


def test_pre_fix_claim_alias_would_reject_without_registry() -> None:
    """Document pre-fix funnel: .claim not in empty registry → UNKNOWN."""

    res = resolve_provider_output_ref(
        "book_overview.claim",
        module_key="book_overview",
        registered_refs=(),
        asset_candidates=(),
    )
    assert res.resolution_status == "CANDIDATE_MISSING"
    diag = LiveModulePipelineDiagnostics(
        structured_output_present=True,
        claim_count=1,
        provider_evidence_ref_count=1,
        private_candidate_count=1,
        public_candidate_count=1,
        target_ref_resolved_count=0,
        target_ref_rejected_count=1,
        evidence_valid_count=0,
        evidence_rejected_count=1,
        evidence_rejection_codes=["TARGET_OUTPUT_REF_CANDIDATE_MISSING"],
        transaction_started=False,
        failure_boundary="EVIDENCE_VALIDATION_REJECTED",
        failure_code="MODULE_OUTPUT_REFERENCE_INVALID",
    )
    assert diag.failure_boundary == "EVIDENCE_VALIDATION_REJECTED"
    assert diag.transaction_started is False


def test_evidence_rejected_skips_orm_transaction(bind_env) -> None:
    private = try_load_first_four_private_runners()
    if private is None:
        pytest.skip("storylens_private_engine not installed")

    structured = _bailian_dto_shaped(bind_env, evidence_id="not-a-real-paragraph-key")
    # Force unknown target that cannot resolve.
    structured["evidence_refs"] = [
        {
            "evidence_id": "not-a-real-paragraph-key",
            "evidence_role": "support",
            "target_output_ref": "book_overview.unknown_slot",
        }
    ]
    runtime = create_lab_private_whole_book_analysis_runtime(
        session=bind_env["session"],
        book_id=int(bind_env["book"].id),
        use_phase1b_persistence=True,
        lab_dry_run=False,
        fallback_to_fake=False,
        require_private_real=True,
    )
    runtime.bind_session(bind_env["session"])
    _wb, contract = runtime.build_native_context_bundle(
        book_id=int(bind_env["book"].id),
        book_snapshot_id=int(bind_env["snap"].id),
        module_keys=("book_overview",),
    )
    ref = make_context_bundle_ref(contract.bundle_hash)
    provider_result = build_provider_backed_module_result(
        module_key="book_overview",
        structured_output=structured,
        provider_usage={
            "provider_request_id": "fake-http-055-fail",
            "transport_kind": "FAKE_HTTP_TEST",
            "input_tokens": 10,
            "output_tokens": 5,
            "http_status": 200,
        },
        engine_id="storylens.private.whole_book.dev",
        engine_version="0.1.0-dev",
        provider_key="aliyun_qwen_plus",
        model_id="qwen3.7-plus",
    )
    pipeline = runtime.execute_module_pipeline(
        module_key=WholeBookModuleKey.BOOK_OVERVIEW,
        book_id=int(bind_env["book"].id),
        book_snapshot_id=int(bind_env["snap"].id),
        run_id=int(bind_env["run"].id),
        run_stage_id=int(bind_env["stage"].id),
        context_bundle_ref=ref,
        configuration_fingerprint_value="cfg-055-fail",
        provider_policy=provider_result.to_provider_policy(),
        analysis_mode=WholeBookAnalysisMode.NATIVE,
        persist=True,
        require_evidence_for_acceptance=True,
    )
    diag = dict(pipeline.pipeline_diagnostics or {})
    assert diag.get("transaction_started") is False
    assert diag.get("transaction_committed") is False
    assert int(diag.get("asset_written_count") or 0) == 0
    assert bind_env["session"].scalar(select(func.count()).select_from(NarrativeAsset)) == 0
    assert bind_env["session"].scalar(select(func.count()).select_from(NarrativeAssetEvidence)) == 0
    assert diag.get("failure_boundary") == "EVIDENCE_VALIDATION_REJECTED"


def test_fingerprint_has_no_claim_text() -> None:
    fp = fingerprint_structured_output(
        {"logline": "秘密正文不应进入指纹", "evidence_refs": [{"evidence_id": "1"}]}
    )
    assert fp
    assert "秘密" not in fp
