"""连接 AI 服务的通用流程——不绑定任何一家厂商。

这个文件接的是 `test_recommended_ai_setup.py` 守着的那些不变量。原来那份测试打的是
`/desktop/ai-setup/recommended-qwen`：一条只为通义千问写的一键路径，把服务商写死成阿里云。
那条路径已经整条删除（设置页上它表现为第二个 API Key 输入框、第二个同意勾选、以及一张
按阿里云算状态却显示 DeepSeek 模型名的卡片）。

**但它守的东西跟厂商无关**，一条都不能丢：

* 密钥不出现在任何响应里，也不落进 SQLite；
* 没有「正文发送同意」就不开云端；
* 反复保存不会重复建 provider 行；
* 状态重载之后还在；
* 模型能连但没有价格数据，就不算「可以开始分析」。

所以这里用通用流程重跑同样的断言：保存配置 → 设为当前服务商 → 开云端 → 记下同意 → 验证。
"""

from __future__ import annotations

import json
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import ApplicationSetting, Base, ProviderConfiguration
from app.db.session import get_db, get_session_factory
from app.main import app
from app.model_gateway.base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ProviderCapabilities,
    ProviderHealth,
)
from app.model_gateway.gateway import ModelGateway
from app.model_gateway.registry import get_model_gateway
from app.services.credentials.fake_store import FakeCredentialStore
from app.services.credentials.service import get_credential_store

PROVIDER_ID = "aliyun_qwen_plus"
MODEL = "qwen3.7-plus"
CONFIG_URL = f"/api/v1/model-providers/{PROVIDER_ID}/configuration"
STATUS_URL = "/api/v1/desktop/ai-connection"
CONSENT_URL = "/api/v1/desktop/ai-connection/consent"


class ProbeFake(ModelProvider):
    name = PROVIDER_ID
    default_model = MODEL

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            enabled=True,
            cloud=True,
            provider_family="aliyun_qwen",
            sends_content_to_cloud=True,
            structured_output_mode="json_object",
            supports_json_object=True,
            supports_boundary_candidates=True,
            requires_boundary_review=True,
            automatic_boundary_routing=False,
            max_context_tokens=32768,
            default_timeout_seconds=30,
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider_name=self.name, status="healthy", detail="ok")

    async def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            text='{"status":"ok"}',
            model=self.default_model,
            input_tokens=1,
            output_tokens=1,
            raw={"id": "fake"},
        )


@pytest.fixture
def env(tmp_path, verified_cloud_pricing) -> Generator[tuple[TestClient, Session, FakeCredentialStore], None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'ai_connection.db'}", connect_args={"check_same_thread": False}
    )
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    store = FakeCredentialStore()
    provider = ProbeFake()

    def override_db() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_session_factory] = lambda: factory
    app.dependency_overrides[get_model_gateway] = lambda: ModelGateway([provider])
    app.dependency_overrides[get_credential_store] = lambda: store
    try:
        with TestClient(app) as client, factory() as session:
            yield client, session, store
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        engine.dispose()


def _save(client: TestClient, *, api_key: str | None, enabled: bool = True) -> dict:
    """通用保存：跟设置页那个「保存设置」按钮走的是同一条路。"""
    current = client.get(CONFIG_URL).json()
    payload = {
        "display_name": current.get("display_name") or "阿里云百炼",
        "region": current.get("region") or "",
        "workspace_id": current.get("workspace_id") or "",
        "base_url": current.get("base_url") or None,
        "plus_model": MODEL,
        "max_model": MODEL,
        "flash_model": MODEL,
        "timeout_seconds": current.get("timeout_seconds") or 300,
        "max_retries": current.get("max_retries") or 3,
        "enabled": enabled,
        "disconnected": not enabled,
        "allow_auto_route": False,
        "raw_logging_enabled": False,
        "api_key": api_key,
    }
    response = client.put(CONFIG_URL, json=payload)
    assert response.status_code in (200, 201), response.text
    return response.json()


