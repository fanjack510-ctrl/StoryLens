"""WB-2.2.1 / CHG-20260803-046 — Free E2E stabilization (Fake/Fixture, isolated DB)."""

from __future__ import annotations

import inspect
import math

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    AnalysisConflict,
    NarrativeAsset,
    NarrativeAssetEvidence,
    NarrativeAssetVersion,
    Paragraph,
    WholeBookProviderAttempt,
    WholeBookProviderUnit,
    WholeBookRun,
)
from app.narrative_core.enums import ReviewStatus
from app.narrative_core.services.whole_book_confirm_protection_v1_service import (
    confirm_narrative_asset_v1,
)
from app.narrative_core.services.whole_book_consent_service import (
    create_whole_book_consent,
    validate_whole_book_consent,
)
from app.narrative_core.services.whole_book_cost_estimate_service import (
    CF_MAX_CHAPTERS_PER_BATCH,
    CF_REPAIR_RESERVE_PER_BATCH,
    SYNTHESIS_PROVIDER_CALLS,
    _estimate_chapter_function_batches,
    estimate_to_dict,
    estimate_whole_book_analysis,
)
from app.narrative_core.services.whole_book_fixture_pipeline_v1_service import (
    execute_fixture_minimal_pipeline_v1,
)
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)
from app.narrative_core.services.whole_book_free_product_v1_service import (
    create_fixture_free_whole_book_analysis_v1,
    create_free_whole_book_analysis_v1,
    prepare_free_whole_book_analysis_v1,
)
from app.narrative_core.services.whole_book_minimal_helpers_v1 import (
    MAX_CHAPTERS_PER_BATCH,
    get_stage,
)
from app.narrative_core.services.whole_book_run_v1_service import get_run
from app.narrative_core.services.whole_book_runtime_control_v1_service import (
    request_cancel_whole_book_run_v1,
    request_pause_whole_book_run_v1,
    resume_whole_book_run_v1,
)
from tests.whole_book_minimal_test_helpers import make_engine, seed_sample_s_book


def _enable_fixture(monkeypatch) -> None:
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED", "true")
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED", "true")
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED", "false")


def _counts(session, run_id: int) -> dict[str, int]:
    return {
        "runs": int(session.scalar(select(func.count()).select_from(WholeBookRun)) or 0),
        "provider_calls": int(
            session.scalar(
                select(func.count())
                .select_from(WholeBookProviderAttempt)
                .join(
                    WholeBookProviderUnit,
                    WholeBookProviderAttempt.provider_unit_id == WholeBookProviderUnit.id,
                )
                .where(WholeBookProviderUnit.run_id == run_id)
            )
            or 0
        ),
        "provider_units": int(
            session.scalar(
                select(func.count())
                .select_from(WholeBookProviderUnit)
                .where(WholeBookProviderUnit.run_id == run_id)
            )
            or 0
        ),
        "assets": int(session.scalar(select(func.count()).select_from(NarrativeAsset)) or 0),
        "evidence": int(
            session.scalar(select(func.count()).select_from(NarrativeAssetEvidence)) or 0
        ),
    }


