"""Phase 2B-R1 CHG-056 — BookOverview DTO semantic candidate mapping (Public)."""

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
from app.narrative_core.services.private_whole_book_analysis_runtime import (
    create_lab_private_whole_book_analysis_runtime,
    try_load_first_four_private_runners,
)
from app.narrative_core.services.provider_backed_module_result import (
    build_provider_backed_module_result,
)
from app.narrative_core.services.provider_transport_kind import FakeHttpProviderTransport
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
    db = _fk_engine(f"sqlite:///{tmp_path / 'chg056.db'}")
    Base.metadata.create_all(db)
    apply_narrative_phase1p_migrations(db)
    apply_narrative_phase1bp_migrations(db)
    factory = sessionmaker(bind=db, autoflush=False, expire_on_commit=False)
    session = factory()
    book = Book(
        title="CHG056 Mapping",
        source_file_name="chg056.txt",
        source_file_hash="f" * 64,
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
        input_hash="b" * 64,
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
    yield {
        "session": session,
        "book": book,
        "snap": snap,
        "run": run,
        "stage": stage,
        "paragraph": paragraphs[0],
        "chapter": chapter,
    }
    session.close()


def _synthetic_dto(env: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    sp = env["paragraph"]
    base = {
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
                "evidence_id": str(sp.id),
                "evidence_role": "support",
                "target_output_ref": "book_overview.claim",
            }
        ],
    }
    base.update(overrides)
    return base


def _run_pipeline(env: dict[str, Any], structured: dict[str, Any], *, persist: bool = True):
    private = try_load_first_four_private_runners()
    if private is None:
        pytest.skip("storylens_private_engine not installed")

    transport = FakeHttpProviderTransport(
        stub_text=json.dumps(structured),
        request_id="fake-http-056",
        input_tokens=90,
        output_tokens=45,
        http_status=200,
    )
    assert transport.transport_kind.value == "FAKE_HTTP_TEST"

    runtime = create_lab_private_whole_book_analysis_runtime(
        session=env["session"],
        book_id=int(env["book"].id),
        use_phase1b_persistence=True,
        lab_dry_run=False,
        fallback_to_fake=False,
        require_private_real=True,
    )
    runtime.bind_session(env["session"])
    _wb, contract = runtime.build_native_context_bundle(
        book_id=int(env["book"].id),
        book_snapshot_id=int(env["snap"].id),
        module_keys=("book_overview",),
    )
    ref = make_context_bundle_ref(contract.bundle_hash)
    provider_result = build_provider_backed_module_result(
        module_key="book_overview",
        structured_output=structured,
        provider_usage={
            "provider_request_id": "fake-http-056",
            "transport_kind": "FAKE_HTTP_TEST",
            "input_tokens": 90,
            "output_tokens": 45,
            "http_status": 200,
            "usage_source": "provider_response",
        },
        engine_id="storylens.private.whole_book.dev",
        engine_version="0.1.0-dev",
        provider_key="aliyun_qwen_plus",
        model_id="qwen3.7-plus",
    )
    policy = provider_result.to_provider_policy()
    fake_engine = getattr(runtime, "fake_engine", None)
    if fake_engine is not None and hasattr(fake_engine, "execute"):
        fake_engine.execute = MagicMock(side_effect=AssertionError("Signed Fake Engine called"))

    pipeline = runtime.execute_module_pipeline(
        module_key=WholeBookModuleKey.BOOK_OVERVIEW,
        book_id=int(env["book"].id),
        book_snapshot_id=int(env["snap"].id),
        run_id=int(env["run"].id),
        run_stage_id=int(env["stage"].id),
        context_bundle_ref=ref,
        configuration_fingerprint_value="cfg-056",
        provider_policy=policy,
        analysis_mode=WholeBookAnalysisMode.NATIVE,
        persist=persist,
        require_evidence_for_acceptance=True,
    )
    return pipeline, transport


