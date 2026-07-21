import json
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    AnalysisRun,
    Book,
    BoundaryDetectionBatchCheckpoint,
    BoundaryReviewDecision,
    Chapter,
    ModelInvocation,
    Paragraph,
)
from app.model_gateway.gateway import ModelGateway
from app.model_gateway.base import ProviderRequestError
from app.schemas.scene import CompactTransitionClassificationResultV35
from app.services.boundary_detection_checkpoints import (
    clone_recovered_checkpoints,
    planned_detection_batches,
    recover_boundary_detection_from_invocations,
    upsert_detection_checkpoint,
)
from app.services.boundary_review_service import confirm_review
from app.services.scene_boundary_adjudicator import (
    validate_candidate_detection,
    validate_candidate_detection_for_review,
)
from app.services.scene_pipeline import _execute, execute_scene_pipeline
from tests.fakes import FakeProvider


def seed_run(testing_session, *, mode: str = "assisted_boundary_review", count: int = 4):
    book = Book(
        title="原创冲突测试",
        source_file_name="conflict.txt",
        source_file_hash="7" * 64,
    )
    testing_session.add(book)
    testing_session.flush()
    chapter = Chapter(
        book_id=book.id,
        chapter_index=1,
        title="第一章",
        section_type="chapter",
    )
    testing_session.add(chapter)
    testing_session.flush()
    paragraphs = []
    for index in range(1, count + 1):
        paragraph = Paragraph(
            id=f"B{book.id:04d}-C0001-P{index:04d}",
            book_id=book.id,
            chapter_id=chapter.id,
            paragraph_index=index,
            raw_text=f"原创测试段落{index}",
            normalized_text=f"原创测试段落{index}",
            char_start=index * 20,
            char_end=index * 20 + 8,
        )
        testing_session.add(paragraph)
        paragraphs.append(paragraph)
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id=str(chapter.id),
        provider="fake",
        model="fake-scene-model",
        prompt_version="v3.5",
        schema_version="v1",
        input_hash="8" * 64,
        prompt_hash="9" * 64,
        status="boundary_candidates_running",
        execution_mode="cloud",
        analysis_mode=mode,
        cloud_consent=True,
        sends_content_to_cloud=True,
    )
    testing_session.add(run)
    testing_session.commit()
    return book, chapter, paragraphs, run


def decision(transition_id: str, *, conflict: bool = False) -> dict:
    return {
        "transition_id": transition_id,
        "boundary_candidate": conflict,
        "goal_relation": "refined" if conflict else "same",
        "action_chain_relation": "continuous",
        "temporal_relation": "continuous",
        "location_relation": "same",
        "viewpoint_relation": "same",
        "trigger_type": "object" if conflict else "none",
        "confidence": 0.85,
    }


def batch_payload(ids: list[str], *, conflict_id: str | None = None) -> str:
    return json.dumps(
        {
            "contract_version": "3.5",
            "decisions": [
                decision(item, conflict=item == conflict_id) for item in ids
            ],
        }
    )


def invocation_for(
    testing_session,
    run: AnalysisRun,
    *,
    payload: str,
    kind: str,
    attempt: int,
    status: str = "succeeded",
) -> ModelInvocation:
    invocation = ModelInvocation(
        run_id=run.id,
        task_type="scene_boundary",
        provider_name=run.provider,
        model_name=run.model,
        prompt_version="v3.5",
        schema_version="v1",
        attempt_no=attempt,
        invocation_kind=kind,
        request_hash=f"{run.id}-{kind}-{attempt}",
        input_snapshot_json="{}",
        raw_response_text="",
        parsed_response_json=payload,
        status=status,
        latency_ms=1,
        http_request_sent=False,
    )
    testing_session.add(invocation)
    testing_session.commit()
    return invocation


def test_automatic_mode_remains_strict_for_semantic_conflict(testing_session):
    _, _, _, run = seed_run(testing_session, mode="automatic")
    plan = planned_detection_batches(testing_session, run)[0]
    ids = list(plan.batch.owned_transition_ids)
    parsed = CompactTransitionClassificationResultV35.model_validate_json(
        batch_payload(ids, conflict_id=ids[1])
    )
    with pytest.raises(
        ValueError, match="candidate decision conflicts with deterministic enum rules"
    ):
        validate_candidate_detection(parsed.decisions, ids)


