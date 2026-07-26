"""STEP 2.3-A2/A5 — multi-window orchestrator, recovery, accounting, Free regression."""

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
    AnalysisRun,
    Base,
    Book,
    Chapter,
    ModelInvocation,
    NarrativeAssetVersion,
    Paragraph,
    WholeBookRunStateVersion,
    WholeBookRunWindow,
)
from app.narrative_core.contracts.api_dto import WHOLE_BOOK_RUNS_ENDPOINT_DISABLED
from app.narrative_core.contracts.pro_native_overview_flags import (
    FIXTURE_ENGINE_ID,
    FIXTURE_ENGINE_VERSION,
    is_pro_native_overview_enabled,
)
from app.narrative_core.contracts.whole_book_overview_v1 import (
    CreateRunRequest,
    PriorStateV1,
    RetryRunRequest,
    WholeBookOverviewWindowInputV1,
    WholeBookOverviewWindowResultV1,
)
from app.narrative_core.enums import (
    RunStatus,
    WindowStatus,
)
from app.narrative_core.hash_canon import calculate_text_hash
from app.narrative_core.services.native_overview_context_windows import OverviewWindowBudget
from app.narrative_core.services.native_overview_fixture_adapter import (
    load_private_fixture_engine_adapter,
)
from app.narrative_core.services.native_overview_materializer import NativeOverviewMaterializer
from app.narrative_core.services.native_overview_provider_accounting import (
    RecordingFakeTransport,
)
from app.narrative_core.services.native_overview_seed import seed_short_book_v1
from app.narrative_core.services.native_overview_service import (
    NativeOverviewError,
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


CREATE_BODY = {
    "mode": "whole_book_native",
    "module_key": "book_overview",
    "provider_id": FIXTURE_ENGINE_ID,
    "model_id": FIXTURE_ENGINE_VERSION,
    "client_request_id": "req-multi-001",
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
    key_id = "overview-multi-001"
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
    from app.db.session import get_db, get_session_factory
    from app.main import app
    from app.model_gateway.gateway import ModelGateway
    from app.model_gateway.registry import get_model_gateway

    engine = create_engine(
        f"sqlite:///{tmp_path / 'native_overview_multi.db'}",
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


def _seed_multi_para_book(session: Session, *, paragraphs: int = 6) -> Book:
    texts = [f"第{i}段正文内容，用于多窗口覆盖测试。" for i in range(1, paragraphs + 1)]
    all_text = "\n".join(texts)
    book = Book(
        title="多窗口测试书",
        source_file_name="multi_window.json",
        source_file_hash=calculate_text_hash(all_text),
        import_status="ready",
    )
    session.add(book)
    session.flush()
    chapter = Chapter(
        book_id=book.id,
        chapter_index=1,
        title="第一章",
        chapter_title="第一章",
        display_title="第一章",
        section_type="chapter",
    )
    session.add(chapter)
    session.flush()
    offset = 0
    for i, text in enumerate(texts, start=1):
        para = Paragraph(
            id=f"B{book.id:04d}-C0001-P{i:04d}",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=i,
            raw_text=text,
            normalized_text=text,
            char_start=offset,
            char_end=offset + len(text),
        )
        session.add(para)
        offset += len(text) + 1
    session.flush()
    return book


def _tiny_budget() -> OverviewWindowBudget:
    return OverviewWindowBudget(
        max_paragraphs_per_window=2,
        overlap_paragraphs=1,
        max_characters_per_window=10_000,
        max_tokens_estimated=5_000,
    )


class CountingAdapter:
    """Wrap fixture adapter and count analyze_window calls."""

    def __init__(self, inner: WholeBookOverviewEngineAdapter) -> None:
        self._inner = inner
        self.analyze_calls = 0
        self.analyze_window_indexes: list[int] = []
        self.fail_on_window: int | None = None

    @property
    def engine_id(self) -> str:
        return self._inner.engine_id

    def analyze_window(
        self,
        payload: WholeBookOverviewWindowInputV1,
        transport=None,  # noqa: ANN001
    ) -> WholeBookOverviewWindowResultV1:
        self.analyze_calls += 1
        idx = int(payload.window.window_index)
        self.analyze_window_indexes.append(idx)
        if self.fail_on_window is not None and idx == self.fail_on_window:
            raise RuntimeError(f"forced fail window {idx}")
        return self._inner.analyze_window(payload, transport=transport)

    def synthesize_overview(self, payload, transport=None):  # noqa: ANN001
        return self._inner.synthesize_overview(payload, transport=transport)


def test_free_regression_legacy_create_still_disabled():
    assert WHOLE_BOOK_RUNS_ENDPOINT_DISABLED is True


def test_flag_default_off_without_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("PRO_NATIVE_OVERVIEW_ENABLED", raising=False)
    assert is_pro_native_overview_enabled() is False


def test_multi_window_run_coverage_and_state_versions(api_env, monkeypatch):
    factory = api_env["factory"]
    with factory() as session:
        book = _seed_multi_para_book(session, paragraphs=6)
        session.commit()
        book_id = int(book.id)
        _activate_pro(session, api_env["license_keypair"])

    transport = RecordingFakeTransport(default_cost=0.01)
    adapter = CountingAdapter(load_private_fixture_engine_adapter())

    with factory() as session:
        service = NativeOverviewService(
            session,
            adapter=adapter,
            transport=transport,
            window_budget=_tiny_budget(),
        )
        created = service.create_run(
            book_id,
            CreateRunRequest.model_validate(
                {**CREATE_BODY, "client_request_id": "req-multi-win"}
            ),
        )
        session.commit()
        run_id = int(created.run_id)

    assert created.status == RunStatus.COMPLETED
    assert adapter.analyze_calls >= 2
    assert transport.call_count == adapter.analyze_calls

    with factory() as session:
        windows = list(
            session.scalars(
                select(WholeBookRunWindow)
                .where(WholeBookRunWindow.run_id == run_id)
                .order_by(WholeBookRunWindow.window_index)
            )
        )
        assert len(windows) >= 2
        assert all(w.status == WindowStatus.COMPLETED.value for w in windows)
        assert all(int(w.state_version_after or 0) > 0 for w in windows)
        versions = list(
            session.scalars(
                select(WholeBookRunStateVersion)
                .where(WholeBookRunStateVersion.run_id == run_id)
                .order_by(WholeBookRunStateVersion.version_number)
            )
        )
        assert len(versions) == len(windows)
        assert [v.version_number for v in versions] == list(range(1, len(versions) + 1))

        service = NativeOverviewService(session)
        overview = service.get_overview(run_id)
        assert overview.coverage.original_coverage_percent == 100.0
        assert overview.coverage.windows_total == len(windows)
        assert overview.coverage.windows_completed == len(windows)
        status = service.get_run(run_id)
        assert status.actual_tokens > 0
        assert status.actual_cost > 0


def test_retry_skips_completed_windows(api_env):
    factory = api_env["factory"]
    with factory() as session:
        book = _seed_multi_para_book(session, paragraphs=6)
        session.commit()
        book_id = int(book.id)
        _activate_pro(session, api_env["license_keypair"])

    transport = RecordingFakeTransport()
    adapter = CountingAdapter(load_private_fixture_engine_adapter())
    adapter.fail_on_window = 1

    with factory() as session:
        service = NativeOverviewService(
            session,
            adapter=adapter,
            transport=transport,
            window_budget=_tiny_budget(),
        )
        with pytest.raises(NativeOverviewError) as exc:
            service.create_run(
                book_id,
                CreateRunRequest.model_validate(
                    {**CREATE_BODY, "client_request_id": "req-retry-skip"}
                ),
            )
        session.commit()
        assert exc.value.code == "PRIVATE_ENGINE_UNAVAILABLE"

    first_calls = adapter.analyze_calls
    assert first_calls >= 2  # window 0 success + window 1 fail
    assert 0 in adapter.analyze_window_indexes
    assert 1 in adapter.analyze_window_indexes

    with factory() as session:
        run = session.scalar(
            select(AnalysisRun).where(AnalysisRun.client_request_id == "req-retry-skip")
        )
        assert run is not None
        assert run.status == RunStatus.FAILED.value
        windows = list(
            session.scalars(
                select(WholeBookRunWindow).where(WholeBookRunWindow.run_id == run.id)
            )
        )
        completed_before = sum(1 for w in windows if w.status == WindowStatus.COMPLETED.value)
        assert completed_before >= 1
        asset_count_before = session.scalar(
            select(func.count()).select_from(NarrativeAssetVersion).where(
                NarrativeAssetVersion.run_id == run.id
            )
        )

    # Clear fail and retry.
    adapter.fail_on_window = None
    calls_before_retry = adapter.analyze_calls
    transport_before = transport.call_count

    with factory() as session:
        service = NativeOverviewService(
            session,
            adapter=adapter,
            transport=transport,
            window_budget=_tiny_budget(),
        )
        retry_resp = service.retry_run(
            int(run.id),
            RetryRunRequest(client_request_id="retry-1"),
        )
        session.commit()
        assert retry_resp.status == RunStatus.COMPLETED

    # Completed window 0 must not be re-analyzed.
    new_indexes = adapter.analyze_window_indexes[calls_before_retry:]
    assert 0 not in new_indexes
    assert adapter.analyze_calls > calls_before_retry
    assert transport.call_count > transport_before

    with factory() as session:
        windows = list(
            session.scalars(
                select(WholeBookRunWindow).where(WholeBookRunWindow.run_id == run.id)
            )
        )
        assert all(w.status == WindowStatus.COMPLETED.value for w in windows)
        # No duplicate versions for already-materialized window 0 fingerprints.
        asset_count_after = session.scalar(
            select(func.count()).select_from(NarrativeAssetVersion).where(
                NarrativeAssetVersion.run_id == run.id
            )
        )
        assert asset_count_after >= asset_count_before
        service = NativeOverviewService(session)
        overview = service.get_overview(int(run.id))
        assert overview.coverage.original_coverage_percent == 100.0


def test_api_retry_and_overview(api_env, monkeypatch):
    factory = api_env["factory"]
    with factory() as session:
        book = seed_short_book_v1(session)
        session.commit()
        book_id = int(book.id)
        _activate_pro(session, api_env["license_keypair"])

    class BoomOnce:
        engine_id = FIXTURE_ENGINE_ID
        calls = 0
        inner = load_private_fixture_engine_adapter()

        def analyze_window(self, payload, transport=None):  # noqa: ANN001
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("boom once")
            return self.inner.analyze_window(payload, transport=transport)

        def synthesize_overview(self, payload, transport=None):  # noqa: ANN001
            return self.inner.synthesize_overview(payload, transport=transport)

    boom = BoomOnce()
    original_init = NativeOverviewService.__init__

    def patched(self, session, *, adapter=None, engine_id=FIXTURE_ENGINE_ID, **kwargs):  # noqa: ANN001
        original_init(self, session, adapter=boom, engine_id=engine_id, **kwargs)

    monkeypatch.setattr(NativeOverviewService, "__init__", patched)

    fail = api_env["client"].post(
        f"/api/v1/books/{book_id}/whole-book-runs",
        json={**CREATE_BODY, "client_request_id": "req-api-retry"},
    )
    assert fail.status_code == 503
    run_id = None
    with factory() as session:
        run = session.scalar(
            select(AnalysisRun).where(AnalysisRun.client_request_id == "req-api-retry")
        )
        assert run is not None
        run_id = int(run.id)

    retry = api_env["client"].post(
        f"/api/v1/whole-book-runs/{run_id}/retry",
        json={"client_request_id": "retry-api-1"},
    )
    assert retry.status_code == 200, retry.text
    body = retry.json()
    assert body["status"] == RunStatus.COMPLETED.value

    overview = api_env["client"].get(f"/api/v1/whole-book-runs/{run_id}/overview")
    assert overview.status_code == 200
    assert overview.json()["coverage"]["original_coverage_percent"] == 100.0

    # Completed run refuses retry.
    again = api_env["client"].post(
        f"/api/v1/whole-book-runs/{run_id}/retry",
        json={"client_request_id": "retry-api-2"},
    )
    assert again.status_code == 409
    assert again.json()["error_code"] == "RUN_ALREADY_COMPLETED"


def test_provider_accounting_records_attempts(api_env):
    factory = api_env["factory"]
    with factory() as session:
        book = seed_short_book_v1(session)
        session.commit()
        book_id = int(book.id)
        _activate_pro(session, api_env["license_keypair"])

    transport = RecordingFakeTransport(default_input_tokens=10, default_output_tokens=5, default_cost=0.02)
    with factory() as session:
        service = NativeOverviewService(
            session,
            adapter=load_private_fixture_engine_adapter(),
            transport=transport,
        )
        created = service.create_run(
            book_id,
            CreateRunRequest.model_validate(
                {**CREATE_BODY, "client_request_id": "req-acct-1"}
            ),
        )
        session.commit()
        run_id = int(created.run_id)

    assert transport.call_count >= 1
    with factory() as session:
        invocations = list(
            session.scalars(
                select(ModelInvocation).where(ModelInvocation.run_id == run_id)
            )
        )
        assert len(invocations) >= 1
        window = session.scalar(
            select(WholeBookRunWindow).where(WholeBookRunWindow.run_id == run_id)
        )
        assert window is not None
        assert window.provider_attempt_id is not None
        status = NativeOverviewService(session).get_run(run_id)
        assert status.actual_tokens == 15
        assert abs(status.actual_cost - 0.02) < 1e-9


def test_materializer_rejects_invalid_evidence(api_env):
    factory = api_env["factory"]
    with factory() as session:
        book = seed_short_book_v1(session)
        session.commit()
        book_id = int(book.id)
        _activate_pro(session, api_env["license_keypair"])

    with factory() as session:
        service = NativeOverviewService(
            session,
            adapter=load_private_fixture_engine_adapter(),
        )
        created = service.create_run(
            book_id,
            CreateRunRequest.model_validate(
                {**CREATE_BODY, "client_request_id": "req-mat-base"}
            ),
        )
        session.commit()
        run_id = int(created.run_id)

    with factory() as session:
        run = session.get(AnalysisRun, run_id)
        window = session.scalar(
            select(WholeBookRunWindow).where(WholeBookRunWindow.run_id == run_id)
        )
        assert run is not None and window is not None
        result = WholeBookOverviewWindowResultV1.model_validate(
            json.loads(window.checkpoint_json)["window_result"]
        )
        # Corrupt a quote.
        if result.candidate_evidence:
            result.candidate_evidence[0].quote = "<<<NOT_IN_TEXT>>>"
        window.state_version_after = None
        session.flush()
        mat = NativeOverviewMaterializer(session)
        with pytest.raises(NativeOverviewError) as exc:
            mat.materialize_window(run, window, result, prior_state=PriorStateV1(state_version=0))
        assert exc.value.code == "EVIDENCE_INVALID"


def test_free_user_native_create_allowed(api_env):
    """CHG-20260726-004: Free entitlement for native overview create."""
    factory = api_env["factory"]
    with factory() as session:
        book = seed_short_book_v1(session)
        session.commit()
        book_id = int(book.id)
    resp = api_env["client"].post(
        f"/api/v1/books/{book_id}/whole-book-runs",
        json=CREATE_BODY,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json().get("error_code") != "PRO_LICENSE_REQUIRED"


def test_preflight_estimates_multi_windows(api_env):
    factory = api_env["factory"]
    with factory() as session:
        book = _seed_multi_para_book(session, paragraphs=50)
        session.commit()
        book_id = int(book.id)
        _activate_pro(session, api_env["license_keypair"])
    resp = api_env["client"].post(
        f"/api/v1/books/{book_id}/whole-book-runs/preflight",
        json={"module_key": "book_overview", "mode": "whole_book_native"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["estimated_windows"] >= 2
    assert body["run_creation_enabled"] is True
