"""CHG-20260807-054 — Free formal real-provider path wiring (fixture gateway).

CHG-078 moved formal create onto the hierarchical V2 engine. V2 reaches the model
through ``_bind_formal_gateway`` — not through the V1 ``MinimalPipelineTransports`` —
so these tests patch that seam. Patching the V1 transports here would leave the real
gateway bound, and a developer machine with a stored API key would run the suite
against the live Provider for real money.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    NarrativeAssetVersion,
    ProviderConfiguration,
    WholeBookProviderAttempt,
    WholeBookProviderUnit,
    WholeBookRun,
)
from app.model_gateway.base import ModelResponse
from app.narrative_core.contracts.whole_book_contract_v1 import ResultOrigin
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
from app.narrative_core.services.whole_book_snapshot_v1_service import create_or_reuse_book_snapshot_v1
from app.narrative_core.services.whole_book_v2_formal_pipeline_v1 import (
    ENGINE_ID as V2_ENGINE_ID,
    _source_chapters,
    execute_hierarchical_v2_pipeline_v1,
)
from app.narrative_core.whole_book_v2.contracts import (
    AssessmentSynthesisUnit,
    ChapterFunctionBatchUnit,
    CharactersSynthesisUnit,
    OverviewTypeSynthesisUnit,
    PacingCoreSynthesisUnit,
    StorySynthesisUnit,
    SuspenseSynthesisUnit,
)
from app.narrative_core.whole_book_v2.engine import (
    DeterministicPrimitiveExtractor,
    SourceChapter,
    WholeBookV2Engine,
)
from app.narrative_core.whole_book_v2.provider_engine import CHAPTER_FUNCTION_BATCH_SIZE
from app.narrative_core.whole_book_v2.repository import WholeBookV2Repository
from tests.whole_book_minimal_test_helpers import make_engine, seed_sample_s_book


def _enable_free(monkeypatch, *, real: bool = True, fixture: bool = True) -> None:
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED", "true")
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED", "true" if fixture else "false")
    monkeypatch.setenv(
        "STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED",
        "true" if real else "false",
    )


class QueueGateway:
    """Fixture ModelGateway: serves synthesis payloads in order, never touches the network."""

    def __init__(self, items: list[dict[str, Any]]):
        self.items = list(items)
        self.calls: list[tuple[str, Any]] = []
        self.deterministic_extraction = True

    async def generate(self, provider: str, request: Any) -> ModelResponse:
        self.calls.append((provider, request))
        if not self.items:
            raise RuntimeError("fixture gateway exhausted")
        item = self.items.pop(0)
        return ModelResponse(
            text=json.dumps(item, ensure_ascii=False),
            model="qwen3.7-plus",
            finish_reason="stop",
            input_tokens=10,
            output_tokens=20,
        )


def _v2_payloads(chapters: list[SourceChapter]) -> list[dict[str, Any]]:
    r = WholeBookV2Engine(DeterministicPrimitiveExtractor(), window_size=3, overlap=0).run(
        run_id=1, book_id=1, title="fixture", chapters=chapters
    )
    return [
        OverviewTypeSynthesisUnit(type_profile=r.type_profile, overview=r.overview).model_dump(
            mode="json"
        ),
        StorySynthesisUnit(story=r.story).model_dump(mode="json"),
        CharactersSynthesisUnit(characters=r.characters).model_dump(mode="json"),
        SuspenseSynthesisUnit(suspense=r.suspense).model_dump(mode="json"),
        PacingCoreSynthesisUnit(pacing=r.pacing).model_dump(mode="json"),
        AssessmentSynthesisUnit(assessment=r.assessment).model_dump(mode="json"),
        # Chapter functions are requested last, in bounded batches (CHG-086).
        *[
            ChapterFunctionBatchUnit(
                functions=r.chapters.functions[i : i + CHAPTER_FUNCTION_BATCH_SIZE]
            ).model_dump(mode="json")
            for i in range(0, max(1, len(r.chapters.functions)), CHAPTER_FUNCTION_BATCH_SIZE)
        ],
    ]


def _patch_v2_gateway(monkeypatch, snapshot_id: int) -> list[QueueGateway]:
    """Bind a fixture gateway instead of the real one, and hand back what was bound.

    Everything above the gateway — planning, extraction, synthesis, persistence — stays
    the production V2 path, so the test still exercises the real formal pipeline. The
    returned list lets a test assert which provider the pipeline actually addressed,
    which is the evidence the V1 provider-attempt rows used to carry.

    The queue is positional, matching the order a cold run requests its units in.
    """
    built: list[QueueGateway] = []

    def _fake_bind(session, *, provider_name: str) -> QueueGateway:
        chapters = _source_chapters(session, SimpleNamespace(snapshot_id=snapshot_id))
        gateway = QueueGateway(_v2_payloads(chapters))
        built.append(gateway)
        return gateway

    monkeypatch.setattr(
        "app.narrative_core.services.whole_book_v2_formal_pipeline_v1._bind_formal_gateway",
        _fake_bind,
    )
    return built


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
        gateways = _patch_v2_gateway(monkeypatch, snap.id)
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
        # The formal run is hierarchical V2 (CHG-078), so its analysis lands in the V2
        # repository. The V1 minimal tables — overview result, provider units, provider
        # attempts — are not written by this path any more, and are not the evidence.
        assert run.engine_id == V2_ENGINE_ID
        assert result["pipeline"]["pipeline"] == "hierarchical_v2"
        assert result["pipeline"]["result_origin"] == "real_provider"
        analysis = WholeBookV2Repository(session).load_result(int(run.id))
        assert analysis is not None
        assert analysis.schema_version == "whole-book-analysis-v2.0"
        asset_count = session.scalar(select(func.count()).select_from(NarrativeAssetVersion)) or 0
        assert asset_count > 0
        # Run is pinned to the seeded formal provider, and that is who the pipeline
        # actually addressed — the point the provider-attempt rows used to make.
        assert run.provider_name == "aliyun_qwen_plus"
        assert run.model_name == "qwen3.7-plus"
        assert len(gateways) == 1
        assert gateways[0].calls
        assert {p for p, _ in gateways[0].calls} == {"aliyun_qwen_plus"}
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
        _patch_v2_gateway(monkeypatch, snap.id)
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
        assert pipe["run_id"] == run_id
        assert pipe["pipeline"] == "hierarchical_v2"
        assert pipe["engine_id"] == V2_ENGINE_ID
        run = session.get(WholeBookRun, run_id)
        assert run.snapshot_id == snap.id
        assert run.consent_id == consent.id
        # V2 carries the modules inside one result document instead of one table per
        # stage; the invariant under test is that they all belong to this run.
        analysis = WholeBookV2Repository(session).load_result(run_id)
        assert analysis is not None
        assert int(analysis.analysis_metadata.run_id) == run_id
        assert analysis.characters.protagonist.stages
        assert analysis.pacing.points
        assert analysis.assessment.dimensions
        assert analysis.chapters.functions
    engine.dispose()


def test_resume_completed_units_not_duplicated(tmp_path, monkeypatch) -> None:
    """Re-entering a finished run must buy nothing and materialize nothing twice."""
    _enable_free(monkeypatch, real=True)
    engine = make_engine(tmp_path, "chg054-resume.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        provider, estimate, consent, snap = _seed_consent(session, book.id)
        monkeypatch.setattr(
            "app.narrative_core.services.whole_book_gateway_transport_v1.resolve_formal_provider_row",
            lambda _s, **_kw: provider,
        )
        gateways = _patch_v2_gateway(monkeypatch, snap.id)
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
        assert len(gateways[0].calls) > 0
        result_before = WholeBookV2Repository(session).load_result(run_id).model_dump_json()

        # V2 keeps its per-unit checkpoints, so a second pass over the same run replays
        # them instead of re-asking the Provider, then the repository refuses to write a
        # second successful result. Both halves are what "not duplicated" means here.
        with pytest.raises(ValueError, match="already materialized"):
            execute_hierarchical_v2_pipeline_v1(session, run_id)
        assert len(gateways) == 2
        assert gateways[1].calls == []
        assert WholeBookV2Repository(session).load_result(run_id).model_dump_json() == result_before
    engine.dispose()
