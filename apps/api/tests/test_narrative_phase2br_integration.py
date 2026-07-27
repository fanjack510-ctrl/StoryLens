"""Phase 2B-R Integration — compose Agent S + T (CHG-20260723-044).

Directed eval: Fake default path, Lab provider gateway, optional private
four-module adapters, Phase1B candidate persistence, production isolation.
No Live Smoke / no live Provider HTTP.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Book, Chapter, NarrativeAssetVersion, Paragraph
from app.main import create_app, mount_private_engine_lab_if_enabled
from app.narrative_core.contracts.api_dto import WHOLE_BOOK_RUNS_ENDPOINT_DISABLED
from app.narrative_core.enums import WholeBookModuleKey
from app.narrative_core.migrations.runner import (
    apply_narrative_phase1bp_migrations,
    apply_narrative_phase1p_migrations,
)
from app.narrative_core.run_shell_contract.mock_lab import WHOLE_BOOK_MOCK_LAB_ENABLED
from app.narrative_core.run_shell_contract.private_engine_lab import (
    PRIVATE_ENGINE_LAB_REQUEST_MARKER_HEADER,
    WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED,
)
from app.narrative_core.services.candidate_persistence_adapter import (
    Phase1BCandidatePersistenceSink,
    RecordingCandidatePersistenceSink,
)
from app.narrative_core.services.private_whole_book_analysis_runtime import (
    PRIVATE_WHOLE_BOOK_RUNTIME_ALIASES,
    RUNTIME_SCHEMA,
    create_lab_private_whole_book_analysis_runtime,
    create_private_whole_book_analysis_runtime,
    try_load_first_four_private_runners,
)
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl
from app.narrative_core.services.whole_book_engine_registry import PRODUCTION_DEFAULT_ENGINE_ID
from app.narrative_core.services.whole_book_module_runner import (
    PrivateModuleRunnerAdapter,
    build_first_four_fake_runners,
)
from app.narrative_core.services.whole_book_provider_gateway import (
    BailianOpenAICompatibleProviderAdapter,
    FakeProviderAdapter,
    create_lab_provider_gateway,
)
from app.routers.whole_book_private_engine_lab_runs import reset_private_engine_lab_sessions_for_tests

REPO_ROOT = Path(__file__).resolve().parents[3]
PRIVATE_SRC = Path(r"D:\Dstorylens-private-engine-wt-integration\src")
VERSION = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()


def _ensure_private_on_path() -> bool:
    if not PRIVATE_SRC.is_dir():
        return False
    token = str(PRIVATE_SRC)
    if token not in sys.path:
        sys.path.insert(0, token)
    return True


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
    db = _fk_engine(f"sqlite:///{tmp_path / 'phase2br_int.db'}")
    Base.metadata.create_all(db)
    apply_narrative_phase1p_migrations(db)
    apply_narrative_phase1bp_migrations(db)
    factory = sessionmaker(bind=db, autoflush=False, expire_on_commit=False)
    s = factory()
    yield s
    s.close()


def _seed_book(session: Session) -> tuple[Book, int]:
    book = Book(
        title="Phase2BR Integration",
        source_file_name="int.txt",
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
    session.flush()
    snapshot = BookSnapshotServiceImpl(session).create_or_reuse_snapshot(book.id)
    session.commit()
    return book, int(snapshot.id)


def test_gates_and_version_locked() -> None:
    assert VERSION == "1.0.5"
    assert WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is True
    assert PRODUCTION_DEFAULT_ENGINE_ID is None
    assert WHOLE_BOOK_MOCK_LAB_ENABLED is False
    assert WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED is False
    edition = (REPO_ROOT / "apps/desktop/src/services/productEdition.ts").read_text(
        encoding="utf-8"
    )
    assert re.search(r"PRO_CAPABILITIES_SHIPPED\s*=\s*false", edition)
    mig = REPO_ROOT / "apps/api/app/narrative_core/migrations"
    names = {p.name for p in mig.glob("*.py")} if mig.is_dir() else set()
    assert not any("phase2br" in n.lower() for n in names)


def test_fake_default_composition_still_works(session: Session) -> None:
    book, snapshot_id = _seed_book(session)
    runtime = create_private_whole_book_analysis_runtime(session=session)
    assert runtime.lab_mode is False
    assert runtime.private_modules_bound is False
    assert isinstance(runtime.persistence, RecordingCandidatePersistenceSink)
    assert len(runtime.module_runners) == 4
    runtime_bundle, contract = runtime.build_native_context_bundle(
        book_id=book.id,
        book_snapshot_id=snapshot_id,
        module_keys=["book_overview"],
    )
    assert runtime_bundle is not None
    result = runtime.execute_module_pipeline(
        module_key=WholeBookModuleKey.BOOK_OVERVIEW,
        book_id=book.id,
        book_snapshot_id=snapshot_id,
        context_bundle_ref=f"ctx-bundle:{contract.bundle_hash}",
        configuration_fingerprint_value=runtime_bundle.configuration_fingerprint,
        provider_policy={
            "provider_kind": "fake",
            "synthetic_output": {"empty_dto": True, "skip_provider": True},
        },
        persist=True,
    )
    assert result.fake is True
    assert result.non_production is True
    assert result.canonical is False
    assert result.candidate_summary["persist"]["orm_written"] is False


def test_lab_provider_gateway_wires_bailian_dry() -> None:
    gw = create_lab_provider_gateway(dry_run=True)
    assert gw.registry is not None
    kinds = set(gw.registry.list_kinds())
    assert "fake" in kinds
    assert "aliyun_qwen_plus" in kinds
    health = gw.health_check("fake")
    assert health.healthy is True
    bailian = gw.registry.get("aliyun_qwen_plus")
    assert isinstance(bailian, BailianOpenAICompatibleProviderAdapter)
    assert bailian.dry_run is True


def test_lab_composition_factory_uses_lab_gateway() -> None:
    runtime = create_lab_private_whole_book_analysis_runtime(
        use_phase1b_persistence=False,
        lab_dry_run=True,
    )
    assert runtime.lab_mode is True
    assert runtime.non_production is True
    assert runtime.provider_gateway is not None
    assert isinstance(runtime.persistence, RecordingCandidatePersistenceSink)
    isolation = runtime.assert_production_isolation()
    assert isolation["ok"] is True
    assert isolation["private_engine_lab_enabled_default"] is False


def test_private_four_module_path_under_lab_when_package_present(session: Session) -> None:
    if not _ensure_private_on_path():
        pytest.skip("private engine worktree not available")
    runners = try_load_first_four_private_runners()
    if not runners:
        pytest.skip("private runners failed to import")
    book, snapshot_id = _seed_book(session)
    runtime = create_lab_private_whole_book_analysis_runtime(
        session=session,
        book_id=book.id,
        use_phase1b_persistence=True,
        private_runners=runners,
        fallback_to_fake=False,
    )
    assert runtime.private_modules_bound is True
    assert isinstance(runtime.persistence, Phase1BCandidatePersistenceSink)
    assert all(isinstance(r, PrivateModuleRunnerAdapter) for r in runtime.module_runners.values())
    runtime_bundle, contract = runtime.build_native_context_bundle(
        book_id=book.id,
        book_snapshot_id=snapshot_id,
        module_keys=["book_overview"],
    )
    ref = f"ctx-bundle:{contract.bundle_hash}"
    result = runtime.execute_module_pipeline(
        module_key=WholeBookModuleKey.BOOK_OVERVIEW,
        book_id=book.id,
        book_snapshot_id=snapshot_id,
        run_id=1,
        run_stage_id=1,
        context_bundle_ref=ref,
        configuration_fingerprint_value=runtime_bundle.configuration_fingerprint,
        provider_policy={
            "provider_kind": "fake",
            "model_route": "fake-route",
            "private_fixture": {
                "logline": "合成概览",
                "partial": True,
                "evidence_refs": ("ev-1",),
                "asset_candidates": [
                    {
                        "asset_type": "event",
                        "title": "Dawn",
                        "output_ref": "ev-dawn",
                        "summary": "candidate",
                    }
                ],
                "synthetic": True,
            },
        },
        persist=True,
        require_evidence_for_acceptance=False,
    )
    assert result.fake is False
    assert result.non_production is True
    assert result.engine_result.module_outputs.get("private_adapter") is True
    assert result.engine_result.module_outputs.get("direct_provider_http") is False
    # Candidate path may write when validation accepts; never auto-canonical.
    persist = result.candidate_summary.get("persist") or {}
    assert persist.get("auto_confirm", False) is False
    assert persist.get("auto_lock", False) is False
    assert persist.get("canonical_overwrite", False) is False


def test_phase1b_sink_wired_for_lab_path(session: Session) -> None:
    book, _snapshot_id = _seed_book(session)
    runtime = create_private_whole_book_analysis_runtime(
        session=session,
        lab_mode=True,
        use_phase1b_persistence=True,
        book_id=book.id,
        private_runners={},  # force empty → Fake runners, but Phase1B sink
        fallback_to_fake=True,
    )
    # empty mapping is falsy → Fake runners; sink still Phase1B
    assert isinstance(runtime.persistence, Phase1BCandidatePersistenceSink)
    assert runtime.lab_mode is True


def test_private_lab_router_mount_gated() -> None:
    reset_private_engine_lab_sessions_for_tests()
    app_off = create_app(environment="development", private_engine_lab_enabled=False)
    client_off = TestClient(app_off)
    r = client_off.post(
        "/api/v1/labs/private-whole-book-runs",
        json={
            "book_id": 1,
            "book_snapshot_id": 1,
            "dry_run": True,
            "data_transfer_consented": True,
            "user_confirmed": True,
            "credential_present": True,
            "preflight_fingerprint": "x",
            "estimate_fingerprint": "x",
            "consent_fingerprint": "x",
            "data_transfer_manifest_hash": "x",
        },
        headers={PRIVATE_ENGINE_LAB_REQUEST_MARKER_HEADER: "1"},
    )
    assert r.status_code in {404, 405}

    app_on = create_app(environment="development", private_engine_lab_enabled=True)
    client_on = TestClient(app_on)
    # Integration: fingerprints required — incomplete body must not create a Run.
    incomplete = client_on.post(
        "/api/v1/labs/private-whole-book-runs",
        json={
            "book_id": 1,
            "book_snapshot_id": 1,
            "dry_run": True,
        },
        headers={PRIVATE_ENGINE_LAB_REQUEST_MARKER_HEADER: "1"},
    )
    assert incomplete.status_code == 422
    contract = client_on.get(
        "/api/v1/labs/private-whole-book-runs/_meta/contract",
        headers={PRIVATE_ENGINE_LAB_REQUEST_MARKER_HEADER: "1"},
    )
    assert contract.status_code == 200
    body = contract.json()
    assert body["WHOLE_BOOK_RUNS_ENDPOINT_DISABLED"] is True
    assert body["PRIVATE_ENGINE_LAB_API_PREFIX"] == "/api/v1/labs/private-whole-book-runs"
    assert body["shell_only"] is False

    prod = create_app(environment="production", private_engine_lab_enabled=True)
    assert mount_private_engine_lab_if_enabled(prod, environment="production", lab_enabled=True) is False


def test_runtime_aliases_and_schema() -> None:
    assert RUNTIME_SCHEMA.startswith("storylens.phase2b")
    assert "PrivateWholeBookAnalysisRuntime" in PRIVATE_WHOLE_BOOK_RUNTIME_ALIASES
    with pytest.raises(RuntimeError):
        create_private_whole_book_analysis_runtime(production=True)


def test_no_new_migrations_static() -> None:
    mig_dir = REPO_ROOT / "apps/api/app/narrative_core/migrations"
    if not mig_dir.is_dir():
        return
    for path in mig_dir.rglob("*"):
        if path.is_file() and "2br" in path.name.lower():
            pytest.fail(f"unexpected phase2br migration file: {path}")


def test_fake_provider_still_default_outside_lab() -> None:
    runtime = create_private_whole_book_analysis_runtime()
    assert runtime.fake_provider is not None or isinstance(
        runtime.provider_gateway.registry.get("fake"), FakeProviderAdapter  # type: ignore[union-attr]
    )
    runners = build_first_four_fake_runners()
    assert len(runners) == 4
