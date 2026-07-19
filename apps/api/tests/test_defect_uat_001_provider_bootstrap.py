"""DEFECT-UAT-001: Aliyun endpoint bootstrap / shared resolution."""

from __future__ import annotations

from app.core.config import Settings
from app.db.models import ProviderConfiguration
from app.services.aliyun_endpoint import (
    CN_BEIJING_PUBLIC_COMPATIBLE_BASE_URL,
    derive_maas_compatible_base_url,
    endpoint_host,
    is_disabled_sentinel_url,
    resolve_aliyun_compatible_base_url,
)
from app.services.provider_bootstrap import ensure_aliyun_provider_configuration


def test_resolve_prefers_explicit_base_url():
    settings = Settings(
        _env_file=None,
        aliyun_base_url="https://env.example/compatible-mode/v1",
        aliyun_workspace_id="env-ws",
    )
    url = resolve_aliyun_compatible_base_url(
        base_url="https://explicit.example/compatible-mode/v1",
        workspace_id="row-ws",
        settings=settings,
    )
    assert url == "https://explicit.example/compatible-mode/v1"


def test_resolve_uses_env_then_workspace_then_public_default():
    settings = Settings(_env_file=None, aliyun_base_url="", aliyun_workspace_id="")
    assert (
        resolve_aliyun_compatible_base_url(settings=settings)
        == CN_BEIJING_PUBLIC_COMPATIBLE_BASE_URL
    )
    settings.aliyun_workspace_id = "llm-demo"
    assert resolve_aliyun_compatible_base_url(settings=settings) == (
        "https://llm-demo.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    )
    settings.aliyun_base_url = "https://from-env.example/compatible-mode/v1"
    assert (
        resolve_aliyun_compatible_base_url(settings=settings)
        == "https://from-env.example/compatible-mode/v1"
    )


def test_resolve_skips_disabled_sentinel():
    settings = Settings(_env_file=None, aliyun_base_url="", aliyun_workspace_id="")
    url = resolve_aliyun_compatible_base_url(
        base_url="https://disabled.invalid/v1",
        settings=settings,
    )
    assert url == CN_BEIJING_PUBLIC_COMPATIBLE_BASE_URL
    assert not is_disabled_sentinel_url(url)
    assert endpoint_host(url) == "dashscope.aliyuncs.com"


def test_derive_maas_matches_docs_formula():
    assert derive_maas_compatible_base_url("ws1") == (
        "https://ws1.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    )


def test_ensure_bootstraps_empty_plus_row(testing_session):
    row = ProviderConfiguration(
        provider_name="aliyun_qwen_plus",
        display_name="阿里云百炼",
        region="cn-beijing",
        workspace_id="",
        base_url="",
        plus_model="qwen3.7-plus",
        enabled=True,
        disconnected=True,
        allow_auto_route=False,
    )
    testing_session.add(row)
    testing_session.commit()

    ensured = ensure_aliyun_provider_configuration(
        testing_session, "aliyun_qwen_plus", create_if_missing=False
    )
    assert ensured is not None
    assert ensured.base_url == CN_BEIJING_PUBLIC_COMPATIBLE_BASE_URL
    assert ensured.allow_auto_route is False
    assert ensured.plus_model == "qwen3.7-plus"
    assert endpoint_host(ensured.base_url) != "disabled.invalid"


def test_ensure_preserves_explicit_custom_endpoint(testing_session):
    custom = "https://custom-ws.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    row = ProviderConfiguration(
        provider_name="aliyun_qwen_plus",
        base_url=custom,
        workspace_id="",
        region="cn-beijing",
        plus_model="qwen3.7-plus",
        enabled=True,
        allow_auto_route=True,  # bootstrap must force false
    )
    testing_session.add(row)
    testing_session.commit()

    ensured = ensure_aliyun_provider_configuration(testing_session, "aliyun_qwen_plus")
    assert ensured.base_url == custom
    assert ensured.allow_auto_route is False
