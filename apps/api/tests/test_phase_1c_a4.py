"""Phase 1C-A.4 staged budget, reservation lifecycle, and resume."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.db.models import (
    AnalysisRun,
    ApplicationSetting,
    BoundaryReviewDecision,
    BoundaryRevision,
    Book,
    Chapter,
    CloudBudgetReservation,
    ModelInvocation,
    Paragraph,
    RequestGateDecision,
    Scene,
)
from app.services.budget_reservation import (
    InsufficientBudgetReservation,
    release_run_reservation,
    reserve_budget,
)
from app.services.boundary_review_service import confirm_review, create_review_session
from app.services.cloud_budget import daily_usage
from app.services.staged_budget import (
    STAGE_ANALYSIS,
    STAGE_BOUNDARY,
    estimate_stage1_boundary,
    estimate_stage2_scene_analysis,
)
from app.schemas.settings import CloudBudgetUpdate
from app.services.cloud_pricing import pricing_status
from tests.paths import config_file


def _seed_chapter(session, paragraphs: int = 12):
    book = Book(title="预算测试", source_file_name="b.txt", source_file_hash="e" * 64)
    session.add(book)
    session.flush()
    chapter = Chapter(
        book_id=book.id, chapter_index=1, title="第一章", section_type="chapter"
    )
    session.add(chapter)
    session.flush()
    rows = []
    for index in range(1, paragraphs + 1):
        row = Paragraph(
            id=f"B0001-C0001-P{index:04d}",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=index,
            raw_text=f"原创段落内容{index}" * 3,
            normalized_text=f"原创段落内容{index}" * 3,
            char_start=index * 10,
            char_end=index * 10 + 8,
        )
        session.add(row)
        rows.append(row)
    session.commit()
    return book, chapter, rows


def _budget_settings(session, **overrides):
    payload = CloudBudgetUpdate().model_dump()
    payload.update(overrides)
    session.merge(
        ApplicationSetting(key="cloud_enabled", value_json=json.dumps(True))
    )
    session.merge(
        ApplicationSetting(key="cloud_budget_settings", value_json=json.dumps(payload))
    )
    session.commit()
    return payload


def test_stage1_estimate_excludes_scene_analysis(testing_session):
    _, _, paragraphs = _seed_chapter(testing_session, 68)
    estimate = estimate_stage1_boundary(paragraphs)
    assert estimate.stage == STAGE_BOUNDARY
    assert estimate.scene_count == 0
    assert "expected_scenes" not in estimate.__dict__
    # Old formula was 2*(ceil(67/3)+ceil(67/8)+ceil(68/4))=98
    assert estimate.worst_case_request_count < 98
    assert estimate.worst_case_total_tokens < 196000
    assert estimate.detection_batch_count >= 1
    assert estimate.adjudication_batch_count_estimated >= 1


def test_stage1_uses_transition_batch_planner(testing_session):
    _, _, paragraphs = _seed_chapter(testing_session, 20)
    estimate = estimate_stage1_boundary(paragraphs)
    assert estimate.transition_count == 19
    assert estimate.detection_batch_count >= 1
    assert estimate.worst_case_request_count == 2 * (
        estimate.detection_batch_count + estimate.adjudication_batch_count_estimated
    )


def test_stage1_reservation_and_release(testing_session):
    reservation = reserve_budget(
        testing_session,
        run_id=None,
        stage=STAGE_BOUNDARY,
        required_requests=4,
        required_tokens=1000,
        required_cost=0.02,
        remaining_requests=20,
        remaining_tokens=50000,
        remaining_cost=1.0,
        expected_requests=2,
        worst_case_requests=4,
    )
    assert reservation.stage == STAGE_BOUNDARY
    assert reservation.status == "active"
    release_run_reservation(testing_session, reservation.run_id or 0, stage=STAGE_BOUNDARY)
    # release by id since run_id is None
    from app.services.budget_reservation import release_reservation

    release_reservation(testing_session, reservation.id)
    testing_session.refresh(reservation)
    assert reservation.status == "released"
    assert reservation.released_at is not None


def test_only_estimated_cost_blocks_reservation(testing_session):
    # Requests and tokens remain visible in the estimate but are advisory. They
    # are alternate units for the same paid usage and must not independently
    # block a run while its explicit CNY budget still covers the estimate.
    request_advisory = reserve_budget(
        testing_session,
        run_id=None,
        stage=STAGE_BOUNDARY,
        required_requests=10,
        required_tokens=10,
        required_cost=0.01,
        remaining_requests=5,
        remaining_tokens=100,
        remaining_cost=1,
    )
    assert request_advisory.status == "active"
    from app.services.budget_reservation import release_reservation

    release_reservation(testing_session, request_advisory.id)
    token_advisory = reserve_budget(
        testing_session,
        run_id=None,
        stage=STAGE_BOUNDARY,
        required_requests=1,
        required_tokens=500,
        required_cost=0.01,
        remaining_requests=10,
        remaining_tokens=100,
        remaining_cost=1,
    )
    assert token_advisory.status == "active"
    release_reservation(testing_session, token_advisory.id)

    with pytest.raises(InsufficientBudgetReservation) as cost_exc:
        reserve_budget(
            testing_session,
            run_id=None,
            stage=STAGE_BOUNDARY,
            required_requests=1,
            required_tokens=10,
            required_cost=2.0,
            remaining_requests=10,
            remaining_tokens=100,
            remaining_cost=1,
        )
    assert cost_exc.value.exceeded_dimensions == ["estimated_cost"]
    detail = cost_exc.value.as_error_detail()
    assert detail["stage"] == STAGE_BOUNDARY
    assert detail["required"]["estimated_cost"] == 2.0


def test_usage_ignores_blocked_and_reservations(testing_session):
    budget = _budget_settings(testing_session)
    reserve_budget(
        testing_session,
        run_id=None,
        stage=STAGE_BOUNDARY,
        required_requests=5,
        required_tokens=1000,
        required_cost=0.1,
        remaining_requests=30,
        remaining_tokens=200000,
        remaining_cost=3,
    )
    testing_session.add(
        RequestGateDecision(
            allowed=False,
            reason_code="INSUFFICIENT_BUDGET_RESERVATION",
            budget_snapshot_json="{}",
        )
    )
    testing_session.commit()
    usage = daily_usage(
        testing_session, budget, True, pricing_status(config_file("cloud_pricing.json"))
    )
    assert usage["request_count"] == 0
    assert usage["reserved_requests"] == 5
    assert usage["blocked_gate_count"] >= 1


def test_awaiting_review_has_no_active_reservation(testing_session):
    book, chapter, paragraphs = _seed_chapter(testing_session, 6)
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id=str(chapter.id),
        provider="aliyun_qwen_plus",
        model="qwen3.7-plus",
        prompt_version="v3.5",
        schema_version="v1",
        input_hash="f" * 64,
        status="running",
        execution_mode="cloud",
        cloud_consent=True,
        sends_content_to_cloud=True,
        analysis_mode="assisted_boundary_review",
    )
    testing_session.add(run)
    testing_session.flush()
    reservation = reserve_budget(
        testing_session,
        run_id=run.id,
        stage=STAGE_BOUNDARY,
        required_requests=4,
        required_tokens=800,
        required_cost=0.01,
        remaining_requests=50,
        remaining_tokens=100000,
        remaining_cost=2,
    )
    decision = {
        "transition_id": "T0002",
        "boundary_candidate": True,
        "goal_relation": "replaced",
        "action_chain_relation": "new_chain",
        "temporal_relation": "continuous",
        "location_relation": "same",
        "viewpoint_relation": "same",
        "trigger_type": "goal",
        "confidence": 0.82,
    }
    testing_session.add(
        ModelInvocation(
            run_id=run.id,
            task_type="scene_boundary",
            provider_name=run.provider,
            model_name=run.model,
            prompt_version="v3.5",
            schema_version="v1",
            attempt_no=1,
            invocation_kind="boundary_candidate_detection",
            request_hash="a" * 64,
            input_snapshot_json="{}",
            raw_response_text="",
            parsed_response_json=json.dumps(
                {"contract_version": "3.5", "decisions": [decision]}
            ),
            status="succeeded",
            latency_ms=1,
            http_request_sent=False,
            mapped_after_paragraph_ids_json=json.dumps([paragraphs[1].id]),
        )
    )
    testing_session.commit()
    create_review_session(testing_session, run)
    release_run_reservation(testing_session, run.id, stage=STAGE_BOUNDARY)
    testing_session.refresh(reservation)
    assert run.status == "awaiting_boundary_review"
    assert reservation.status == "released"
    active = testing_session.scalar(
        select(func.count())
        .select_from(CloudBudgetReservation)
        .where(
            CloudBudgetReservation.run_id == run.id,
            CloudBudgetReservation.status == "active",
        )
    )
    assert active == 0


def test_stage2_estimate_uses_final_scenes(testing_session):
    _, chapter, paragraphs = _seed_chapter(testing_session, 8)
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id=str(chapter.id),
        provider="aliyun_qwen_plus",
        model="qwen3.7-plus",
        prompt_version="v3.5",
        schema_version="v1",
        input_hash="1" * 64,
        status="boundary_confirmed",
        execution_mode="cloud",
        cloud_consent=True,
        sends_content_to_cloud=True,
    )
    testing_session.add(run)
    testing_session.flush()
    scenes = [
        Scene(
            scene_key=f"S{index}",
            book_id=chapter.book_id,
            chapter_id=chapter.id,
            ordinal=index,
            start_paragraph_id=paragraphs[index - 1].id,
            end_paragraph_id=paragraphs[index - 1].id,
            content_hash="c" * 64,
            created_by_run_id=run.id,
            boundary_confidence=1.0,
        )
        for index in range(1, 4)
    ]
    testing_session.add_all(scenes)
    testing_session.commit()
    estimate = estimate_stage2_scene_analysis(testing_session, scenes, paragraphs)
    assert estimate.stage == STAGE_ANALYSIS
    assert estimate.scene_count == 3
    assert estimate.worst_case_request_count == 6
    assert estimate.detection_batch_count == 0


def test_stage2_budget_block_keeps_revision_and_scenes(testing_session):
    from tests.test_phase_1c_a import seed

    _, chapter, paragraphs, run = seed(testing_session)
    review = create_review_session(testing_session, run)
    decision = testing_session.scalar(select(BoundaryReviewDecision))
    decision.user_decision = "accept"
    decision.final_boundary = True
    testing_session.commit()
    revision, scenes = confirm_review(testing_session, review, "tester")
    assert revision.id and len(scenes) >= 1
    run.status = "boundary_confirmed_budget_blocked"
    run.error_code = "INSUFFICIENT_BUDGET_RESERVATION"
    run.failed_stage = "scene_analysis_budget"
    testing_session.commit()
    assert testing_session.get(BoundaryRevision, revision.id) is not None
    assert testing_session.scalar(
        select(func.count()).select_from(Scene).where(Scene.boundary_revision_id == revision.id)
    ) == len(scenes)
