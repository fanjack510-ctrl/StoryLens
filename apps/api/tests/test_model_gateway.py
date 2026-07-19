import json

import pytest
from sqlalchemy import select

from app.db.models import AnalysisRun, ModelInvocation
from app.model_gateway.gateway import ModelGateway, ProviderNotFoundError
from app.schemas.scene import SceneBoundaryResult
from app.services.prompt_service import load_prompt
from app.services.structured_output import (
    StructuredOutputError,
    extract_json_object,
    generate_validated,
)
from tests.fakes import FakeProvider


def make_run(session) -> AnalysisRun:
    run = AnalysisRun(
        task_type="scene_pipeline",
        subject_type="chapter",
        subject_id="1",
        provider="fake",
        model="fake",
        prompt_version="v1",
        schema_version="v1",
        prompt_hash="x",
        input_hash="x",
        status="running",
    )
    session.add(run)
    session.commit()
    return run


def test_provider_registry_and_capabilities(fake_provider: FakeProvider) -> None:
    gateway = ModelGateway([fake_provider])
    assert gateway.get("fake").capabilities().max_context_tokens == 32000
    with pytest.raises(ProviderNotFoundError):
        gateway.get("missing")


@pytest.mark.asyncio
async def test_provider_health_success_and_failure() -> None:
    assert (await FakeProvider(healthy=True).health()).status == "healthy"
    assert (await FakeProvider(healthy=False).health()).status == "unhealthy"


def test_extract_json_from_code_fence() -> None:
    value = extract_json_object('prefix ```json\n{"ok":{"value":1}}\n``` suffix')
    assert json.loads(value) == {"ok": {"value": 1}}


@pytest.mark.asyncio
async def test_json_repair_success(testing_session) -> None:
    valid = '{"chapter_id":"B0001-C0001","boundaries":[],"overall_confidence":1}'
    provider = FakeProvider(["not json", valid])
    run = make_run(testing_session)
    result = await generate_validated(
        session=testing_session,
        gateway=ModelGateway([provider]),
        run_id=run.id,
        provider_name="fake",
        task_type="scene_boundary",
        prompt=load_prompt("scene_boundary"),
        schema=SceneBoundaryResult,
        input_snapshot={},
        user_content="input",
        business_validator=lambda _: None,
    )
    assert result.chapter_id == "B0001-C0001"
    assert len(list(testing_session.scalars(select(ModelInvocation)))) == 2


@pytest.mark.asyncio
async def test_pydantic_validation_failure_enters_repair(testing_session) -> None:
    invalid_schema = '{"chapter_id":"B0001-C0001","boundaries":[],"overall_confidence":2}'
    valid = '{"chapter_id":"B0001-C0001","boundaries":[],"overall_confidence":1}'
    provider = FakeProvider([invalid_schema, valid])
    run = make_run(testing_session)
    result = await generate_validated(
        session=testing_session,
        gateway=ModelGateway([provider]),
        run_id=run.id,
        provider_name="fake",
        task_type="scene_boundary",
        prompt=load_prompt("scene_boundary"),
        schema=SceneBoundaryResult,
        input_snapshot={},
        user_content="input",
        business_validator=lambda _: None,
    )
    assert result.overall_confidence == 1
    invocations = list(
        testing_session.scalars(select(ModelInvocation).order_by(ModelInvocation.id))
    )
    assert invocations[0].error_code == "SCHEMA_VALIDATION_FAILED"
    assert invocations[1].status == "succeeded"


@pytest.mark.asyncio
async def test_json_repair_final_failure(testing_session) -> None:
    provider = FakeProvider(["bad", "bad", "bad"])
    run = make_run(testing_session)
    with pytest.raises(StructuredOutputError):
        await generate_validated(
            session=testing_session,
            gateway=ModelGateway([provider]),
            run_id=run.id,
            provider_name="fake",
            task_type="scene_boundary",
            prompt=load_prompt("scene_boundary"),
            schema=SceneBoundaryResult,
            input_snapshot={},
            user_content="input",
            business_validator=lambda _: None,
        )
    assert len(list(testing_session.scalars(select(ModelInvocation)))) == 3
