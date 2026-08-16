"""CHG-20260807-054 — Free formal real-provider path wiring (mocked transports)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    NarrativeAssetVersion,
    ProviderConfiguration,
    WholeBookOverviewResult,
    WholeBookProviderAttempt,
    WholeBookProviderUnit,
    WholeBookRun,
)
from app.narrative_core.contracts.whole_book_contract_v1 import ResultOrigin
from app.narrative_core.services.fixture_window_analysis_sample_s import (
    build_fixture_window_payload_from_request_dict,
)
from app.narrative_core.services.whole_book_consent_service import (
    create_whole_book_consent,
    validate_whole_book_consent,
)
from app.narrative_core.services.whole_book_cost_estimate_service import estimate_whole_book_analysis
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)
from app.narrative_core.services.whole_book_free_product_v1_service import (
    create_fixture_free_whole_book_analysis_v1,
    create_free_whole_book_analysis_v1,
)
from app.narrative_core.services.whole_book_minimal_chapter_functions_v1_service import (
    FixtureChapterFunctionsTransport,
)
from app.narrative_core.services.whole_book_minimal_overview_v1_service import FixtureOverviewTransport
from app.narrative_core.services.whole_book_minimal_pipeline_v1_service import MinimalPipelineTransports
from app.narrative_core.services.whole_book_minimal_structure_stages_v1_service import (
    FixtureStructureTransport,
)
from app.narrative_core.services.whole_book_provider_orchestrator import ProviderCallResult
from app.narrative_core.services.whole_book_snapshot_v1_service import create_or_reuse_book_snapshot_v1
from tests.whole_book_minimal_test_helpers import make_engine, seed_sample_s_book


def _enable_free(monkeypatch, *, real: bool = True, fixture: bool = True) -> None:
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED", "true")
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED", "true" if fixture else "false")
    monkeypatch.setenv(
        "STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED",
        "true" if real else "false",
    )


@dataclass
class FormalMockWindowTransport:
    """Fixture Sample-S payloads with formal provenance (no network)."""

    provider_id: str = "aliyun_qwen_plus"
    model_name: str = "qwen3.7-plus"
    calls: list[str] = field(default_factory=list)

    def invoke(self, *, unit_key: str, unit_type: str, request_payload: dict[str, Any]) -> ProviderCallResult:
        self.calls.append(unit_key)
        payload = build_fixture_window_payload_from_request_dict(request_payload)
        prov = dict(payload.get("provenance") or {})
        prov["result_origin"] = ResultOrigin.formal.value
        prov["deterministic"] = False
        prov["provider_id"] = self.provider_id
        prov["model_name"] = self.model_name
        payload["provenance"] = prov
        return ProviderCallResult(
            ok=True,
            result_payload=payload,
            result_origin=ResultOrigin.formal.value,
        )


@dataclass
class FormalMockOverviewTransport:
    provider_id: str = "aliyun_qwen_plus"
    model_name: str = "qwen3.7-plus"
    calls: list[str] = field(default_factory=list)
    _inner: FixtureOverviewTransport = field(default_factory=FixtureOverviewTransport)

    def invoke(self, *, unit_key: str, unit_type: str, request_payload: dict[str, Any]) -> ProviderCallResult:
        self.calls.append(unit_key)
        # Seed maps from request entities/assets for Sample S overview builder.
        entities = request_payload.get("entities") or []
        assets = request_payload.get("assets") or []
        evidences = request_payload.get("evidences") or []
        self._inner.entity_name_to_id = {
            str(e.get("canonical_name")): int(e["entity_id"])
            for e in entities
            if e.get("canonical_name") is not None and e.get("entity_id") is not None
        }
        self._inner.asset_title_to_id = {
            str(a.get("title")): int(a["asset_id"])
            for a in assets
            if a.get("title") is not None and a.get("asset_id") is not None
        }
        self._inner.evidence_ids = [int(e["evidence_id"]) for e in evidences if e.get("evidence_id") is not None]
        self._inner.key_event_asset_ids = [
            int(a["asset_id"])
            for a in assets
            if a.get("asset_type") == "event" and a.get("asset_id") is not None
        ]
        self._inner.important_entity_ids = list(self._inner.entity_name_to_id.values())
        raw = self._inner.invoke(unit_key=unit_key, unit_type=unit_type, request_payload=request_payload)
        payload = dict(raw.result_payload or {})
        result = dict(payload.get("result") or {})
        result["result_origin"] = ResultOrigin.formal.value
        prov = dict(result.get("provenance") or {})
        prov["result_origin"] = ResultOrigin.formal.value
        prov["deterministic"] = False
        prov["provider_id"] = self.provider_id
        prov["model_name"] = self.model_name
        result["provenance"] = prov
        payload["result"] = result
        payload.pop("provenance", None)
        return ProviderCallResult(
            ok=True,
            result_payload=payload,
            result_origin=ResultOrigin.formal.value,
        )


def _formal_mock_transports() -> MinimalPipelineTransports:
    return MinimalPipelineTransports(
        window=FormalMockWindowTransport(),
        overview=FormalMockOverviewTransport(),
        structure=FixtureStructureTransport(mode="multi_stage"),
        chapter_functions=FixtureChapterFunctionsTransport(mode="available"),
    )


def _seed_consent(session, book_id: int):
    provider = session.scalar(
        select(ProviderConfiguration).where(ProviderConfiguration.provider_name == "aliyun_qwen_plus")
    )
    if provider is None:
        provider = ProviderConfiguration(
            provider_name="aliyun_qwen_plus",
            plus_model="qwen3.7-plus",
            enabled=True,
            disconnected=False,
            credential_reference="keyring:aliyun_qwen_plus",
        )
        session.add(provider)
        session.flush()
    else:
        provider.enabled = True
        provider.disconnected = False
        provider.plus_model = "qwen3.7-plus"
        provider.credential_reference = provider.credential_reference or "keyring:aliyun_qwen_plus"
        session.flush()
    estimate = estimate_whole_book_analysis(session, book_id, "whole_book_native", provider.id)
    estimate.pricing_status = "unavailable"
    session.flush()
    consent = create_whole_book_consent(
        session,
        book_id=book_id,
        estimate_id=estimate.id,
        user_budget_limit_cny="1000",
        max_provider_calls=200,
        max_input_tokens=10_000_000,
        max_output_tokens=10_000_000,
    )
    snap = create_or_reuse_book_snapshot_v1(session, book_id)["snapshot"]
    return provider, estimate, consent, snap


def test_real_flag_off_still_disabled(tmp_path, monkeypatch) -> None:
    _enable_free(monkeypatch, real=False)
    engine = make_engine(tmp_path, "chg054-off.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        _, estimate, consent, _ = _seed_consent(session, book.id)
        with pytest.raises(WholeBookFoundationError) as exc:
            create_free_whole_book_analysis_v1(
                session,
                book.id,
                estimate_id=estimate.id,
                consent_id=consent.id,
                client_request_id="off-1",
                execute_pipeline=False,
            )
        assert exc.value.code == WholeBookFoundationErrorCode.WHOLE_BOOK_REAL_PROVIDER_DISABLED.value
        assert session.scalar(select(func.count()).select_from(WholeBookRun)) == 0
    engine.dispose()


def test_real_flag_on_no_capability_disabled(tmp_path, monkeypatch) -> None:
    _enable_free(monkeypatch, real=True)
    engine = make_engine(tmp_path, "chg054-on.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        provider, estimate, consent, snap = _seed_consent(session, book.id)

        # Mirrors `resolve_formal_provider_row(session, *, provider_name, provider_config_id)`.
        # The stub was written before the callers passed the config id and had drifted out of
        # step with the function it replaces, so every test using it failed on the call rather
        # than on anything it was meant to check.
        def _resolve(_session, *, provider_name=None, provider_config_id=None):
            return provider

        monkeypatch.setattr(
            "app.narrative_core.services.whole_book_gateway_transport_v1.resolve_formal_provider_row",
            _resolve,
        )
        monkeypatch.setattr(
            "app.narrative_core.services.whole_book_minimal_pipeline_v1_service.build_formal_gateway_transports",
            lambda _s, **_kw: _formal_mock_transports(),
        )
        result = create_free_whole_book_analysis_v1(
            session,
            book.id,
            estimate_id=estimate.id,
            consent_id=consent.id,
            client_request_id="on-1",
            execute_pipeline=True,
        )
        assert result["result_origin"] == ResultOrigin.formal.value
        assert result["run_id"] > 0
        assert result["snapshot_id"] == snap.id
        assert result["pipeline"] is not None
        run = session.get(WholeBookRun, result["run_id"])
        assert run is not None
        assert run.result_origin == ResultOrigin.formal.value
        assert run.consent_id == consent.id
        assert "WHOLE_BOOK_CAPABILITY_DISABLED" not in str(result)
        # Characters/events come from real window units → materialize, not overview invent.
        asset_count = session.scalar(select(func.count()).select_from(NarrativeAssetVersion)) or 0
        assert asset_count > 0
        overview = session.scalar(
            select(WholeBookOverviewResult).where(WholeBookOverviewResult.run_id == run.id)
        )
        assert overview is not None
        units = list(
            session.scalars(select(WholeBookProviderUnit).where(WholeBookProviderUnit.run_id == run.id))
        )
        assert len(units) >= 4  # windows + overview + structure + CF
        attempts = list(
            session.scalars(
                select(WholeBookProviderAttempt).join(WholeBookProviderUnit).where(
                    WholeBookProviderUnit.run_id == run.id
                )
            )
        )
        assert any(a.provider_id == "aliyun_qwen_plus" for a in attempts)
        assert any(a.model_name == "qwen3.7-plus" for a in attempts)
    engine.dispose()


def test_provider_unavailable_explicit_error(tmp_path, monkeypatch) -> None:
    _enable_free(monkeypatch, real=True)
    engine = make_engine(tmp_path, "chg054-unavail.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        _, estimate, consent, _ = _seed_consent(session, book.id)

        def _boom(_session, *, provider_name=None, provider_config_id=None):
            raise WholeBookFoundationError(
                WholeBookFoundationErrorCode.WHOLE_BOOK_REAL_PROVIDER_DISABLED,
                "正式 Provider API Key 不可用",
            )

        monkeypatch.setattr(
            "app.narrative_core.services.whole_book_gateway_transport_v1.resolve_formal_provider_row",
            _boom,
        )
        with pytest.raises(WholeBookFoundationError) as exc:
            create_free_whole_book_analysis_v1(
                session,
                book.id,
                estimate_id=estimate.id,
                consent_id=consent.id,
                client_request_id="unavail-1",
                execute_pipeline=False,
            )
        assert exc.value.code == WholeBookFoundationErrorCode.WHOLE_BOOK_REAL_PROVIDER_DISABLED.value
        assert session.scalar(select(func.count()).select_from(WholeBookRun)) == 0
    engine.dispose()


def test_consent_invalid_rejects_create(tmp_path, monkeypatch) -> None:
    _enable_free(monkeypatch, real=True)
    engine = make_engine(tmp_path, "chg054-consent.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        provider, estimate, consent, _ = _seed_consent(session, book.id)
        monkeypatch.setattr(
            "app.narrative_core.services.whole_book_gateway_transport_v1.resolve_formal_provider_row",
            lambda _s, **_kw: provider,
        )
        with pytest.raises(WholeBookFoundationError):
            create_free_whole_book_analysis_v1(
                session,
                book.id,
                estimate_id=estimate.id,
                consent_id=consent.id + 99999,
                client_request_id="bad-consent",
                execute_pipeline=False,
            )
    engine.dispose()


def test_revision_change_rejects_old_consent(tmp_path, monkeypatch) -> None:
    _enable_free(monkeypatch, real=True)
    engine = make_engine(tmp_path, "chg054-rev.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        provider, estimate, consent, snap = _seed_consent(session, book.id)
        # Mutate consent hash to simulate book revision drift.
        consent.book_revision_hash = "deadbeef" * 8
        session.flush()
        monkeypatch.setattr(
            "app.narrative_core.services.whole_book_gateway_transport_v1.resolve_formal_provider_row",
            lambda _s, **_kw: provider,
        )
        with pytest.raises(WholeBookFoundationError) as exc:
            create_free_whole_book_analysis_v1(
                session,
                book.id,
                estimate_id=estimate.id,
                consent_id=consent.id,
                client_request_id="rev-1",
                execute_pipeline=False,
            )
        assert exc.value.code == WholeBookFoundationErrorCode.WHOLE_BOOK_BOOK_CHANGED.value
        # Still valid under matching revision after restore
        consent.book_revision_hash = estimate.book_revision_hash
        session.flush()
        validate_whole_book_consent(
            session,
            consent.id,
            book_id=book.id,
            estimate_id=estimate.id,
            snapshot_id=snap.id,
        )
    engine.dispose()


def test_fixture_preview_independent_when_real_on(tmp_path, monkeypatch) -> None:
    _enable_free(monkeypatch, real=True, fixture=True)
    engine = make_engine(tmp_path, "chg054-fixture.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        result = create_fixture_free_whole_book_analysis_v1(
            session, book.id, client_request_id="fx-1", execute_pipeline=True
        )
        assert result["result_origin"] == ResultOrigin.fixture.value
        run = session.get(WholeBookRun, result["run_id"])
        assert run is not None
        assert run.result_origin == ResultOrigin.fixture.value
        attempts = list(
            session.scalars(
                select(WholeBookProviderAttempt).join(WholeBookProviderUnit).where(
                    WholeBookProviderUnit.run_id == run.id
                )
            )
        )
        # Fixture path must not record aliyun formal attempts.
        assert all(a.provider_id != "aliyun_qwen_plus" for a in attempts)
    engine.dispose()


def test_formal_four_modules_same_run_snapshot_revision(tmp_path, monkeypatch) -> None:
    _enable_free(monkeypatch, real=True)
    engine = make_engine(tmp_path, "chg054-four.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        provider, estimate, consent, snap = _seed_consent(session, book.id)
        monkeypatch.setattr(
            "app.narrative_core.services.whole_book_gateway_transport_v1.resolve_formal_provider_row",
            lambda _s, **_kw: provider,
        )
        monkeypatch.setattr(
            "app.narrative_core.services.whole_book_minimal_pipeline_v1_service.build_formal_gateway_transports",
            lambda _s, **_kw: _formal_mock_transports(),
        )
        result = create_free_whole_book_analysis_v1(
            session,
            book.id,
            estimate_id=estimate.id,
            consent_id=consent.id,
            client_request_id="four-1",
            execute_pipeline=True,
        )
        run_id = result["run_id"]
        pipe = result["pipeline"]
        assert pipe["extraction"]["run_id"] == run_id
        assert pipe["materialization"]["run_id"] == run_id
        assert pipe["overview"]["run_id"] == run_id
        assert pipe["structure"]["run_id"] == run_id
        assert pipe["chapter_functions"]["run_id"] == run_id
        run = session.get(WholeBookRun, run_id)
        assert run.snapshot_id == snap.id
        assert run.consent_id == consent.id
        assert session.scalar(
            select(func.count()).select_from(WholeBookOverviewResult).where(
                WholeBookOverviewResult.run_id == run_id
            )
        )
    engine.dispose()


def test_resume_completed_units_not_duplicated(tmp_path, monkeypatch) -> None:
    _enable_free(monkeypatch, real=True)
    engine = make_engine(tmp_path, "chg054-resume.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        provider, estimate, consent, _ = _seed_consent(session, book.id)
        transports = _formal_mock_transports()
        monkeypatch.setattr(
            "app.narrative_core.services.whole_book_gateway_transport_v1.resolve_formal_provider_row",
            lambda _s, **_kw: provider,
        )
        monkeypatch.setattr(
            "app.narrative_core.services.whole_book_minimal_pipeline_v1_service.build_formal_gateway_transports",
            lambda _s: transports,
        )
        first = create_free_whole_book_analysis_v1(
            session,
            book.id,
            estimate_id=estimate.id,
            consent_id=consent.id,
            client_request_id="resume-1",
            execute_pipeline=True,
        )
        session.commit()
        run_id = first["run_id"]
        units_before = session.scalar(
            select(func.count()).select_from(WholeBookProviderUnit).where(
                WholeBookProviderUnit.run_id == run_id
            )
        )
        attempts_before = session.scalar(
            select(func.count()).select_from(WholeBookProviderAttempt).join(WholeBookProviderUnit).where(
                WholeBookProviderUnit.run_id == run_id
            )
        )
        window_calls_before = len(transports.window.calls)  # type: ignore[union-attr]
        from app.narrative_core.services.whole_book_minimal_pipeline_v1_service import (
            execute_minimal_pipeline_v1,
        )

        again = execute_minimal_pipeline_v1(session, run_id, transports=transports)
        assert again["run_status"] == "completed"
        units_after = session.scalar(
            select(func.count()).select_from(WholeBookProviderUnit).where(
                WholeBookProviderUnit.run_id == run_id
            )
        )
        attempts_after = session.scalar(
            select(func.count()).select_from(WholeBookProviderAttempt).join(WholeBookProviderUnit).where(
                WholeBookProviderUnit.run_id == run_id
            )
        )
        assert units_after == units_before
        assert attempts_after == attempts_before
        assert len(transports.window.calls) == window_calls_before  # type: ignore[union-attr]
    engine.dispose()
