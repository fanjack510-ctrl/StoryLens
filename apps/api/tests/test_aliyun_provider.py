from fastapi.testclient import TestClient
from sqlalchemy import select

import pytest

from app.core.config import Settings
from app.db.models import ModelInvocation
from app.model_gateway.base import ProviderCapabilities
from app.model_gateway.gateway import ModelGateway
from app.model_gateway.providers.openai_compatible import OpenAICompatibleProvider
from app.schemas.scene import SceneBoundaryResult
from app.services.prompt_service import load_prompt
from app.services.structured_output import generate_validated
from tests.fakes import FakeProvider
from tests.test_scene_pipeline import import_chapter


class CloudFake(FakeProvider):
    def __init__(self, name: str, responses=None, manual_only: bool = False):
        super().__init__(responses=responses)
        self.name = name
        self.default_model = name
        self._manual_only = manual_only

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            max_context_tokens=32768,
            default_timeout_seconds=300,
            enabled=True,
            profile_name=self.name,
            manual_only=self._manual_only,
            structured_output_mode="json_object",
            supports_json_object=True,
            supports_thinking_control=True,
            cloud=True,
            provider_family="aliyun_qwen",
            sends_content_to_cloud=True,
            region="cn-beijing",
        )


def test_aliyun_settings_and_roles() -> None:
    settings = Settings(_env_file=None)
    assert settings.aliyun_enabled is False
    assert settings.aliyun_plus_model == "qwen3.7-plus"
    assert settings.aliyun_max_model == "qwen3.7-max"
    assert settings.aliyun_flash_model == "qwen3.6-flash"
    provider = OpenAICompatibleProvider(
        name="aliyun_qwen_plus",
        base_url="https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        api_key="secret",
        default_model="qwen3.7-plus",
        timeout_seconds=300,
        max_context_tokens=32768,
        cloud=True,
        supports_json_object=True,
        sends_content_to_cloud=True,
        region="cn-beijing",
    )
    capabilities = provider.capabilities()
    assert capabilities.cloud and capabilities.sends_content_to_cloud
    assert capabilities.region == "cn-beijing"


def test_cloud_consent_required(client: TestClient) -> None:
    chapter_id = import_chapter(client)
    from app.main import app
    from app.model_gateway.registry import get_model_gateway

    cloud = CloudFake("aliyun_qwen_plus")
    app.dependency_overrides[get_model_gateway] = lambda: ModelGateway([cloud])
    denied = client.post(
        f"/api/v1/chapters/{chapter_id}/analysis-runs",
        json={"provider_name": cloud.name, "execution_mode": "cloud", "cloud_consent": False},
    )
    assert denied.status_code == 422
    assert denied.json()["error_code"] == "CLOUD_CONSENT_REQUIRED"


@pytest.mark.asyncio
async def test_json_repair_inherits_run_provider_and_cloud_audit_is_redacted(
    testing_session,
) -> None:
    """DEFECT-015: JSON repair stays on authorized Plus; no Flash fallback."""
    from tests.test_model_gateway import make_run

    valid = '{"chapter_id":"B0001-C0001","boundaries":[],"overall_confidence":1}'
    plus = CloudFake("aliyun_qwen_plus", ["not-json", valid])
    plus.default_model = "qwen3.7-plus"
    run = make_run(testing_session)
    run.provider = plus.name
    run.model = "qwen3.7-plus"
    testing_session.commit()
    result = await generate_validated(
        session=testing_session,
        gateway=ModelGateway([plus]),
        run_id=run.id,
        provider_name=plus.name,
        task_type="scene_boundary",
        prompt=load_prompt("scene_boundary", "v2"),
        schema=SceneBoundaryResult,
        input_snapshot={"paragraphs": [{"id": "B0001-C0001-P0001", "text": "私密正文"}]},
        user_content="JSON task",
        business_validator=lambda _: None,
    )
    assert result.boundaries == []
    rows = list(testing_session.scalars(select(ModelInvocation).order_by(ModelInvocation.id)))
    assert [row.provider_name for row in rows] == [plus.name, plus.name]
    assert [row.invocation_kind for row in rows] == ["initial", "json_repair"]
    assert all(row.model_name == "qwen3.7-plus" for row in rows)
    assert all(row.is_cloud and row.sends_content_to_cloud for row in rows)
    assert all("私密正文" not in row.input_snapshot_json for row in rows)
    assert all(row.raw_response_text == "" for row in rows)
    assert rows[0].content_hash and rows[0].estimated_cost is None
    assert "secret" not in (rows[0].request_parameters_json or "")
