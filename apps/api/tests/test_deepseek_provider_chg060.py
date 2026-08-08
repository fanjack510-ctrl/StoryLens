"""CHG-20260808-060: DeepSeek formal provider — targeted unit/integration tests.

Never calls real DeepSeek APIs.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.models import ApplicationSetting, Base, ProviderConfiguration, WholeBookRun
from app.model_gateway.base import ModelRequest, ModelResponse, ProviderRequestError
from app.model_gateway.provider_errors import (
    ERROR_CATEGORY_AUTHENTICATION,
    ERROR_CATEGORY_PAYMENT_REQUIRED,
    ERROR_CATEGORY_RATE_LIMITED,
    ERROR_CATEGORY_SERVER,
    categorize_provider_error,
    chinese_message_for_http_status,
    safe_message,
)
from app.model_gateway.providers.openai_compatible import OpenAICompatibleProvider
from app.model_gateway.registry import get_model_gateway
from app.services.credentials.fake_store import FakeCredentialStore
from app.services.provider_bootstrap import (
    ensure_deepseek_provider_configuration,
    is_deepseek_provider,
)
from app.services.provider_pricing import (
    DEEPSEEK_MODEL_FLASH,
    DEEPSEEK_MODEL_PRO,
    DEEPSEEK_PROVIDER,
    TOKEN_ESTIMATE_METHOD_HEURISTIC,
    estimate_actual_cost_cny,
    estimate_pre_run_cost_cny,
    estimate_tokens_heuristic,
    get_model_pricing,
)
from app.services.provider_runtime import (
    apply_provider_runtime,
    get_active_cloud_provider,
    set_active_cloud_provider,
)
from app.services.provider_usage_accounting import aggregate_estimated_actual_cost_cny


@pytest.fixture()
def session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _deepseek_provider(**kwargs: Any) -> OpenAICompatibleProvider:
    defaults = dict(
        name="deepseek",
        base_url="https://api.deepseek.com",
        api_key="sk-test-deepseek-key",
        default_model=DEEPSEEK_MODEL_FLASH,
        timeout_seconds=30,
        max_context_tokens=8192,
        enabled=True,
        cloud=True,
        provider_family="deepseek",
        supports_json_object=True,
        supports_thinking_control=True,
    )
    defaults.update(kwargs)
    return OpenAICompatibleProvider(**defaults)


def test_config_defaults_include_deepseek() -> None:
    s = Settings(
        _env_file=None,  # type: ignore[call-arg]
    )
    assert s.deepseek_base_url == "https://api.deepseek.com"
    assert s.deepseek_model == DEEPSEEK_MODEL_FLASH
    assert s.deepseek_timeout_seconds == 300
    assert "deepseek-chat" not in {s.deepseek_model}
    assert "deepseek-reasoner" not in {s.deepseek_model}


def test_registry_has_deepseek_and_aliyun() -> None:
    get_model_gateway.cache_clear()
    gw = get_model_gateway()
    names = {p.name for p in gw.providers()}
    assert "deepseek" in names
    assert "aliyun_qwen_plus" in names
    deepseek = gw.get("deepseek")
    assert deepseek.provider_family == "deepseek"
    assert deepseek.cloud is True
    assert deepseek.default_model == DEEPSEEK_MODEL_FLASH
    get_model_gateway.cache_clear()


def test_independent_key_storage_fake_store() -> None:
    store = FakeCredentialStore()
    store.set("aliyun_qwen_plus", "sk-aliyun-secret")
    store.set("deepseek", "TESTSECRET_DEEPSEEK_ALPHA")
    assert store.get("aliyun_qwen_plus") == "sk-aliyun-secret"
    assert store.get("deepseek") == "TESTSECRET_DEEPSEEK_ALPHA"
    store.delete("deepseek")
    assert store.get("deepseek") is None
    assert store.get("aliyun_qwen_plus") == "sk-aliyun-secret"


def test_provider_switch_preserves_keys(session: Session) -> None:
    store = FakeCredentialStore()
    store.set("aliyun_qwen_plus", "sk-aliyun-keep")
    store.set("deepseek", "TESTSECRET_DEEPSEEK_KEEP")
    set_active_cloud_provider(session, "deepseek")
    session.commit()
    assert get_active_cloud_provider(session) == "deepseek"
    set_active_cloud_provider(session, "aliyun_qwen_plus")
    session.commit()
    assert get_active_cloud_provider(session) == "aliyun_qwen_plus"
    assert store.get("aliyun_qwen_plus") == "sk-aliyun-keep"
    assert store.get("deepseek") == "TESTSECRET_DEEPSEEK_KEEP"


@pytest.mark.asyncio
async def test_flash_pro_request_mapping_and_thinking_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_post(self, url, **kwargs):  # noqa: ANN001
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            json={
                "model": captured["json"]["model"],
                "choices": [{"message": {"content": '{"ok":true}', "reasoning_content": "secret"}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                    "prompt_cache_hit_tokens": 3,
                    "prompt_cache_miss_tokens": 7,
                },
            },
            request=request,
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    for model in (DEEPSEEK_MODEL_FLASH, DEEPSEEK_MODEL_PRO):
        provider = _deepseek_provider(default_model=model)
        resp = await provider.generate(
            ModelRequest(
                messages=[{"role": "user", "content": "hi"}],
                response_format_mode="json_object",
                enable_thinking=True,
                model=model,
            )
        )
        body = captured["json"]
        assert body["model"] == model
        assert body["thinking"] == {"type": "disabled"}
        assert "chat_template_kwargs" not in body
        assert body["response_format"] == {"type": "json_object"}
        assert resp.text == '{"ok":true}'
        assert "secret" not in resp.text
        assert resp.cache_hit_tokens == 3
        assert resp.cache_miss_tokens == 7
        assert model not in {"deepseek-chat", "deepseek-reasoner"}


@pytest.mark.asyncio
async def test_aliyun_still_sends_chat_template_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_post(self, url, **kwargs):  # noqa: ANN001
        captured["json"] = kwargs.get("json")
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            json={
                "model": "qwen3.7-plus",
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
            request=request,
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    provider = OpenAICompatibleProvider(
        name="aliyun_qwen_plus",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key="sk-aliyun",
        default_model="qwen3.7-plus",
        timeout_seconds=30,
        max_context_tokens=8192,
        enabled=True,
        cloud=True,
        provider_family="aliyun_qwen",
        supports_json_object=True,
    )
    await provider.generate(
        ModelRequest(messages=[{"role": "user", "content": "hi"}], enable_thinking=False)
    )
    assert captured["json"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert "thinking" not in captured["json"]


def test_flash_pro_pricing_and_pre_post_run_cost() -> None:
    flash = get_model_pricing(DEEPSEEK_MODEL_FLASH)
    pro = get_model_pricing(DEEPSEEK_MODEL_PRO)
    assert flash is not None and pro is not None
    assert flash.input_cache_hit_per_1m == 0.02
    assert flash.input_cache_miss_per_1m == 1.00
    assert flash.output_per_1m == 2.00
    assert pro.input_cache_hit_per_1m == 0.025
    assert pro.input_cache_miss_per_1m == 3.00
    assert pro.output_per_1m == 6.00

    cmin, cmax, err = estimate_pre_run_cost_cny(
        DEEPSEEK_MODEL_FLASH,
        estimated_input_tokens=1_000_000,
        estimated_output_tokens_min=850_000,
        estimated_output_tokens_max=1_250_000,
    )
    assert err is None
    assert cmin == pytest.approx(1.0 + 0.85 * 2.0)
    assert cmax == pytest.approx(1.0 + 1.25 * 2.0)

    actual = estimate_actual_cost_cny(
        DEEPSEEK_MODEL_FLASH,
        cache_hit_tokens=500_000,
        cache_miss_tokens=500_000,
        completion_tokens=1_000_000,
    )
    assert actual == pytest.approx(0.5 * 0.02 + 0.5 * 1.0 + 2.0)


def test_token_estimate_heuristic_label() -> None:
    assert TOKEN_ESTIMATE_METHOD_HEURISTIC == "heuristic"
    n = estimate_tokens_heuristic("汉" * 10 + "abcde")
    assert n >= 1


def test_bootstrap_deepseek_defaults(session: Session) -> None:
    row = ensure_deepseek_provider_configuration(session, create_if_missing=True)
    assert row is not None
    assert is_deepseek_provider(row.provider_name)
    assert row.display_name == "深度求索/DeepSeek"
    assert row.plus_model == DEEPSEEK_MODEL_FLASH
    assert "api.deepseek.com" in (row.base_url or "")


def test_provider_runtime_does_not_apply_aliyun_url(session: Session) -> None:
    session.add(
        ProviderConfiguration(
            provider_name="deepseek",
            enabled=True,
            disconnected=False,
            base_url="https://api.deepseek.com",
            plus_model=DEEPSEEK_MODEL_PRO,
            workspace_id="should-not-matter",
            region="cn-beijing",
        )
    )
    session.commit()
    provider = _deepseek_provider(default_model=DEEPSEEK_MODEL_FLASH, enabled=False)
    store = FakeCredentialStore()
    store.set("deepseek", "sk-ds")
    apply_provider_runtime(provider, session, store)
    assert provider.enabled is True
    assert provider.base_url == "https://api.deepseek.com"
    assert provider.default_model == DEEPSEEK_MODEL_PRO
    assert provider.api_key == "sk-ds"
    assert "compatible-mode" not in provider.base_url


def test_run_provider_model_pinning(session: Session) -> None:
    from app.db.models import Book

    book = Book(
        title="t",
        source_file_name="t.txt",
        source_file_hash="a" * 64,
    )
    session.add(book)
    session.flush()
    run = WholeBookRun(
        book_id=book.id,
        snapshot_id=None,
        mode="whole_book_native",
        status="paused",
        idempotency_key="pin-1",
        engine_id="e",
        engine_version="1",
        contract_version="v1",
        result_origin="formal",
        provider_name="deepseek",
        model_name=DEEPSEEK_MODEL_PRO,
    )
    session.add(run)
    session.commit()

    session.add(
        ProviderConfiguration(
            provider_name="deepseek",
            enabled=True,
            disconnected=False,
            plus_model=DEEPSEEK_MODEL_FLASH,
            base_url="https://api.deepseek.com",
            credential_reference="keyring:deepseek",
        )
    )
    session.add(
        ProviderConfiguration(
            provider_name="aliyun_qwen_plus",
            enabled=True,
            disconnected=False,
            plus_model="qwen3.7-plus",
            credential_reference="keyring:aliyun_qwen_plus",
        )
    )
    set_active_cloud_provider(session, "aliyun_qwen_plus")
    session.commit()

    store = FakeCredentialStore()
    store.set("deepseek", "sk-ds")
    store.set("aliyun_qwen_plus", "sk-aliyun")

    from app.narrative_core.services.whole_book_minimal_pipeline_v1_service import (
        build_formal_gateway_transports,
    )
    import app.narrative_core.services.whole_book_gateway_transport_v1 as gw

    monkey_store = store

    class _Store:
        def available(self):
            return True

        def get(self, name: str):
            return monkey_store.get(name)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(gw, "KeyringCredentialStore", lambda: _Store())
    try:
        transports = build_formal_gateway_transports(session, run=run)
        assert transports.window.provider_id == "deepseek"
        assert transports.window.model_name == DEEPSEEK_MODEL_PRO
        # Active settings changed to aliyun — resume still pinned to deepseek/pro.
        assert get_active_cloud_provider(session) == "aliyun_qwen_plus"
    finally:
        monkeypatch.undo()


@pytest.mark.parametrize(
    "status,category,needle",
    [
        (401, ERROR_CATEGORY_AUTHENTICATION, "API Key"),
        (402, ERROR_CATEGORY_PAYMENT_REQUIRED, "余额"),
        (429, ERROR_CATEGORY_RATE_LIMITED, "限流"),
        (500, ERROR_CATEGORY_SERVER, "内部错误"),
        (503, ERROR_CATEGORY_SERVER, "暂时不可用"),
    ],
)
def test_http_error_chinese_mapping(status: int, category: str, needle: str) -> None:
    assert categorize_provider_error("http_error", http_status=status) == category
    msg = chinese_message_for_http_status(status)
    assert msg and needle in msg


@pytest.mark.asyncio
async def test_http_status_raises_chinese(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_post(self, url, **kwargs):  # noqa: ANN001
        request = httpx.Request("POST", url)
        return httpx.Response(402, json={"error": {"message": "insufficient"}}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    provider = _deepseek_provider()
    with pytest.raises(ProviderRequestError) as raised:
        await provider.generate(ModelRequest(messages=[{"role": "user", "content": "hi"}]))
    assert raised.value.http_status_code == 402
    assert raised.value.error_category == ERROR_CATEGORY_PAYMENT_REQUIRED
    assert "余额" in str(raised.value)


def test_secret_redaction() -> None:
    text = safe_message(
        "Bearer TESTSECRET_DEEPSEEK_ALPHA failed at https://api.deepseek.com/v1",
        fallback="x",
    )
    assert "TESTSECRET_DEEPSEEK_ALPHA" not in text
    assert "api.deepseek.com" not in text
    assert "[REDACTED]" in text


def test_usage_accounting_aggregation() -> None:
    total = aggregate_estimated_actual_cost_cny(
        [
            {
                "model_name": DEEPSEEK_MODEL_FLASH,
                "cache_hit_tokens": 0,
                "cache_miss_tokens": 1_000_000,
                "output_tokens": 1_000_000,
            },
            {
                "model_name": DEEPSEEK_MODEL_FLASH,
                "cache_hit_tokens": 1_000_000,
                "cache_miss_tokens": 0,
                "output_tokens": 0,
            },
        ]
    )
    assert total == pytest.approx(1.0 + 2.0 + 0.02)


@pytest.mark.asyncio
async def test_mocked_gateway_transport_generate_path(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    session.add(
        ProviderConfiguration(
            provider_name="deepseek",
            enabled=True,
            disconnected=False,
            plus_model=DEEPSEEK_MODEL_FLASH,
            base_url="https://api.deepseek.com",
            credential_reference="keyring:deepseek",
        )
    )
    session.commit()
    store = FakeCredentialStore()
    store.set("deepseek", "sk-ds")

    class _Store:
        def available(self):
            return True

        def get(self, name: str):
            return store.get(name)

    import app.narrative_core.services.whole_book_gateway_transport_v1 as gw

    monkeypatch.setattr(gw, "KeyringCredentialStore", lambda: _Store())

    async def fake_generate(provider_name, request):  # noqa: ANN001
        assert provider_name == "deepseek"
        assert request.response_format_mode == "json_object"
        assert request.enable_thinking is False
        return ModelResponse(
            text=json.dumps(
                {
                    "characters": [{"name": "甲", "quote": "甲"}],
                    "events": [{"title": "事", "summary": "事", "quote": "甲"}],
                },
                ensure_ascii=False,
            ),
            model=DEEPSEEK_MODEL_FLASH,
            input_tokens=100,
            output_tokens=50,
            cache_hit_tokens=20,
            cache_miss_tokens=80,
        )

    fake_gw = MagicMock()
    fake_provider = _deepseek_provider()
    fake_gw.get.return_value = fake_provider
    fake_gw.generate = AsyncMock(side_effect=fake_generate)
    monkeypatch.setattr(gw, "get_model_gateway", lambda: fake_gw)
    monkeypatch.setattr(gw, "bind_gateway_runtime", lambda g, s, st: g)
    monkeypatch.setattr(gw, "apply_provider_runtime", lambda p, s, st: p)

    row = ensure_deepseek_provider_configuration(session, create_if_missing=True)
    assert row is not None
    transport = gw.GatewayWindowAnalysisTransport(session, provider_row=row)
    result = transport.invoke(
        unit_key="w1",
        unit_type="window",
        request_payload={
            "run": {"run_id": 1},
            "snapshot": {"snapshot_id": 1},
            "window": {
                "window_id": 1,
                "window_index": 0,
                "chapter_start_index": 0,
                "chapter_end_index": 0,
            },
            "paragraphs": [
                {
                    "global_paragraph_index": 0,
                    "text": "甲走过街道。",
                    "snapshot_id": 1,
                    "snapshot_chapter_id": 1,
                    "snapshot_paragraph_id": 1,
                    "chapter_id": 1,
                    "chapter_index": 0,
                    "paragraph_index": 0,
                    "text_hash": "a" * 64,
                }
            ],
        },
    )
    assert result.ok is True, result.error_message_safe
    assert result.input_tokens == 100
    assert result.output_tokens == 50
    assert isinstance(result.cost_cny, Decimal)


def test_cloud_pricing_json_has_deepseek_eligibility_prices() -> None:
    from pathlib import Path

    path = Path(__file__).resolve().parents[3] / "config" / "cloud_pricing.default.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    flash = data["models"][DEEPSEEK_MODEL_FLASH]
    pro = data["models"][DEEPSEEK_MODEL_PRO]
    assert flash["input_per_million"] == 1.0  # miss
    assert flash["output_per_million"] == 2.0
    assert pro["input_per_million"] == 3.0
    assert pro["output_per_million"] == 6.0


def test_resolve_formal_provider_accepts_provider_name(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.narrative_core.services import whole_book_gateway_transport_v1 as gw

    session.add(
        ProviderConfiguration(
            provider_name="deepseek",
            enabled=True,
            disconnected=False,
            plus_model=DEEPSEEK_MODEL_FLASH,
            base_url="https://api.deepseek.com",
            credential_reference="keyring:deepseek",
        )
    )
    session.commit()
    store = FakeCredentialStore()
    store.set("deepseek", "sk-ds")

    class _Store:
        def available(self):
            return True

        def get(self, name: str):
            return store.get(name)

    monkeypatch.setattr(gw, "KeyringCredentialStore", lambda: _Store())
    row = gw.resolve_formal_provider_row(session, provider_name="deepseek")
    assert row.provider_name == "deepseek"