@pytest.mark.asyncio
async def test_assisted_conflict_creates_checkpoint_and_review_without_repair(
    testing_session,
):
    _, _, _, run = seed_run(testing_session)
    plan = planned_detection_batches(testing_session, run)[0]
    ids = list(plan.batch.owned_transition_ids)
    provider = FakeProvider([batch_payload(ids, conflict_id=ids[1])])
    awaiting = await _execute(testing_session, ModelGateway([provider]), run)

    assert awaiting is True
    assert provider.calls == 1
    checkpoint = testing_session.scalar(select(BoundaryDetectionBatchCheckpoint))
    assert checkpoint.status == "conflicted_completed"
    issues = json.loads(checkpoint.issues_json)
    assert issues[0]["transition_id"] == ids[1]
    assert issues[0]["conflict_code"] == "CANDIDATE_TRUE_WITHOUT_LEGAL_REASON"
    assert issues[0]["review_priority"] == "high"
    conflict = testing_session.scalar(
        select(BoundaryReviewDecision).where(
            BoundaryReviewDecision.semantic_conflict.is_(True)
        )
    )
    assert conflict.transition_id == ids[1]
    assert conflict.user_decision == "pending"
    assert conflict.final_boundary is False
    assert run.status == "awaiting_boundary_review"
    kinds = list(
        testing_session.scalars(
            select(ModelInvocation.invocation_kind).where(
                ModelInvocation.run_id == run.id
            )
        )
    )
    assert kinds == ["boundary_candidate_detection"]


@pytest.mark.asyncio
async def test_structural_error_repairs_and_is_not_semantic_conflict(testing_session):
    _, _, _, run = seed_run(testing_session)
    plan = planned_detection_batches(testing_session, run)[0]
    ids = list(plan.batch.owned_transition_ids)
    provider = FakeProvider(
        [
            batch_payload(ids[:-1]),
            batch_payload(ids),
        ]
    )
    assert await _execute(testing_session, ModelGateway([provider]), run) is True
    assert provider.calls == 2
    kinds = list(
        testing_session.scalars(
            select(ModelInvocation.invocation_kind)
            .where(ModelInvocation.run_id == run.id)
            .order_by(ModelInvocation.id)
        )
    )
    assert kinds == ["boundary_candidate_detection", "structural_repair"]
    checkpoint = testing_session.scalar(select(BoundaryDetectionBatchCheckpoint))
    assert checkpoint.status == "completed"
    assert json.loads(checkpoint.issues_json) == []


def test_review_validator_keeps_conflict_in_coverage(testing_session):
    _, _, _, run = seed_run(testing_session)
    plan = planned_detection_batches(testing_session, run)[0]
    ids = list(plan.batch.owned_transition_ids)
    parsed = CompactTransitionClassificationResultV35.model_validate_json(
        batch_payload(ids, conflict_id=ids[1])
    )
    result = validate_candidate_detection_for_review(parsed.decisions, ids)
    covered = {
        item.transition_id
        for item in result.valid_decisions + result.conflicted_decisions
    }
    assert covered == set(ids)
    assert result.conflicted_decisions[0].transition_id == ids[1]


@pytest.mark.asyncio
async def test_completed_checkpoint_skips_provider_call(testing_session):
    _, chapter, _, run = seed_run(testing_session)
    plan = planned_detection_batches(testing_session, run)[0]
    ids = list(plan.batch.owned_transition_ids)
    parsed = CompactTransitionClassificationResultV35.model_validate_json(
        batch_payload(ids)
    )
    validation = validate_candidate_detection_for_review(parsed.decisions, ids)
    upsert_detection_checkpoint(
        testing_session,
        run=run,
        chapter_id=chapter.id,
        planned=plan,
        invocation_id=None,
        validation=validation,
        status="completed",
    )
    provider = FakeProvider()
    assert await _execute(testing_session, ModelGateway([provider]), run) is True
    assert provider.calls == 0


