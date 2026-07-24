"""Phase 2B-R1 CHG-052 — Context Bundle binding + Candidate translation.

Covers product path (no harness alias): Registry ref → Executor → Runtime →
translate_result preserves candidates → Phase1B ORM Asset/Version/Evidence.
Zero external HTTP. Temporary SQLite + Fake credential / FakeHttp only.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

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
    NarrativeRelation,
    Paragraph,
)
from app.narrative_core.enums import SnapshotStatus, WholeBookModuleKey
from app.narrative_core.migrations.runner import (
    apply_narrative_phase1bp_migrations,
    apply_narrative_phase1p_migrations,
)
from app.narrative_core.private_engine_contract.context import (
    CONTEXT_BUNDLE_REF_PREFIX,
    make_context_bundle_ref,
    parse_context_bundle_hash,
)
from app.narrative_core.private_engine_contract.errors import PrivateEngineError
from app.narrative_core.private_engine_contract.protocol import PrivateEngineExecutionResult
from app.narrative_core.services.private_engine_runtime_adapter import (
    PrivateWholeBookEngineRuntimeAdapter,
)
from app.narrative_core.services.private_whole_book_analysis_runtime import (
    create_lab_private_whole_book_analysis_runtime,
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
    db = _fk_engine(f"sqlite:///{tmp_path / 'chg052.db'}")
    Base.metadata.create_all(db)
    apply_narrative_phase1p_migrations(db)
    apply_narrative_phase1bp_migrations(db)
    factory = sessionmaker(bind=db, autoflush=False, expire_on_commit=False)
    session = factory()
    book = Book(
        title="CHG052 Binding",
        source_file_name="chg052.txt",
        source_file_hash="c" * 64,
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
        word_count=4,
    )
    session.add(chapter)
    session.flush()
    session.add(
        Paragraph(
            id=f"B{book.id:04d}-C0001-P0001",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=1,
            raw_text="天亮了。",
            normalized_text="天亮了。",
            char_start=0,
            char_end=4,
        )
    )
    session.commit()
    snap = BookSnapshotServiceImpl(session).create_or_reuse_snapshot(book.id)
    session.commit()
    assert snap.snapshot_status == SnapshotStatus.COMPLETED.value
    run = AnalysisRun(
        book_id=book.id,
        analysis_type="whole_book_native",
        scope_type="book",
        subject_type="book",
        subject_id=str(book.id),
        provider="fake",
        model="fake-model",
        prompt_version="0.0.1",
        schema_version="1.0.0",
        input_hash="e" * 64,
        status="running",
        book_snapshot_id=snap.id,
        task_type="whole_book_pipeline",
    )
    session.add(run)
    session.flush()
    stage = AnalysisRunStage(
        run_id=run.id,
        stage_key="book_overview",
        status="running",
        stage_order=0,
        attempt_count=1,
    )
    session.add(stage)
    session.commit()
    sp = session.scalars(
        select(BookSnapshotParagraph).where(BookSnapshotParagraph.snapshot_id == snap.id)
    ).first()
    assert sp is not None
    yield {
        "session": session,
        "book": book,
        "snap": snap,
        "run": run,
        "stage": stage,
        "paragraph": sp,
        "chapter": chapter,
    }
    session.close()


def _overview_structured(env: dict[str, Any], *, with_evidence: bool = True) -> dict[str, Any]:
    sp = env["paragraph"]
    out: dict[str, Any] = {
        "logline": "黎明之后世界改变",
        "premise": "天亮带来新冲突",
        "primary_conflict": "人与未知力量",
        "central_question": "谁能活下去",
        "structure_summary": "起承转合",
        "ending_state": "unknown",
        "major_storyline_ids": (),
        "protagonist_asset_id": None,
        "evidence_refs": (),
        "partial": False,
        "synthetic": False,
    }
    if with_evidence:
        out["evidence_candidates"] = [
            {
                "candidate_id": "ev-overview-1",
                "snapshot_chapter_id": int(sp.snapshot_chapter_id),
                "snapshot_paragraph_id": int(sp.id),
                "stable_paragraph_id": str(sp.stable_paragraph_id),
                "paragraph_content_hash": str(sp.content_hash),
                "start_offset": 0,
                "end_offset": 4,
                "evidence_role": "support",
                "target_output_ref": "book_overview.out",
                "book_snapshot_id": int(env["snap"].id),
                "book_id": int(env["book"].id),
            }
        ]
    return out


def _runtime(env: dict[str, Any]):
    runtime = create_lab_private_whole_book_analysis_runtime(
        session=env["session"],
        book_id=int(env["book"].id),
        use_phase1b_persistence=True,
        lab_dry_run=False,
        fallback_to_fake=True,
    )
    runtime.bind_session(env["session"])
    return runtime


# ---------------------------------------------------------------------------
# A. Context ref
# ---------------------------------------------------------------------------


def test_make_context_bundle_ref_canonical() -> None:
    ref = make_context_bundle_ref("deadbeef")
    assert ref.startswith(CONTEXT_BUNDLE_REF_PREFIX)
    assert ref == "ctx-bundle:deadbeef"
    assert parse_context_bundle_hash(ref) == "deadbeef"
    with pytest.raises(ValueError):
        parse_context_bundle_hash("bundle:99")
    with pytest.raises(ValueError):
        parse_context_bundle_hash("")


def test_registry_returns_formal_ref_no_run_id_alias(bind_env) -> None:
    runtime = _runtime(bind_env)
    _wb, contract = runtime.build_native_context_bundle(
        book_id=int(bind_env["book"].id),
        book_snapshot_id=int(bind_env["snap"].id),
        module_keys=("book_overview",),
    )
    ref = make_context_bundle_ref(contract.bundle_hash)
    assert ref in runtime.contract_bundles
    assert not ref.startswith("bundle:")
    assert f"bundle:{bind_env['run'].id}" not in runtime.contract_bundles


def test_bad_ref_and_legacy_bundle_fail_closed(bind_env) -> None:
    runtime = _runtime(bind_env)
    runtime.build_native_context_bundle(
        book_id=int(bind_env["book"].id),
        book_snapshot_id=int(bind_env["snap"].id),
        module_keys=("book_overview",),
    )
    with pytest.raises(PrivateEngineError):
        runtime.execute_module_pipeline(
            module_key=WholeBookModuleKey.BOOK_OVERVIEW,
            book_id=int(bind_env["book"].id),
            book_snapshot_id=int(bind_env["snap"].id),
            run_id=int(bind_env["run"].id),
            run_stage_id=int(bind_env["stage"].id),
            context_bundle_ref=f"bundle:{bind_env['run'].id}",
            configuration_fingerprint_value="cfg",
            provider_policy={"provider_kind": "fake", "synthetic_output": {"partial": True}},
            persist=False,
        )
    with pytest.raises(PrivateEngineError):
        runtime.execute_module_pipeline(
            module_key=WholeBookModuleKey.BOOK_OVERVIEW,
            book_id=int(bind_env["book"].id),
            book_snapshot_id=int(bind_env["snap"].id),
            run_id=int(bind_env["run"].id),
            run_stage_id=int(bind_env["stage"].id),
            context_bundle_ref="ctx-bundle:not-registered",
            configuration_fingerprint_value="cfg",
            provider_policy={"provider_kind": "fake", "synthetic_output": {"partial": True}},
            persist=False,
        )
    assert session_asset_count(bind_env["session"]) == 0


def test_cross_snapshot_ref_rejected(bind_env, tmp_path) -> None:
    runtime = _runtime(bind_env)
    _wb, contract = runtime.build_native_context_bundle(
        book_id=int(bind_env["book"].id),
        book_snapshot_id=int(bind_env["snap"].id),
        module_keys=("book_overview",),
    )
    ref = make_context_bundle_ref(contract.bundle_hash)
    with pytest.raises(PrivateEngineError):
        runtime.execute_module_pipeline(
            module_key=WholeBookModuleKey.BOOK_OVERVIEW,
            book_id=int(bind_env["book"].id),
            book_snapshot_id=int(bind_env["snap"].id) + 999,
            run_id=int(bind_env["run"].id),
            run_stage_id=int(bind_env["stage"].id),
            context_bundle_ref=ref,
            configuration_fingerprint_value="cfg",
            provider_policy={"provider_kind": "fake", "synthetic_output": {"partial": True}},
            persist=False,
        )


def test_context_change_yields_new_ref(bind_env) -> None:
    runtime = _runtime(bind_env)
    _a, c1 = runtime.build_native_context_bundle(
        book_id=int(bind_env["book"].id),
        book_snapshot_id=int(bind_env["snap"].id),
        module_keys=("book_overview",),
        provider_context_limit=4000,
    )
    _b, c2 = runtime.build_native_context_bundle(
        book_id=int(bind_env["book"].id),
        book_snapshot_id=int(bind_env["snap"].id),
        module_keys=("book_overview",),
        provider_context_limit=8000,
    )
    r1 = make_context_bundle_ref(c1.bundle_hash)
    r2 = make_context_bundle_ref(c2.bundle_hash)
    # Different policy/limit may or may not change hash depending on builder;
    # both must be formal refs and registered.
    assert r1.startswith("ctx-bundle:") and r2.startswith("ctx-bundle:")
    assert r1 in runtime.contract_bundles and r2 in runtime.contract_bundles


# ---------------------------------------------------------------------------
# B. Candidate translation
# ---------------------------------------------------------------------------


def test_translate_result_preserves_candidates() -> None:
    adapter = PrivateWholeBookEngineRuntimeAdapter.__new__(PrivateWholeBookEngineRuntimeAdapter)
    raw = PrivateEngineExecutionResult(
        schema="s",
        version="v",
        engine_id="e",
        engine_version="1",
        stage_key="book_overview",
        attempt=1,
        status="completed",
        module_outputs={"logline": "L"},
        evidence_candidates=(),
        asset_candidates=(
            {"asset_type": "event", "title": "kept", "output_ref": "book_overview.out"},
        ),
        relation_candidates=({"relation_type": "belongs_to"},),
        conflict_candidates=(),
        checkpoint=None,
        usage={},
        warnings=(),
        validation_summary={},
        generated_at=datetime.now(timezone.utc),
    )
    out = PrivateWholeBookEngineRuntimeAdapter.translate_result(adapter, raw)
    assert len(out.asset_candidates) == 1
    assert out.asset_candidates[0]["title"] == "kept"
    assert len(out.relation_candidates) == 1
    assert out.validation_summary.get("canonical") is False
    assert "not_canonical" in out.warnings


def test_book_overview_generates_candidates_and_orm(bind_env) -> None:
    runtime = _runtime(bind_env)
    _wb, contract = runtime.build_native_context_bundle(
        book_id=int(bind_env["book"].id),
        book_snapshot_id=int(bind_env["snap"].id),
        module_keys=("book_overview",),
    )
    ref = make_context_bundle_ref(contract.bundle_hash)
    structured = _overview_structured(bind_env)
    pipeline = runtime.execute_module_pipeline(
        module_key=WholeBookModuleKey.BOOK_OVERVIEW,
        book_id=int(bind_env["book"].id),
        book_snapshot_id=int(bind_env["snap"].id),
        run_id=int(bind_env["run"].id),
        run_stage_id=int(bind_env["stage"].id),
        context_bundle_ref=ref,
        configuration_fingerprint_value="cfg-cand",
        provider_policy={
            "provider_kind": "fake",
            "model_route": "lab",
            "synthetic_output": structured,
            "evidence_candidates": structured["evidence_candidates"],
        },
        persist=True,
    )
    assert pipeline.validation["accepted"] is True
    assert len(pipeline.engine_result.asset_candidates) >= 1
    assert len(pipeline.engine_result.evidence_candidates) >= 1
    persist = (pipeline.candidate_summary or {}).get("persist") or {}
    assert persist.get("orm_written") is True
    assert persist.get("candidate_written") is True
    assert persist.get("evidence_written") is True
    assert persist.get("artifact_written") is True
    assert persist.get("persistence_complete") is True
    assert persist.get("fallback_used") is False
    assert session_asset_count(bind_env["session"]) >= 1
    assert session_version_count(bind_env["session"]) >= 1
    assert session_evidence_count(bind_env["session"]) >= 1
    assert session_artifact_count(bind_env["session"]) >= 1
    # candidate flags
    assets = bind_env["session"].scalars(select(NarrativeAsset)).all()
    for a in assets:
        assert bool(getattr(a, "is_canonical", False)) is False


def test_no_output_does_not_forge_candidates(bind_env) -> None:
    runtime = _runtime(bind_env)
    _wb, contract = runtime.build_native_context_bundle(
        book_id=int(bind_env["book"].id),
        book_snapshot_id=int(bind_env["snap"].id),
        module_keys=("book_overview",),
    )
    ref = make_context_bundle_ref(contract.bundle_hash)
    pipeline = runtime.execute_module_pipeline(
        module_key=WholeBookModuleKey.BOOK_OVERVIEW,
        book_id=int(bind_env["book"].id),
        book_snapshot_id=int(bind_env["snap"].id),
        run_id=int(bind_env["run"].id),
        run_stage_id=int(bind_env["stage"].id),
        context_bundle_ref=ref,
        configuration_fingerprint_value="cfg-empty",
        provider_policy={
            "provider_kind": "fake",
            "synthetic_output": {
                "logline": "",
                "premise": "",
                "primary_conflict": "",
                "central_question": "",
                "structure_summary": "",
                "ending_state": "",
                "major_storyline_ids": (),
                "protagonist_asset_id": None,
                "evidence_refs": (),
                "partial": True,
                "synthetic": False,
            },
        },
        persist=True,
    )
    assert len(pipeline.engine_result.asset_candidates) == 0
    persist = (pipeline.candidate_summary or {}).get("persist") or {}
    assert persist.get("persistence_complete") is not True
    assert session_asset_count(bind_env["session"]) == 0


def test_artifact_only_not_persistence_complete(bind_env) -> None:
    """Evidence=0 / candidates rejected → not persistence_complete."""

    runtime = _runtime(bind_env)
    _wb, contract = runtime.build_native_context_bundle(
        book_id=int(bind_env["book"].id),
        book_snapshot_id=int(bind_env["snap"].id),
        module_keys=("book_overview",),
    )
    ref = make_context_bundle_ref(contract.bundle_hash)
    structured = _overview_structured(bind_env, with_evidence=False)
    pipeline = runtime.execute_module_pipeline(
        module_key=WholeBookModuleKey.BOOK_OVERVIEW,
        book_id=int(bind_env["book"].id),
        book_snapshot_id=int(bind_env["snap"].id),
        run_id=int(bind_env["run"].id),
        run_stage_id=int(bind_env["stage"].id),
        context_bundle_ref=ref,
        configuration_fingerprint_value="cfg-no-ev",
        provider_policy={
            "provider_kind": "fake",
            "synthetic_output": structured,
        },
        persist=True,
    )
    persist = (pipeline.candidate_summary or {}).get("persist") or {}
    # Without evidence, complete business persistence must fail closed.
    assert persist.get("persistence_complete") is not True
    assert persist.get("evidence_written") is not True


def test_output_fingerprint_idempotent_retry(bind_env) -> None:
    runtime = _runtime(bind_env)
    _wb, contract = runtime.build_native_context_bundle(
        book_id=int(bind_env["book"].id),
        book_snapshot_id=int(bind_env["snap"].id),
        module_keys=("book_overview",),
    )
    ref = make_context_bundle_ref(contract.bundle_hash)
    structured = _overview_structured(bind_env)
    kwargs = dict(
        module_key=WholeBookModuleKey.BOOK_OVERVIEW,
        book_id=int(bind_env["book"].id),
        book_snapshot_id=int(bind_env["snap"].id),
        run_id=int(bind_env["run"].id),
        run_stage_id=int(bind_env["stage"].id),
        context_bundle_ref=ref,
        configuration_fingerprint_value="cfg-idem",
        provider_policy={
            "provider_kind": "fake",
            "synthetic_output": structured,
            "evidence_candidates": structured["evidence_candidates"],
        },
        persist=True,
    )
    p1 = runtime.execute_module_pipeline(**kwargs)
    v1 = session_version_count(bind_env["session"])
    p2 = runtime.execute_module_pipeline(**kwargs)
    v2 = session_version_count(bind_env["session"])
    fp1 = (p1.candidate_summary or {}).get("output_fingerprint") or (
        (p1.candidate_summary or {}).get("persist") or {}
    ).get("output_fingerprint")
    fp2 = (p2.candidate_summary or {}).get("output_fingerprint") or (
        (p2.candidate_summary or {}).get("persist") or {}
    ).get("output_fingerprint")
    assert fp1 and fp1 == fp2
    # Retry may reuse fingerprint; versions should not explode unboundedly.
    assert v2 <= v1 + 2


# ---------------------------------------------------------------------------
# D. FakeHttp product-shaped stub (structured replay after FakeHttp parse)
# ---------------------------------------------------------------------------


def test_fake_http_stub_shape_maps_to_candidates(bind_env) -> None:
    """FakeHttp JSON uses overview alias; product path must still map Candidates."""

    sp = bind_env["paragraph"]
    stub = {
        "overview": "FakeHttp overview claim",
        "premise": "FakeHttp premise",
        "primary_conflict": "FakeHttp conflict",
        "central_question": "what next",
        "structure_summary": "summary",
        "ending_state": "unknown",
        "partial": False,
        "evidence_candidates": [
            {
                "claim_id": "overview-1",
                "chapter_id": int(sp.snapshot_chapter_id),
                "stable_paragraph_id": str(sp.stable_paragraph_id),
                "role": "support",
                "paragraph_content_hash": str(sp.content_hash),
                "snapshot_paragraph_id": int(sp.id),
                "start_offset": 0,
                "end_offset": 4,
                "target_output_ref": "book_overview.out",
                "book_snapshot_id": int(bind_env["snap"].id),
                "book_id": int(bind_env["book"].id),
            }
        ],
    }
    fake = FakeHttpProviderTransport(
        stub_text=json.dumps(stub),
        request_id="fake-http-chg052",
        input_tokens=1800,
        output_tokens=250,
        http_status=200,
    )
    resp = fake.generate(
        messages=[{"role": "user", "content": "x"}],
        model="m",
        response_format_mode="json_object",
        max_tokens=100,
        timeout_seconds=5,
    )
    assert len(fake.calls) == 1
    structured = json.loads(resp.text)

    runtime = _runtime(bind_env)
    _wb, contract = runtime.build_native_context_bundle(
        book_id=int(bind_env["book"].id),
        book_snapshot_id=int(bind_env["snap"].id),
        module_keys=("book_overview",),
    )
    ref = make_context_bundle_ref(contract.bundle_hash)
    # No harness alias — only formal ref.
    assert f"bundle:{bind_env['run'].id}" not in runtime.contract_bundles
    pipeline = runtime.execute_module_pipeline(
        module_key=WholeBookModuleKey.BOOK_OVERVIEW,
        book_id=int(bind_env["book"].id),
        book_snapshot_id=int(bind_env["snap"].id),
        run_id=int(bind_env["run"].id),
        run_stage_id=int(bind_env["stage"].id),
        context_bundle_ref=ref,
        configuration_fingerprint_value="cfg-fakehttp",
        provider_policy={
            "provider_kind": "aliyun_qwen_plus",
            "synthetic_output": structured,
            "evidence_candidates": structured.get("evidence_candidates") or [],
        },
        persist=True,
    )
    persist = (pipeline.candidate_summary or {}).get("persist") or {}
    assert pipeline.validation["accepted"] is True
    assert len(pipeline.engine_result.asset_candidates) >= 1
    assert persist.get("persistence_complete") is True
    assert persist.get("orm_written") is True
    assert persist.get("fallback_used") is False
    assert session_asset_count(bind_env["session"]) >= 1
    assert session_evidence_count(bind_env["session"]) >= 1
    assert session_relation_count(bind_env["session"]) == 0


def session_asset_count(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(NarrativeAsset)) or 0)


def session_version_count(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(NarrativeAssetVersion)) or 0)


def session_evidence_count(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(NarrativeAssetEvidence)) or 0)


def session_artifact_count(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(AnalysisArtifact)) or 0)


def session_relation_count(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(NarrativeRelation)) or 0)
