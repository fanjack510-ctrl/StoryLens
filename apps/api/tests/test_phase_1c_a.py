import json

import pytest
from sqlalchemy import func, select
from pathlib import Path

from app.db.models import (
    AnalysisRun,
    Book,
    BoundaryReviewDecision,
    BoundaryRevision,
    Chapter,
    ModelInvocation,
    Paragraph,
    ProviderConfiguration,
    ApplicationSetting,
    Scene,
)
from app.api.v1.analysis import create_run_record
from app.model_gateway.base import ProviderCapabilities
from app.model_gateway.gateway import ModelGateway
from app.schemas.scene import AnalysisRunCreate
from app.services.provider_eligibility import (
    evaluate_manual_boundary_candidate,
    provider_eligibility,
)
from tests.fakes import FakeProvider
from app.services.boundary_review_service import (
    confirm_review,
    create_review_session,
    preview_ranges,
    update_counts,
)


def seed(testing_session):
    book = Book(
        title="原创审阅测试", source_file_name="review.txt", source_file_hash="a" * 64
    )
    testing_session.add(book)
    testing_session.flush()
    chapter = Chapter(book_id=book.id, chapter_index=1, title="第一章", section_type="chapter")
    testing_session.add(chapter)
    testing_session.flush()
    paragraphs = []
    for index in range(1, 7):
        paragraph = Paragraph(
            id=f"B0001-C0001-P{index:04d}", book_id=book.id, chapter_id=chapter.id,
            paragraph_index=index, raw_text=f"原创段落{index}", normalized_text=f"原创段落{index}",
            char_start=index * 10, char_end=index * 10 + 5,
        )
        testing_session.add(paragraph)
        paragraphs.append(paragraph)
    run = AnalysisRun(
        task_type="scene_pipeline", subject_type="chapter", subject_id=str(chapter.id),
        provider="aliyun_qwen_plus", model="configured-plus", prompt_version="v3.5",
        schema_version="v1", input_hash="b" * 64, status="running", execution_mode="cloud",
        cloud_consent=True, sends_content_to_cloud=True,
    )
    testing_session.add(run)
    testing_session.flush()
    decision = {
        "transition_id": "T0002", "boundary_candidate": True,
        "goal_relation": "replaced", "action_chain_relation": "new_chain",
        "temporal_relation": "continuous", "location_relation": "same",
        "viewpoint_relation": "same", "trigger_type": "goal", "confidence": 0.82,
    }
    testing_session.add(ModelInvocation(
        run_id=run.id, task_type="scene_boundary", provider_name=run.provider,
        model_name=run.model, prompt_version="v3.5", schema_version="v1", attempt_no=1,
        invocation_kind="boundary_candidate_detection", request_hash="c" * 64,
        input_snapshot_json="{}", raw_response_text="", parsed_response_json=json.dumps(
            {"contract_version": "3.5", "decisions": [decision]}
        ), status="succeeded", latency_ms=1, http_request_sent=False,
        selected_transition_ids_json='["T0002"]',
        mapped_after_paragraph_ids_json=json.dumps([paragraphs[1].id]),
    ))
    testing_session.add(ModelInvocation(
        run_id=run.id, task_type="scene_boundary_adjudication", provider_name=run.provider,
        model_name=run.model, prompt_version="v1", schema_version="v1", attempt_no=1,
        invocation_kind="boundary_candidate_adjudication", request_hash="d" * 64,
        input_snapshot_json="{}", raw_response_text="", parsed_response_json=json.dumps({
            "contract_version": "1.0", "verdicts": [{
                "transition_id": "T0002", "accept": True,
                "scope_relation": "primary_scene_change",
                "continuity_relation": "new_scene_chain", "confidence": 0.9,
            }]
        }), status="succeeded", latency_ms=1, http_request_sent=False,
    ))
    testing_session.commit()
    return book, chapter, paragraphs, run


def test_candidate_generation_creates_pending_review_and_waiting_task(testing_session):
    _, _, _, run = seed(testing_session)
    review = create_review_session(testing_session, run)
    decision = testing_session.scalar(select(BoundaryReviewDecision))
    assert review.status == "pending" and review.candidate_count == 1
    assert run.status == "awaiting_boundary_review"
    assert decision.review_priority == "high"
    assert "api" not in decision.first_pass_json.lower()


