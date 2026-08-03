"""WB-2.2 — Chapter functions Free backend matrix A–Y."""

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
from app.narrative_core.services.chapter_functions_output_contract_v2 import (
    CANONICAL_FUNCTION_LABELS,
    normalize_function_labels,
    validate_chapter_functions_provider_output_v2,
)
from app.narrative_core.services.whole_book_chapter_functions_product_v1_service import (
    get_lab_chapter_functions_v1_from_v2,
    get_run_chapter_functions_product_v1,
)
from app.narrative_core.services.whole_book_confirm_protection_v1_service import (
    confirm_narrative_asset_v1,
)
from app.narrative_core.services.whole_book_cost_estimate_service import estimate_whole_book_analysis
from app.narrative_core.services.whole_book_fixture_pipeline_v1_service import (
    execute_fixture_minimal_pipeline_v1,
)
from app.narrative_core.services.whole_book_foundation_errors import WholeBookFoundationError
from app.narrative_core.services.whole_book_free_product_v1_service import (
    prepare_free_whole_book_analysis_v1,
)
from app.narrative_core.services.whole_book_minimal_chapter_functions_v1_service import (
    _persist_chapter_function_assets,
    synthesize_minimal_chapter_functions_v1,
)
from app.narrative_core.services.whole_book_minimal_helpers_v1 import MAX_CHAPTERS_PER_BATCH
from app.narrative_core.services.whole_book_minimal_overview_v1_service import (
    synthesize_minimal_book_overview_v1,
)
from app.narrative_core.services.whole_book_product_capability_v1 import (
    AccessTier,
    resolve_capability_access,
)
from app.narrative_core.services.whole_book_run_v1_service import (
    get_run,
    start_whole_book_run_v1,
)
from app.narrative_core.services.whole_book_runtime_control_v1_service import (
    request_cancel_whole_book_run_v1,
    request_pause_whole_book_run_v1,
    resume_whole_book_run_v1,
)
from tests.whole_book_minimal_test_helpers import (
    make_engine,
    prepare_sample_s_run,
    seed_sample_s_book,
)


def _pipeline(session, run_id: int, *, cf_mode: str = "available", structure_mode: str = "multi_stage"):
    return execute_fixture_minimal_pipeline_v1(
        session,
        run_id,
        structure_mode=structure_mode,
        chapter_functions_mode=cf_mode,
    )


