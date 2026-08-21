import json

import pytest
from sqlalchemy import func, select

from app.db.models import ModelInvocation, RequestGateDecision
from app.model_gateway.base import ProviderCapabilities
from app.model_gateway.gateway import ModelGateway
from app.schemas.scene import SceneAnalysisResult, SceneBoundaryResult
from app.services.budget_reservation import (
    InsufficientBudgetReservation,
    release_reservation,
    reserve_budget,
)
from app.services.cloud_budget import RequestBlockedError
from app.services.prompt_service import load_prompt, with_response_contract
from app.services.response_contract import contract_hash, example_skeleton
from app.services.structured_output import generate_validated
from tests.fakes import FakeProvider
from tests.test_model_gateway import make_run


class CloudFake(FakeProvider):
    name = "aliyun_qwen_plus"
    default_model = "configured-plus"

    def capabilities(self):
        return ProviderCapabilities(
            max_context_tokens=100000,
            default_timeout_seconds=30,
            cloud=True,
            provider_family="aliyun_qwen",
            sends_content_to_cloud=True,
            region="cn-beijing",
            structured_output_mode="json_object",
            supports_json_object=True,
        )


def boundary_json():
    return json.dumps({"chapter_id": "B0001-C0001", "boundaries": [], "overall_confidence": 1})


def analysis_json():
    def field(summary, ids):
        return {"summary": summary, "evidence_paragraph_ids": ids}
    return json.dumps(
        {
            "scene_id": "B0001-C0001-S0001",
            "entry_state": field("进入", ["B0001-C0001-P0001"]),
            "goal": field("寻找", ["B0001-C0001-P0001"]),
            "obstacle": field("阻碍", ["B0001-C0001-P0002"]),
            "key_actions": [field("行动", ["B0001-C0001-P0002"])],
            "turning_point": field("", []),
            "outcome": field("完成", ["B0001-C0001-P0002"]),
            "unresolved_question": field("", []),
            "function_tags": ["事件推进"],
            "confidence": 0.9,
        },
        ensure_ascii=False,
    )


def test_v3_contract_and_prompt_share_pydantic_schema():
    prompt = with_response_contract(load_prompt("scene_boundary", "v3"), SceneBoundaryResult)
    assert "chapter_id" in prompt.system and "after_paragraph_id" in prompt.system
    assert contract_hash(SceneBoundaryResult)
    assert set(example_skeleton(SceneBoundaryResult)) == {
        "chapter_id",
        "boundaries",
        "overall_confidence",
    }


@pytest.mark.asyncio
async def test_valid_first_response_does_not_call_flash(testing_session):
    run = make_run(testing_session)
    plus = CloudFake([boundary_json()])
    result = await generate_validated(
        session=testing_session,
        gateway=ModelGateway([plus]),
        run_id=run.id,
        provider_name=plus.name,
        task_type="scene_boundary",
        prompt=load_prompt("scene_boundary", "v3"),
        schema=SceneBoundaryResult,
        input_snapshot={},
        user_content="original fixture",
        business_validator=lambda _: None,
    )
    assert result.boundaries == [] and plus.calls == 1


@pytest.mark.asyncio
async def test_scene_analysis_first_response_matches_contract(testing_session):
    run = make_run(testing_session)
    plus = CloudFake([analysis_json()])
    result = await generate_validated(
        session=testing_session,
        gateway=ModelGateway([plus]),
        run_id=run.id,
        provider_name=plus.name,
        task_type="scene_analysis",
        prompt=load_prompt("scene_analysis", "v3"),
        schema=SceneAnalysisResult,
        input_snapshot={},
        user_content="original fixture",
        business_validator=lambda _: None,
    )
    assert result.key_actions and plus.calls == 1


@pytest.mark.asyncio
async def test_blocked_before_send_creates_no_invocation(testing_session):
    class Blocked(CloudFake):
        async def generate(self, request):
            raise RequestBlockedError("CLOUD_BUDGET_EXCEEDED")

    run = make_run(testing_session)
    with pytest.raises(RequestBlockedError):
        await generate_validated(
            session=testing_session,
            gateway=ModelGateway([Blocked()]),
            run_id=run.id,
            provider_name="aliyun_qwen_plus",
            task_type="scene_boundary",
            prompt=load_prompt("scene_boundary", "v3"),
            schema=SceneBoundaryResult,
            input_snapshot={},
            user_content="x",
            business_validator=lambda _: None,
        )
    assert testing_session.scalar(select(func.count()).select_from(ModelInvocation)) == 0


def test_reservation_rejects_before_work_and_records_gate(testing_session):
    """钱不够就在动手之前拒绝，并记下这次拦截。

    原先这条用请求数触发（要 4 次、剩 2 次）。请求数已不再是闸门——它和 Token 量的是同一
    件事的另外两种单位——所以改用费用触发。要守的规矩没变：不能先干活再发现超预算。
    """
    with pytest.raises(InsufficientBudgetReservation):
        reserve_budget(
            testing_session,
            run_id=None,
            stage="boundary_review_generation",
            required_requests=4,
            required_tokens=100,
            required_cost=2.0,
            remaining_requests=2,
            remaining_tokens=1000,
            remaining_cost=1,
        )
    assert testing_session.scalar(select(func.count()).select_from(RequestGateDecision)) == 1


def test_reservation_release(testing_session):
    reservation = reserve_budget(
        testing_session,
        run_id=None,
        stage="boundary_review_generation",
        required_requests=2,
        required_tokens=100,
        required_cost=0.01,
        remaining_requests=10,
        remaining_tokens=1000,
        remaining_cost=1,
    )
    release_reservation(testing_session, reservation.id)
    assert reservation.status == "released"