def _connect(client: TestClient, *, api_key: str, consent: bool = True) -> dict:
    _save(client, api_key=api_key)
    client.put("/api/v1/settings/active-cloud-provider", json={"provider_name": PROVIDER_ID})
    client.put("/api/v1/settings/cloud", json={"enabled": True})
    client.put(CONSENT_URL, json={"accepted": consent})
    return client.get(STATUS_URL).json()


def test_saving_a_key_makes_the_provider_connected(env) -> None:
    client, _session, store = env
    status = _connect(client, api_key="sk-real-key")
    assert status["provider_name"] == PROVIDER_ID
    assert status["credential_configured"] is True
    assert status["provider_enabled"] is True
    assert status["cloud_enabled"] is True
    assert store.get(PROVIDER_ID) == "sk-real-key"


def test_api_key_is_never_returned_by_the_api(env) -> None:
    """密钥只进不出。任何一个响应里出现它，就等于把它写进了日志和排查截图。"""
    client, _session, _store = env
    _connect(client, api_key="sk-secret-value")
    for url in (STATUS_URL, CONFIG_URL, "/api/v1/settings/cloud"):
        assert "sk-secret-value" not in client.get(url).text


def test_api_key_is_not_stored_in_sqlite(env, tmp_path) -> None:
    """密钥归钥匙串，不归数据库——数据库会被备份、被导出、被随手拷走。"""
    client, session, _store = env
    _connect(client, api_key="sk-not-in-db")
    session.expire_all()
    rows = session.scalars(select(ProviderConfiguration)).all()
    assert all("sk-not-in-db" not in json.dumps(row.__dict__, default=str) for row in rows)
    settings = session.scalars(select(ApplicationSetting)).all()
    assert all("sk-not-in-db" not in (row.value_json or "") for row in settings)


def test_without_consent_cloud_analysis_is_not_ready(env) -> None:
    """没同意就不能开工。同意是一件独立的事，不能被「保存成功」顺手带过。"""
    client, _session, _store = env
    status = _connect(client, api_key="sk-test-key-0001", consent=False)
    assert status["cloud_body_consent"] is False
    assert status["analysis_ready"] is False


def test_saving_twice_does_not_duplicate_the_provider_row(env) -> None:
    client, session, _store = env
    _connect(client, api_key="sk-test-key-0001")
    _connect(client, api_key="sk-test-key-0001")
    session.expire_all()
    rows = session.scalars(
        select(ProviderConfiguration).where(ProviderConfiguration.provider_name == PROVIDER_ID)
    ).all()
    assert len(rows) == 1


def test_status_survives_a_reload(env) -> None:
    """重载之后状态还在。否则用户每次进设置页都会看到「尚未配置」，然后重配一遍。"""
    client, _session, _store = env
    first = _connect(client, api_key="sk-test-key-0001")
    again = client.get(STATUS_URL).json()
    assert again["credential_configured"] is True
    assert again["provider_enabled"] == first["provider_enabled"]
    assert again["cloud_enabled"] == first["cloud_enabled"]


def test_model_reachable_but_pricing_missing_is_not_ready(env, monkeypatch) -> None:
    """能连上不等于能开工：算不出钱就不能开始，否则用户会在不知情的情况下花钱。"""
    client, _session, _store = env
    monkeypatch.setattr(
        "app.services.ai_connection_status.model_pricing_available",
        lambda *_args, **_kwargs: False,
    )
    status = _connect(client, api_key="sk-test-key-0001")
    assert status["provider_eligible"] is False
    assert "pricing_unavailable" in status["blockers"]
    assert status["analysis_ready"] is False


def test_status_follows_the_selected_provider_not_a_hardcoded_one(env) -> None:
    """状态要跟着用户选的那家走。

    这正是删掉旧路径的原因：那一支把服务商写死成阿里云，于是选了 DeepSeek 的人，看到的是
    按阿里云算出来的状态和「配置已更改，需要重新验证」——指纹永远对不上，那句话验证多少次
    都消不掉。
    """
    client, _session, _store = env
    _connect(client, api_key="sk-test-key-0001")
    status = client.get(STATUS_URL).json()
    active = client.get("/api/v1/settings/active-cloud-provider").json()
    assert status["provider_name"] == active["provider_name"]
