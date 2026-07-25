"""STEP 2.2-A — Native Overview walking-skeleton backend (§10.12)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AnalysisArtifact,
    AnalysisRun,
    AnalysisRunStage,
    Base,
    Book,
    Chapter,
    NarrativeAsset,
    NarrativeAssetEvidence,
    NarrativeAssetVersion,
    NarrativeEntity,
    Paragraph,
    WholeBookRunStateVersion,
    WholeBookRunWindow,
)
from app.narrative_core.contracts.api_dto import WHOLE_BOOK_RUNS_ENDPOINT_DISABLED
from app.narrative_core.contracts.pro_native_overview_flags import (
    FIXTURE_DEVELOPMENT_WARNING,
    FIXTURE_ENGINE_ID,
    FIXTURE_ENGINE_VERSION,
    is_pro_native_overview_enabled,
)
from app.narrative_core.contracts.whole_book_overview_fixture_hash import (
    default_public_fixture_dir,
    verify_fixture_manifest,
)
from app.narrative_core.contracts.whole_book_overview_v1 import CreateRunRequest
from app.narrative_core.enums import OverviewProductionStageKey, RunStatus, WindowStatus
from app.narrative_core.services.native_overview_fixture_adapter import (
    load_private_fixture_engine_adapter,
)
from app.narrative_core.services.native_overview_seed import seed_short_book_v1
from app.narrative_core.services.native_overview_service import (
    OVERVIEW_PROJECTION_ARTIFACT_TYPE,
    NativeOverviewService,
)
from app.narrative_core.services.whole_book_overview_engine_protocol import (
    WholeBookOverviewEngineAdapter,
)
from app.services import entitlement
from app.services.license_crypto import (
    build_unsigned_payload,
    encode_license,
    private_key_b64url,
    public_key_b64url,
)


EXPECTED_COMBINED = "ecf419c6e79bcc4fc899b116e9e5b7c9b8810de9cba70fec9d0f61282f635d55"

CREATE_BODY = {
    "mode": "whole_book_native",
    "module_key": "book_overview",
    "provider_id": FIXTURE_ENGINE_ID,
    "model_id": FIXTURE_ENGINE_VERSION,
    "client_request_id": "req-skeleton-001",
    "consent": {
        "estimated_tokens": 0,
        "estimated_cost": 0.0,
        "currency": "CNY",
        "confirmed": True,
    },
}


@pytest.fixture()
def license_keypair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    priv = Ed25519PrivateKey.generate()
    key_id = "overview-skel-001"
    pub = public_key_b64url(priv.public_key())
    config = {
        "keys": [
            {
                "key_id": key_id,
                "signature_version": 1,
                "algorithm": "ed25519",
                "environment": "test",
                "public_key_b64url": pub,
                "status": "active",
            }
        ],
        "commerce": {
            "afdian_product_url": "https://afdian.com/item/test",
            "product_code": "storylens_pro",
        },
    }
    path = tmp_path / "license_public_keys.test.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(entitlement, "is_production_runtime", lambda: False)
    monkeypatch.setattr(entitlement, "license_config_path", lambda: path)
    monkeypatch.setattr(entitlement, "app_major_version", lambda: 1)
    return priv, key_id, private_key_b64url(priv)


def _activate_pro(session: Session, license_keypair) -> None:
    priv, key_id, _ = license_keypair
    payload = build_unsigned_payload(major_version=1, key_id=key_id)
    code = encode_license(payload, priv)
    entitlement.activate_license_code(session, code)
    session.commit()


@pytest.fixture()
def enable_native_overview(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PRO_NATIVE_OVERVIEW_ENABLED", "true")
    assert is_pro_native_overview_enabled() is True


@pytest.fixture()
def api_env(tmp_path, fake_provider, license_keypair, enable_native_overview):
    """Temp SQLite + TestClient with shared session factory."""
    from app.db.session import get_db, get_session_factory
    from app.main import app
    from app.model_gateway.gateway import ModelGateway
    from app.model_gateway.registry import get_model_gateway

    engine = create_engine(
        f"sqlite:///{tmp_path / 'native_overview.db'}",
        connect_args={"check_same_thread": False},
    )
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_db():
        with factory() as session:
            yield session

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_session_factory] = lambda: factory
    app.dependency_overrides[get_model_gateway] = lambda: ModelGateway([fake_provider])
    client = TestClient(app)
    try:
        yield {"client": client, "factory": factory, "license_keypair": license_keypair}
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        engine.dispose()


def _seed_pro_book(api_env) -> int:
    factory = api_env["factory"]
    with factory() as session:
        book = seed_short_book_v1(session)
        session.commit()
        book_id = int(book.id)
        _activate_pro(session, api_env["license_keypair"])
    return book_id


def test_fixture_hash_unchanged():
    result = verify_fixture_manifest(default_public_fixture_dir())
    assert result["combined_sha256"] == EXPECTED_COMBINED
    assert WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is True


def test_preflight_native_overview(api_env):
    book_id = _seed_pro_book(api_env)
    resp = api_env["client"].post(
        f"/api/v1/books/{book_id}/whole-book-runs/preflight",
        json={"module_key": "book_overview", "mode": "whole_book_native"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["book_id"] == str(book_id)
    assert body["chapter_count"] == 2
    assert body["paragraph_count"] == 4
    assert body["license_allowed"] is True
    assert body["run_creation_enabled"] is True
    assert body["estimated_tokens"] == 0
    assert body["estimated_cost"] == 0.0
    assert FIXTURE_DEVELOPMENT_WARNING in body["warnings"]
    assert body["blocking_errors"] == []


def test_free_403(api_env):
    factory = api_env["factory"]
    with factory() as session:
        book = seed_short_book_v1(session)
        session.commit()
        book_id = int(book.id)
    resp = api_env["client"].post(
        f"/api/v1/books/{book_id}/whole-book-runs",
        json=CREATE_BODY,
    )
    assert resp.status_code == 403
    body = resp.json()
    assert body["error_code"] == "PRO_LICENSE_REQUIRED"


def test_feature_flag_off(api_env, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PRO_NATIVE_OVERVIEW_ENABLED", "false")
    book_id = _seed_pro_book(api_env)
    pre = api_env["client"].post(
        f"/api/v1/books/{book_id}/whole-book-runs/preflight",
        json={"module_key": "book_overview", "mode": "whole_book_native"},
    )
    assert pre.status_code == 200
    assert pre.json()["run_creation_enabled"] is False
    assert any(
        (e.get("code") if isinstance(e, dict) else e) == "PRO_NATIVE_OVERVIEW_UNAVAILABLE"
        for e in pre.json()["blocking_errors"]
    )
    resp = api_env["client"].post(
        f"/api/v1/books/{book_id}/whole-book-runs",
        json=CREATE_BODY,
    )
    assert resp.status_code == 503
    assert resp.json()["error_code"] == "PRO_NATIVE_OVERVIEW_UNAVAILABLE"


def test_create_run_happy_path(api_env):
    book_id = _seed_pro_book(api_env)
    resp = api_env["client"].post(
        f"/api/v1/books/{book_id}/whole-book-runs",
        json=CREATE_BODY,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == RunStatus.COMPLETED.value
    assert body["mode"] == "whole_book_native"
    assert body["module_key"] == "book_overview"
    run_id = int(body["run_id"])
    snapshot_id = int(body["snapshot_id"])

    factory = api_env["factory"]
    with factory() as session:
        run = session.get(AnalysisRun, run_id)
        assert run is not None
        assert run.book_snapshot_id == snapshot_id
        assert run.provider == FIXTURE_ENGINE_ID
        assert run.model == FIXTURE_ENGINE_VERSION
        stages = list(
            session.scalars(
                select(AnalysisRunStage)
                .where(AnalysisRunStage.run_id == run_id)
                .order_by(AnalysisRunStage.stage_order)
            )
        )
        assert [s.stage_key for s in stages] == [k.value for k in OverviewProductionStageKey]
        assert all(s.status == "completed" for s in stages)

        windows = list(
            session.scalars(select(WholeBookRunWindow).where(WholeBookRunWindow.run_id == run_id))
        )
        assert len(windows) == 1
        w = windows[0]
        assert w.window_index == 0
        assert w.status == WindowStatus.COMPLETED.value
        assert w.attempt_count == 1
        assert w.start_chapter_id != w.end_chapter_id
        assert w.state_version_after == 1

        entities = session.scalars(
            select(NarrativeEntity).where(NarrativeEntity.book_id == book_id)
        ).all()
        assert len(entities) >= 1
        assets = session.scalars(
            select(NarrativeAsset).where(NarrativeAsset.book_id == book_id)
        ).all()
        assert len(assets) >= 3
        versions = session.scalars(
            select(NarrativeAssetVersion).where(NarrativeAssetVersion.run_id == run_id)
        ).all()
        assert len(versions) >= 3
        evidence = session.scalars(select(NarrativeAssetEvidence)).all()
        assert len(evidence) >= 2
        state_versions = session.scalars(
            select(WholeBookRunStateVersion).where(WholeBookRunStateVersion.run_id == run_id)
        ).all()
        assert len(state_versions) >= 1
        artifact = session.scalar(
            select(AnalysisArtifact).where(
                AnalysisArtifact.run_id == run_id,
                AnalysisArtifact.artifact_type == OVERVIEW_PROJECTION_ARTIFACT_TYPE,
            )
        )
        assert artifact is not None


def test_get_run_and_overview_coverage(api_env):
    book_id = _seed_pro_book(api_env)
    created = api_env["client"].post(
        f"/api/v1/books/{book_id}/whole-book-runs",
        json=CREATE_BODY,
    ).json()
    run_id = created["run_id"]

    status = api_env["client"].get(f"/api/v1/whole-book-runs/{run_id}")
    assert status.status_code == 200
    st = status.json()
    assert st["status"] == "completed"
    assert st["provider"] == FIXTURE_ENGINE_ID
    assert st["progress"]["total_windows"] == 1
    assert st["progress"]["completed_windows"] == 1
    assert st["progress"]["percent"] == 100.0

    overview = api_env["client"].get(f"/api/v1/whole-book-runs/{run_id}/overview")
    assert overview.status_code == 200
    ov = overview.json()
    assert ov["coverage"]["original_coverage_percent"] == 100.0
    assert ov["coverage"]["original_paragraphs_total"] == 4
    assert ov["coverage"]["original_paragraphs_covered"] == 4
    assert ov["overview"]["protagonist"]["value"] == "林澈"
    assert ov["engine_version"] == FIXTURE_ENGINE_VERSION
    assert FIXTURE_DEVELOPMENT_WARNING in ov["warnings"] or ov["warnings"]
    assert len(ov["evidence_index"]) >= 1
    link = ov["evidence_index"][0]["deep_link"]
    assert link["book_id"] == str(book_id)
    assert link["paragraph_id"]


def test_client_request_id_idempotent(api_env):
    book_id = _seed_pro_book(api_env)
    r1 = api_env["client"].post(
        f"/api/v1/books/{book_id}/whole-book-runs",
        json=CREATE_BODY,
    )
    r2 = api_env["client"].post(
        f"/api/v1/books/{book_id}/whole-book-runs",
        json=CREATE_BODY,
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["run_id"] == r2.json()["run_id"]
    factory = api_env["factory"]
    with factory() as session:
        count = session.scalar(
            select(func.count())
            .select_from(AnalysisRun)
            .where(
                AnalysisRun.book_id == book_id,
                AnalysisRun.client_request_id == CREATE_BODY["client_request_id"],
            )
        )
        assert count == 1


def test_private_adapter_failure(api_env, monkeypatch: pytest.MonkeyPatch):
    class Boom:
        engine_id = FIXTURE_ENGINE_ID

        def analyze_window(self, payload, transport=None):  # noqa: ANN001
            raise RuntimeError("fixture boom")

        def synthesize_overview(self, payload, transport=None):  # noqa: ANN001
            raise RuntimeError("fixture boom")

    book_id = _seed_pro_book(api_env)

    original_init = NativeOverviewService.__init__

    def patched_init(self, session, *, adapter=None, engine_id=FIXTURE_ENGINE_ID):  # noqa: ANN001
        original_init(self, session, adapter=Boom(), engine_id=engine_id)

    monkeypatch.setattr(NativeOverviewService, "__init__", patched_init)

    resp = api_env["client"].post(
        f"/api/v1/books/{book_id}/whole-book-runs",
        json={**CREATE_BODY, "client_request_id": "req-fail-001"},
    )
    assert resp.status_code == 503
    assert resp.json()["error_code"] == "PRIVATE_ENGINE_UNAVAILABLE"

    factory = api_env["factory"]
    with factory() as session:
        run = session.scalar(
            select(AnalysisRun).where(AnalysisRun.client_request_id == "req-fail-001")
        )
        assert run is not None
        assert run.status == RunStatus.FAILED.value
        assert run.error_code == "PRIVATE_ENGINE_UNAVAILABLE"
        failed_stages = list(
            session.scalars(
                select(AnalysisRunStage).where(
                    AnalysisRunStage.run_id == run.id,
                    AnalysisRunStage.status == "failed",
                )
            )
        )
        assert len(failed_stages) >= 1


def test_new_session_reread(api_env):
    book_id = _seed_pro_book(api_env)
    created = api_env["client"].post(
        f"/api/v1/books/{book_id}/whole-book-runs",
        json=CREATE_BODY,
    ).json()
    run_id = created["run_id"]

    # Brand-new session (not the request session) must still read completed facts.
    factory = api_env["factory"]
    with factory() as session:
        run = session.get(AnalysisRun, int(run_id))
        assert run is not None and run.status == "completed"
        evidence_count = session.scalar(select(func.count()).select_from(NarrativeAssetEvidence))
        assert int(evidence_count or 0) >= 2
        artifact = session.scalar(
            select(AnalysisArtifact).where(
                AnalysisArtifact.run_id == int(run_id),
                AnalysisArtifact.artifact_type == OVERVIEW_PROJECTION_ARTIFACT_TYPE,
            )
        )
        assert artifact is not None

    overview = api_env["client"].get(f"/api/v1/whole-book-runs/{run_id}/overview")
    assert overview.status_code == 200
    assert overview.json()["run"]["status"] == "completed"


def test_does_not_call_chapter_aggregation_insights(api_env, monkeypatch: pytest.MonkeyPatch):
    book_id = _seed_pro_book(api_env)
    calls: list[str] = []

    from app.routers import pro_whole_book_insights as insights_mod

    original = insights_mod.get_whole_book_insights

    def guarded(*args, **kwargs):  # noqa: ANN001
        calls.append("hit")
        return original(*args, **kwargs)

    monkeypatch.setattr(insights_mod, "get_whole_book_insights", guarded)

    created = api_env["client"].post(
        f"/api/v1/books/{book_id}/whole-book-runs",
        json={**CREATE_BODY, "client_request_id": "req-no-insights"},
    )
    assert created.status_code == 201
    overview = api_env["client"].get(
        f"/api/v1/whole-book-runs/{created.json()['run_id']}/overview"
    )
    assert overview.status_code == 200
    # Overview walking skeleton must not hit chapter-aggregation insights.
    assert calls == []


def test_free_book_chapter_paragraph_read_regression(api_env):
    book_id = _seed_pro_book(api_env)
    client: TestClient = api_env["client"]
    book = client.get(f"/api/v1/books/{book_id}")
    assert book.status_code == 200
    chapters = client.get(f"/api/v1/books/{book_id}/chapters")
    assert chapters.status_code == 200
    assert len(chapters.json()) == 2
    chapter_id = chapters.json()[0]["id"]
    paras = client.get(f"/api/v1/chapters/{chapter_id}/paragraphs")
    assert paras.status_code == 200
    assert len(paras.json()["items"] if isinstance(paras.json(), dict) else paras.json()) >= 2


def test_fixture_engine_loads_via_loader():
    from app.narrative_core.services.whole_book_overview_engine_loader import (
        load_overview_engine,
    )

    adapter = load_overview_engine(FIXTURE_ENGINE_ID)
    assert adapter.engine_id == FIXTURE_ENGINE_ID
    assert isinstance(adapter, WholeBookOverviewEngineAdapter)


def test_force_fake_removed():
    from app.narrative_core.services.native_overview_fixture_adapter import (
        get_fixture_adapter,
    )
    from app.narrative_core.services.whole_book_overview_engine_loader import (
        EngineLoadError,
    )

    with pytest.raises(EngineLoadError):
        get_fixture_adapter(force_fake=True)


def test_create_run_request_validates():
    CreateRunRequest.model_validate(CREATE_BODY)