def test_a_normal_per_chapter_functions(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb22-a.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        result = _pipeline(session, run_id)
        session.commit()
        assert result["run_status"] == "completed"
        assert result["chapter_functions"]["chapter_count"] >= 1
        payload = get_run_chapter_functions_product_v1(session, run_id)
        assert payload is not None
        assert payload["result_status"] == "completed"
        assert payload["contract_version"] == "v2"
        chapters = payload["chapter_functions"]["chapters"]
        assert len(chapters) >= 1
        for ch in chapters:
            primary = ch.get("primary_function")
            if primary is not None:
                assert primary in CANONICAL_FUNCTION_LABELS
            for sec in ch.get("secondary_functions") or []:
                assert sec in CANONICAL_FUNCTION_LABELS
            assert ch.get("supporting_citation_ids")
        assert payload["evidence_references"]
    engine.dispose()


def test_b_multi_function_chapter(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb22-b.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        _pipeline(session, run_id, cf_mode="multi_function")
        session.commit()
        payload = get_run_chapter_functions_product_v1(session, run_id)
        multi = [
            c
            for c in payload["chapter_functions"]["chapters"]
            if c.get("primary_function") and (c.get("secondary_functions") or [])
        ]
        assert multi
        for ch in multi:
            assert ch["primary_function"] not in ch["secondary_functions"]
    engine.dispose()


def test_c_primary_null_legal(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb22-c.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        result = _pipeline(session, run_id, cf_mode="primary_null")
        session.commit()
        assert result["run_status"] == "completed"
        payload = get_run_chapter_functions_product_v1(session, run_id)
        assert any(c.get("primary_function") is None for c in payload["chapter_functions"]["chapters"])
        assert any(c.get("secondary_functions") for c in payload["chapter_functions"]["chapters"])
    engine.dispose()


def test_d_controlled_label_reject(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb22-d.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        result = _pipeline(session, run_id, cf_mode="failed_unknown_label")
        session.commit()
        assert result["chapter_functions"]["result_status"] == "failed"
        assert result["chapter_functions"]["failure_code"] in {
            "CHAPTER_FN_LABEL_UNKNOWN",
            "CHAPTER_FN_EMPTY_RESULT_AFTER_REPAIR",
            "CHAPTER_FN_CONTRACT_FAILURE",
            "DTO_VALIDATION_FAILED",
        }
        versions = list(
            session.scalars(
                select(NarrativeAssetVersion).where(
                    NarrativeAssetVersion.asset_type == "chapter_function",
                    NarrativeAssetVersion.is_canonical.is_(True),
                )
            ).all()
        )
        assert versions == []
    engine.dispose()


def test_e_synonym_normalize() -> None:
    primary, secondary, err = normalize_function_labels("rising", ["bridge", "aside", "rising"])
    assert err is None
    assert primary == "escalation"
    assert secondary == ("transition", "side_story")
    p2, s2, err2 = normalize_function_labels("ending", ["none"])
    assert err2 is None
    assert p2 == "resolution"
    assert s2 == ("empty",)


def test_f_evidence_missing(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb22-f.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        result = _pipeline(session, run_id, cf_mode="missing_citation")
        session.commit()
        assert result["chapter_functions"]["result_status"] == "failed"
        assert result["chapter_functions"]["failure_code"] in {
            "CHAPTER_FN_CITATION_EMPTY",
            "CHAPTER_FN_EMPTY_RESULT_AFTER_REPAIR",
            "DTO_VALIDATION_FAILED",
        }
    engine.dispose()


def test_g_truncation_repair_success(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb22-g.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        result = _pipeline(session, run_id, cf_mode="repair_success")
        session.commit()
        assert result["chapter_functions"]["result_status"] == "completed"
        assert result["chapter_functions"]["provider_calls"] >= 1
    engine.dispose()


def test_h_repair_still_illegal(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb22-h.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        result = _pipeline(session, run_id, cf_mode="failed_empty")
        session.commit()
        assert result["chapter_functions"]["failure_code"] in {
            "CHAPTER_FN_EMPTY_RESULT_AFTER_REPAIR",
            "CHAPTER_FN_REQUIRED_CHAPTER_MISSING",
            "CHAPTER_FN_COVERAGE_SCOPE_BINDING_MISMATCH",
        }
    engine.dispose()


def test_i_coverage_insufficient(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb22-i.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        result = _pipeline(session, run_id, cf_mode="insufficient")
        session.commit()
        run = get_run(session, run_id)
        assert run.status == "completed"
        payload = get_run_chapter_functions_product_v1(session, run_id)
        assert payload["result_status"] == "completed"
        assert payload["coverage_scope"] == "insufficient"
        assert payload["chapter_functions"]["chapters"] == []
        assert result["chapter_functions"]["product_result_status"] == "insufficient"
    engine.dispose()


def test_j_capability_true_empty_illegal() -> None:
    validation = validate_chapter_functions_provider_output_v2(
        {
            "contract_version": "v2",
            "evidence_contract_version": "v2",
            "coverage_scope": "full_selected_range",
            "chapters": [],
        },
        allowed_citation_ids=["c-1"],
        capabilities={
            "expected_coverage_scope": "full_selected_range",
            "requires_chapter_observation": True,
            "permits_empty_observation": False,
        },
        repair_count=1,
    )
    assert validation.ok is False
    assert validation.failure_code in {
        "CHAPTER_FN_EMPTY_RESULT_AFTER_REPAIR",
        "CHAPTER_FN_REQUIRED_CHAPTER_MISSING",
    }


def test_k_non_contiguous_no_invention(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb22-k.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        _pipeline(session, run_id)
        session.commit()
        payload = get_run_chapter_functions_product_v1(session, run_id)
        orders = [int(c["chapter_order"]) for c in payload["chapter_functions"]["chapters"]]
        assert len(orders) == len(set(orders))
        for ch in payload["chapter_functions"]["chapters"]:
            assert ch.get("supporting_citation_ids")
    engine.dispose()


def test_l_empty_duplicate_deterministic() -> None:
    primary, secondary, err = normalize_function_labels("setup", ["setup", "transition", "transition"])
    assert err is None
    assert primary == "setup"
    assert secondary == ("transition",)
    validation = validate_chapter_functions_provider_output_v2(
        {
            "contract_version": "v2",
            "coverage_scope": "full_selected_range",
            "chapters": [
                {
                    "chapter_id": 1,
                    "chapter_order": 1,
                    "primary_function": "setup",
                    "secondary_functions": [],
                    "observed_summary": {
                        "value": "a",
                        "status": "observed",
                        "citation_ids": ["c1"],
                        "confidence": 0.5,
                    },
                    "confidence": 0.5,
                    "supporting_citation_ids": ["c1"],
                },
                {
                    "chapter_id": 2,
                    "chapter_order": 1,
                    "primary_function": "escalation",
                    "secondary_functions": [],
                    "observed_summary": {
                        "value": "b",
                        "status": "observed",
                        "citation_ids": ["c1"],
                        "confidence": 0.5,
                    },
                    "confidence": 0.5,
                    "supporting_citation_ids": ["c1"],
                },
            ],
        },
        allowed_citation_ids=["c1"],
        capabilities={
            "expected_coverage_scope": "full_selected_range",
            "requires_chapter_observation": True,
        },
    )
    assert validation.ok is False
    assert validation.failure_code == "CHAPTER_FN_CHAPTER_ORDER_DUPLICATE"


def test_m_long_book_batching() -> None:
    from app.narrative_core.services.whole_book_minimal_chapter_functions_v1_service import (
        _batch_chapter_units,
        _merge_chapter_results,
    )
    from app.narrative_core.services.fixture_chapter_functions_sample_s import (
        build_fixture_chapter_functions_v2,
    )

    assert MAX_CHAPTERS_PER_BATCH == 8
    units = [
        {"chapter_id": i, "chapter_order": i, "citation_ids": [f"c{i}"]}
        for i in range(1, 11)
    ]
    batches = _batch_chapter_units(units)
    assert len(batches) == 2
    assert all(len(b) <= 8 for b in batches)
    covered = [u["chapter_order"] for b in batches for u in b]
    assert covered == list(range(1, 11))
    parts = [
        build_fixture_chapter_functions_v2(
            citation_ids=[u["citation_ids"][0] for u in batch],
            chapter_units=batch,
            mode="long_book",
        )
        for batch in batches
    ]
    merged = _merge_chapter_results(parts)
    orders = [int(c["chapter_order"]) for c in merged["chapters"]]
    assert orders == list(range(1, 11))


def test_n_pause_then_resume(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb22-n.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        start_whole_book_run_v1(session, run_id)
        request_pause_whole_book_run_v1(session, run_id)
        session.commit()
        assert get_run(session, run_id).status == "paused"
        resume_whole_book_run_v1(session, run_id)
        start_whole_book_run_v1(session, run_id)
        result = _pipeline(session, run_id)
        session.commit()
        assert result["run_status"] == "completed"
        assert result["chapter_functions"]["chapter_count"] >= 1
    engine.dispose()


def test_o_cancel_blocks_resume(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb22-o.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        start_whole_book_run_v1(session, run_id)
        request_cancel_whole_book_run_v1(session, run_id)
        session.commit()
        assert get_run(session, run_id).status == "cancelled"
        with pytest.raises(WholeBookFoundationError):
            resume_whole_book_run_v1(session, run_id)
        payload = get_run_chapter_functions_product_v1(session, run_id)
        assert payload["result_status"] == "canceled"
    engine.dispose()


def test_p_duplicate_resume_no_extra_provider_calls(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb22-p.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        first = _pipeline(session, run_id)
        session.commit()
        calls_1 = session.query(WholeBookProviderAttempt).count()
        again = _pipeline(session, run_id)
        session.commit()
        calls_2 = session.query(WholeBookProviderAttempt).count()
        assert again["chapter_functions"]["reused"] is True or again["run_status"] == "completed"
        assert again["chapter_functions"]["provider_calls"] == 0
        assert calls_2 == calls_1
        assert first["chapter_functions"]["provider_calls"] >= 1
    engine.dispose()


def test_q_confirmed_no_overwrite(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb22-q.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, book_id = prepare_sample_s_run(session)
        _pipeline(session, run_id)
        session.commit()
        version = session.scalar(
            select(NarrativeAssetVersion).where(
                NarrativeAssetVersion.asset_type == "chapter_function",
                NarrativeAssetVersion.is_canonical.is_(True),
            )
        )
        assert version is not None
        confirm_narrative_asset_v1(session, version.asset_id)
        session.commit()
        from app.narrative_core.services.whole_book_chapter_functions_product_v1_service import (
            load_chapter_functions_checkpoint_envelope,
        )

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
        confirmed = session.get(NarrativeAssetVersion, version.id)
        assert confirmed.review_status == ReviewStatus.CONFIRMED.value
        assert confirmed.is_canonical is True
        assert "Confirmed-Overwrite-Attempt" not in (confirmed.summary or "")
        assert meta["confirmed_skipped"] >= 1
    engine.dispose()


def test_r_conflict_version_creation(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb22-r.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, book_id = prepare_sample_s_run(session)
        _pipeline(session, run_id)
        session.commit()
        version = session.scalar(
            select(NarrativeAssetVersion).where(
                NarrativeAssetVersion.asset_type == "chapter_function",
                NarrativeAssetVersion.is_canonical.is_(True),
            )
        )
        confirm_narrative_asset_v1(session, version.asset_id)
        session.commit()
        from app.narrative_core.services.whole_book_chapter_functions_product_v1_service import (
            load_chapter_functions_checkpoint_envelope,
        )

        envelope = load_chapter_functions_checkpoint_envelope(session, run_id)
        cf = dict(envelope["chapter_functions"])
        cf["chapters"][0]["primary_function"] = "flashback"
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
    engine.dispose()


def test_s_native_input_audit_counts_zero(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb22-s.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        result = _pipeline(session, run_id)
        session.commit()
        assert result["chapter_functions"]["result_status"] == "completed"
        from app.narrative_core.services.whole_book_native_input_audit_v1 import (
            assert_native_input_independence_v1,
        )

        audit = assert_native_input_independence_v1(session, run_id)
        assert audit.chapter_analysis_asset_count == 0
        assert audit.reader_journey_asset_count == 0
        assert getattr(audit, "chapter_aggregate_asset_count", 0) == 0
        from app.narrative_core.services.whole_book_chapter_functions_product_v1_service import (
            load_chapter_functions_checkpoint_envelope,
        )

        env = load_chapter_functions_checkpoint_envelope(session, run_id)
        usage = env.get("native_input_usage") or {}
        assert usage.get("chapter_analysis_asset_count") == 0
        assert usage.get("reader_journey_asset_count") == 0
        assert usage.get("aggregate_insights_asset_count") == 0
    engine.dispose()


def test_t_structure_absent_still_runs(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb22-t.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        start_whole_book_run_v1(session, run_id)
        from app.narrative_core.services.whole_book_minimal_extraction_v1_service import (
            FixtureWindowAnalysisTransport,
            execute_minimal_entity_event_extraction_v1,
        )
        from app.narrative_core.services.whole_book_minimal_materialization_v1_service import (
            materialize_minimal_narrative_assets_v1,
        )

        execute_minimal_entity_event_extraction_v1(
            session, run_id, transport=FixtureWindowAnalysisTransport()
        )
        materialize_minimal_narrative_assets_v1(session, run_id)
        synthesize_minimal_book_overview_v1(session, run_id, finalize_run=False)
        # Skip structure entirely.
        cf = synthesize_minimal_chapter_functions_v1(session, run_id, mode="available", finalize_run=True)
        session.commit()
        assert cf["result_status"] == "completed"
        assert cf["chapter_count"] >= 1
    engine.dispose()


def test_u_structure_derived_context_only(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb22-u.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        _pipeline(session, run_id, cf_mode="structure_context_available")
        session.commit()
        payload = get_run_chapter_functions_product_v1(session, run_id)
        caps = payload["chapter_functions"].get("context_capabilities") or {}
        derived = caps.get("structure_derived_context") or {}
        assert derived.get("marker") == "DERIVED_CONTEXT_NOT_FACT"
        # Evidence must be catalog citations, not structure-only strings.
        for cid in payload["evidence_references"]:
            assert isinstance(cid, str) and cid
            assert not str(cid).startswith("structure_stages.")
    engine.dispose()


def test_v_lab_v1_adapter(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb22-v.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        _pipeline(session, run_id, cf_mode="multi_function")
        session.commit()
        free = get_run_chapter_functions_product_v1(session, run_id)
        assert free["contract_version"] == "v2"
        assert "chapters" in free["chapter_functions"]
        lab = get_lab_chapter_functions_v1_from_v2(session, run_id)
        assert lab is not None
        assert lab["contract_version"] == "v1"
        assert lab["items"]
        item = lab["items"][0]
        assert "function_labels" in item
        # Labels derived from primary+secondary.
        primary = free["chapter_functions"]["chapters"][0].get("primary_function")
        secondary = free["chapter_functions"]["chapters"][0].get("secondary_functions") or []
        expected = [x for x in ((primary,) if primary else ()) + tuple(secondary) if x]
        matching = next(i for i in lab["items"] if i["chapter_order"] == free["chapter_functions"]["chapters"][0]["chapter_order"])
        assert list(matching["function_labels"]) == expected
    engine.dispose()


def test_w_pro_insights_isolation() -> None:
    # Free path never materializes Pro ChapterFunctionsResultV1 distribution payload.
    from app.narrative_core.product_contract.module_results import (
        ChapterFunctionsResultDto,
        ChapterFunctionsResultV2,
        resolve_module_result_dto_class,
    )
    from app.narrative_core.enums import WholeBookModuleKey

    dto = resolve_module_result_dto_class(
        WholeBookModuleKey.CHAPTER_FUNCTIONS,
        {"contract_version": "v2"},
    )
    assert dto is ChapterFunctionsResultV2
    dto_v1 = resolve_module_result_dto_class(
        WholeBookModuleKey.CHAPTER_FUNCTIONS,
        {"contract_version": "v1"},
    )
    assert dto_v1 is ChapterFunctionsResultDto
    assert not hasattr(ChapterFunctionsResultV2, "distribution")


def test_x_pagination_cursor(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb22-x.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        _pipeline(session, run_id)
        session.commit()
        page1 = get_run_chapter_functions_product_v1(session, run_id, limit=1)
        assert len(page1["items"]) == 1
        assert page1["total_chapters"] >= 2
        assert page1["next_cursor"]
        page2 = get_run_chapter_functions_product_v1(
            session, run_id, limit=1, cursor=page1["next_cursor"]
        )
        assert len(page2["items"]) == 1
        assert page1["items"][0]["chapter_order"] < page2["items"][0]["chapter_order"]
        filtered = get_run_chapter_functions_product_v1(session, run_id, function="setup")
        for item in filtered["items"]:
            assert item.get("primary_function") == "setup" or "setup" in (
                item.get("secondary_functions") or []
            )
        status_f = get_run_chapter_functions_product_v1(session, run_id, status="observed")
        assert status_f["total_chapters"] >= 1
    engine.dispose()


def test_y_cost_estimate_includes_chapter_functions(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_FEATURE_ENABLED", "true")
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED", "true")
    engine = make_engine(tmp_path, "wb22-y.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        from app.db.models import ProviderConfiguration

        provider = ProviderConfiguration(provider_name="fixture", plus_model="fixture-model")
        session.add(provider)
        session.flush()
        est = estimate_whole_book_analysis(session, book.id, "whole_book_native", provider.id)
        # window_count(3) + overview + structure + chapter_functions = 6
        assert est.estimated_provider_call_count >= 4
        cap = resolve_capability_access("whole_book.chapter_functions", AccessTier.free)
        assert cap["access_status"] == "granted"
        prepare = prepare_free_whole_book_analysis_v1(session, book.id)
        assert prepare is not None
    engine.dispose()


def test_capability_available() -> None:
    cap = resolve_capability_access("whole_book.chapter_functions", AccessTier.free)
    assert cap["release_status"] == "available"
    assert cap["access_status"] == "granted"


def test_absent_404_envelope(tmp_path) -> None:
    engine = make_engine(tmp_path, "wb22-absent.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run_id, _ = prepare_sample_s_run(session)
        start_whole_book_run_v1(session, run_id)
        session.commit()
        assert get_run_chapter_functions_product_v1(session, run_id) is None
    engine.dispose()


def test_prepare_dual_path_regression(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_FEATURE_ENABLED", "true")
    monkeypatch.setenv("STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED", "true")
    engine = make_engine(tmp_path, "wb22-prepare.db")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        book, _ = seed_sample_s_book(session)
        payload = prepare_free_whole_book_analysis_v1(session, book.id)
        assert "estimate" in payload or "cost_estimate" in payload or "book_id" in payload
    engine.dispose()
