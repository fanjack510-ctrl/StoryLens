import json

import pytest
from sqlalchemy import func, select

from app.db.models import AnalysisRun, ApplicationSetting, Book, ModelInvocation
from app.model_gateway.base import ModelResponse
from app.model_gateway.gateway import ModelGateway
from app.schemas.scene import SceneBoundaryResult
from app.services.cloud_output_policy import CloudOutputLimitTooLow, resolve_output_limit
from app.services.fixture_service import get_or_create_fixture_book
from app.services.prompt_service import load_prompt
from app.services.structured_output import generate_validated
from tests.test_model_gateway import make_run
from tests.test_phase_2b1 import CloudFake, boundary_json


def test_cloud_task_output_policy_and_hard_limit(testing_session):
    boundary = resolve_output_limit(
        testing_session, task_type="scene_boundary", invocation_kind="initial", cloud=True
    )
    analysis = resolve_output_limit(
        testing_session, task_type="scene_analysis", invocation_kind="initial", cloud=True
    )
    assert (boundary.effective_limit, analysis.effective_limit) == (768, 1600)
    assert boundary.user_hard_limit == 4000
    testing_session.add(
        ApplicationSetting(
            key="cloud_budget_settings",
            value_json=json.dumps({"cloud_max_output_tokens_per_request": 500}),
        )
    )
    testing_session.commit()
    with pytest.raises(CloudOutputLimitTooLow, match="CLOUD_OUTPUT_LIMIT_TOO_LOW"):
        resolve_output_limit(
            testing_session,
            task_type="scene_boundary",
            invocation_kind="initial",
            cloud=True,
        )


@pytest.mark.asyncio
async def test_truncated_output_retries_same_plus_with_full_limit(testing_session):
    run = make_run(testing_session)

    class TruncatingPlus(CloudFake):
        async def generate(self, request):
            self.calls += 1
            self.requests.append(request)
            if self.calls == 1:
                return ModelResponse(
                    text='{"chapter_id":"B0001',
                    model=self.default_model,
                    http_status_code=200,
                    finish_reason="length",
                    output_tokens=128,
                )
            return ModelResponse(
                text=boundary_json(),
                model=self.default_model,
                http_status_code=200,
                finish_reason="stop",
            )

    plus = TruncatingPlus()
    result = await generate_validated(
        session=testing_session,
        gateway=ModelGateway([plus]),
        run_id=run.id,
        provider_name=plus.name,
        task_type="scene_boundary",
        prompt=load_prompt("scene_boundary", "v3.1"),
        schema=SceneBoundaryResult,
        input_snapshot={},
        user_content="fixture",
        business_validator=lambda _: None,
    )
    rows = list(
        testing_session.scalars(
            select(ModelInvocation).where(ModelInvocation.run_id == run.id).order_by(ModelInvocation.id)
        )
    )
    assert result.boundaries == []
    assert plus.calls == 2
    assert [row.invocation_kind for row in rows] == ["initial", "truncation_retry"]
    assert rows[0].error_code == "OUTPUT_TRUNCATED"
    assert all(request.max_output_tokens == 768 for request in plus.requests)
    assert all(row.requested_output_tokens == 768 for row in rows)


@pytest.mark.asyncio
async def test_missing_field_is_schema_failure_not_key_error(testing_session):
    run = make_run(testing_session)
    run.provider = "aliyun_qwen_plus"
    run.model = "qwen3.7-plus"
    testing_session.commit()

    # DEFECT-015: schema_repair stays on authorized Plus (no Flash switch).
    plus = CloudFake([json.dumps({"boundaries": []}), boundary_json()])
    plus.name = "aliyun_qwen_plus"
    plus.default_model = "qwen3.7-plus"
    result = await generate_validated(
        session=testing_session,
        gateway=ModelGateway([plus]),
        run_id=run.id,
        provider_name=plus.name,
        task_type="scene_boundary",
        prompt=load_prompt("scene_boundary", "v3.1"),
        schema=SceneBoundaryResult,
        input_snapshot={},
        user_content="fixture with {literal_json_braces}",
        business_validator=lambda _: None,
    )
    rows = list(
        testing_session.scalars(
            select(ModelInvocation).where(ModelInvocation.run_id == run.id).order_by(ModelInvocation.id)
        )
    )
    assert result.boundaries == []
    assert rows[0].error_code == "SCHEMA_VALIDATION_FAILED"
    assert rows[1].invocation_kind == "schema_repair"
    assert rows[1].provider_name == "aliyun_qwen_plus"
    assert rows[1].model_name == "qwen3.7-plus"


@pytest.mark.asyncio
async def test_pre_send_failure_is_not_counted_as_http_request(testing_session):
    run = make_run(testing_session)

    class PreSendFailure(CloudFake):
        async def generate(self, request):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("database is locked")
            return ModelResponse(text=boundary_json(), model=self.default_model, http_status_code=200)

    provider = PreSendFailure()
    result = await generate_validated(
        session=testing_session,
        gateway=ModelGateway([provider]),
        run_id=run.id,
        provider_name=provider.name,
        task_type="scene_boundary",
        prompt=load_prompt("scene_boundary", "v3.1"),
        schema=SceneBoundaryResult,
        input_snapshot={},
        user_content="fixture",
        business_validator=lambda _: None,
    )
    rows = list(
        testing_session.scalars(
            select(ModelInvocation).where(ModelInvocation.run_id == run.id).order_by(ModelInvocation.id)
        )
    )
    assert result.boundaries == []
    assert [row.http_request_sent for row in rows] == [False, True]
    assert rows[0].audit_type == "pre_send_failure" and rows[0].sent_at is None


def test_fixture_book_is_idempotent_and_versioned(testing_session):
    args = dict(
        fixture_name="original_story",
        fixture_version="1",
        title="原创短篇",
        paragraphs=["第一段", "第二段"],
        source_file_name="original.txt",
    )
    first, created = get_or_create_fixture_book(testing_session, **args)
    testing_session.commit()
    second, created_again = get_or_create_fixture_book(testing_session, **args)
    assert created and not created_again and first.id == second.id
    newer, newer_created = get_or_create_fixture_book(
        testing_session, **{**args, "fixture_version": "2"}
    )
    testing_session.commit()
    assert newer_created and newer.id != first.id
    assert testing_session.scalar(select(func.count()).select_from(Book)) == 2
    for suffix in ("a", "b"):
        testing_session.add(
            AnalysisRun(
                task_type="scene_pipeline",
                subject_type="chapter",
                subject_id=str(first.chapters[0].id),
                provider="fake",
                model="fake",
                prompt_version="v3.1",
                schema_version="v1",
                input_hash=suffix * 64,
                status="queued",
            )
        )
    testing_session.commit()
    assert testing_session.scalar(select(func.count()).select_from(AnalysisRun)) == 2


def test_v31_prompts_use_same_contract_and_scene_analysis_budget(testing_session):
    prompt = load_prompt("scene_boundary", "v3.1")
    assert "previous_primary_goal" in prompt.system
    assert "prompt" not in prompt.version.lower()
    decision = resolve_output_limit(
        testing_session, task_type="scene_analysis", invocation_kind="initial", cloud=True
    )
    assert decision.effective_limit == 1600