def test_accept_reject_manual_preview_and_confirmation(testing_session):
    """Confirm-only product path: proposal from user_decision, then fingerprint confirm."""
    from app.services.boundary_review_service import confirm_review_from_final_proposal
    from app.services.final_boundary_proposal import build_final_boundary_proposal

    _, chapter, paragraphs, run = seed(testing_session)
    # Longer body text so short-fragment consolidation keeps accepted cuts.
    for index, paragraph in enumerate(paragraphs, start=1):
        long_text = f"这是用于场景划分测试的较长正文段落内容{index}。" * 8
        paragraph.raw_text = long_text
        paragraph.normalized_text = long_text
        paragraph.char_end = paragraph.char_start + len(long_text)
    review = create_review_session(testing_session, run)
    model = testing_session.scalar(select(BoundaryReviewDecision))
    model.user_decision = "accept"
    # confirm_only: do not rely on pre-confirm final_boundary materialization
    testing_session.add(
        BoundaryReviewDecision(
            review_session_id=review.id,
            transition_id="M-P4",
            left_paragraph_id=paragraphs[3].id,
            right_paragraph_id=paragraphs[4].id,
            model_candidate=False,
            model_confidence=0,
            first_pass_json="{}",
            review_priority="high",
            user_decision="manually_added",
            final_boundary=False,
        )
    )
    testing_session.commit()
    update_counts(testing_session, review)

    proposal = build_final_boundary_proposal(testing_session, review)
    assert proposal.validation_status == "valid"
    assert proposal.final_boundary_left_ids == [paragraphs[1].id, paragraphs[3].id]
    assert proposal.scene_count == 3
    assert [(row["start_paragraph_id"], row["end_paragraph_id"]) for row in proposal.final_scene_ranges] == [
        (paragraphs[0].id, paragraphs[1].id),
        (paragraphs[2].id, paragraphs[3].id),
        (paragraphs[4].id, paragraphs[5].id),
    ]

    revision, scenes, replay = confirm_review_from_final_proposal(
        testing_session,
        review,
        confirmed_by="offline-reviewer",
        proposal_fingerprint=proposal.proposal_fingerprint,
    )
    assert replay is False
    assert revision.coverage_rate == 1 and len(scenes) == 3
    assert review.status == "confirmed" and run.status == "boundary_confirmed"
    assert all(item.boundary_revision_id == revision.id for item in scenes)
    assert scenes[1].start_paragraph_id == paragraphs[2].id


def test_confirmation_requires_every_model_candidate_decided(testing_session):
    from app.services.boundary_review_service import BoundaryReviewIncomplete

    _, _, _, run = seed(testing_session)
    review = create_review_session(testing_session, run)
    with pytest.raises(BoundaryReviewIncomplete) as raised:
        confirm_review(testing_session, review, "reviewer")
    assert raised.value.pending_count >= 1
    assert raised.value.pending_transition_ids
    detail = raised.value.as_error_detail()
    assert detail["error_code"] == "BOUNDARY_REVIEW_INCOMPLETE"
    assert detail["pending_transition_ids"] == raised.value.pending_transition_ids


def test_reject_produces_single_continuous_scene(testing_session):
    _, _, paragraphs, run = seed(testing_session)
    review = create_review_session(testing_session, run)
    decision = testing_session.scalar(select(BoundaryReviewDecision))
    decision.user_decision = "reject"
    revision, scenes = confirm_review(testing_session, review, "reviewer")
    assert len(scenes) == 1
    assert scenes[0].start_paragraph_id == paragraphs[0].id
    assert scenes[0].end_paragraph_id == paragraphs[-1].id
    assert revision.final_boundaries_json == "[]"


def test_revision_and_old_run_history_are_retained(testing_session):
    _, _, _, run = seed(testing_session)
    review = create_review_session(testing_session, run)
    decision = testing_session.scalar(select(BoundaryReviewDecision))
    decision.user_decision = "reject"
    revision, _ = confirm_review(testing_session, review, "reviewer")
    assert testing_session.get(AnalysisRun, run.id) is run
    assert testing_session.get(BoundaryRevision, revision.id) is revision
    assert testing_session.scalar(select(func.count()).select_from(Scene)) == 1


def test_plus_remains_non_default_and_auto_route_disabled(testing_session):
    config = ProviderConfiguration(
        provider_name="aliyun_qwen_plus", enabled=True, disconnected=False,
        allow_auto_route=False,
    )
    testing_session.add(config)
    testing_session.commit()
    assert config.allow_auto_route is False


