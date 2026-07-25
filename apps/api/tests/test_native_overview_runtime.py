"""STEP 2.3-A5 — Multi-window / recovery / retry API / Free regression tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AnalysisRun,
    Base,
    ModelInvocation,
    NarrativeAsset,
    NarrativeAssetEvidence,
    NarrativeAssetVersion,
    NarrativeEntity,
    WholeBookRunStateVersion,
    WholeBookRunWindow,
)
from app.narrative_core.contracts.api_dto import WHOLE_BOOK_RUNS_ENDPOINT_DISABLED
from app.narrative_core.contracts.pro_native_overview_flags import (
    FIXTURE_ENGINE_ID,
    is_pro_native_overview_enabled,
)
from app.narrative_core.enums import RunStatus, WindowStatus
from app.narrative_core.services.native_overview_context_windows import OverviewWindowBudget
from app.narrative_core.services.native_overview_provider_accounting import (
    RecordingFakeTransport,
)
from app.narrative_core.services.native_overview_seed import seed_short_book_v1
from app.narrative_core.services.native_overview_service import NativeOverviewService
from app.services import entitlement
from app.services.license_crypto import (
    build_unsigned_payload,
    encode_license,
    private_key_b64url,
    public_key_b64url,
)

CREATE_BODY = {
    "mode": "whole_book_native",
    "module_key": "book_overview",
    "provider_id": FIXTURE_ENGINE_ID,
    "model_id": "fixture-native-overview-1",
    "client_request_id": "req-runtime-001",
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
    key_id = "overview-runtime-001"
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
def api_env(tmp_path, fake_provider, license_keypair, enable_native_overview, monkeypatch):
    from app.db.session import get_db, get_session_factory
    from app.main import app
    from app.model_gateway.gateway import ModelGateway
    from app.model_gateway.registry import get_model_gateway

    engine = create_engine(
        f"sqlite:///{tmp_path / 'native_overview_runtime.db'}",
        connect_args={"check_same_thread": False},
    )
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    transport = RecordingFakeTransport()
    budget = OverviewWindowBudget(
        max_paragraphs_per_window=1,
        overlap_paragraphs=0,
        max_characters_per_window=50_000,
        max_tokens_estimated=20_000,
    )

    original_init = NativeOverviewService.__init__

    def patched_init(self, session, *, adapter=None, engine_id=FIXTURE_ENGINE_ID, **kwargs):  # noqa: ANN001
        original_init(
            self,
            session,
            adapter=adapter,
            engine_id=engine_id,
            transport=transport,
            window_budget=budget,
        )

    monkeypatch.setattr(NativeOverviewService, "__init__", patched_init)

    def override_db():
        with factory() as session:
            yield session

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_session_factory] = lambda: factory
    app.dependency_overrides[get_model_gateway] = lambda: ModelGateway([fake_provider])
    client = TestClient(app)
    try:
        yield {
            "client": client,
            "factory": factory,
            "license_keypair": license_keypair,
            "transport": transport,
            "budget": budget,
        }
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


def test_flag_default_and_legacy_endpoint_gate():
    assert WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is True


def test_multi_window_run_full_coverage(api_env):
    book_id = _seed_pro_book(api_env)
    resp = api_env["client"].post(
        f"/api/v1/books/{book_id}/whole-book-runs",
        json={**CREATE_BODY, "client_request_id": "req-multi-001"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == RunStatus.COMPLETED.value
    run_id = int(body["run_id"])

    factory = api_env["factory"]
    with factory() as session:
        windows = list(
            session.scalars(
                select(WholeBookRunWindow)
                .where(WholeBookRunWindow.run_id == run_id)
                .order_by(WholeBookRunWindow.window_index)
            )
        )
        assert len(windows) == 4
        assert all(w.status == WindowStatus.COMPLETED.value for w in windows)
        assert [w.window_index for w in windows] == [0, 1, 2, 3]
        assert all(int(w.attempt_count or 0) == 1 for w in windows)
        state_versions = list(
            session.scalars(
                select(WholeBookRunStateVersion)
                .where(WholeBookRunStateVersion.run_id == run_id)
                .order_by(WholeBookRunStateVersion.version_number)
            )
        )
        assert len(state_versions) == 4
        assert [s.version_number for s in state_versions] == [1, 2, 3, 4]
        # Entity merge across windows: same protagonist collapses.
        entities = session.scalars(
            select(NarrativeEntity).where(NarrativeEntity.book_id == book_id)
        ).all()
        assert len(entities) >= 1
        invocations = session.scalars(
            select(ModelInvocation).where(ModelInvocation.run_id == run_id)
        ).all()
        assert len(invocations) == 4
        assert api_env["transport"].call_count == 4

    overview = api_env["client"].get(f"/api/v1/whole-book-runs/{run_id}/overview")
    assert overview.status_code == 200
    cov = overview.json()["coverage"]
    assert cov["original_coverage_percent"] == 100.0
    assert cov["original_paragraphs_total"] == 4
    assert cov["original_paragraphs_covered"] == 4
    assert cov["windows_total"] == 4
    assert cov["windows_completed"] == 4

    status = api_env["client"].get(f"/api/v1/whole-book-runs/{run_id}")
    assert status.status_code == 200
    st = status.json()
    assert st["progress"]["total_windows"] == 4
    assert st["progress"]["completed_windows"] == 4
    assert st["actual_tokens"] > 0


def test_retry_skips_completed_windows(api_env, monkeypatch: pytest.MonkeyPatch):
    book_id = _seed_pro_book(api_env)
    transport: RecordingFakeTransport = api_env["transport"]

    class Flaky:
        engine_id = FIXTURE_ENGINE_ID
        calls = 0

        def analyze_window(self, payload, transport=None):  # noqa: ANN001
            Flaky.calls += 1
            if Flaky.calls == 2:
                raise RuntimeError("boom-on-second-window")
            from app.narrative_core.services.whole_book_overview_engine_loader import (
                load_overview_engine,
            )

            return load_overview_engine(FIXTURE_ENGINE_ID).analyze_window(payload, transport)

        def synthesize_overview(self, payload, transport=None):  # noqa: ANN001
            from app.narrative_core.services.whole_book_overview_engine_loader import (
                load_overview_engine,
            )

            return load_overview_engine(FIXTURE_ENGINE_ID).synthesize_overview(
                payload, transport
            )

    original_init = NativeOverviewService.__init__

    def flaky_init(self, session, *, adapter=None, engine_id=FIXTURE_ENGINE_ID, **kwargs):  # noqa: ANN001
        original_init(
            self,
            session,
            adapter=Flaky(),
            engine_id=engine_id,
            transport=transport,
            window_budget=api_env["budget"],
        )

    monkeypatch.setattr(NativeOverviewService, "__init__", flaky_init)

    failed = api_env["client"].post(
        f"/api/v1/books/{book_id}/whole-book-runs",
        json={**CREATE_BODY, "client_request_id": "req-retry-fail"},
    )
    assert failed.status_code == 503
    factory = api_env["factory"]
    with factory() as session:
        run = session.scalar(
            select(AnalysisRun).where(AnalysisRun.client_request_id == "req-retry-fail")
        )
        assert run is not None
        assert run.status == RunStatus.FAILED.value
        run_id = int(run.id)
        windows = list(
            session.scalars(
                select(WholeBookRunWindow)
                .where(WholeBookRunWindow.run_id == run_id)
                .order_by(WholeBookRunWindow.window_index)
            )
        )
        assert windows[0].status == WindowStatus.COMPLETED.value
        assert windows[1].status == WindowStatus.FAILED.value
        completed_attempts_before = int(windows[0].attempt_count or 0)
        provider_calls_before = transport.call_count

    # Restore healthy service for retry.
    def healthy_init(self, session, *, adapter=None, engine_id=FIXTURE_ENGINE_ID, **kwargs):  # noqa: ANN001
        original_init(
            self,
            session,
            adapter=None,
            engine_id=engine_id,
            transport=transport,
            window_budget=api_env["budget"],
        )

    monkeypatch.setattr(NativeOverviewService, "__init__", healthy_init)

    retry = api_env["client"].post(
        f"/api/v1/whole-book-runs/{run_id}/retry",
        json={"client_request_id": "retry-1", "reason": "recover second window"},
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["status"] == RunStatus.COMPLETED.value

    # Idempotent replay
    retry2 = api_env["client"].post(
        f"/api/v1/whole-book-runs/{run_id}/retry",
        json={"client_request_id": "retry-1"},
    )
    assert retry2.status_code == 200
    assert retry2.json()["status"] == RunStatus.COMPLETED.value

    with factory() as session:
        windows = list(
            session.scalars(
                select(WholeBookRunWindow)
                .where(WholeBookRunWindow.run_id == run_id)
                .order_by(WholeBookRunWindow.window_index)
            )
        )
        assert all(w.status == WindowStatus.COMPLETED.value for w in windows)
        assert int(windows[0].attempt_count or 0) == completed_attempts_before
        assert int(windows[1].attempt_count or 0) >= 2
        # Completed window must not trigger extra provider Attempt on retry.
        assert transport.call_count == provider_calls_before + 3  # windows 1..3

        asset_versions = session.scalars(
            select(NarrativeAssetVersion).where(NarrativeAssetVersion.run_id == run_id)
        ).all()
        fingerprints = [v.source_fingerprint for v in asset_versions]
        assert len(fingerprints) == len(set(fingerprints))

    overview = api_env["client"].get(f"/api/v1/whole-book-runs/{run_id}/overview")
    assert overview.status_code == 200
    assert overview.json()["coverage"]["original_coverage_percent"] == 100.0


def test_resume_rejected_unless_paused(api_env):
    book_id = _seed_pro_book(api_env)
    created = api_env["client"].post(
        f"/api/v1/books/{book_id}/whole-book-runs",
        json={**CREATE_BODY, "client_request_id": "req-resume-gate"},
    )
    assert created.status_code == 201
    run_id = created.json()["run_id"]
    resume = api_env["client"].post(
        f"/api/v1/whole-book-runs/{run_id}/resume",
        json={"client_request_id": "resume-1"},
    )
    assert resume.status_code == 409
    assert resume.json()["error_code"] in {
        "RUN_ALREADY_COMPLETED",
        "RUN_NOT_RESUMABLE",
    }


def test_completed_run_not_retryable(api_env):
    book_id = _seed_pro_book(api_env)
    created = api_env["client"].post(
        f"/api/v1/books/{book_id}/whole-book-runs",
        json={**CREATE_BODY, "client_request_id": "req-no-retry-completed"},
    )
    assert created.status_code == 201
    run_id = created.json()["run_id"]
    retry = api_env["client"].post(
        f"/api/v1/whole-book-runs/{run_id}/retry",
        json={"client_request_id": "retry-completed"},
    )
    assert retry.status_code == 409
    assert retry.json()["error_code"] == "RUN_ALREADY_COMPLETED"


def test_free_regression_403_and_book_reads(api_env):
    factory = api_env["factory"]
    with factory() as session:
        book = seed_short_book_v1(session)
        session.commit()
        book_id = int(book.id)

    client: TestClient = api_env["client"]
    denied = client.post(
        f"/api/v1/books/{book_id}/whole-book-runs",
        json={**CREATE_BODY, "client_request_id": "req-free-deny"},
    )
    assert denied.status_code == 403
    assert denied.json()["error_code"] == "PRO_LICENSE_REQUIRED"

    # Free book/chapter/paragraph reads still work without Pro.
    book = client.get(f"/api/v1/books/{book_id}")
    assert book.status_code == 200
    chapters = client.get(f"/api/v1/books/{book_id}/chapters")
    assert chapters.status_code == 200
    assert len(chapters.json()) == 2


def test_materializer_idempotent_retry_no_duplicate_evidence(api_env, monkeypatch):
    """Re-materializing the same completed window result must not duplicate rows."""
    book_id = _seed_pro_book(api_env)
    created = api_env["client"].post(
        f"/api/v1/books/{book_id}/whole-book-runs",
        json={**CREATE_BODY, "client_request_id": "req-idem-mat"},
    )
    assert created.status_code == 201
    run_id = int(created.json()["run_id"])
    factory = api_env["factory"]
    with factory() as session:
        before_assets = session.scalar(
            select(func.count()).select_from(NarrativeAsset).where(NarrativeAsset.book_id == book_id)
        )
        before_evidence = session.scalar(select(func.count()).select_from(NarrativeAssetEvidence))
        before_versions = session.scalar(
            select(func.count())
            .select_from(NarrativeAssetVersion)
            .where(NarrativeAssetVersion.run_id == run_id)
        )
        from app.narrative_core.contracts.whole_book_overview_v1 import (
            WholeBookOverviewWindowResultV1,
        )
        from app.narrative_core.services.native_overview_materializer import (
            NativeOverviewMaterializer,
        )

        window = session.scalar(
            select(WholeBookRunWindow).where(
                WholeBookRunWindow.run_id == run_id,
                WholeBookRunWindow.window_index == 0,
            )
        )
        assert window is not None
        raw = json.loads(window.checkpoint_json or "{}").get("window_result")
        result = WholeBookOverviewWindowResultV1.model_validate(raw)
        run = session.get(AnalysisRun, run_id)
        mat = NativeOverviewMaterializer(session)
        prior = mat.load_prior_state(run_id)
        # Force same version_number path by using prior.state_version-1 equivalent.
        from app.narrative_core.contracts.whole_book_overview_v1 import PriorStateV1

        mat.materialize_window(
            run,
            window,
            result,
            prior_state=PriorStateV1(state_version=max(0, int(prior.state_version) - 1)),
        )
        session.commit()
        after_assets = session.scalar(
            select(func.count()).select_from(NarrativeAsset).where(NarrativeAsset.book_id == book_id)
        )
        after_evidence = session.scalar(select(func.count()).select_from(NarrativeAssetEvidence))
        after_versions = session.scalar(
            select(func.count())
            .select_from(NarrativeAssetVersion)
            .where(NarrativeAssetVersion.run_id == run_id)
        )
        assert after_assets == before_assets
        assert after_versions == before_versions
        assert after_evidence == before_evidence
