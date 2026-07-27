"""Tests for chapter analysis development-only smoke fake transport."""

from __future__ import annotations

import os

import pytest

from app.model_gateway.base import ModelRequest, ProviderRequestError
from app.services.chapter_analysis_smoke_fake_transport import (
    chapter_smoke_fake_generate,
    is_chapter_analysis_smoke_fake_enabled,
    is_chapter_analysis_smoke_fake_requested,
    synthesize_chapter_smoke_fake_text,
)


@pytest.fixture(autouse=True)
def _clear_smoke_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE", raising=False)
    monkeypatch.delenv("STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE_FAIL", raising=False)
    monkeypatch.setenv("STORYLENS_APP_ENV", "development")


def test_smoke_fake_default_off() -> None:
    assert is_chapter_analysis_smoke_fake_requested() is False
    assert is_chapter_analysis_smoke_fake_enabled() is False


def test_smoke_fake_enabled_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE", "1")
    monkeypatch.setenv("STORYLENS_APP_ENV", "development")
    assert is_chapter_analysis_smoke_fake_enabled() is True


def test_smoke_fake_rejected_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE", "1")
    monkeypatch.setenv("STORYLENS_APP_ENV", "production")
    assert is_chapter_analysis_smoke_fake_requested() is True
    assert is_chapter_analysis_smoke_fake_enabled() is False


def test_synthesize_scene_analysis_uses_prompt_paragraphs() -> None:
    req = ModelRequest(
        messages=[
            {
                "role": "user",
                "content": (
                    'scene analysis for "paragraph_id":"B0009-C0003-P0002","text":"灯塔今晚会亮"'
                    ' and "paragraph_id":"B0009-C0003-P0003","text":"信标机仍在工作"'
                    ' scene_id B0009-C0003-S0001'
                ),
            }
        ]
    )
    text = synthesize_chapter_smoke_fake_text(req)
    assert "B0009-C0003-P0002" in text
    assert "灯塔今晚会亮" in text or "推进" in text
    assert "entry_state" in text


def test_synthesize_v35_boundary_decisions_for_short_chapter() -> None:
    req = ModelRequest(
        messages=[
            {
                "role": "user",
                "content": (
                    "场景边界识别器 owned_transition_ids boundary_candidate "
                    "B0001-C0001-P0001 B0001-C0001-P0002"
                ),
            }
        ]
    )
    payload = synthesize_chapter_smoke_fake_text(req)
    assert '"contract_version": "3.5"' in payload
    assert '"boundary_candidate": false' in payload
    assert "decisions" in payload


@pytest.mark.asyncio
async def test_fail_injection_raises_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE", "1")
    monkeypatch.setenv("STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE_FAIL", "1")
    monkeypatch.setenv("STORYLENS_APP_ENV", "development")
    req = ModelRequest(messages=[{"role": "user", "content": "B0001-C0001-P0001 hello"}])
    with pytest.raises(ProviderRequestError) as exc:
        await chapter_smoke_fake_generate(
            req, provider_name="aliyun_qwen_plus", default_model="qwen3.7-plus"
        )
    assert exc.value.retryable is True


@pytest.mark.asyncio
async def test_openai_compatible_uses_smoke_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE", "1")
    monkeypatch.setenv("STORYLENS_APP_ENV", "development")
    from app.model_gateway.providers.openai_compatible import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(
        name="aliyun_qwen_plus",
        base_url="https://disabled.invalid/v1",
        api_key="",
        default_model="qwen3.7-plus",
        timeout_seconds=5,
        max_context_tokens=8192,
        enabled=True,
        cloud=True,
        supports_scene_analysis=True,
        supports_boundary_candidates=True,
        requires_boundary_review=True,
    )
    health = await provider.health()
    assert health.status == "healthy"
    assert health.detail == "chapter_analysis_smoke_fake"
    resp = await provider.generate(
        ModelRequest(messages=[{"role": "user", "content": "B0001-C0001-P0001 港口夜雨"}])
    )
    assert resp.request_id and resp.request_id.startswith("smoke-fake-")
    assert "entry_state" in resp.text