class Store:
    def __init__(self, value="secret-reference"):
        self.value = value
    def available(self): return True
    def get(self, _): return self.value
    def set(self, *_): pass
    def delete(self, *_): pass


def configured_eligibility(testing_session, *, cloud=True, credential="secret-reference"):
    testing_session.add_all([
        ApplicationSetting(key="cloud_enabled", value_json=json.dumps(cloud)),
        ApplicationSetting(key="cloud_budget_settings", value_json=json.dumps({
            "cloud_request_budget_enabled": True, "cloud_daily_request_limit": 30,
            "cloud_daily_token_limit": 200000, "cloud_daily_estimated_cost_limit": 1,
        })),
        ProviderConfiguration(
            provider_name="aliyun_qwen_plus", enabled=True, disconnected=False,
            allow_auto_route=False, base_url="https://redacted.invalid/v1",
            credential_reference="keyring:aliyun_qwen_plus",
        ),
    ])
    testing_session.commit()
    capabilities = ProviderCapabilities(
        max_context_tokens=32000, default_timeout_seconds=10, enabled=True, cloud=True,
        supports_json_object=True, supports_structured_output=True,
        supports_scene_analysis=True, supports_boundary_candidates=True,
        automatic_boundary_routing=False, requires_boundary_review=True,
    )
    return provider_eligibility(
        testing_session, provider_name="aliyun_qwen_plus", capabilities=capabilities,
        healthy=True, store=Store(credential), pricing_path=Path("config/cloud_pricing.json"),
    )


def test_manual_eligibility_does_not_require_default_or_auto_route(
    testing_session, verified_cloud_pricing
):
    result = configured_eligibility(testing_session)
    assert result["manual_boundary_candidate_eligible"] is True
    assert result["automatic_route_eligible"] is False
    assert "auto_route_disabled" in result["automatic_route_blockers"]
    assert result["workflow_prompts"] == {
        "boundary_candidate": "v3.5", "boundary_adjudication": "v1",
        "scene_analysis": "v3.2", "thinking": False,
        "boundary_confirmation": "human_required",
    }


def test_unified_manual_evaluation_has_versioned_readiness(
    testing_session, verified_cloud_pricing
):
    configured_eligibility(testing_session)
    capabilities = ProviderCapabilities(
        max_context_tokens=32000, default_timeout_seconds=10, enabled=True, cloud=True,
        supports_boundary_candidates=True, requires_boundary_review=True,
    )
    result = evaluate_manual_boundary_candidate(
        testing_session, provider_name="aliyun_qwen_plus", capabilities=capabilities,
        store=Store("secret-reference"), pricing_path=Path("config/cloud_pricing.json"),
    )
    assert result["manual_boundary_candidate_eligible"] is True
    assert result["manual_selection_blockers"] == []
    assert result["health_state"] == "healthy"
    assert result["health_source"] == "configured_readiness"
    assert result["capability_schema_version"] == "1c-a-2"


@pytest.mark.parametrize(
    ("cloud", "credential", "blocker"),
    [(False, "secret-reference", "cloud_master_switch_off"),
     (True, None, "credential_missing")],
)
def test_manual_eligibility_reports_specific_blockers(
    testing_session, cloud, credential, blocker
):
    result = configured_eligibility(testing_session, cloud=cloud, credential=credential)
    assert result["manual_boundary_candidate_eligible"] is False
    assert blocker in result["manual_selection_blockers"]


def test_assisted_run_records_mode_without_model_request(testing_session):
    _, chapter, _, _ = seed(testing_session)
    provider = FakeProvider()
    provider.name = "aliyun_qwen_plus"
    provider.default_model = "configured-plus"
    provider.capabilities = lambda: ProviderCapabilities(
        max_context_tokens=32000, default_timeout_seconds=10, enabled=True, cloud=True,
        supports_boundary_candidates=True, requires_boundary_review=True,
    )
    run = create_run_record(
        testing_session, chapter,
        AnalysisRunCreate(
            provider_name=provider.name, execution_mode="cloud", cloud_consent=True,
            analysis_mode="assisted_boundary_review",
        ),
        ModelGateway([provider]),
    )
    assert run.analysis_mode == "assisted_boundary_review"
    assert provider.calls == 0
