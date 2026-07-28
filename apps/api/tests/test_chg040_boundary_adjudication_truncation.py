"""CHG-20260728-040: scene boundary output budget + batching + truncation retry."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.db.models import AnalysisRun, ModelInvocation
from app.model_gateway.base import ModelResponse
from app.model_gateway.gateway import ModelGateway
from app.schemas.scene import (
    BoundaryCandidateAdjudicationResult,
    BoundaryCandidateVerdict,
)
from app.services.prompt_service import load_prompt
from app.services.scene_boundary_adjudication_batching import (
    MAX_TARGET_CANDIDATES_PER_BATCH,
    merge_adjudication_batches,
    plan_output_bounded_adjudication_batches,
    validate_batch_coverage,
)
from app.services.scene_boundary_output_budget import (
    SceneBoundaryOutputBudgetTooLow,
    compute_scene_boundary_output_budget_v1,
    compute_truncation_retry_limit,
    round_up_to_256,
)
from app.services.scene_transitions import AdjacentTransition
from app.services.structured_output import generate_validated
from app.services.validation_errors import StructuralValidationError
from tests.test_model_gateway import make_run
from tests.test_phase_2b1 import CloudFake


def test_round_up_to_256():
    assert round_up_to_256(1) == 256
    assert round_up_to_256(256) == 256
    assert round_up_to_256(257) == 512
    assert round_up_to_256(1152) == 1280


@pytest.mark.parametrize(
    "count,expected",
    [
        (1, 1024),
        (5, 1280),
        (10, 1792),
    ],
)
def test_initial_budget_examples(count, expected):
    budget = compute_scene_boundary_output_budget_v1(
        target_candidate_count=count,
        user_output_hard_cap=4000,
    )
    assert budget.initial_output_limit == expected
    assert budget.initial_output_limit != 768
    assert budget.initial_output_limit <= 4000


def test_budget_respects_user_hard_cap_trim():
    budget = compute_scene_boundary_output_budget_v1(
        target_candidate_count=10,
        user_output_hard_cap=1500,
    )
    assert budget.initial_output_limit == 1500


def test_budget_respects_provider_and_model_caps():
    budget = compute_scene_boundary_output_budget_v1(
        target_candidate_count=10,
        user_output_hard_cap=4000,
        model_output_cap=1600,
        provider_output_cap=2000,
    )
    assert budget.effective_hard_cap == 1600
    assert budget.initial_output_limit == 1600


def test_budget_too_low_blocks():
    with pytest.raises(SceneBoundaryOutputBudgetTooLow) as exc:
        compute_scene_boundary_output_budget_v1(
            target_candidate_count=5,
            user_output_hard_cap=768,
        )
    assert exc.value.error_code == "SCENE_BOUNDARY_OUTPUT_BUDGET_TOO_LOW"


def test_truncation_retry_limits_strictly_increase():
    hard = 4000
    first = 1792
    second = compute_truncation_retry_limit(
        previous_limit=first, effective_hard_cap=hard, attempt_no=2
    )
    assert second is not None and second > first
    third = compute_truncation_retry_limit(
        previous_limit=second, effective_hard_cap=hard, attempt_no=3
    )
    assert third == hard
    assert third > second
    assert (
        compute_truncation_retry_limit(
            previous_limit=hard, effective_hard_cap=hard, attempt_no=3
        )
        is None
    )


def test_truncation_retry_at_1024_hard_cap_stops():
    assert (
        compute_truncation_retry_limit(
            previous_limit=1024, effective_hard_cap=1024, attempt_no=2
        )
        is None
    )


def _transitions(n: int) -> tuple[list[AdjacentTransition], dict[str, str], list[str]]:
    items: list[AdjacentTransition] = []
    texts: dict[str, str] = {}
    ids: list[str] = []
    for i in range(1, n + 1):
        left = f"P{i:04d}"
        right = f"P{i + 1:04d}"
        tid = f"T{i:04d}"
        texts[left] = f"left-{i}-" + ("字" * 20)
        texts[right] = f"right-{i}-" + ("字" * 20)
        items.append(AdjacentTransition(tid, left, right))
        ids.append(tid)
    return items, texts, ids


@pytest.mark.parametrize("n,batches", [(0, 0), (1, 1), (10, 1), (11, 2), (20, 2), (25, 3)])
def test_output_batching_sizes(n, batches):
    items, texts, ids = _transitions(max(n, 1))
    planned = plan_output_bounded_adjudication_batches(ids[:n], items, texts, run_id=3)
    assert len(planned) == batches
    assert MAX_TARGET_CANDIDATES_PER_BATCH == 10
    flat = [tid for b in planned for tid in b.target_candidate_ids]
    assert flat == ids[:n]
    for b in planned:
        assert len(b.target_candidate_ids) <= 10
        for cid in b.context_only_candidate_ids:
            assert cid not in b.target_candidate_ids


def test_batching_context_neighbors_and_stable_order():
    items, texts, ids = _transitions(20)
    planned = plan_output_bounded_adjudication_batches(ids, items, texts, run_id=9)
    assert len(planned) == 2
    assert list(planned[0].target_candidate_ids) == ids[:10]
    assert list(planned[1].target_candidate_ids) == ids[10:]
    assert planned[1].context_only_candidate_ids[0] == ids[9]
    assert planned[0].batch_key != planned[1].batch_key
    assert planned[0].content_key != planned[1].content_key


def _verdict(tid: str, accept: bool = False) -> BoundaryCandidateVerdict:
    if accept:
        return BoundaryCandidateVerdict(
            transition_id=tid,
            accept=True,
            scope_relation="primary_scene_change",
            continuity_relation="new_scene_chain",
            confidence=0.9,
        )
    return BoundaryCandidateVerdict(
        transition_id=tid,
        accept=False,
        scope_relation="local_subgoal_change",
        continuity_relation="same_scene_chain",
        confidence=0.8,
    )


def test_batch_coverage_and_merge():
    targets = ["T1", "T2"]
    ok = BoundaryCandidateAdjudicationResult(
        contract_version="1.0",
        verdicts=[_verdict("T1"), _verdict("T2")],
    )
    validate_batch_coverage(ok, target_candidate_ids=targets)
    leaked = BoundaryCandidateAdjudicationResult(
        contract_version="1.0",
        verdicts=[_verdict("T1"), _verdict("CTX")],
    )
    with pytest.raises(StructuralValidationError):
        validate_batch_coverage(
            leaked,
            target_candidate_ids=targets,
            context_only_candidate_ids=["CTX"],
        )
    merged = merge_adjudication_batches(
        original_candidate_order=["T1", "T2", "T3", "T4"],
        batch_results=[
            (
                ["T3", "T4"],
                BoundaryCandidateAdjudicationResult(
                    contract_version="1.0",
                    verdicts=[_verdict("T3"), _verdict("T4")],
                ),
            ),
            (["T1", "T2"], ok),
        ],
    )
    assert [v.transition_id for v in merged.verdicts] == ["T1", "T2", "T3", "T4"]


@pytest.mark.asyncio
async def test_adaptive_truncation_increases_limit(testing_session):
    run = make_run(testing_session)
    run.provider = "aliyun_qwen_plus"
    run.model = "qwen3.7-plus"
    testing_session.commit()

    class CountingTruncationFake(CloudFake):
        def __init__(self) -> None:
            super().__init__([])
            self.limits: list[int] = []

        async def generate(self, request):
            self.calls += 1
            self.requests.append(request)
            limit = int(request.max_output_tokens or 0)
            self.limits.append(limit)
            if self.calls == 1:
                return ModelResponse(
                    text='{"contract_version":"1.0","verdicts":[',
                    model=self.default_model,
                    http_status_code=200,
                    input_tokens=100,
                    output_tokens=limit,
                    total_tokens=100 + limit,
                    finish_reason="length",
                    request_id=f"fake-{self.calls}",
                )
            body = {
                "contract_version": "1.0",
                "verdicts": [
                    {
                        "transition_id": "T0001",
                        "accept": False,
                        "scope_relation": "local_subgoal_change",
                        "continuity_relation": "same_scene_chain",
                        "confidence": 0.7,
                    },
                    {
                        "transition_id": "T0002",
                        "accept": False,
                        "scope_relation": "local_subgoal_change",
                        "continuity_relation": "same_scene_chain",
                        "confidence": 0.7,
                    },
                ],
            }
            return ModelResponse(
                text=json.dumps(body, ensure_ascii=False),
                model=self.default_model,
                http_status_code=200,
                input_tokens=120,
                output_tokens=200,
                total_tokens=320,
                finish_reason="stop",
                request_id=f"fake-{self.calls}",
            )

    fake = CountingTruncationFake()
    prompt = load_prompt("scene_boundary_adjudication", "v1.1.2")
    snapshot = {
        "target_candidate_ids": ["T0001", "T0002"],
        "context_only_candidate_ids": [],
        "candidates": [],
        "paragraphs": [],
    }
    result = await generate_validated(
        session=testing_session,
        gateway=ModelGateway([fake]),
        run_id=run.id,
        provider_name=fake.name,
        task_type="scene_boundary_adjudication",
        prompt=prompt,
        schema=BoundaryCandidateAdjudicationResult,
        input_snapshot=snapshot,
        user_content=prompt.user_template.format(input_json=json.dumps(snapshot)),
        business_validator=lambda value: validate_batch_coverage(
            value, target_candidate_ids=["T0001", "T0002"]
        ),
        initial_invocation_kind="boundary_candidate_adjudication",
        output_tokens_override=1792,
        adaptive_truncation_budget=True,
        truncation_hard_cap=4000,
    )
    assert len(result.verdicts) == 2
    assert fake.calls == 2
    assert fake.limits[0] == 1792
    assert fake.limits[1] > 1792
    assert fake.limits[1] != fake.limits[0]
    rows = list(
        testing_session.scalars(
            select(ModelInvocation)
            .where(ModelInvocation.run_id == run.id)
            .order_by(ModelInvocation.id)
        )
    )
    assert len(rows) == 2
    assert rows[0].finish_reason == "length"
    assert rows[0].requested_output_tokens == 1792
    assert rows[1].requested_output_tokens == fake.limits[1]
    assert rows[1].requested_output_tokens > rows[0].requested_output_tokens


@pytest.mark.asyncio
async def test_hard_cap_truncation_does_not_repeat_same_limit(testing_session):
    run = make_run(testing_session)
    run.provider = "aliyun_qwen_plus"
    testing_session.commit()

    class CapFake(CloudFake):
        def __init__(self) -> None:
            super().__init__([])
            self.limits: list[int] = []

        async def generate(self, request):
            self.calls += 1
            self.requests.append(request)
            limit = int(request.max_output_tokens or 0)
            self.limits.append(limit)
            return ModelResponse(
                text='{"contract_version":"1.0","verdicts":[',
                model=self.default_model,
                http_status_code=200,
                input_tokens=50,
                output_tokens=limit,
                total_tokens=50 + limit,
                finish_reason="length",
            )

    fake = CapFake()
    prompt = load_prompt("scene_boundary_adjudication", "v1.1.2")
    snapshot = {"target_candidate_ids": ["T0001"], "context_only_candidate_ids": []}
    with pytest.raises(Exception) as exc:
        await generate_validated(
            session=testing_session,
            gateway=ModelGateway([fake]),
            run_id=run.id,
            provider_name=fake.name,
            task_type="scene_boundary_adjudication",
            prompt=prompt,
            schema=BoundaryCandidateAdjudicationResult,
            input_snapshot=snapshot,
            user_content="fixture",
            business_validator=lambda _: None,
            initial_invocation_kind="boundary_candidate_adjudication",
            output_tokens_override=1024,
            adaptive_truncation_budget=True,
            truncation_hard_cap=1024,
        )
    assert "SCENE_BOUNDARY_OUTPUT_TRUNCATED_AT_HARD_CAP" in str(exc.value.error_code)
    assert fake.calls == 1
    assert fake.limits == [1024]


def test_batch_coverage_missing_and_unknown():
    targets = ["T1", "T2"]
    missing = BoundaryCandidateAdjudicationResult(
        contract_version="1.0",
        verdicts=[_verdict("T1")],
    )
    with pytest.raises(StructuralValidationError) as exc:
        validate_batch_coverage(missing, target_candidate_ids=targets)
    assert exc.value.error_code == "SCENE_BOUNDARY_BATCH_COVERAGE_INVALID"
    unknown = BoundaryCandidateAdjudicationResult(
        contract_version="1.0",
        verdicts=[_verdict("T1"), _verdict("TX")],
    )
    with pytest.raises(StructuralValidationError):
        validate_batch_coverage(
            unknown,
            target_candidate_ids=targets,
            known_candidate_ids={"T1", "T2"},
        )


def test_checkpoint_reuse_by_content_key(testing_session):
    from app.services.boundary_adjudication_checkpoints import (
        load_reusable_adjudication_batches,
        save_adjudication_batch_checkpoint,
        save_adjudication_plan,
    )

    source = make_run(testing_session)
    items, texts, ids = _transitions(20)
    planned = plan_output_bounded_adjudication_batches(ids, items, texts, run_id=source.id)
    save_adjudication_plan(
        testing_session,
        run=source,
        candidate_ids=ids,
        batch_total=len(planned),
        prompt_version="v1.1.2",
    )
    batch0 = planned[0]
    result = BoundaryCandidateAdjudicationResult(
        contract_version="1.0",
        verdicts=[_verdict(tid) for tid in batch0.target_candidate_ids],
    )
    save_adjudication_batch_checkpoint(
        testing_session,
        run=source,
        batch_key=batch0.batch_key,
        content_key=batch0.content_key,
        batch_index=batch0.batch_index,
        target_candidate_ids=list(batch0.target_candidate_ids),
        result=result,
        prompt_version="v1.1.2",
    )
    testing_session.commit()

    retry = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id="1",
        provider="fake",
        model="fake",
        prompt_version="v3.5",
        schema_version="v1",
        prompt_hash="x",
        input_hash="x",
        status="running",
        retry_of_run_id=source.id,
    )
    testing_session.add(retry)
    testing_session.commit()
    reusable = load_reusable_adjudication_batches(testing_session, run=retry)
    assert batch0.content_key in reusable
    assert reusable[batch0.content_key]["status"] == "completed"
    assert "raw_response" not in reusable[batch0.content_key]
    # Hash change: different paragraph text => different content_key
    texts2 = {k: v + "-changed" for k, v in texts.items()}
    planned2 = plan_output_bounded_adjudication_batches(
        ids, items, texts2, run_id=retry.id
    )
    assert planned2[0].content_key not in reusable


@pytest.mark.asyncio
async def test_non_length_json_error_does_not_raise_output_limit(testing_session):
    run = make_run(testing_session)
    run.provider = "aliyun_qwen_plus"
    testing_session.commit()

    class BadJsonFake(CloudFake):
        def __init__(self) -> None:
            super().__init__([])
            self.limits: list[int] = []

        async def generate(self, request):
            self.calls += 1
            self.requests.append(request)
            self.limits.append(int(request.max_output_tokens or 0))
            return ModelResponse(
                text="not-json-at-all",
                model=self.default_model,
                http_status_code=200,
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
                finish_reason="stop",
            )

    fake = BadJsonFake()
    prompt = load_prompt("scene_boundary_adjudication", "v1.1.2")
    with pytest.raises(Exception):
        await generate_validated(
            session=testing_session,
            gateway=ModelGateway([fake]),
            run_id=run.id,
            provider_name=fake.name,
            task_type="scene_boundary_adjudication",
            prompt=prompt,
            schema=BoundaryCandidateAdjudicationResult,
            input_snapshot={"target_candidate_ids": ["T0001"]},
            user_content="fixture",
            business_validator=lambda _: None,
            initial_invocation_kind="boundary_candidate_adjudication",
            output_tokens_override=1792,
            adaptive_truncation_budget=True,
            truncation_hard_cap=4000,
        )
    # Non-length JSON failures must not bump the adaptive output limit.
    assert fake.limits
    assert all(limit == 1792 for limit in fake.limits)
