import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    Base,
    AnalysisRun,
    CloudBudgetReservation,
    ModelInvocation,
    Paragraph,
    RequestGateDecision,
)
from app.db.session import get_db, get_session_factory
from app.main import app
from app.model_gateway.base import (
    ModelRequest,
    ModelResponse,
    ProviderCapabilities,
    ProviderRequestError,
)
from app.model_gateway.gateway import ModelGateway
from app.model_gateway.registry import get_model_gateway
from app.services.credentials.fake_store import FakeCredentialStore
from app.services.credentials.service import get_credential_store


class ConnectionTestFake:
    name = "aliyun_qwen_plus"
    default_model = "qwen3.7-plus"

    def __init__(self, error: ProviderRequestError | None = None) -> None:
        self.calls = 0
        self.requests: list[ModelRequest] = []
        self.error = error
        self.response_text = '{"status":"ok"}'

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            max_context_tokens=32768,
            default_timeout_seconds=30,
            enabled=True,
            cloud=True,
            provider_family="aliyun_qwen",
            sends_content_to_cloud=True,
            structured_output_mode="json_object",
            supports_json_object=True,
        )

    async def health(self):
        raise AssertionError("connection test must not use health()")

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return ModelResponse(
            text=self.response_text,
            model="qwen3.7-plus-response",
            http_status_code=200,
            input_tokens=37,
            output_tokens=6,
            total_tokens=43,
            request_id="provider-secret-request-id",
            finish_reason="stop",
        )


@pytest.fixture
def connection_env(tmp_path, verified_cloud_pricing):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'connection-test.db'}",
        connect_args={"check_same_thread": False},
    )
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    provider = ConnectionTestFake()
    store = FakeCredentialStore()

    def override_db():
        with factory() as session:
            yield session

    previous_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_session_factory] = lambda: factory
    app.dependency_overrides[get_model_gateway] = lambda: ModelGateway([provider])
    app.dependency_overrides[get_credential_store] = lambda: store
    try:
        with TestClient(app) as client, factory() as session:
            yield client, session, provider, store
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        engine.dispose()


def configure_cloud(client: TestClient, store: FakeCredentialStore) -> None:
    app.dependency_overrides[get_credential_store] = lambda: store
    response = client.put(
        "/api/v1/model-providers/aliyun_qwen_plus/configuration",
        json={
            "display_name": "测试Plus",
            "region": "cn-beijing",
            "base_url": "https://example.invalid/compatible-mode/v1",
            "plus_model": "qwen3.7-plus",
            "enabled": True,
            "disconnected": False,
            "allow_auto_route": False,
            "api_key": "sk-fake-credential",
        },
    )
    assert response.status_code == 200
    assert client.put("/api/v1/settings/cloud", json={"enabled": True}).status_code == 200


