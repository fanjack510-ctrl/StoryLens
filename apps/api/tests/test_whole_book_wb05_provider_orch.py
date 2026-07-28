"""WB-0.5 provider orchestration / idempotency / resume tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.db.models import Book, Chapter, Paragraph, ProviderConfiguration, WholeBookProviderAttempt
from app.narrative_core.services.whole_book_consent_service import create_whole_book_consent
from app.narrative_core.services.whole_book_cost_estimate_service import estimate_whole_book_analysis
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)
from app.narrative_core.services.whole_book_provider_orchestrator import (
    CountingFakeWholeBookProvider,
    WholeBookProviderOrchestrator,
    ensure_test_run,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Base


def _session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'orch.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def _seed(session):
    book = Book(title="orch", source_file_name="o.txt", source_file_hash="f" * 64)
    session.add(book)
    session.flush()
    ch = Chapter(book_id=book.id, chapter_index=0, title="c", content_hash="1" * 64)
    session.add(ch)
    session.flush()
    text = "汉" * 300
    session.add(
        Paragraph(
            id="p-orch-0",
            book_id=book.id,
            chapter_id=ch.id,
            paragraph_index=0,
            raw_text=text,
            normalized_text=text,
            char_start=0,
            char_end=len(text),
            content_hash="2" * 64,
        )
    )
    provider = ProviderConfiguration(provider_name="orch-p", plus_model="qwen3.7-plus")
    session.add(provider)
    session.flush()
    est = estimate_whole_book_analysis(session, book.id, "whole_book_native", provider.id)
    est.pricing_status = "unavailable"
    est.estimated_cost_max_cny = None
    session.flush()
    consent = create_whole_book_consent(
        session,
        book_id=book.id,
        estimate_id=est.id,
        user_budget_limit_cny="100",
        max_provider_calls=20,
        max_input_tokens=1_000_000,
        max_output_tokens=1_000_000,
        auto_retry_enabled=False,
        max_retries_per_unit=1,
    )
    run = ensure_test_run(session, book_id=book.id, consent_id=consent.id)
    session.commit()
    return book, consent, run


def test_idempotent_single_call(tmp_path) -> None:
    session = _session(tmp_path)
    _book, consent, run = _seed(session)
    orch = WholeBookProviderOrchestrator(session)
    fake = CountingFakeWholeBookProvider()
    payload = {"unit": "u1"}
    r1 = orch.execute_provider_unit(
        run_id=run.id,
        stage_code="extract_entities_events",
        unit_type="window_analysis",
        unit_key="u1",
        request_payload=payload,
        consent_id=consent.id,
        transport=fake,
    )
    r2 = orch.execute_provider_unit(
        run_id=run.id,
        stage_code="extract_entities_events",
        unit_type="window_analysis",
        unit_key="u1",
        request_payload=payload,
        consent_id=consent.id,
        transport=fake,
    )
    session.commit()
    assert r1["status"] == "completed"
    assert r2["status"] == "reused"
    assert fake.call_count == 1
    assert fake.network_calls == 0


def test_running_duplicate_rejected(tmp_path) -> None:
    session = _session(tmp_path)
    _book, consent, run = _seed(session)
    orch = WholeBookProviderOrchestrator(session)
    # Manually mark running
    from app.db.models import WholeBookProviderUnit
    from app.narrative_core.services.whole_book_provider_orchestrator import (
        build_idempotency_key,
        stable_request_hash,
    )

    payload = {"unit": "u-run"}
    req_hash = stable_request_hash(payload)
    idem = build_idempotency_key(
        run_id=run.id,
        stage_code="extract_entities_events",
        unit_type="window_analysis",
        unit_key="u-run",
        request_hash=req_hash,
        engine_version=orch.engine_version,
        prompt_version=orch.prompt_version,
    )
    unit = WholeBookProviderUnit(
        run_id=run.id,
        stage_code="extract_entities_events",
        unit_key="u-run",
        unit_type="window_analysis",
        idempotency_key=idem,
        request_hash=req_hash,
        status="running",
        attempt_count=1,
    )
    session.add(unit)
    session.commit()
    with pytest.raises(WholeBookFoundationError) as exc:
        orch.execute_provider_unit(
            run_id=run.id,
            stage_code="extract_entities_events",
            unit_type="window_analysis",
            unit_key="u-run",
            request_payload=payload,
            consent_id=consent.id,
            transport=CountingFakeWholeBookProvider(),
        )
    assert exc.value.code == WholeBookFoundationErrorCode.WHOLE_BOOK_UNIT_RUNNING.value


def test_failed_requires_explicit_retry(tmp_path) -> None:
    session = _session(tmp_path)
    _book, consent, run = _seed(session)
    orch = WholeBookProviderOrchestrator(session)
    fake = CountingFakeWholeBookProvider(fail_once_unit_keys={"u-fail"})
    payload = {"unit": "u-fail"}
    r1 = orch.execute_provider_unit(
        run_id=run.id,
        stage_code="extract_entities_events",
        unit_type="window_analysis",
        unit_key="u-fail",
        request_payload=payload,
        consent_id=consent.id,
        transport=fake,
    )
    assert r1["status"] == "failed"
    with pytest.raises(WholeBookFoundationError):
        orch.execute_provider_unit(
            run_id=run.id,
            stage_code="extract_entities_events",
            unit_type="window_analysis",
            unit_key="u-fail",
            request_payload=payload,
            consent_id=consent.id,
            transport=fake,
            allow_retry=False,
        )
    r2 = orch.retry_failed_provider_unit(r1["unit_id"], consent.id, fake, request_payload=payload)
    assert r2["status"] == "completed"
    assert fake.call_count == 2


def test_budget_blocks_without_attempt(tmp_path) -> None:
    session = _session(tmp_path)
    _book, consent, run = _seed(session)
    consent.max_provider_calls = 0
    session.commit()
    orch = WholeBookProviderOrchestrator(session)
    fake = CountingFakeWholeBookProvider()
    before = session.scalars(select(WholeBookProviderAttempt)).all()
    with pytest.raises(WholeBookFoundationError) as exc:
        orch.execute_provider_unit(
            run_id=run.id,
            stage_code="extract_entities_events",
            unit_type="window_analysis",
            unit_key="u-budget",
            request_payload={"u": 1},
            consent_id=consent.id,
            transport=fake,
        )
    assert exc.value.code == WholeBookFoundationErrorCode.WHOLE_BOOK_CALL_BUDGET_EXCEEDED.value
    after = session.scalars(select(WholeBookProviderAttempt)).all()
    assert len(after) == len(before)
    assert fake.call_count == 0


def test_resume_plan_and_ten_unit_scenario(tmp_path) -> None:
    session = _session(tmp_path)
    _book, consent, run = _seed(session)
    orch = WholeBookProviderOrchestrator(session)
    fake = CountingFakeWholeBookProvider()
    stage = "extract_entities_events"
    # First wave: units 1-4 success
    for i in range(1, 5):
        orch.execute_provider_unit(
            run_id=run.id,
            stage_code=stage,
            unit_type="window_analysis",
            unit_key=f"u{i}",
            request_payload={"i": i},
            consent_id=consent.id,
            transport=fake,
        )
    # Pre-create pending logical units 5-10 (not executed) to model interrupt mid-run.
    from app.db.models import WholeBookProviderUnit
    from app.narrative_core.services.whole_book_provider_orchestrator import (
        build_idempotency_key,
        stable_request_hash,
    )

    for i in range(5, 11):
        payload = {"i": i}
        req_hash = stable_request_hash(payload)
        idem = build_idempotency_key(
            run_id=run.id,
            stage_code=stage,
            unit_type="window_analysis",
            unit_key=f"u{i}",
            request_hash=req_hash,
            engine_version=orch.engine_version,
            prompt_version=orch.prompt_version,
        )
        session.add(
            WholeBookProviderUnit(
                run_id=run.id,
                stage_code=stage,
                unit_key=f"u{i}",
                unit_type="window_analysis",
                idempotency_key=idem,
                request_hash=req_hash,
                status="pending",
                attempt_count=0,
            )
        )
    session.commit()
    assert fake.call_count == 4

    # Rebuild session / orchestrator / fake transport
    engine = create_engine(f"sqlite:///{tmp_path / 'orch.db'}")
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session2 = Session()
    orch2 = WholeBookProviderOrchestrator(session2)
    fake2 = CountingFakeWholeBookProvider()
    plan = orch2.resume_incomplete_provider_units(run.id, stage)
    assert len(plan["completed"]) == 4
    assert len(plan["skipped"]) == 4
    assert len(plan["pending"]) == 6
    for item in plan["pending"]:
        orch2.execute_provider_unit(
            run_id=run.id,
            stage_code=stage,
            unit_type=item["unit_type"],
            unit_key=item["unit_key"],
            request_payload={"i": int(item["unit_key"][1:])},
            consent_id=consent.id,
            transport=fake2,
        )
    session2.commit()
    assert fake2.call_count == 6
    assert fake.call_count + fake2.call_count == 10

    fake3 = CountingFakeWholeBookProvider()
    orch3 = WholeBookProviderOrchestrator(session2)
    for i in range(1, 11):
        result = orch3.execute_provider_unit(
            run_id=run.id,
            stage_code=stage,
            unit_type="window_analysis",
            unit_key=f"u{i}",
            request_payload={"i": i},
            consent_id=consent.id,
            transport=fake3,
        )
        assert result["status"] == "reused"
    assert fake3.call_count == 0


def test_resume_does_not_auto_call(tmp_path) -> None:
    session = _session(tmp_path)
    _book, consent, run = _seed(session)
    orch = WholeBookProviderOrchestrator(session)
    fake = CountingFakeWholeBookProvider()
    orch.execute_provider_unit(
        run_id=run.id,
        stage_code="extract_entities_events",
        unit_type="window_analysis",
        unit_key="only",
        request_payload={"x": 1},
        consent_id=consent.id,
        transport=fake,
    )
    calls_before = fake.call_count
    plan = orch.resume_incomplete_provider_units(run.id, "extract_entities_events")
    assert calls_before == fake.call_count
    assert plan["completed"]


def test_token_and_cost_budget_gates(tmp_path) -> None:
    session = _session(tmp_path)
    _book, consent, run = _seed(session)
    orch = WholeBookProviderOrchestrator(session)
    fake = CountingFakeWholeBookProvider()
    consent.max_input_tokens = 10
    session.commit()
    with pytest.raises(WholeBookFoundationError) as exc:
        orch.execute_provider_unit(
            run_id=run.id,
            stage_code="extract_entities_events",
            unit_type="window_analysis",
            unit_key="tok",
            request_payload={"t": 1},
            consent_id=consent.id,
            transport=fake,
            projected_input_tokens=100,
        )
    assert exc.value.code == WholeBookFoundationErrorCode.WHOLE_BOOK_INPUT_TOKEN_BUDGET_EXCEEDED.value

    consent.max_input_tokens = 1_000_000
    consent.max_output_tokens = 1
    session.commit()
    with pytest.raises(WholeBookFoundationError) as exc2:
        orch.execute_provider_unit(
            run_id=run.id,
            stage_code="extract_entities_events",
            unit_type="window_analysis",
            unit_key="out",
            request_payload={"t": 2},
            consent_id=consent.id,
            transport=fake,
            projected_output_tokens=50,
        )
    assert exc2.value.code == WholeBookFoundationErrorCode.WHOLE_BOOK_OUTPUT_TOKEN_BUDGET_EXCEEDED.value

    consent.max_output_tokens = 1_000_000
    consent.user_budget_limit_cny = Decimal("0.001")
    session.commit()
    with pytest.raises(WholeBookFoundationError) as exc3:
        orch.execute_provider_unit(
            run_id=run.id,
            stage_code="extract_entities_events",
            unit_type="window_analysis",
            unit_key="cost",
            request_payload={"t": 3},
            consent_id=consent.id,
            transport=fake,
            projected_cost_cny=Decimal("1.00"),
        )
    assert exc3.value.code == WholeBookFoundationErrorCode.WHOLE_BOOK_COST_BUDGET_EXCEEDED.value
    assert fake.call_count == 0
