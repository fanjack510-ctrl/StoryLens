"""Phase 2B-R Agent T — first four real modules + candidate persistence (CHG-043).

Synthetic / Fake Gateway only. No live Provider. No gate flips.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app import __version__

from app.db.models import (
    AnalysisArtifact,
    AnalysisRun,
    Base,
    Book,
    Chapter,
    NarrativeAssetVersion,
    Paragraph,
)
from app.narrative_core.contracts.api_dto import WHOLE_BOOK_RUNS_ENDPOINT_DISABLED
from app.narrative_core.enums import AnalysisScopeType, AnalysisType, SnapshotStatus, WholeBookModuleKey
from app.narrative_core.migrations.runner import (
    apply_narrative_phase1bp_migrations,
    apply_narrative_phase1p_migrations,
)
from app.narrative_core.private_engine_contract.candidate import CandidatePersistenceContract
from app.narrative_core.private_engine_contract.protocol import PrivateEngineExecutionResult
from app.narrative_core.private_engine_contract.validation import ModuleOutputValidationReport
from app.narrative_core.run_shell_contract.mock_lab import WHOLE_BOOK_MOCK_LAB_ENABLED
from app.narrative_core.services.candidate_persistence_adapter import (
    Phase1BCandidatePersistenceSink,
    RecordingCandidatePersistenceSink,
    provenance_attributes,
)
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl
from app.narrative_core.services.whole_book_candidate_builder import (
    AssetCandidateCommand,
    ModuleCandidateBuildResult,
    StageArtifactPayload,
)
from app.narrative_core.services.whole_book_engine_registry import PRODUCTION_DEFAULT_ENGINE_ID
from app.narrative_core.services.whole_book_evaluation_harness import WholeBookEvaluationHarness
from app.narrative_core.services.whole_book_evidence_pipeline import EvidenceCandidateBuilder
from app.narrative_core.services.whole_book_module_runner import (
    FakeBookOverviewRunner,
    PrivateModuleRunnerAdapter,
    build_first_four_fake_runners,
    build_private_module_runner_adapters,
    make_execution_request,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
VERSION = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()


def _fk_engine(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


@pytest.fixture()
def session(tmp_path):
    db = _fk_engine(f"sqlite:///{tmp_path / 'phase2br_t.db'}")
    Base.metadata.create_all(db)
    apply_narrative_phase1p_migrations(db)
    apply_narrative_phase1bp_migrations(db)
    factory = sessionmaker(bind=db, autoflush=False, expire_on_commit=False)
    s = factory()
    yield s
    s.close()


def _seed_book_run_snapshot(session: Session) -> tuple[Book, AnalysisRun, int]:
    book = Book(
        title="Phase2BR Synthetic",
        source_file_name="synth.txt",
        source_file_hash="b" * 64,
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
    session.flush()
    snapshot = BookSnapshotServiceImpl(session).create_or_reuse_snapshot(book.id)
    assert snapshot.snapshot_status == SnapshotStatus.COMPLETED.value
    run = AnalysisRun(
        book_id=book.id,
        analysis_type=AnalysisType.WHOLE_BOOK_NATIVE.value,
        scope_type=AnalysisScopeType.BOOK.value,
        subject_type="book",
        subject_id=str(book.id),
        provider="fake",
        model="fake-model",
        prompt_version="0.0.1-fake",
        schema_version="1.0.0",
        input_hash="d" * 64,
        status="running",
        book_snapshot_id=snapshot.id,
        task_type="whole_book_pipeline",
    )
    session.add(run)
    session.commit()
    return book, run, int(snapshot.id)


def _contract(**overrides: Any) -> CandidatePersistenceContract:
    base = dict(
        run_id=1,
        run_stage_id=1,
        book_snapshot_id=1,
        engine_id="storylens.private.whole_book.dev",
        engine_version="0.1.0-dev",
        module_key="structure_stages",
        module_version="1.0.0",
        prompt_pack_id="storylens.private.prompt_pack.structure_stages",
        prompt_pack_version="1.0.0",
        configuration_fingerprint="cfg-fp",
        output_fingerprint="out-fp" + ("0" * 48),
        evidence_refs=("ev-1",),
        mock=True,
        private_engine=True,
        write_kind="candidate_asset_version",
    )
    base.update(overrides)
    return CandidatePersistenceContract(**base)


def test_gates_remain_frozen() -> None:
    assert VERSION == __version__
    assert WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is True
    assert WHOLE_BOOK_MOCK_LAB_ENABLED is False
    assert PRODUCTION_DEFAULT_ENGINE_ID is None
    edition = (REPO_ROOT / "apps/desktop/src/services/productEdition.ts").read_text(encoding="utf-8")
    assert "PRO_CAPABILITIES_SHIPPED = false" in edition or "PRO_CAPABILITIES_SHIPPED=false" in edition.replace(
        " ", ""
    )


def test_fake_runners_still_available() -> None:
    runners = build_first_four_fake_runners()
    assert set(runners) == {
        WholeBookModuleKey.BOOK_OVERVIEW,
        WholeBookModuleKey.STRUCTURE_STAGES,
        WholeBookModuleKey.CHAPTER_FUNCTIONS,
        WholeBookModuleKey.STORYLINES,
    }
    req = make_execution_request(
        provider_policy={"provider_kind": "fake", "synthetic_output": {"empty_dto": True, "skip_provider": True}}
    )
    result = runners[WholeBookModuleKey.BOOK_OVERVIEW].execute(req)
    assert result.module_outputs.get("fake") is True


@dataclass
class _StubPrivateRunner:
    module_key: str = "book_overview"

    def execute(self, request):  # noqa: ANN001
        return PrivateEngineExecutionResult(
            schema="storylens.private_engine.result.v1",
            version="0.1.0-dev",
            engine_id="storylens.private.whole_book.dev",
            engine_version="0.1.0-dev",
            stage_key="analyze_structure",
            attempt=0,
            status="completed",
            module_outputs={
                "module_key": self.module_key,
                "partial": True,
                "private_engine": True,
                "fake": False,
                "non_production": True,
                "force_single_protagonist": False,
                "logline": "",
                "premise": "",
                "central_question": "",
                "primary_conflict": "",
                "protagonist_asset_id": None,
                "major_storyline_ids": (),
                "structure_summary": "",
                "ending_state": "unknown",
                "evidence_refs": (),
                "book_id": request.book_id,
                "book_snapshot_id": request.book_snapshot_id,
                "direct_provider_http": False,
                "credential_read": False,
            },
            evidence_candidates=(),
            asset_candidates=(),
            relation_candidates=(),
            conflict_candidates=(),
            checkpoint=None,
            usage={"private": True},
            warnings=("stub",),
            validation_summary={"accepted": False, "canonical": False},
            generated_at=datetime(2026, 7, 24, 0, 0, 0),
        )

    def validate_output(self, result):  # noqa: ANN001
        return ModuleOutputValidationReport(
            schema_valid=True,
            references_valid=True,
            evidence_valid=True,
            snapshot_valid=True,
            duplicate_summary={},
            conflict_summary={},
            missing_fields=(),
            invalid_refs=(),
            evidence_coverage={},
            warnings=("stub",),
            accepted=False,
            retry_recommended=False,
        )

    def collect_evidence(self, request):  # noqa: ANN001
        _ = request
        return ()

    def health_check(self, module_key):  # noqa: ANN001
        return type(
            "H",
            (),
            {
                "module_key": str(getattr(module_key, "value", module_key)),
                "healthy": True,
                "prompt_pack_version": "1.0.0",
                "details": ("stub_private",),
            },
        )()


def test_private_module_runner_adapter_delegates() -> None:
    adapters = build_private_module_runner_adapters(
        private_runners={WholeBookModuleKey.BOOK_OVERVIEW: _StubPrivateRunner()},
        fallback_to_fake=False,
    )
    req = make_execution_request(module_key=WholeBookModuleKey.BOOK_OVERVIEW)
    result = adapters[WholeBookModuleKey.BOOK_OVERVIEW].execute(req)
    assert result.module_outputs.get("private_adapter") is True
    assert result.module_outputs.get("private_engine") is True
    assert result.module_outputs.get("fake") is False
    assert result.module_outputs.get("direct_provider_http") is False
    health = adapters[WholeBookModuleKey.BOOK_OVERVIEW].health_check(WholeBookModuleKey.BOOK_OVERVIEW)
    assert health.healthy is True
    assert "private_adapter" in health.details


def test_private_adapter_fallback_to_fake() -> None:
    adapter = PrivateModuleRunnerAdapter(
        module_key=WholeBookModuleKey.BOOK_OVERVIEW,
        private_runner=None,
        fallback_to_fake=True,
    )
    req = make_execution_request(
        provider_policy={"provider_kind": "fake", "synthetic_output": {"empty_dto": True, "skip_provider": True}}
    )
    result = adapter.execute(req)
    assert result.module_outputs.get("fake") is True


def test_recording_sink_still_works() -> None:
    sink = RecordingCandidatePersistenceSink()
    built = ModuleCandidateBuildResult(
        asset_commands=(),
        relation_commands=(),
        evidence_commands=(),
        conflict_commands=(),
        stage_artifact=None,
        output_fingerprint="x",
        rejected=False,
        orm_written=False,
        synthetic=True,
    )
    out = sink.persist_commands(built)
    assert out["orm_written"] is False
    assert len(sink.calls) == 1


def test_phase1b_sink_writes_candidates_only(session: Session) -> None:
    book, run, snapshot_id = _seed_book_run_snapshot(session)
    sink = Phase1BCandidatePersistenceSink(session, book_id=book.id)
    contract = _contract(run_id=run.id, book_snapshot_id=snapshot_id, mock=True)
    asset_cmd = AssetCandidateCommand(
        write_kind="candidate_asset_version",
        contract=contract,
        payload={
            "book_id": book.id,
            "asset_type": "structure_stage",
            "title": "Stage A",
            "summary": "candidate only",
            "output_ref": "stage-a",
            "review_status": "candidate",
        },
    )
    artifact = StageArtifactPayload(
        write_kind="stage_artifact",
        contract=_contract(
            run_id=run.id,
            book_snapshot_id=snapshot_id,
            write_kind="stage_artifact",
            mock=True,
        ),
        payload={
            "module_key": "structure_stages",
            "stage_key": "analyze_structure",
            "status": "completed",
            "synthetic": True,
            "non_production": True,
        },
    )
    built = ModuleCandidateBuildResult(
        asset_commands=(asset_cmd,),
        relation_commands=(),
        evidence_commands=(),
        conflict_commands=(),
        stage_artifact=artifact,
        output_fingerprint=contract.output_fingerprint,
        rejected=False,
        orm_written=False,
        synthetic=True,
    )
    out = sink.persist_commands(built)
    session.commit()
    assert out["orm_written"] is True
    assert out["auto_confirm"] is False
    assert out["auto_lock"] is False
    assert out["canonical_overwrite"] is False
    versions = list(session.scalars(select(NarrativeAssetVersion)).all())
    assert len(versions) == 1
    assert versions[0].review_status == "candidate"
    assert versions[0].is_canonical is False
    attrs = json.loads(versions[0].attributes_json or "{}")
    assert attrs["engine_id"] == contract.engine_id
    assert attrs["module_key"] == "structure_stages"
    assert attrs["run_stage_id"] == 1
    assert attrs["output_fingerprint"] == contract.output_fingerprint
    artifacts = list(session.scalars(select(AnalysisArtifact)).all())
    assert len(artifacts) == 1


def test_phase1b_sink_rejects_validation_and_budget(session: Session) -> None:
    book, run, snapshot_id = _seed_book_run_snapshot(session)
    sink = Phase1BCandidatePersistenceSink(session, book_id=book.id)
    rejected = ModuleCandidateBuildResult(
        asset_commands=(),
        relation_commands=(),
        evidence_commands=(),
        conflict_commands=(),
        stage_artifact=None,
        output_fingerprint="",
        rejected=True,
        synthetic=True,
    )
    out = sink.persist_commands(rejected)
    assert out["orm_written"] is False
    assert out["deny_reason"] == "rejected_validation"

    sink.budget_remaining = False
    contract = _contract(run_id=run.id, book_snapshot_id=snapshot_id)
    built = ModuleCandidateBuildResult(
        asset_commands=(
            AssetCandidateCommand(
                write_kind="candidate_asset_version",
                contract=contract,
                payload={"book_id": book.id, "asset_type": "event", "title": "x"},
            ),
        ),
        relation_commands=(),
        evidence_commands=(),
        conflict_commands=(),
        stage_artifact=None,
        output_fingerprint=contract.output_fingerprint,
        rejected=False,
        synthetic=True,
    )
    out2 = sink.persist_commands(built)
    assert out2["orm_written"] is False
    assert out2["deny_reason"] == "budget_denied"
    assert session.scalar(select(NarrativeAssetVersion)) is None


def test_provenance_attributes_bind_contract_fields() -> None:
    attrs = provenance_attributes(_contract())
    assert attrs["run_id"] == 1
    assert attrs["engine_version"] == "0.1.0-dev"
    assert attrs["prompt_pack_version"] == "1.0.0"
    assert attrs["auto_confirm"] is False


def test_evidence_pipeline_private_selection_hook() -> None:
    class Hook:
        def select_evidence(self, *, candidates, module_key=None):  # noqa: ANN001
            return tuple(candidates)[:1] if candidates else ()

    builder = EvidenceCandidateBuilder(private_selection_hook=Hook())
    # Without explicit candidates, apply_private_selection is identity on empty.
    assert builder.apply_private_selection(()) == ()


def test_evaluation_harness_phase2bv_hooks() -> None:
    harness = WholeBookEvaluationHarness()
    harness.register_phase2bv_hook("synthetic_only", lambda: True)
    summary = harness.phase2bv_prep_summary()
    assert summary["copyrighted_novel_corpus"] is False
    assert "synthetic://" in summary["fixture_schemes"]
    assert "synthetic_only" in summary["hooks"]
    harness.attach_private_runners(build_first_four_fake_runners())
    assert len(harness.runners) == 4


def test_adapter_unbound_without_fallback_raises() -> None:
    adapter = PrivateModuleRunnerAdapter(
        module_key=WholeBookModuleKey.BOOK_OVERVIEW,
        private_runner=None,
        fallback_to_fake=False,
    )
    with pytest.raises(Exception):
        adapter.execute(make_execution_request())
