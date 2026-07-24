"""Phase 2B-R1 CHG-049 — Live Smoke Runtime DI directed tests.

Formal Lab uses PrivateProviderInputBundleResolver + Credential Adapter.
Fake resolver is explicit opt-in only. Zero external HTTP.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, select, text
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
    Paragraph,
)
from app.main import create_app, mount_private_engine_lab_if_enabled
from app.narrative_core.contracts.api_dto import WHOLE_BOOK_RUNS_ENDPOINT_DISABLED
from app.narrative_core.enums import SnapshotStatus
from app.narrative_core.migrations.runner import apply_narrative_phase1bp_migrations
from app.narrative_core.run_shell_contract.mock_lab import WHOLE_BOOK_MOCK_LAB_ENABLED
from app.narrative_core.run_shell_contract.private_engine_lab import (
    WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED,
)
from app.narrative_core.services.formal_private_provider_input_resolver import (
    FormalPrivateProviderInputBundleResolverAdapter,
    FormalPrivateResolverUnavailable,
)
from app.narrative_core.services.private_whole_book_live_readiness_runtime import (
    create_live_readiness_runtime,
    get_or_create_default_live_readiness_runtime,
    reset_default_live_readiness_runtime_for_tests,
)
from app.narrative_core.services.provider_input_bundle_resolver import (
    FakeProviderInputBundleResolver,
)
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl
from app.narrative_core.services.whole_book_engine_registry import PRODUCTION_DEFAULT_ENGINE_ID
from app.narrative_core.services.whole_book_provider_gateway import (
    CapturingProviderTransport,
    ExistingCredentialServiceAdapter,
    StubTransportResponse,
)
from app.services.book_service import import_book


class _FakeKeyStore:
    def __init__(self, mapping: dict[str, str] | None = None) -> None:
        self._map = dict(mapping or {})

    def available(self) -> bool:
        return True

    def get(self, provider_kind: str) -> str | None:
        return self._map.get(provider_kind)


def _fk_engine(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _):  # noqa: ANN001
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return engine


def _seed_fixture_bytes() -> bytes:
    # 3 short chapters — enough for Snapshot + non-fake selection.
    parts = ["-----章节内容开始-----\n\n"]
    for i, title in enumerate(["开端", "转折", "收束"], start=1):
        body = ("这是合成验收段落。" * 40) + f"章{i}结束。"
        parts.append(f"第{i}章 {title}\n\n{body}\n\n")
    return "".join(parts).encode("utf-8")


@pytest.fixture
def di_env(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", raising=False)
    reset_default_live_readiness_runtime_for_tests()
    db = _fk_engine(f"sqlite:///{tmp_path / 'di-fix.db'}")
    Base.metadata.create_all(db)
    apply_narrative_phase1bp_migrations(db)
    factory = sessionmaker(bind=db, autoflush=False, expire_on_commit=False)
    session = factory()
    book = import_book(session, "di-smoke.txt", _seed_fixture_bytes())
    snap = BookSnapshotServiceImpl(session).create_or_reuse_snapshot(book.id)
    session.commit()
    assert snap.snapshot_status in {SnapshotStatus.COMPLETED, SnapshotStatus.COMPLETED.value, "completed"}
    store = _FakeKeyStore({"aliyun_qwen_plus": "sk-test-not-real"})
    cred = ExistingCredentialServiceAdapter(store=store, enabled=True)
    transport = CapturingProviderTransport(
        stub=StubTransportResponse(text='{"synthetic":true}', input_tokens=1, output_tokens=1)
    )
    runtime = create_live_readiness_runtime(
        environment="test",
        lab_enabled=True,
        dry_run=True,
        allow_network=False,
        session=session,
        credential_adapter=cred,
        transport=transport,
        allow_fake_resolver=False,
        auto_wire_credentials=False,
    )
    yield {
        "session": session,
        "book": book,
        "snapshot": snap,
        "runtime": runtime,
        "transport": transport,
        "cred": cred,
        "store": store,
        "db": db,
    }
    session.close()
    db.dispose()
    reset_default_live_readiness_runtime_for_tests()


def test_formal_runtime_resolver_is_not_fake(di_env) -> None:
    rt = di_env["runtime"]
    assert rt.uses_fake_resolver is False
    assert isinstance(rt.resolver, FormalPrivateProviderInputBundleResolverAdapter)


def test_fake_resolver_only_with_explicit_opt_in(di_env) -> None:
    rt = create_live_readiness_runtime(
        environment="test",
        lab_enabled=True,
        allow_fake_resolver=True,
        auto_wire_credentials=False,
        session=di_env["session"],
    )
    assert rt.uses_fake_resolver is True
    assert isinstance(rt.resolver, FakeProviderInputBundleResolver)


def test_missing_private_resolver_fail_closed(monkeypatch: pytest.MonkeyPatch, di_env) -> None:
    import app.narrative_core.services.formal_private_provider_input_resolver as mod

    def _boom(**_k):
        raise FormalPrivateResolverUnavailable("forced")

    monkeypatch.setattr(mod, "load_private_provider_input_bundle_resolver", _boom)
    with pytest.raises(FormalPrivateResolverUnavailable):
        create_live_readiness_runtime(
            environment="test",
            lab_enabled=True,
            allow_fake_resolver=False,
            auto_wire_credentials=False,
            session=di_env["session"],
        )


def test_preflight_estimate_real_snapshot_selection(di_env) -> None:
    rt = di_env["runtime"]
    session: Session = di_env["session"]
    book = di_env["book"]
    snap = di_env["snapshot"]
    rt.bind_session(session)
    pre = rt.preflight.preflight(
        book_id=book.id,
        book_snapshot_id=snap.id,
        configuration_fingerprint="di-cfg",
        requested_modules=("book_overview",),
    )
    assert pre.ok is True
    assert pre.details.get("credential_present") is True
    assert pre.details.get("calls_provider") is False
    rt.estimate.snapshot_content_hash = str(pre.snapshot_content_hash or "")
    est = rt.estimate.estimate(
        book_id=book.id,
        book_snapshot_id=snap.id,
        configuration_fingerprint="di-cfg",
        provider_key="aliyun_qwen_plus",
        model_id="qwen3.7-plus",
        quality_profile="balanced",
        requested_modules=("book_overview",),
        preflight_fingerprint=pre.fingerprint,
    )
    cached = rt.estimate._cache[est.fingerprint]
    manifest = cached["primary_manifest"].safe_dict()
    chars = int(manifest["source_character_count"])
    assert chars != 19
    assert chars > 100
    chapter_ids = [str(x) for x in (manifest.get("selected_chapter_ids") or [])]
    paragraph_ids = [str(x) for x in (manifest.get("selected_paragraph_ids") or [])]
    assert chapter_ids
    assert paragraph_ids
    # Selected chapter IDs must exist on Snapshot
    snap_ch_ids = {
        str(r)
        for r in session.scalars(
            text("SELECT id FROM book_snapshot_chapters WHERE snapshot_id=:s").bindparams(s=snap.id)
        ).all()
    }
    # scalars on text() may return Row; use execute
    rows = session.execute(
        text("SELECT id FROM book_snapshot_chapters WHERE snapshot_id=:s"), {"s": snap.id}
    ).fetchall()
    snap_ch_ids = {str(r[0]) for r in rows}
    for cid in chapter_ids:
        assert cid in snap_ch_ids
    rows_p = session.execute(
        text("SELECT id FROM book_snapshot_paragraphs WHERE snapshot_id=:s"), {"s": snap.id}
    ).fetchall()
    snap_p_ids = {str(r[0]) for r in rows_p}
    # paragraph refs may be snapshot paragraph ids
    for pid in paragraph_ids:
        assert pid in snap_p_ids or pid.startswith("B")
    # Token estimate scales with content
    assert int(est.usage_summary["estimated_input_tokens"]) > 66
    safe = manifest
    blob = str(safe)
    assert "这是合成验收段落" not in blob
    assert "messages" not in safe
    assert "system_instruction" not in safe
    assert len(di_env["transport"].calls) == 0
    assert session.scalar(select(AnalysisRun).count() if False else text("SELECT COUNT(*) FROM analysis_runs")) == 0
    assert session.scalar(text("SELECT COUNT(*) FROM analysis_run_stages")) == 0
    assert session.scalar(text("SELECT COUNT(*) FROM narrative_assets")) == 0
    assert session.scalar(text("SELECT COUNT(*) FROM narrative_asset_evidence")) == 0


def test_token_estimate_changes_with_longer_text(di_env, tmp_path) -> None:
    session: Session = di_env["session"]
    # Import a longer book into same DB
    long_bytes = ("-----章节内容开始-----\n\n第一章 长文\n\n" + ("加长正文。" * 200) + "\n\n").encode(
        "utf-8"
    )
    book2 = import_book(session, "di-long.txt", long_bytes)
    snap2 = BookSnapshotServiceImpl(session).create_or_reuse_snapshot(book2.id)
    session.commit()
    rt = di_env["runtime"]
    rt.bind_session(session)
    pre1 = rt.preflight.preflight(
        book_id=di_env["book"].id,
        book_snapshot_id=di_env["snapshot"].id,
        configuration_fingerprint="di-cfg-a",
        requested_modules=("book_overview",),
    )
    rt.estimate.snapshot_content_hash = str(pre1.snapshot_content_hash or "")
    est1 = rt.estimate.estimate(
        book_id=di_env["book"].id,
        book_snapshot_id=di_env["snapshot"].id,
        configuration_fingerprint="di-cfg-a",
        provider_key="aliyun_qwen_plus",
        model_id="qwen3.7-plus",
        quality_profile="balanced",
        requested_modules=("book_overview",),
        preflight_fingerprint=pre1.fingerprint,
    )
    pre2 = rt.preflight.preflight(
        book_id=book2.id,
        book_snapshot_id=snap2.id,
        configuration_fingerprint="di-cfg-b",
        requested_modules=("book_overview",),
    )
    rt.estimate.snapshot_content_hash = str(pre2.snapshot_content_hash or "")
    est2 = rt.estimate.estimate(
        book_id=book2.id,
        book_snapshot_id=snap2.id,
        configuration_fingerprint="di-cfg-b",
        provider_key="aliyun_qwen_plus",
        model_id="qwen3.7-plus",
        quality_profile="balanced",
        requested_modules=("book_overview",),
        preflight_fingerprint=pre2.fingerprint,
    )
    assert est1.usage_summary["estimated_input_tokens"] != est2.usage_summary["estimated_input_tokens"]
    assert est1.fingerprint != est2.fingerprint


def test_credential_adapter_present_and_missing(di_env) -> None:
    present = ExistingCredentialServiceAdapter(store=di_env["store"], enabled=True)
    assert present.resolve("aliyun_qwen_plus")
    missing = ExistingCredentialServiceAdapter(store=_FakeKeyStore({}), enabled=True)
    assert missing.resolve("aliyun_qwen_plus") is None
    # client bool cannot invent presence — server reads adapter
    assert bool(missing.resolve("aliyun_qwen_plus")) is False


def test_default_runtime_refuses_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_default_live_readiness_runtime_for_tests()
    rt = get_or_create_default_live_readiness_runtime(environment="test", lab_enabled=True)
    assert rt.uses_fake_resolver is False
    reset_default_live_readiness_runtime_for_tests()


def test_production_isolation_flags() -> None:
    assert WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is True
    assert WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED is False
    assert WHOLE_BOOK_MOCK_LAB_ENABLED is False
    assert PRODUCTION_DEFAULT_ENGINE_ID is None
    app = create_app()
    before = len(app.routes)
    assert mount_private_engine_lab_if_enabled(app, environment="production", lab_enabled=True) is False
    assert len(app.routes) == before


def test_capturing_transport_no_body_dump(di_env) -> None:
    t = di_env["transport"]
    t.generate(
        messages=[{"role": "user", "content": "SECRET_BODY_SHOULD_NOT_PERSIST_LONG"}],
        model="qwen3.7-plus",
        response_format_mode="json_object",
        max_tokens=8,
        timeout_seconds=1,
    )
    assert len(t.calls) == 1
    assert "SECRET_BODY" not in str(t.calls[0])
    assert "message_count" in t.calls[0]