def test_unconfirmed_connection_test_does_not_send(connection_env) -> None:
    client, session, provider, _store = connection_env
    before = session.scalar(select(func.count()).select_from(ModelInvocation))
    response = client.post(
        "/api/v1/model-providers/aliyun_qwen_plus/test",
        json={"confirmed": False, "test_type": "minimal_json", "max_output_tokens": 32},
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "PAID_TEST_CONFIRMATION_REQUIRED"
    assert provider.calls == 0
    session.expire_all()
    after = session.scalar(select(func.count()).select_from(ModelInvocation))
    assert before == after


def test_confirmed_connection_test_is_exactly_one_minimal_request(connection_env) -> None:
    client, session, provider, store = connection_env
    configure_cloud(client, store)
    paragraph_count = session.scalar(select(func.count()).select_from(Paragraph))

    response = client.post(
        "/api/v1/model-providers/aliyun_qwen_plus/test",
        json={"confirmed": True, "test_type": "minimal_json", "max_output_tokens": 32},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "healthy"
    assert body["http_status"] == 200
    assert body["json_valid"] is True and body["schema_valid"] is True
    assert body["input_tokens"] == 37
    assert body["output_tokens"] == 6
    assert body["total_tokens"] == 43
    assert body["invocation_id"] > 0
    assert body["request_id"].startswith("rid#")
    assert "provider-secret-request-id" not in response.text

    assert provider.calls == 1
    request = provider.requests[0]
    assert request.max_output_tokens == 32
    assert request.temperature == 0
    assert request.enable_thinking is False
    assert request.response_format_mode == "json_object"
    rendered = json.dumps(request.messages, ensure_ascii=False)
    assert any('{"status":"ok"}' in item["content"] for item in request.messages)
    assert "novel" in rendered.lower()
    assert "B000" not in rendered
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(Paragraph)) == paragraph_count

    invocations = list(
        session.scalars(
            select(ModelInvocation).where(ModelInvocation.task_type == "connection_test")
        )
    )
    assert len(invocations) == 1
    invocation = invocations[0]
    assert invocation.attempt_no == 1
    assert invocation.invocation_kind == "connection_test"
    assert invocation.raw_response_text == ""
    assert invocation.parsed_response_json == '{"status":"ok"}'
    params = json.loads(invocation.request_parameters_json)
    assert params["max_real_requests"] == 1
    assert params["repair_enabled"] is False
    assert invocation.input_tokens == 37
    assert invocation.total_tokens == 43
    assert invocation.estimated_cost is not None
    assert "sk-fake-credential" not in invocation.input_snapshot_json


def test_failed_connection_test_records_structured_provider_error(connection_env) -> None:
    client, session, provider, store = connection_env
    provider_error = ProviderRequestError(
        "connection timed out",
        http_request_sent=True,
        error_code="PROVIDER_CONNECT_TIMEOUT",
        exception_type="ConnectTimeout",
        provider="aliyun_qwen_plus",
        model="qwen3.7-plus",
        retryable=True,
        timeout_kind="connect",
        transport_kind="connect_timeout",
    )
    provider.error = provider_error
    configure_cloud(client, store)

    response = client.post(
        "/api/v1/model-providers/aliyun_qwen_plus/test",
        json={"confirmed": True, "test_type": "minimal_json", "max_output_tokens": 32},
    )
    assert response.status_code == 502
    body = response.json()
    assert body["error_code"] == "PROVIDER_CONNECT_TIMEOUT"
    assert body["retryable"] is True
    assert body["transport_kind"] == "connect_timeout"
    assert body["invocation_id"] > 0
    assert provider.calls == 1
    session.expire_all()
    invocation = session.get(ModelInvocation, body["invocation_id"])
    assert invocation.status == "failed"
    assert invocation.error_code == "PROVIDER_CONNECT_TIMEOUT"
    assert invocation.error_message


def test_budget_block_creates_gate_but_no_invocation(connection_env) -> None:
    client, session, provider, store = connection_env
    configure_cloud(client, store)
    # 用费用卡住，不是请求数：请求数与 Token 已不再是闸门。要验的是「预算不足时只记一条
    # 拦截、不发任何调用」，与用哪一维卡住无关——而连接测试本身只花约 ¥0.00001，卡在
    # 请求数上会让它连自我验证都做不了，那正是死锁的中间一环。
    budget = client.get("/api/v1/settings/cloud-budget").json()
    budget["cloud_daily_estimated_cost_limit"] = 0.000001
    assert client.put("/api/v1/settings/cloud-budget", json=budget).status_code == 200
    session.add(
        AnalysisRun(
            task_type="connection_test",
            subject_type="provider",
            subject_id="existing",
            provider="aliyun_qwen_plus",
            model="qwen3.7-plus",
            prompt_version="v1",
            schema_version="v1",
            input_hash="x",
            prompt_hash="x",
            status="failed",
        )
    )
    session.commit()
    run = session.scalar(
        select(AnalysisRun).where(AnalysisRun.subject_id == "existing")
    )
    session.add(
        ModelInvocation(
            run_id=run.id,
            task_type="connection_test",
            provider_name="aliyun_qwen_plus",
            model_name="qwen3.7-plus",
            prompt_version="v1",
            schema_version="v1",
            attempt_no=1,
            invocation_kind="connection_test",
            request_hash="x",
            input_snapshot_json="{}",
            raw_response_text="",
            status="failed",
            latency_ms=1,
            is_cloud=True,
            sends_content_to_cloud=True,
            http_request_sent=True,
            audit_type="provider_invocation",
        )
    )
    session.commit()
    before_invocations = session.scalar(
        select(func.count()).select_from(ModelInvocation)
    )

    response = client.post(
        "/api/v1/model-providers/aliyun_qwen_plus/test",
        json={"confirmed": True, "test_type": "minimal_json", "max_output_tokens": 32},
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "INSUFFICIENT_BUDGET_RESERVATION"
    assert provider.calls == 0
    session.expire_all()
    after_invocations = session.scalar(
        select(func.count()).select_from(ModelInvocation)
    )
    assert before_invocations == after_invocations
    gate = session.scalar(
        select(RequestGateDecision).order_by(RequestGateDecision.id.desc())
    )
    assert gate.allowed is False


def test_ui_connection_test_does_not_require_aliyun_test_env(
    connection_env, monkeypatch
) -> None:
    client, _session, provider, store = connection_env
    monkeypatch.delenv("STORYLENS_RUN_ALIYUN_TESTS", raising=False)
    configure_cloud(client, store)
    response = client.post(
        "/api/v1/model-providers/aliyun_qwen_plus/test",
        json={"confirmed": True, "test_type": "minimal_json", "max_output_tokens": 32},
    )
    assert response.status_code == 200
    assert provider.calls == 1


def test_preflight_is_zero_generation(connection_env) -> None:
    client, session, provider, store = connection_env
    configure_cloud(client, store)
    before_invocations = session.scalar(select(func.count()).select_from(ModelInvocation))
    before_gates = session.scalar(select(func.count()).select_from(RequestGateDecision))
    response = client.post(
        "/api/v1/model-providers/aliyun_qwen_plus/test/preflight"
    )
    assert response.status_code == 200
    assert response.json()["max_real_requests"] == 1
    assert response.json()["sends_user_content"] is False
    assert provider.calls == 0
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(ModelInvocation)) == before_invocations
    assert session.scalar(select(func.count()).select_from(RequestGateDecision)) == before_gates


def test_output_limit_above_64_is_rejected_before_send(connection_env) -> None:
    client, _session, provider, store = connection_env
    configure_cloud(client, store)
    response = client.post(
        "/api/v1/model-providers/aliyun_qwen_plus/test",
        json={"confirmed": True, "test_type": "minimal_json", "max_output_tokens": 65},
    )
    assert response.status_code == 422
    assert response.json()["error_code"] in {"REQUEST_SCHEMA_INVALID", "REQUEST_VALIDATION_ERROR"}
    assert provider.calls == 0


def test_missing_credential_blocks_before_send(connection_env) -> None:
    client, _session, provider, store = connection_env
    configure_cloud(client, store)
    store.delete("aliyun_qwen_plus")
    response = client.post(
        "/api/v1/model-providers/aliyun_qwen_plus/test",
        json={"confirmed": True, "test_type": "minimal_json", "max_output_tokens": 32},
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "CREDENTIAL_MISSING"
    assert provider.calls == 0


def test_cloud_master_off_blocks_before_send(connection_env) -> None:
    client, _session, provider, store = connection_env
    configure_cloud(client, store)
    assert client.put("/api/v1/settings/cloud", json={"enabled": False}).status_code == 200
    response = client.post(
        "/api/v1/model-providers/aliyun_qwen_plus/test",
        json={"confirmed": True, "test_type": "minimal_json", "max_output_tokens": 32},
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "CLOUD_MASTER_SWITCH_OFF"
    assert provider.calls == 0


@pytest.mark.parametrize(
    "response_text",
    ["not-json", '{"status":"ok","unexpected":true}'],
)
def test_invalid_minimal_response_fails_without_repair(
    connection_env, response_text: str
) -> None:
    client, session, provider, store = connection_env
    provider.response_text = response_text
    configure_cloud(client, store)
    response = client.post(
        "/api/v1/model-providers/aliyun_qwen_plus/test",
        json={"confirmed": True, "test_type": "minimal_json", "max_output_tokens": 32},
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "REQUEST_VALIDATION_ERROR"
    assert provider.calls == 1
    invocation = session.get(ModelInvocation, response.json()["invocation_id"])
    assert invocation.status == "failed"
    assert json.loads(invocation.request_parameters_json)["repair_enabled"] is False


def test_success_writes_one_allowed_gate_and_no_reservation(connection_env) -> None:
    client, session, provider, store = connection_env
    configure_cloud(client, store)
    response = client.post(
        "/api/v1/model-providers/aliyun_qwen_plus/test",
        json={"confirmed": True, "test_type": "minimal_json", "max_output_tokens": 32},
    )
    assert response.status_code == 200
    session.expire_all()
    gates = list(session.scalars(select(RequestGateDecision)))
    assert len(gates) == 1
    assert gates[0].allowed is True
    assert gates[0].reason_code == "CONNECTION_TEST_ALLOWED"
    assert session.scalar(select(func.count()).select_from(CloudBudgetReservation)) == 0
    assert provider.calls == 1


def test_legacy_confirmation_field_remains_explicit(connection_env) -> None:
    client, _session, provider, store = connection_env
    configure_cloud(client, store)
    response = client.post(
        "/api/v1/model-providers/aliyun_qwen_plus/test",
        json={"confirm_paid_request": True, "max_output_tokens": 32},
    )
    assert response.status_code == 200
    assert provider.calls == 1