def test_offline_recovery_uses_last_schema_valid_attempt(testing_session):
    _, _, _, run = seed_run(testing_session, count=18)
    plans = planned_detection_batches(testing_session, run)
    assert plans
    last_invocation = None
    for index, plan in enumerate(plans):
        ids = list(plan.batch.owned_transition_ids)
        initial = invocation_for(
            testing_session,
            run,
            payload=batch_payload(ids, conflict_id=ids[0] if index == len(plans) - 1 else None),
            kind="boundary_candidate_detection",
            attempt=1,
            status="failed" if index == len(plans) - 1 else "succeeded",
        )
        last_invocation = initial
        if index == len(plans) - 1:
            last_invocation = invocation_for(
                testing_session,
                run,
                payload=batch_payload(ids, conflict_id=ids[0]),
                kind="business_repair",
                attempt=2,
                status="failed",
            )
    before_invocations = testing_session.scalar(
        select(func.count()).select_from(ModelInvocation)
    )
    report = recover_boundary_detection_from_invocations(
        testing_session, run.id, persist=True
    )
    after_invocations = testing_session.scalar(
        select(func.count()).select_from(ModelInvocation)
    )
    assert report.recovered_batch_count == len(plans)
    assert report.remaining_batch_indices == []
    assert report.semantic_conflict_count == 1
    assert report.recovered[-1]["invocation_id"] == last_invocation.id
    assert before_invocations == after_invocations


def test_clone_checkpoints_records_source_without_rewriting_old_run(testing_session):
    _, chapter, _, source = seed_run(testing_session)
    plan = planned_detection_batches(testing_session, source)[0]
    ids = list(plan.batch.owned_transition_ids)
    parsed = CompactTransitionClassificationResultV35.model_validate_json(
        batch_payload(ids)
    )
    upsert_detection_checkpoint(
        testing_session,
        run=source,
        chapter_id=chapter.id,
        planned=plan,
        invocation_id=None,
        validation=validate_candidate_detection_for_review(parsed.decisions, ids),
        status="completed",
    )
    target = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id=source.subject_id,
        provider=source.provider,
        model=source.model,
        prompt_version="v3.5",
        schema_version="v1",
        input_hash=source.input_hash,
        prompt_hash=source.prompt_hash,
        status="boundary_candidates_running",
        execution_mode="cloud",
        analysis_mode="assisted_boundary_review",
        cloud_consent=True,
        recovered_from_run_id=source.id,
    )
    testing_session.add(target)
    testing_session.commit()
    assert clone_recovered_checkpoints(testing_session, source.id, target) == 1
    assert clone_recovered_checkpoints(testing_session, source.id, target) == 0
    copied = testing_session.scalar(
        select(BoundaryDetectionBatchCheckpoint).where(
            BoundaryDetectionBatchCheckpoint.run_id == target.id
        )
    )
    assert copied.source_run_id == source.id
    assert source.status == "boundary_candidates_running"


def test_accepting_conflict_preserves_manual_source(testing_session):
    _, _, _, run = seed_run(testing_session)
    plan = planned_detection_batches(testing_session, run)[0]
    ids = list(plan.batch.owned_transition_ids)
    parsed = CompactTransitionClassificationResultV35.model_validate_json(
        batch_payload(ids, conflict_id=ids[1])
    )
    upsert_detection_checkpoint(
        testing_session,
        run=run,
        chapter_id=int(run.subject_id),
        planned=plan,
        invocation_id=None,
        validation=validate_candidate_detection_for_review(parsed.decisions, ids),
        status="conflicted_completed",
    )
    from app.services.boundary_review_service import create_review_session

    review = create_review_session(testing_session, run)
    conflict = testing_session.scalar(
        select(BoundaryReviewDecision).where(
            BoundaryReviewDecision.semantic_conflict.is_(True)
        )
    )
    conflict.user_decision = "accept"
    conflict.manual_reason_type = "other_manual_boundary"
    conflict.user_reason = "人工确认叙事单元在此结束"
    revision, _scenes = confirm_review(testing_session, review, "reviewer")
    payload = json.loads(revision.final_boundaries_json)
    assert payload[0]["source"] == "user_accepted_model_conflict"
    assert conflict.manual_reason_type == "other_manual_boundary"