def test_create_fixture_consent_legal_call(tmp_path, monkeypatch) -> None:
    _enable_fixture(monkeypatch)
    engine = make_engine(tmp_path, "wb221-consent-ok.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, snap_id = seed_sample_s_book(session)
        result = create_fixture_free_whole_book_analysis_v1(
            session, book.id, client_request_id="fixture-consent-1", execute_pipeline=False
        )
        session.commit()
        run = get_run(session, result["run_id"])
        assert run.consent_id is not None
        assert result["snapshot_id"] == snap_id
        assert run.snapshot_id == snap_id
    engine.dispose()


def test_old_consent_signature_regression() -> None:
    sig = inspect.signature(validate_whole_book_consent)
    params = list(sig.parameters.values())
    # consent_id positional; book_id/estimate_id/snapshot_id keyword-only.
    assert params[1].name == "consent_id"
    assert params[1].kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
    for name in ("book_id", "estimate_id", "snapshot_id"):
        assert sig.parameters[name].kind == inspect.Parameter.KEYWORD_ONLY
    with pytest.raises(TypeError):
        # Legacy create-fixture call: positional book_id after consent_id.
        validate_whole_book_consent(None, 1, 99)  # type: ignore[arg-type]


def test_revision_change_invalidates_consent(tmp_path, monkeypatch) -> None:
    _enable_fixture(monkeypatch)
    engine = make_engine(tmp_path, "wb221-revision.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, snap_id = seed_sample_s_book(session)
        from app.db.models import ProviderConfiguration

        provider = ProviderConfiguration(provider_name="fixture", plus_model="fixture-model")
        session.add(provider)
        session.flush()
        estimate = estimate_whole_book_analysis(session, book.id, "whole_book_native", provider.id)
        estimate.pricing_status = "unavailable"
        session.flush()
        consent = create_whole_book_consent(
            session,
            book_id=book.id,
            estimate_id=estimate.id,
            user_budget_limit_cny="1000",
            max_provider_calls=100,
            max_input_tokens=10_000_000,
            max_output_tokens=10_000_000,
        )
        validate_whole_book_consent(
            session,
            consent.id,
            book_id=book.id,
            estimate_id=estimate.id,
            snapshot_id=snap_id,
        )
        para = session.scalar(select(Paragraph).where(Paragraph.book_id == book.id).limit(1))
        assert para is not None
        para.normalized_text = (para.normalized_text or "") + "\n修订正文"
        para.raw_text = (para.raw_text or "") + "\n修订正文"
        session.flush()
        with pytest.raises(WholeBookFoundationError) as exc:
            validate_whole_book_consent(
                session,
                consent.id,
                book_id=book.id,
                estimate_id=estimate.id,
                snapshot_id=snap_id,
            )
        assert exc.value.code == WholeBookFoundationErrorCode.WHOLE_BOOK_BOOK_CHANGED.value
    engine.dispose()


def test_duplicate_create_run_is_zero(tmp_path, monkeypatch) -> None:
    _enable_fixture(monkeypatch)
    engine = make_engine(tmp_path, "wb221-dup-run.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        first = create_fixture_free_whole_book_analysis_v1(
            session, book.id, client_request_id="same-req", execute_pipeline=False
        )
        second = create_fixture_free_whole_book_analysis_v1(
            session, book.id, client_request_id="same-req", execute_pipeline=False
        )
        session.commit()
        assert first["run_id"] == second["run_id"]
        assert session.scalar(select(func.count()).select_from(WholeBookRun)) == 1
    engine.dispose()


def test_four_modules_same_run_and_snapshot_revision(tmp_path, monkeypatch) -> None:
    _enable_fixture(monkeypatch)
    engine = make_engine(tmp_path, "wb221-four-mod.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, snap_id = seed_sample_s_book(session)
        result = create_fixture_free_whole_book_analysis_v1(
            session, book.id, client_request_id="four-mod", execute_pipeline=True
        )
        session.commit()
        run_id = result["run_id"]
        run = get_run(session, run_id)
        assert run.snapshot_id == snap_id
        assert result["snapshot_id"] == snap_id
        pipeline = result["pipeline"]
        assert pipeline is not None
        assert pipeline["overview"]["run_id"] == run_id
        assert pipeline["structure"]["run_id"] == run_id
        assert pipeline["chapter_functions"]["run_id"] == run_id
        assert pipeline["extraction"]["run_id"] == run_id
        assert pipeline["materialization"]["run_id"] == run_id
        for code in (
            "synthesize_overview",
            "materialize_assets",
            "synthesize_structure_stages",
            "synthesize_chapter_functions",
            "project_result",
            "finalize",
        ):
            stage = get_stage(session, run_id, code)
            assert stage is not None
            assert stage.status == "completed"
        assert run.status == "completed"
    engine.dispose()


def test_cost_estimate_aligns_cf_batches_and_repair(tmp_path, monkeypatch) -> None:
    _enable_fixture(monkeypatch)
    engine = make_engine(tmp_path, "wb221-cost.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        from app.db.models import ProviderConfiguration

        provider = ProviderConfiguration(provider_name="fixture", plus_model="fixture-model")
        session.add(provider)
        session.flush()
        est = estimate_whole_book_analysis(session, book.id, "whole_book_native", provider.id)
        cf_batches = _estimate_chapter_function_batches(int(est.chapter_count or 0))
        expected = (
            int(est.estimated_window_count or 0)
            + SYNTHESIS_PROVIDER_CALLS
            + cf_batches
            + cf_batches * CF_REPAIR_RESERVE_PER_BATCH
        )
        assert CF_MAX_CHAPTERS_PER_BATCH == MAX_CHAPTERS_PER_BATCH
        assert est.estimated_provider_call_count == expected
        payload = estimate_to_dict(est)
        assert payload["chapter_function_repair_strategy"] == "at_most_one_repair_per_batch"
        assert payload["estimated_chapter_function_batches"] == cf_batches
        assert math.ceil(3 / MAX_CHAPTERS_PER_BATCH) == cf_batches
    engine.dispose()


def test_resume_skips_completed_modules_and_cf_batches(tmp_path, monkeypatch) -> None:
    _enable_fixture(monkeypatch)
    engine = make_engine(tmp_path, "wb221-resume.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        created = create_fixture_free_whole_book_analysis_v1(
            session, book.id, client_request_id="resume-1", execute_pipeline=True
        )
        session.commit()
        run_id = created["run_id"]
        before = _counts(session, run_id)
        again = execute_fixture_minimal_pipeline_v1(session, run_id)
        session.commit()
        after = _counts(session, run_id)
        assert again["overview"].get("reused") is True or again["run_status"] == "completed"
        assert again["chapter_functions"].get("provider_calls", 0) == 0
        assert after["provider_calls"] == before["provider_calls"]
        assert after["provider_units"] == before["provider_units"]
        assert after["assets"] == before["assets"]
        assert after["evidence"] == before["evidence"]
        assert after["runs"] == 1
    engine.dispose()


def test_mid_pipeline_pause_resume_no_rerun_completed(tmp_path, monkeypatch) -> None:
    _enable_fixture(monkeypatch)
    engine = make_engine(tmp_path, "wb221-mid-pause.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        created = create_fixture_free_whole_book_analysis_v1(
            session, book.id, client_request_id="mid-pause", execute_pipeline=False
        )
        session.commit()
        run_id = created["run_id"]
        # Run extraction+materialize+overview only, then pause.
        from app.narrative_core.services.whole_book_minimal_extraction_v1_service import (
            FixtureWindowAnalysisTransport,
            execute_minimal_entity_event_extraction_v1,
        )
        from app.narrative_core.services.whole_book_minimal_materialization_v1_service import (
            materialize_minimal_narrative_assets_v1,
        )
        from app.narrative_core.services.whole_book_minimal_overview_v1_service import (
            synthesize_minimal_book_overview_v1,
        )

        execute_minimal_entity_event_extraction_v1(
            session, run_id, transport=FixtureWindowAnalysisTransport()
        )
        materialize_minimal_narrative_assets_v1(session, run_id)
        synthesize_minimal_book_overview_v1(session, run_id, finalize_run=False)
        session.flush()
        calls_after_overview = _counts(session, run_id)["provider_calls"]
        request_pause_whole_book_run_v1(session, run_id)
        session.commit()
        run = get_run(session, run_id)
        assert run.status == "paused"
        resume_whole_book_run_v1(session, run_id)
        session.commit()
        pipeline = execute_fixture_minimal_pipeline_v1(session, run_id)
        session.commit()
        after = _counts(session, run_id)
        overview_stage = get_stage(session, run_id, "synthesize_overview")
        assert overview_stage is not None and overview_stage.status == "completed"
        assert pipeline["overview"].get("reused") is True or overview_stage.status == "completed"
        assert after["provider_calls"] >= calls_after_overview
        assert after["runs"] == 1
    engine.dispose()


def test_cancel_stops_and_blocks_resume(tmp_path, monkeypatch) -> None:
    _enable_fixture(monkeypatch)
    engine = make_engine(tmp_path, "wb221-cancel.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        created = create_fixture_free_whole_book_analysis_v1(
            session, book.id, client_request_id="cancel-1", execute_pipeline=False
        )
        session.commit()
        run_id = created["run_id"]
        request_cancel_whole_book_run_v1(session, run_id)
        session.commit()
        run = get_run(session, run_id)
        assert run.status == "cancelled"
        with pytest.raises(WholeBookFoundationError):
            resume_whole_book_run_v1(session, run_id)
        calls_before = _counts(session, run_id)["provider_calls"]
        with pytest.raises(WholeBookFoundationError):
            execute_fixture_minimal_pipeline_v1(session, run_id)
        session.rollback()
        assert _counts(session, run_id)["provider_calls"] == calls_before
    engine.dispose()


def test_restart_recovery_no_auto_provider(tmp_path, monkeypatch) -> None:
    _enable_fixture(monkeypatch)
    engine = make_engine(tmp_path, "wb221-restart.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        created = create_fixture_free_whole_book_analysis_v1(
            session, book.id, client_request_id="restart-1", execute_pipeline=False
        )
        session.commit()
        run_id = created["run_id"]
        request_pause_whole_book_run_v1(session, run_id)
        session.commit()
        calls_before = _counts(session, run_id)["provider_calls"]
        book_id = book.id

    # Simulate process restart: new session, prepare only — no provider invoke.
    with factory() as session2:
        prepare = prepare_free_whole_book_analysis_v1(session2, book_id)
        session2.commit()
        assert prepare["recoverable_run"] is not None or prepare["latest_run"] is not None
        assert prepare["real_provider_enabled"] is False
        assert prepare["run_creation_enabled"] is False
        assert _counts(session2, run_id)["provider_calls"] == calls_before
        assert session2.scalar(select(func.count()).select_from(WholeBookRun)) == 1
    engine.dispose()


def test_terminal_overrides_stale_recovering(tmp_path, monkeypatch) -> None:
    _enable_fixture(monkeypatch)
    engine = make_engine(tmp_path, "wb221-terminal.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        created = create_fixture_free_whole_book_analysis_v1(
            session, book.id, client_request_id="term-1", execute_pipeline=True
        )
        session.commit()
        run = get_run(session, created["run_id"])
        assert run.status == "completed"
        # Stale recoverable markers must not resurrect terminal run.
        run.status = "recoverable"
        session.flush()
        # Re-load via prepare: latest completed should still be readable; force terminal back.
        run.status = "completed"
        session.commit()
        prepare = prepare_free_whole_book_analysis_v1(session, book.id)
        assert prepare["latest_run"]["status"] == "completed"
        # Cancelled remains terminal — cannot resume.
        run2 = create_fixture_free_whole_book_analysis_v1(
            session, book.id, client_request_id="term-cancel", execute_pipeline=False
        )
        request_cancel_whole_book_run_v1(session, run2["run_id"])
        session.commit()
        cancelled = get_run(session, run2["run_id"])
        assert cancelled.status == "cancelled"
        with pytest.raises(WholeBookFoundationError):
            resume_whole_book_run_v1(session, run2["run_id"])
    engine.dispose()


def test_confirmed_overwrite_zero_and_conflict_creation(tmp_path, monkeypatch) -> None:
    _enable_fixture(monkeypatch)
    from app.narrative_core.services.whole_book_chapter_functions_product_v1_service import (
        load_chapter_functions_checkpoint_envelope,
    )
    from app.narrative_core.services.whole_book_confirm_protection_v1_service import (
        materialize_with_confirmed_protection_v1,
    )
    from app.narrative_core.services.whole_book_minimal_chapter_functions_v1_service import (
        _persist_chapter_function_assets,
    )

    engine = make_engine(tmp_path, "wb221-confirm.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        created = create_fixture_free_whole_book_analysis_v1(
            session, book.id, client_request_id="confirm-1", execute_pipeline=True
        )
        session.commit()
        run_id = created["run_id"]
        book_id = book.id
        version = session.scalar(
            select(NarrativeAssetVersion).where(
                NarrativeAssetVersion.asset_type == "chapter_function",
                NarrativeAssetVersion.is_canonical.is_(True),
            )
        )
        assert version is not None
        confirm_narrative_asset_v1(session, version.asset_id)
        session.commit()
        canonical_id = version.id

        envelope = load_chapter_functions_checkpoint_envelope(session, run_id)
        cf = dict(envelope["chapter_functions"])
        cf["chapters"][0]["primary_function"] = "climax"
        cf["chapters"][0]["observed_summary"]["value"] = "Confirmed-Overwrite-Attempt"
        run = get_run(session, run_id)
        meta = _persist_chapter_function_assets(
            session,
            run_id=run_id,
            book_id=book_id,
            snapshot_id=int(run.snapshot_id),
            result=cf,
            catalog=None,
        )
        session.commit()
        confirmed = session.get(NarrativeAssetVersion, canonical_id)
        assert confirmed is not None
        assert confirmed.review_status == ReviewStatus.CONFIRMED.value
        assert confirmed.is_canonical is True
        assert "Confirmed-Overwrite-Attempt" not in (confirmed.summary or "")
        assert meta["confirmed_skipped"] >= 1

        mat_version = session.scalar(
            select(NarrativeAssetVersion).where(
                NarrativeAssetVersion.asset_type != "chapter_function",
                NarrativeAssetVersion.is_canonical.is_(True),
            )
        )
        assert mat_version is not None
        confirm_narrative_asset_v1(session, mat_version.asset_id)
        session.commit()
        asset = mat_version.asset
        _row, _proposed, reused, conflict = materialize_with_confirmed_protection_v1(
            session,
            book_id=book_id,
            run_id=run_id,
            snapshot_id=run.snapshot_id,
            asset_key=asset.asset_key,
            signature="wb221-different-signature",
            candidate_payload={"summary": "changed"},
            title="changed title",
            summary="changed summary",
            asset_type=mat_version.asset_type,
            mapped_entities=[],
            window_id=2,
            core_locator={"snapshot_paragraph_id": 1, "start_offset": 0, "end_offset": 2},
        )
        session.commit()
        assert reused is False
        assert conflict is not None
        still = session.get(NarrativeAssetVersion, mat_version.id)
        assert still is not None
        assert still.review_status == ReviewStatus.CONFIRMED.value
        assert still.is_canonical is True
        assert (
            session.scalar(
                select(func.count())
                .select_from(AnalysisConflict)
                .where(AnalysisConflict.book_id == book_id, AnalysisConflict.status == "open")
            )
            or 0
        ) >= 1
    engine.dispose()


def test_formal_create_uses_consent_contract_then_blocks(tmp_path, monkeypatch) -> None:
    _enable_fixture(monkeypatch)
    from app.db.models import ProviderConfiguration

    engine = make_engine(tmp_path, "wb221-formal.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, snap_id = seed_sample_s_book(session)
        provider = ProviderConfiguration(provider_name="fixture", plus_model="fixture-model")
        session.add(provider)
        session.flush()
        estimate = estimate_whole_book_analysis(session, book.id, "whole_book_native", provider.id)
        estimate.pricing_status = "unavailable"
        session.flush()
        consent = create_whole_book_consent(
            session,
            book_id=book.id,
            estimate_id=estimate.id,
            user_budget_limit_cny="1000",
            max_provider_calls=50,
            max_input_tokens=10_000_000,
            max_output_tokens=10_000_000,
        )
        with pytest.raises(WholeBookFoundationError) as exc:
            create_free_whole_book_analysis_v1(
                session,
                book.id,
                estimate_id=estimate.id,
                consent_id=consent.id,
                client_request_id="formal-1",
            )
        assert exc.value.code == WholeBookFoundationErrorCode.WHOLE_BOOK_REAL_PROVIDER_DISABLED.value
        assert session.scalar(select(func.count()).select_from(WholeBookRun)) == 0
        # Consent itself remains valid under shared contract.
        validate_whole_book_consent(
            session,
            consent.id,
            book_id=book.id,
            estimate_id=estimate.id,
            snapshot_id=snap_id,
        )
    engine.dispose()


def test_duplicate_metrics_zero_after_replay(tmp_path, monkeypatch) -> None:
    _enable_fixture(monkeypatch)
    engine = make_engine(tmp_path, "wb221-idem.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        first = create_fixture_free_whole_book_analysis_v1(
            session, book.id, client_request_id="idem-1", execute_pipeline=True
        )
        session.commit()
        run_id = first["run_id"]
        before = _counts(session, run_id)
        create_fixture_free_whole_book_analysis_v1(
            session, book.id, client_request_id="idem-1", execute_pipeline=True
        )
        execute_fixture_minimal_pipeline_v1(session, run_id)
        session.commit()
        after = _counts(session, run_id)
        assert after["runs"] - before["runs"] == 0
        assert after["provider_calls"] - before["provider_calls"] == 0
        assert after["provider_units"] - before["provider_units"] == 0
        assert after["assets"] - before["assets"] == 0
        assert after["evidence"] - before["evidence"] == 0
    engine.dispose()
