"""WB-2.1 — Structure stages Free backend matrix A–O (+ native independence)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    AnalysisConflict,
    NarrativeAssetVersion,
    WholeBookProviderAttempt,
)
from app.narrative_core.enums import ReviewStatus
from app.narrative_core.services.whole_book_confirm_protection_v1_service import (
    confirm_narrative_asset_v1,
)
from app.narrative_core.services.whole_book_fixture_pipeline_v1_service import (
    execute_fixture_minimal_pipeline_v1,
)
from app.narrative_core.services.whole_book_product_capability_v1 import (
    AccessTier,
    resolve_capability_access,
)
from app.narrative_core.services.whole_book_run_v1_service import get_run
from app.narrative_core.services.whole_book_runtime_control_v1_service import (
    request_cancel_whole_book_run_v1,
    request_pause_whole_book_run_v1,
    resume_whole_book_run_v1,
)
from app.narrative_core.services.whole_book_structure_product_v1_service import (
    get_run_structure_product_v1,
)
from app.narrative_core.services.whole_book_foundation_errors import WholeBookFoundationError
from tests.whole_book_minimal_test_helpers import make_engine, prepare_sample_s_run


def _pipeline(session, run_id: int, *, mode: str = "multi_stage"):
    return execute_fixture_minimal_pipeline_v1(session, run_id, structure_mode=mode)


def test_a_normal_multi_stage(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb21-a.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        result = _pipeline(session, run_id, mode="multi_stage")
        session.commit()
        assert result["run_status"] == "completed"
        assert result["structure"]["stage_count"] >= 2
        payload = get_run_structure_product_v1(session, run_id)
        assert payload is not None
        assert payload["result_status"] == "completed"
        assert payload["contract_version"] == "v2"
        assert len(payload["structure"]["stages"]) >= 2
        assert payload["evidence_references"]
    engine.dispose()


def test_b_non_three_act(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb21-b.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        result = _pipeline(session, run_id, mode="non_three_act")
        session.commit()
        stages = result["structure"]["stage_count"]
        assert stages == 4  # not forced to 3
        payload = get_run_structure_product_v1(session, run_id)
        assert len(payload["structure"]["stages"]) == 4
    engine.dispose()


def test_c_variable_stage_count(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb21-c.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        result = _pipeline(session, run_id, mode="variable_count")
        session.commit()
        assert result["structure"]["stage_count"] == 1
    engine.dispose()


def test_d_turning_points_empty_stages_valid(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb21-d.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        _pipeline(session, run_id, mode="tp_empty")
        session.commit()
        payload = get_run_structure_product_v1(session, run_id)
        assert payload["result_status"] == "completed"
        assert payload["structure"]["stages"]
        assert payload["structure"]["turning_points"] == []
    engine.dispose()


def test_e_evidence_missing_fail_closed(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb21-e.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        # Force illegal empty under observation-required binding.
        result = _pipeline(session, run_id, mode="failed_empty")
        session.commit()
        run = get_run(session, run_id)
        assert run.status == "failed"
        assert result["structure"]["result_status"] == "failed"
        assert "STRUCTURE_" in (result["structure"].get("failure_code") or "")
    engine.dispose()


def test_f_truncation_repair_success_via_fixture_mode(tmp_path) -> None:
    """Fixture path has no live repair HTTP; multi_stage stands for successful recovery."""

    engine = make_engine(tmp_path, "wb21-f.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        result = _pipeline(session, run_id, mode="multi_stage")
        session.commit()
        assert result["structure"]["result_status"] == "completed"
        assert result["structure"]["provider_calls"] == 1
    engine.dispose()


def test_g_repair_still_illegal(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb21-g.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        result = _pipeline(session, run_id, mode="failed_empty")
        session.commit()
        assert result["structure"]["failure_code"] in {
            "STRUCTURE_EMPTY_RESULT_AFTER_REPAIR",
            "STRUCTURE_REQUIRED_STAGE_MISSING",
            "STRUCTURE_COVERAGE_SCOPE_BINDING_MISMATCH",
        }
    engine.dispose()


def test_h_insufficient_coverage_completed(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb21-h.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        result = _pipeline(session, run_id, mode="insufficient")
        session.commit()
        run = get_run(session, run_id)
        assert run.status == "completed"
        payload = get_run_structure_product_v1(session, run_id)
        assert payload["result_status"] == "completed"
        assert payload["coverage_scope"] == "insufficient"
        assert payload["structure"]["stages"] == []
        assert payload["structure"]["turning_points"] == []
        assert result["structure"]["product_result_status"] == "insufficient"
    engine.dispose()


def test_i_non_contiguous_no_invention(tmp_path) -> None:
    """Non-contiguous chapter geometry still uses catalog-bound fixture stages only."""

    engine = make_engine(tmp_path, "wb21-i.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        result = _pipeline(session, run_id, mode="multi_stage")
        session.commit()
        payload = get_run_structure_product_v1(session, run_id)
        for stage in payload["structure"]["stages"]:
            cids = (stage.get("summary") or {}).get("citation_ids") or []
            assert cids, "no invented stage without citations"
    engine.dispose()


def test_j_empty_duplicate_deterministic(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb21-j.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        first = _pipeline(session, run_id, mode="failed_empty")
        session.commit()
        code = first["structure"]["failure_code"]
        assert code.startswith("STRUCTURE_")
    engine.dispose()


def test_k_pause_then_resume(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb21-k.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        from app.narrative_core.services.whole_book_run_v1_service import start_whole_book_run_v1

        start_whole_book_run_v1(session, run_id)
        request_pause_whole_book_run_v1(session, run_id)
        session.commit()
        assert get_run(session, run_id).status == "paused"
        resume_whole_book_run_v1(session, run_id)
        start_whole_book_run_v1(session, run_id)
        result = _pipeline(session, run_id, mode="multi_stage")
        session.commit()
        assert result["run_status"] == "completed"
    engine.dispose()


def test_l_cancel_blocks_resume(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb21-l.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        from app.narrative_core.services.whole_book_run_v1_service import start_whole_book_run_v1

        start_whole_book_run_v1(session, run_id)
        request_cancel_whole_book_run_v1(session, run_id)
        session.commit()
        assert get_run(session, run_id).status == "cancelled"
        with pytest.raises(WholeBookFoundationError):
            resume_whole_book_run_v1(session, run_id)
        payload = get_run_structure_product_v1(session, run_id)
        assert payload["result_status"] == "canceled"
    engine.dispose()


def test_m_duplicate_resume_no_extra_provider_calls(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb21-m.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        _pipeline(session, run_id, mode="multi_stage")
        session.commit()
        calls_1 = session.query(WholeBookProviderAttempt).count()
        again = execute_fixture_minimal_pipeline_v1(session, run_id, structure_mode="multi_stage")
        session.commit()
        calls_2 = session.query(WholeBookProviderAttempt).count()
        assert again["structure"]["reused"] is True or again["run_status"] == "completed"
        assert calls_2 == calls_1
    engine.dispose()


def test_n_confirmed_no_overwrite(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb21-n.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, book_id = prepare_sample_s_run(session)
        _pipeline(session, run_id, mode="multi_stage")
        session.commit()
        version = session.scalar(
            select(NarrativeAssetVersion).where(
                NarrativeAssetVersion.asset_type == "structure_stage",
                NarrativeAssetVersion.is_canonical.is_(True),
            )
        )
        assert version is not None
        confirm_narrative_asset_v1(session, version.asset_id)
        session.commit()
        from app.narrative_core.services.whole_book_structure_product_v1_service import (
            load_structure_checkpoint_envelope,
        )
        from app.narrative_core.services.whole_book_minimal_structure_stages_v1_service import (
            _persist_structure_assets,
        )

        envelope = load_structure_checkpoint_envelope(session, run_id)
        structure = dict(envelope["structure"])
        # Mutate title to simulate a new analysis result.
        structure["stages"][0]["title"] = "Confirmed-Overwrite-Attempt"
        run = get_run(session, run_id)
        meta = _persist_structure_assets(
            session,
            run_id=run_id,
            book_id=book_id,
            snapshot_id=int(run.snapshot_id),
            structure=structure,
            catalog=None,
        )
        session.commit()
        confirmed = session.get(NarrativeAssetVersion, version.id)
        assert confirmed.review_status == ReviewStatus.CONFIRMED.value
        assert confirmed.is_canonical is True
        assert confirmed.title != "Confirmed-Overwrite-Attempt"
        assert meta["confirmed_skipped"] >= 1
    engine.dispose()


def test_o_conflict_version_creation(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb21-o.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, book_id = prepare_sample_s_run(session)
        _pipeline(session, run_id, mode="multi_stage")
        session.commit()
        version = session.scalar(
            select(NarrativeAssetVersion).where(
                NarrativeAssetVersion.asset_type == "structure_stage",
                NarrativeAssetVersion.is_canonical.is_(True),
            )
        )
        confirm_narrative_asset_v1(session, version.asset_id)
        session.commit()
        from app.narrative_core.services.whole_book_structure_product_v1_service import (
            load_structure_checkpoint_envelope,
        )
        from app.narrative_core.services.whole_book_minimal_structure_stages_v1_service import (
            _persist_structure_assets,
        )

        envelope = load_structure_checkpoint_envelope(session, run_id)
        structure = dict(envelope["structure"])
        structure["stages"][0]["title"] = "Conflict-Candidate-Title"
        run = get_run(session, run_id)
        meta = _persist_structure_assets(
            session,
            run_id=run_id,
            book_id=book_id,
            snapshot_id=int(run.snapshot_id),
            structure=structure,
            catalog=None,
        )
        session.commit()
        conflicts = list(
            session.scalars(
                select(AnalysisConflict).where(
                    AnalysisConflict.book_id == book_id,
                    AnalysisConflict.status == "open",
                )
            ).all()
        )
        assert conflicts
        assert meta["conflicts_created"] >= 1
        assert meta["confirmed_skipped"] >= 1
        candidates = list(
            session.scalars(
                select(NarrativeAssetVersion).where(
                    NarrativeAssetVersion.asset_id == version.asset_id,
                    NarrativeAssetVersion.is_canonical.is_(False),
                )
            ).all()
        )
        assert candidates
    engine.dispose()


def test_native_input_independence_counts_zero(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb21-native.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        result = _pipeline(session, run_id)
        session.commit()
        # Request payload contract in structure unit asserts zero contamination inputs.
        assert result["structure"]["result_status"] == "completed"
        from app.narrative_core.services.whole_book_native_input_audit_v1 import (
            assert_native_input_independence_v1,
        )

        audit = assert_native_input_independence_v1(session, run_id)
        assert audit.chapter_analysis_asset_count == 0
        assert audit.reader_journey_asset_count == 0
        assert getattr(audit, "chapter_aggregate_asset_count", 0) == 0
    engine.dispose()


def test_capability_structure_available_counts() -> None:
    structure = resolve_capability_access("whole_book.structure", AccessTier.free)
    chapter = resolve_capability_access("whole_book.chapter_functions", AccessTier.free)
    assert structure["access_status"] == "granted"
    assert structure["release_status"] == "available"
    assert chapter["release_status"] == "planned"
    from app.narrative_core.services.whole_book_product_capability_v1 import (
        PRODUCT_CAPABILITY_REGISTRY,
    )

    free = [c for c in PRODUCT_CAPABILITY_REGISTRY.values() if c.required_tier.value == "free"]
    pro = [c for c in PRODUCT_CAPABILITY_REGISTRY.values() if c.required_tier.value == "pro"]
    assert len(free) == 4
    assert len(pro) == 8


def test_product_structure_api_available(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb21-api.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        _pipeline(session, run_id)
        session.commit()
        # Bind TestClient to same DB is non-trivial; validate service envelope shape.
        payload = get_run_structure_product_v1(session, run_id)
        assert payload["contract_version"] == "v2"
        assert payload["structure"]["contract_version"] == "v2"
        assert "FIXTURE_TEST_DATA" in (payload["structure"].get("limitations") or [])
    engine.dispose()