def test_recover_endpoint_requires_consent_and_is_idempotent(
    client, fake_provider, verified_cloud_pricing
):
    from app.db.models import ApplicationSetting, ProviderConfiguration
    from app.db.session import get_session_factory
    from app.main import app
    from app.model_gateway.base import ProviderCapabilities
    from app.services.credentials.service import get_credential_store

    class Store:
        def available(self):
            return True

        def get(self, _):
            return "secret"

        def set(self, *_):
            pass

        def delete(self, *_):
            pass

    factory = app.dependency_overrides[get_session_factory]()
    app.dependency_overrides[get_credential_store] = lambda: Store()
    fake_provider.name = "aliyun_qwen_plus"
    fake_provider.default_model = "configured-plus"
    fake_provider.capabilities = lambda: ProviderCapabilities(
        max_context_tokens=32000,
        default_timeout_seconds=10,
        enabled=True,
        cloud=True,
        supports_boundary_candidates=True,
        requires_boundary_review=True,
        sends_content_to_cloud=True,
    )
    with factory() as session:
        _, chapter, _, source = seed_run(session, count=18)
        source.provider = "aliyun_qwen_plus"
        source.model = "configured-plus"
        source.status = "failed"
        session.add(ApplicationSetting(key="cloud_enabled", value_json="true"))
        session.add(
            ApplicationSetting(
                key="cloud_budget_settings",
                value_json=json.dumps(
                    {
                        "cloud_request_budget_enabled": True,
                        "cloud_daily_request_limit": 500,
                        "cloud_daily_token_limit": 500000,
                        "cloud_daily_estimated_cost_limit": 50,
                    }
                ),
            )
        )
        session.add(
            ProviderConfiguration(
                provider_name="aliyun_qwen_plus",
                enabled=True,
                disconnected=False,
                allow_auto_route=False,
                base_url="https://redacted.invalid/v1",
                credential_reference="keyring:aliyun_qwen_plus",
            )
        )
        plans = planned_detection_batches(session, source)
        for plan in plans[:3]:
            ids = list(plan.batch.owned_transition_ids)
            payload = batch_payload(
                ids, conflict_id=ids[0] if plan.batch_index == 3 else None
            )
            invocation = invocation_for(
                session,
                source,
                payload=payload,
                kind="boundary_candidate_detection",
                attempt=1,
            )
            parsed = CompactTransitionClassificationResultV35.model_validate_json(
                payload
            )
            upsert_detection_checkpoint(
                session,
                run=source,
                chapter_id=chapter.id,
                planned=plan,
                invocation_id=invocation.id,
                validation=validate_candidate_detection_for_review(
                    parsed.decisions, ids
                ),
                status=(
                    "conflicted_completed"
                    if plan.batch_index == 3
                    else "completed"
                ),
            )
        session.commit()
        source_id = source.id

    denied = client.post(
        f"/api/v1/analysis-runs/{source_id}/recover",
        json={
            "client_request_id": "recover-test-001",
            "cloud_consent": False,
            "confirmed": True,
        },
    )
    assert denied.status_code == 422
    assert denied.json()["error_code"] == "CLOUD_CONSENT_REQUIRED"

    preflight = client.post(
        f"/api/v1/analysis-runs/{source_id}/recover/preflight",
        json={"cloud_consent": True},
    )
    assert preflight.status_code == 200, preflight.text
    pre = preflight.json()
    assert pre["provider_name"] == "aliyun_qwen_plus"
    assert pre["eligible"] is True
    assert pre["blockers"] == []
    assert pre["reused_batch_count"] == 3
    assert client.get("/api/v1/analysis-runs").json()  # no new run from preflight
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AnalysisRun)) == 1
        assert session.scalar(select(func.count()).select_from(ModelInvocation)) == 3

    created = client.post(
        f"/api/v1/analysis-runs/{source_id}/recover",
        json={
            "client_request_id": "recover-test-001",
            "cloud_consent": True,
            "confirmed": True,
            "provider_state_version": pre["provider_state_version"],
        },
    )
    assert created.status_code == 202, created.text
    body = created.json()
    assert body["recovered_from_run_id"] == source_id
    assert body["reused_batch_count"] == 3
    assert body["run_id"] > source_id
    assert body["status"] in {"queued", "boundary_candidates_running", "boundary_candidates_partial", "awaiting_boundary_review", "failed", "failed_provider", "failed_structural"}
    assert "remaining_batch_count" in body
    assert body["reservation_id"] is not None

    with factory() as session:
        assert session.get(AnalysisRun, source_id).status == "failed"

    replay = client.post(
        f"/api/v1/analysis-runs/{source_id}/recover",
        json={
            "client_request_id": "recover-test-001",
            "cloud_consent": True,
            "confirmed": True,
            "provider_state_version": pre["provider_state_version"],
        },
    )
    assert replay.status_code == 202
    assert replay.json()["run_id"] == body["run_id"]
    assert replay.json()["idempotent_replay"] is True