def test_typed_dto_maps_and_persists(bind_env) -> None:
    structured = _synthetic_dto(bind_env)
    pipeline, transport = _run_pipeline(bind_env, structured)
    assert transport.transport_kind.value == "FAKE_HTTP_TEST"
    diag = dict(pipeline.pipeline_diagnostics or {})
    assert diag.get("structured_output_present") is True
    assert diag.get("structured_output_schema") == "BookOverviewResultDto"
    assert diag.get("dto_mapper_status") == "mapped"
    assert int(diag.get("semantic_source_field_count") or 0) >= 1
    assert int(diag.get("semantic_claim_count") or 0) >= 1
    assert int(diag.get("private_candidate_count") or 0) >= 1
    assert int(diag.get("public_candidate_count") or 0) >= 1
    assert int(diag.get("provider_evidence_ref_count") or 0) >= 1
    assert int(diag.get("target_ref_resolved_count") or 0) >= 1
    assert int(diag.get("evidence_valid_count") or 0) >= 1
    assert int(diag.get("candidate_command_count") or 0) >= 1
    assert int(diag.get("evidence_command_count") or 0) >= 1
    assert diag.get("transaction_committed") is True
    persist = dict((pipeline.candidate_summary or {}).get("persist") or {})
    assert persist.get("persistence_complete") is True
    session = bind_env["session"]
    assert session.scalar(select(func.count()).select_from(NarrativeAsset)) >= 1
    assert session.scalar(select(func.count()).select_from(NarrativeAssetVersion)) >= 1
    assert session.scalar(select(func.count()).select_from(NarrativeAssetEvidence)) >= 1
    assert session.scalar(select(func.count()).select_from(AnalysisArtifact)) >= 1
    safe = json.dumps(diag, ensure_ascii=False)
    assert "合成" not in safe
    assert "credential" not in safe.lower()


def test_nested_wrapper_rejected_fail_closed(bind_env) -> None:
    """CHG-057: undeclared BookOverviewResultDto wrapper must not be unwrapped."""

    sp = bind_env["paragraph"]
    structured = {
        "BookOverviewResultDto": {
            "logline": "嵌套合成总览",
            "premise": "嵌套合成前提",
            "centralQuestion": "嵌套合成问题",
            "primaryConflict": "嵌套合成冲突",
            "structureSummary": "嵌套合成结构",
            "endingState": "unknown",
            "evidenceRefs": [
                {
                    "evidenceId": str(sp.id),
                    "evidenceRole": "support",
                    "targetOutputRef": "book_overview.claim",
                }
            ],
            "synthetic": False,
        }
    }
    pipeline, _ = _run_pipeline(bind_env, structured)
    diag = dict(pipeline.pipeline_diagnostics or {})
    assert int(diag.get("semantic_claim_count") or 0) == 0
    assert int(diag.get("private_candidate_count") or 0) == 0
    assert diag.get("transaction_committed") is not True


def test_flat_camel_case_aliases_persist(bind_env) -> None:
    sp = bind_env["paragraph"]
    structured = {
        "logline": "camel合成总览",
        "premise": "camel合成前提",
        "centralQuestion": "camel合成问题",
        "primaryConflict": "camel合成冲突",
        "structureSummary": "camel合成结构",
        "endingState": "unknown",
        "protagonist_asset_id": None,
        "major_storyline_ids": [],
        "evidenceRefs": [
            {
                "evidenceId": str(sp.id),
                "evidenceRole": "support",
                "targetOutputRef": "book_overview.claim",
            }
        ],
        "confidence": 0.55,
    }
    pipeline, _ = _run_pipeline(bind_env, structured)
    diag = dict(pipeline.pipeline_diagnostics or {})
    assert int(diag.get("semantic_claim_count") or 0) >= 1
    assert int(diag.get("private_candidate_count") or 0) >= 1
    assert diag.get("transaction_committed") is True


def test_empty_semantic_fields_fail_closed(bind_env) -> None:
    structured = _synthetic_dto(
        bind_env,
        logline="",
        premise="",
        central_question="",
        primary_conflict="",
        structure_summary="",
        ending_state="",
        evidence_refs=[],
    )
    pipeline, _ = _run_pipeline(bind_env, structured, persist=True)
    diag = dict(pipeline.pipeline_diagnostics or {})
    assert int(diag.get("private_candidate_count") or 0) == 0
    assert int(diag.get("candidate_command_count") or 0) == 0
    assert diag.get("transaction_committed") is not True
    assert diag.get("failure_boundary") in {
        "PRIVATE_TRANSLATION_EMPTY",
        "CANDIDATE_COMMAND_EMPTY",
        "PROVIDER_RESULT_EMPTY",
    }
    session = bind_env["session"]
    assert session.scalar(select(func.count()).select_from(NarrativeAsset)) == 0
    assert session.scalar(select(func.count()).select_from(NarrativeAssetEvidence)) == 0


def test_evidence_refs_lost_fail_closed(bind_env) -> None:
    structured = _synthetic_dto(bind_env, evidence_refs=[])
    pipeline, _ = _run_pipeline(bind_env, structured)
    diag = dict(pipeline.pipeline_diagnostics or {})
    # Candidates may exist, but evidence path must fail closed for live acceptance.
    assert diag.get("transaction_committed") is not True or int(
        diag.get("evidence_valid_count") or 0
    ) == 0
    session = bind_env["session"]
    assert session.scalar(select(func.count()).select_from(NarrativeAssetEvidence)) == 0
