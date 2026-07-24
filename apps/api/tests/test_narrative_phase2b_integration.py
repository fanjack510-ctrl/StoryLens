"""Phase 2B Integration — Fake Provider E2E (CHG-20260723-040).

Composes Agent P/Q/R into PrivateWholeBookAnalysisRuntime and exercises:
Snapshot → Context Bundle → Fake Provider → Fake Module Runner →
Output/Evidence Validation → Candidate Commands → Result DTO.

No formal prompts, no real model calls, no production whole-book runs.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Book, BookSnapshot, Chapter, Paragraph
from app.narrative_core.contracts.api_dto import WHOLE_BOOK_RUNS_ENDPOINT_DISABLED
from app.narrative_core.enums import EvidenceRole, SnapshotStatus, WholeBookModuleKey
from app.narrative_core.migrations.runner import apply_narrative_phase1p_migrations
from app.narrative_core.private_engine_contract.errors import (
    PrivateEngineError,
    PrivateEngineErrorCode,
)
from app.narrative_core.run_shell_contract.mock_lab import WHOLE_BOOK_MOCK_LAB_ENABLED
from app.narrative_core.services.auxiliary_context_source import (
    FixtureAuxiliaryContextSource,
    make_stale_aux_fixture,
)
from app.narrative_core.services.candidate_persistence_adapter import (
    RecordingCandidatePersistenceSink,
)
from app.narrative_core.services.paragraph_grouping_policy import (
    DEFAULT_MAX_PARAGRAPHS_PER_GROUP,
    DEFAULT_OVERLAP_PARAGRAPHS,
    ParagraphGroupingPolicy,
)
from app.narrative_core.services.private_whole_book_analysis_runtime import (
    PRIVATE_WHOLE_BOOK_RUNTIME_ALIASES,
    RUNTIME_SCHEMA,
    RUNTIME_VERSION,
    create_private_whole_book_analysis_runtime,
)
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl
from app.narrative_core.services.whole_book_context_bundle_mapper import (
    WholeBookContextBundleMapper,
)
from app.narrative_core.services.whole_book_engine_registry import PRODUCTION_DEFAULT_ENGINE_ID
from app.narrative_core.services.whole_book_evidence_validator import DefaultEvidenceValidator
from app.narrative_core.services.whole_book_module_runner import make_execution_request

REPO_ROOT = Path(__file__).resolve().parents[3]


def _factory(tmp_path, name: str = "phase2b_int.db"):
    engine = create_engine(
        f"sqlite:///{tmp_path / name}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    apply_narrative_phase1p_migrations(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False), engine


def _seed_book(
    session: Session,
    *,
    title: str = "Synth Integration Book",
    chapters: list[tuple[str, list[str]]] | None = None,
) -> Book:
    book = Book(
        title=title,
        source_file_name=f"{title}.txt",
        source_file_hash=f"hash-{title}",
        created_at=datetime.now(timezone.utc),
    )
    session.add(book)
    session.flush()
    bodies = chapters or [
        ("第一章", ["甲段文字内容", "乙段继续"]),
        ("第二章", ["丙段收束", "丁段补充"]),
    ]
    for chapter_index, (ch_title, paragraphs) in enumerate(bodies, start=1):
        chapter = Chapter(
            book_id=book.id,
            chapter_index=chapter_index,
            title=ch_title,
            display_title=ch_title,
            chapter_title=ch_title,
            source_title_line=ch_title,
            word_count=sum(len(p) for p in paragraphs),
        )
        session.add(chapter)
        session.flush()
        offset = 0
        for p_index, text_body in enumerate(paragraphs, start=1):
            session.add(
                Paragraph(
                    id=f"B{book.id:04d}-C{chapter_index:04d}-P{p_index:04d}",
                    book_id=book.id,
                    chapter_id=chapter.id,
                    paragraph_index=p_index,
                    raw_text=text_body,
                    normalized_text=text_body,
                    char_start=offset,
                    char_end=offset + len(text_body),
                )
            )
            offset += len(text_body) + 1
    session.commit()
    return book


def _completed_snapshot(session: Session, book: Book) -> BookSnapshot:
    service = BookSnapshotServiceImpl(session)
    snap = service.create_or_reuse_snapshot(book.id)
    session.commit()
    assert snap.snapshot_status == SnapshotStatus.COMPLETED
    return snap


def _first_para_evidence(session: Session, snap: BookSnapshot, *, module_key: str) -> dict:
    chapter = sorted(snap.chapters, key=lambda c: c.chapter_order)[0]
    para = sorted(chapter.paragraphs, key=lambda p: p.paragraph_order)[0]
    return {
        "candidate_id": f"ev-{module_key}-1",
        "book_snapshot_id": snap.id,
        "snapshot_chapter_id": chapter.id,
        "snapshot_paragraph_id": para.id,
        "stable_paragraph_id": para.stable_paragraph_id,
        "paragraph_content_hash": para.content_hash,
        "start_offset": 0,
        "end_offset": min(8, max(1, para.end_offset - para.start_offset)),
        "evidence_role": EvidenceRole.SUPPORT.value,
        "target_output_ref": f"{module_key}.claim",
        "preview": "synthetic",
        "book_id": snap.book_id,
        "from_derived_summary": False,
    }


def _register_view(runtime, session: Session, book: Book, snap: BookSnapshot) -> None:
    validator = DefaultEvidenceValidator(session)
    view = validator.build_view_from_session(
        book_id=book.id,
        book_snapshot_id=snap.id,
    )
    runtime.register_evidence_view(view)


def test_runtime_composition_aliases_and_schema() -> None:
    assert RUNTIME_SCHEMA.startswith("storylens.phase2b")
    assert RUNTIME_VERSION == "1.0.0"
    assert "PrivateWholeBookAnalysisRuntime" in PRIVATE_WHOLE_BOOK_RUNTIME_ALIASES
    runtime = create_private_whole_book_analysis_runtime()
    assert runtime.schema == RUNTIME_SCHEMA
    assert runtime.provider_gateway is not None
    assert len(runtime.module_runners) == 4
    with pytest.raises(RuntimeError):
        create_private_whole_book_analysis_runtime(production=True)


def test_paragraph_grouping_policy_defaults_and_fingerprint() -> None:
    policy = ParagraphGroupingPolicy.default()
    assert policy.max_paragraphs_per_group == DEFAULT_MAX_PARAGRAPHS_PER_GROUP == 40
    assert policy.overlap_paragraphs == DEFAULT_OVERLAP_PARAGRAPHS == 2
    with pytest.raises(ValueError):
        ParagraphGroupingPolicy(max_paragraphs_per_group=2, overlap_paragraphs=2)
    shrunk = policy.with_overrides(provider_context_limit=500, max_tokens_estimated=3000)
    g = shrunk.to_grouping_dict()
    assert g["max_paragraphs_per_group"] < 40
    assert g["defaults_are_initial_only"] is True


def test_context_bundle_mapper_round_trip(tmp_path) -> None:
    factory, _ = _factory(tmp_path, "mapper.db")
    with factory() as session:
        book = _seed_book(session)
        snap = _completed_snapshot(session, book)
        runtime = create_private_whole_book_analysis_runtime(session=session)
        runtime_bundle, contract = runtime.build_native_context_bundle(
            book_id=book.id,
            book_snapshot_id=snap.id,
            module_keys=("book_overview",),
        )
        restored = WholeBookContextBundleMapper.round_trip(runtime_bundle)
        assert restored.bundle_hash == runtime_bundle.bundle_hash
        assert restored.snapshot_content_hash == contract.snapshot_content_hash
        assert restored.chapter_hashes == contract.chapter_hashes
        assert "full_text" not in json.dumps(runtime_bundle.to_public_dict())


def test_scenario_overview_native_e2e(tmp_path) -> None:
    factory, engine = _factory(tmp_path, "overview.db")
    sink = RecordingCandidatePersistenceSink()
    with factory() as session:
        book = _seed_book(session)
        snap = _completed_snapshot(session, book)
        runtime = create_private_whole_book_analysis_runtime(
            session=session,
            package_root=tmp_path / "packages",
            persistence=sink,
        )
        packages = runtime.prepare_engine_packages(tmp_path / "packages")
        assert packages["fake"] is True
        assert packages["signed"] is True
        _register_view(runtime, session, book, snap)

        runtime_bundle, contract = runtime.build_native_context_bundle(
            book_id=book.id,
            book_snapshot_id=snap.id,
            module_keys=("book_overview",),
        )
        assert runtime_bundle.mode.value == "native"
        ref = f"ctx-bundle:{contract.bundle_hash}"
        evidence = _first_para_evidence(session, snap, module_key="book_overview")

        result = runtime.execute_module_pipeline(
            module_key=WholeBookModuleKey.BOOK_OVERVIEW,
            book_id=book.id,
            book_snapshot_id=snap.id,
            context_bundle_ref=ref,
            configuration_fingerprint_value=contract.configuration_fingerprint,
            provider_policy={
                "provider_kind": "fake",
                "model_route": "fake-route",
                "synthetic_output": {
                    "overview_mode": "no_central_conflict",
                    "force_accept": True,
                    "partial": True,
                    "evidence_candidates": (evidence,),
                    "required_claims": 1,
                    "evidenced_claims": 1,
                    "asset_candidates": ({"asset_type": "storyline", "synthetic": True},),
                },
            },
        )
        assert result.fake is True
        assert result.synthetic is True
        assert result.canonical is False
        assert result.asset_written is False
        assert result.network is False
        assert result.model_called is False
        assert result.formal_prompt is False
        assert result.validation["accepted"] is True
        assert result.candidate_summary["rejected"] is False
        assert result.candidate_summary["orm_written"] is False
        assert sink.calls
        assert sink.calls[0].orm_written is False
        table_names = set(inspect(engine).get_table_names())
        assert "narrative_pattern" not in table_names


def test_overview_no_protagonist_and_multi(tmp_path) -> None:
    factory, _ = _factory(tmp_path, "overview_modes.db")
    with factory() as session:
        book = _seed_book(session)
        snap = _completed_snapshot(session, book)
        runtime = create_private_whole_book_analysis_runtime(session=session)
        _, contract = runtime.build_native_context_bundle(
            book_id=book.id,
            book_snapshot_id=snap.id,
            module_keys=("book_overview",),
        )
        ref = f"ctx-bundle:{contract.bundle_hash}"
        for mode in ("no_central_conflict", "multi_protagonist", "partial"):
            out = runtime.execute_module_pipeline(
                module_key="book_overview",
                book_id=book.id,
                book_snapshot_id=snap.id,
                context_bundle_ref=ref,
                configuration_fingerprint_value=contract.configuration_fingerprint,
                provider_policy={
                    "provider_kind": "fake",
                    "synthetic_output": {
                        "overview_mode": mode,
                        "force_accept": True,
                        "skip_provider": True,
                    },
                },
                persist=False,
            )
            dto = out.engine_result.module_outputs
            assert dto.get("protagonist_asset_id") is None


def test_scenario_structure_non_three_act(tmp_path) -> None:
    factory, _ = _factory(tmp_path, "structure.db")
    with factory() as session:
        book = _seed_book(session)
        snap = _completed_snapshot(session, book)
        runtime = create_private_whole_book_analysis_runtime(session=session)
        _register_view(runtime, session, book, snap)
        _, contract = runtime.build_native_context_bundle(
            book_id=book.id,
            book_snapshot_id=snap.id,
            module_keys=("structure_stages",),
        )
        ref = f"ctx-bundle:{contract.bundle_hash}"
        evidence = _first_para_evidence(session, snap, module_key="structure_stages")
        result = runtime.execute_module_pipeline(
            module_key="structure_stages",
            book_id=book.id,
            book_snapshot_id=snap.id,
            context_bundle_ref=ref,
            configuration_fingerprint_value=contract.configuration_fingerprint,
            provider_policy={
                "provider_kind": "fake",
                "synthetic_output": {
                    "structure_mode": "five_stages",
                    "force_accept": True,
                    "evidence_candidates": (evidence,),
                },
            },
            persist=False,
        )
        stages = result.engine_result.module_outputs.get("stages") or []
        assert len(stages) == 5
        assert result.validation["schema_valid"] is True
        # Must not force three-act templates.
        assert len(stages) != 3


def test_scenario_chapter_functions(tmp_path) -> None:
    factory, _ = _factory(tmp_path, "chapter_fn.db")
    with factory() as session:
        book = _seed_book(session)
        snap = _completed_snapshot(session, book)
        runtime = create_private_whole_book_analysis_runtime(session=session)
        _, contract = runtime.build_native_context_bundle(
            book_id=book.id,
            book_snapshot_id=snap.id,
            module_keys=("chapter_functions",),
        )
        ref = f"ctx-bundle:{contract.bundle_hash}"
        result = runtime.execute_module_pipeline(
            module_key="chapter_functions",
            book_id=book.id,
            book_snapshot_id=snap.id,
            context_bundle_ref=ref,
            configuration_fingerprint_value=contract.configuration_fingerprint,
            provider_policy={
                "provider_kind": "fake",
                "synthetic_output": {
                    "chapter_mode": "side_story_flashback_empty",
                    "force_accept": True,
                    "skip_provider": True,
                },
            },
            persist=False,
        )
        labels = set(result.engine_result.module_outputs.get("function_labels") or ())
        forbidden = {"xianxia_breakthrough", "sys_panel", "cultivation_realm"}
        assert not (labels & forbidden)


def test_scenario_storylines(tmp_path) -> None:
    factory, _ = _factory(tmp_path, "storylines.db")
    with factory() as session:
        book = _seed_book(session)
        snap = _completed_snapshot(session, book)
        runtime = create_private_whole_book_analysis_runtime(session=session)
        _, contract = runtime.build_native_context_bundle(
            book_id=book.id,
            book_snapshot_id=snap.id,
            module_keys=("storylines",),
        )
        ref = f"ctx-bundle:{contract.bundle_hash}"
        result = runtime.execute_module_pipeline(
            module_key="storylines",
            book_id=book.id,
            book_snapshot_id=snap.id,
            context_bundle_ref=ref,
            configuration_fingerprint_value=contract.configuration_fingerprint,
            provider_policy={
                "provider_kind": "fake",
                "synthetic_output": {
                    "storyline_type": "quest",
                    "status": "paused",
                    "force_accept": True,
                    "skip_provider": True,
                    "key_event_ids": (1, 2),
                },
            },
            persist=False,
        )
        out = result.engine_result.module_outputs
        assert out.get("storyline_type") in {"main", "side", "relationship", "quest", "unknown"}
        assert out.get("status") in {
            "active",
            "paused",
            "resumed",
            "terminated",
            "incomplete",
            "unknown",
        }
        assert out.get("storyline_type") != "character_list"


def test_scenario_enhanced_degrade(tmp_path) -> None:
    factory, _ = _factory(tmp_path, "enhanced.db")
    aux = FixtureAuxiliaryContextSource()
    with factory() as session:
        book = _seed_book(session)
        snap = _completed_snapshot(session, book)
        aux.register(book.id, snap.id, make_stale_aux_fixture())
        runtime = create_private_whole_book_analysis_runtime(
            session=session,
            auxiliary_source=aux,
        )
        runtime_bundle, contract = runtime.build_enhanced_context_bundle(
            book_id=book.id,
            book_snapshot_id=snap.id,
            module_keys=("book_overview",),
        )
        assert runtime_bundle.mode.value == "enhanced"
        assert runtime_bundle.coverage.degraded is True
        assert any("stale" in w or "missing" in w or "degraded" in w for w in runtime_bundle.warnings)
        assert contract.snapshot_content_hash == snap.content_hash
        assert contract.book_snapshot_id == snap.id


def test_scenario_validation_rejection(tmp_path) -> None:
    factory, _ = _factory(tmp_path, "reject.db")
    with factory() as session:
        book = _seed_book(session)
        snap = _completed_snapshot(session, book)
        runtime = create_private_whole_book_analysis_runtime(session=session)
        _register_view(runtime, session, book, snap)
        _, contract = runtime.build_native_context_bundle(
            book_id=book.id,
            book_snapshot_id=snap.id,
            module_keys=("book_overview",),
        )
        ref = f"ctx-bundle:{contract.bundle_hash}"

        cases = [
            {"schema_error": True},
            {"invalid_ref": True, "protagonist_asset_id": 999},
            {"evidence_insufficient": True},
            {"snapshot_mismatch": True},
            {"cross_book": True},
            {"duplicate": True},
            {"conflict": True},
        ]
        for marker in cases:
            result = runtime.execute_module_pipeline(
                module_key="book_overview",
                book_id=book.id,
                book_snapshot_id=snap.id,
                context_bundle_ref=ref,
                configuration_fingerprint_value=contract.configuration_fingerprint,
                provider_policy={
                    "provider_kind": "fake",
                    "synthetic_output": {
                        "empty_dto": True,
                        "skip_provider": True,
                        **marker,
                    },
                },
                persist=True,
                require_evidence_for_acceptance=True,
            )
            assert result.validation["accepted"] is False
            assert result.candidate_summary["rejected"] is True

        chapter = sorted(snap.chapters, key=lambda c: c.chapter_order)[0]
        para = sorted(chapter.paragraphs, key=lambda p: p.paragraph_order)[0]
        bad_evidence = {
            "candidate_id": "ev-bad-hash",
            "book_snapshot_id": snap.id,
            "snapshot_chapter_id": chapter.id,
            "snapshot_paragraph_id": para.id,
            "stable_paragraph_id": "wrong-stable",
            "paragraph_content_hash": "definitely-not-matching",
            "start_offset": 0,
            "end_offset": 4,
            "evidence_role": EvidenceRole.SUPPORT.value,
            "target_output_ref": "book_overview.claim",
            "preview": "x",
            "book_id": book.id,
        }
        result = runtime.execute_module_pipeline(
            module_key="book_overview",
            book_id=book.id,
            book_snapshot_id=snap.id,
            context_bundle_ref=ref,
            configuration_fingerprint_value=contract.configuration_fingerprint,
            provider_policy={
                "provider_kind": "fake",
                "synthetic_output": {
                    "force_accept": True,
                    "evidence_candidates": (bad_evidence,),
                    "skip_provider": True,
                },
            },
            persist=False,
            require_evidence_for_acceptance=True,
        )
        assert result.validation["evidence_valid"] is False
        assert result.validation["accepted"] is False


def test_scenario_resume(tmp_path) -> None:
    factory, _ = _factory(tmp_path, "resume.db")
    with factory() as session:
        book = _seed_book(session)
        snap = _completed_snapshot(session, book)
        runtime = create_private_whole_book_analysis_runtime(session=session)
        _, contract = runtime.build_native_context_bundle(
            book_id=book.id,
            book_snapshot_id=snap.id,
            module_keys=("book_overview",),
        )
        ref = f"ctx-bundle:{contract.bundle_hash}"
        runner = runtime.module_runners[WholeBookModuleKey.BOOK_OVERVIEW]
        req = make_execution_request(
            module_key=WholeBookModuleKey.BOOK_OVERVIEW,
            book_id=book.id,
            book_snapshot_id=snap.id,
            context_bundle_ref=ref,
            configuration_fingerprint=contract.configuration_fingerprint,
            provider_policy={
                "provider_kind": "fake",
                "synthetic_output": {"force_accept": True, "skip_provider": True, "partial": True},
            },
            checkpoint_ref="ckpt:initial",
        )
        runner.context_bundles[ref] = contract
        first = runner.execute(req)
        assert first.checkpoint is not None
        resumed = runner.resume(req)
        assert resumed.status in {"completed_fake", "resumed_deduplicated"}

        from app.narrative_core.services.whole_book_module_runner import ModuleCheckpointValidator

        # Prompt pack change must reject.
        with pytest.raises(PrivateEngineError) as exc:
            ModuleCheckpointValidator().validate_resume(
                checkpoint=first.checkpoint,
                current_engine_id=first.checkpoint.engine_id,
                current_engine_version=first.checkpoint.engine_version,
                current_prompt_pack_id="fake.prompt_pack.first_four",
                current_prompt_pack_version="9.9.9-changed",
                current_context_bundle_hash=contract.bundle_hash,
                current_book_snapshot_id=snap.id,
                current_configuration_fingerprint=contract.configuration_fingerprint,
            )
        assert exc.value.code == PrivateEngineErrorCode.PROMPT_PACK_INCOMPATIBLE

        # Context hash change must reject.
        with pytest.raises(PrivateEngineError) as exc2:
            ModuleCheckpointValidator().validate_resume(
                checkpoint=first.checkpoint,
                current_engine_id=first.checkpoint.engine_id,
                current_engine_version=first.checkpoint.engine_version,
                current_prompt_pack_id=first.checkpoint.prompt_pack_id,
                current_prompt_pack_version=first.checkpoint.prompt_pack_version,
                current_context_bundle_hash="mutated-hash-not-matching",
                current_book_snapshot_id=snap.id,
                current_configuration_fingerprint=contract.configuration_fingerprint,
            )
        assert exc2.value.code == PrivateEngineErrorCode.ENGINE_CHECKPOINT_INCOMPATIBLE

        # Output dedupe on second resume.
        runner.emitted_output_fingerprints.clear()
        first_resume = runner.resume(req)
        second_resume = runner.resume(req)
        assert first_resume.status != "resumed_deduplicated"
        assert second_resume.status == "resumed_deduplicated" or second_resume.module_outputs.get(
            "resume_deduped"
        )


def test_scenario_production_isolation(tmp_path) -> None:
    factory, _ = _factory(tmp_path, "prod.db")
    with factory() as session:
        book = _seed_book(session)
        _completed_snapshot(session, book)
        runtime = create_private_whole_book_analysis_runtime(
            session=session,
            package_root=tmp_path / "packages",
        )
        runtime.prepare_engine_packages(tmp_path / "packages")
        proof = runtime.assert_production_isolation()
        assert proof["ok"] is True, proof["errors"]
        assert PRODUCTION_DEFAULT_ENGINE_ID is None
        assert WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is True
        assert WHOLE_BOOK_MOCK_LAB_ENABLED is False


def test_metamorphic_grouping_and_provider_limit(tmp_path) -> None:
    factory, _ = _factory(tmp_path, "meta.db")
    with factory() as session:
        book = _seed_book(session)
        snap = _completed_snapshot(session, book)
        runtime = create_private_whole_book_analysis_runtime(
            session=session,
            grouping_policy=ParagraphGroupingPolicy.default(),
        )
        _, c1 = runtime.build_native_context_bundle(
            book_id=book.id,
            book_snapshot_id=snap.id,
            module_keys=("book_overview",),
            provider_context_limit=8000,
        )
        runtime.grouping_policy = ParagraphGroupingPolicy(
            max_paragraphs_per_group=10,
            overlap_paragraphs=1,
        )
        runtime.bind_session(session)
        _, c2 = runtime.build_native_context_bundle(
            book_id=book.id,
            book_snapshot_id=snap.id,
            module_keys=("book_overview",),
            provider_context_limit=8000,
        )
        assert c1.bundle_hash != c2.bundle_hash
        assert c1.configuration_fingerprint != c2.configuration_fingerprint

        runtime.grouping_policy = ParagraphGroupingPolicy.default()
        runtime.bind_session(session)
        _, c_hi = runtime.build_native_context_bundle(
            book_id=book.id,
            book_snapshot_id=snap.id,
            module_keys=("book_overview",),
            provider_context_limit=50_000,
        )
        _, c_lo = runtime.build_native_context_bundle(
            book_id=book.id,
            book_snapshot_id=snap.id,
            module_keys=("book_overview",),
            provider_context_limit=64,
        )
        assert c_hi.configuration_fingerprint != c_lo.configuration_fingerprint


def test_provider_gateway_is_agent_p_default() -> None:
    runtime = create_private_whole_book_analysis_runtime()
    from app.narrative_core.services.whole_book_provider_gateway import (
        DefaultWholeBookProviderGateway,
        FakeProviderAdapter,
    )

    assert isinstance(runtime.provider_gateway, DefaultWholeBookProviderGateway)
    assert isinstance(runtime.fake_provider or FakeProviderAdapter(), FakeProviderAdapter)
    adapter = runtime.module_runners[WholeBookModuleKey.BOOK_OVERVIEW].provider_adapter
    assert adapter is not None
    assert adapter.gateway is runtime.provider_gateway


def test_static_security_scan_paths() -> None:
    root = REPO_ROOT / "apps" / "api" / "app" / "narrative_core"
    patterns = re.compile(
        r"api[_-]?key|authorization|bearer|credential|system prompt|ignore previous|"
        r"requests\.|httpx\.|aiohttp\.|openai|dashscope|llama-server",
        re.I,
    )
    hits: list[str] = []
    for path in root.rglob("*.py"):
        name = path.name
        if not any(
            token in name
            for token in (
                "private_engine",
                "module",
                "context",
                "evidence",
                "provider",
                "prompt",
                "phase2b",
            )
        ):
            continue
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), start=1):
            if not patterns.search(line):
                continue
            lower = line.lower()
            if any(
                k in lower
                for k in (
                    "forbidden",
                    "must not",
                    "never",
                    "protocol",
                    "error",
                    "assert",
                    "banned",
                    "no_",
                    "without",
                    "resolver",
                    "detail_code",
                    "not log",
                    "not enter",
                    "not call",
                    "not read",
                    "not serialize",
                    "test",
                    "fake",
                    "synthetic",
                    "forbids",
                    "blocks",
                    "absence",
                    "re-check",
                    "_credential",
                    "credential_read",
                    '"api_key"',
                    '"apikey"',
                    '"credential"',
                    '"credentials"',
                    '"authorization"',
                    '"bearer"',
                    "existingcredentialserviceadapter",
                    "resolve credentials only",
                    "formal prompts",
                    "license, credential",
                    "no orm",
                )
            ):
                continue
            if "CredentialStore" in line or "ProviderCredentialResolver" in line:
                continue
            if "NoCredentialFakeResolver" in line or "credential_resolver" in line:
                continue
            if "ExistingCredentialServiceAdapter" in line:
                continue
            hits.append(f"{path.relative_to(REPO_ROOT)}:{i}:{line.strip()}")
    assert not hits, "unexpected sensitive hits:\n" + "\n".join(hits[:20])


def test_version_and_gates_locked() -> None:
    version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert version == "1.0.5"
    assert PRODUCTION_DEFAULT_ENGINE_ID is None
    assert WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is True
    assert WHOLE_BOOK_MOCK_LAB_ENABLED is False