def test_manual_eligibility_ignores_business_validation_http_200(
    testing_session, verified_cloud_pricing
):
    """HTTP 200 + BUSINESS_VALIDATION_ERROR must not mark Provider unhealthy."""
    from datetime import datetime, timezone

    from app.db.models import ModelInvocation, ProviderConfiguration, ApplicationSetting
    from app.model_gateway.base import ProviderCapabilities
    from app.services.provider_eligibility import ProviderEligibilityService

    class Store:
        def available(self):
            return True

        def get(self, _):
            return "secret"

        def set(self, *_):
            pass

        def delete(self, *_):
            pass

    book, chapter, _, run = seed_run(testing_session, count=4)
    testing_session.add(ApplicationSetting(key="cloud_enabled", value_json="true"))
    testing_session.add(
        ApplicationSetting(
            key="cloud_budget_settings",
            value_json=json.dumps(
                {
                    "cloud_request_budget_enabled": True,
                    "cloud_daily_request_limit": 500,
                    "cloud_daily_token_limit": 500000,
                    "cloud_daily_estimated_cost_limit": 50,
                }
            ),
        )
    )
    testing_session.add(
        ProviderConfiguration(
            provider_name="aliyun_qwen_plus",
            enabled=True,
            disconnected=False,
            allow_auto_route=False,
            base_url="https://redacted.invalid/v1",
            credential_reference="keyring:aliyun_qwen_plus",
        )
    )
    run.provider = "aliyun_qwen_plus"
    testing_session.add(
        ModelInvocation(
            run_id=run.id,
            task_type="connection_test",
            provider_name="aliyun_qwen_plus",
            model_name="qwen3.7-plus",
            prompt_version="v1",
            schema_version="v1",
            attempt_no=1,
            request_hash="h1",
            input_snapshot_json="{}",
            raw_response_text="",
            status="succeeded",
            latency_ms=1,
            invocation_kind="connection_test",
            http_status_code=200,
            http_request_sent=True,
            created_at=datetime.now(timezone.utc),
        )
    )
    testing_session.add(
        ModelInvocation(
            run_id=run.id,
            task_type="scene_boundary",
            provider_name="aliyun_qwen_plus",
            model_name="qwen3.7-plus",
            prompt_version="v1",
            schema_version="v1",
            attempt_no=1,
            request_hash="h2",
            input_snapshot_json="{}",
            raw_response_text="",
            status="failed",
            latency_ms=1,
            error_code="BUSINESS_VALIDATION_ERROR",
            invocation_kind="boundary_candidate_detection",
            http_status_code=200,
            http_request_sent=True,
            created_at=datetime.now(timezone.utc),
        )
    )
    testing_session.commit()
    caps = ProviderCapabilities(
        max_context_tokens=32000,
        default_timeout_seconds=10,
        enabled=False,  # registry default must not block cloud recovery
        cloud=True,
        supports_boundary_candidates=True,
        requires_boundary_review=True,
        automatic_boundary_routing=False,
    )
    result = ProviderEligibilityService.evaluate_manual_boundary_candidate(
        testing_session,
        provider_name="aliyun_qwen_plus",
        capabilities=caps,
        store=Store(),
        pricing_path=Path("config/cloud_pricing.json"),
    )
    assert result["manual_boundary_candidate_eligible"] is True
    assert result["manual_selection_blockers"] == []
    assert result["health_state"] == "healthy"
    assert result["allow_auto_route"] is False
    # Ignore unused locals for seed shape.
    assert book.id and chapter.id


@pytest.mark.asyncio
async def test_provider_failure_after_checkpoint_marks_partial(testing_session):
    _, _, _, run = seed_run(testing_session, count=18)
    plans = planned_detection_batches(testing_session, run)
    assert len(plans) > 1
    first_ids = list(plans[0].batch.owned_transition_ids)
    failure = ProviderRequestError(
        "连接Provider超时",
        error_code="PROVIDER_CONNECT_TIMEOUT",
        retryable=True,
        transport_kind="connect_timeout",
    )
    provider = FakeProvider([batch_payload(first_ids), failure, failure, failure, failure, failure])
    factory = sessionmaker(
        bind=testing_session.bind, autoflush=False, expire_on_commit=False
    )
    await execute_scene_pipeline(factory, ModelGateway([provider]), run.id)
    testing_session.expire_all()
    refreshed = testing_session.get(AnalysisRun, run.id)
    assert refreshed.status == "boundary_candidates_partial"
    assert refreshed.failed_stage == "provider_request"
    assert testing_session.scalar(
        select(func.count())
        .select_from(BoundaryDetectionBatchCheckpoint)
        .where(
            BoundaryDetectionBatchCheckpoint.run_id == run.id,
            BoundaryDetectionBatchCheckpoint.status == "completed",
        )
    ) == 1
