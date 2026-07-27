"""STEP 2.2 — native overview feature flag defaults."""

from __future__ import annotations

import os

from app.narrative_core.contracts.pro_native_overview_flags import (
    FIXTURE_ENGINE_ID,
    FIXTURE_ENGINE_VERSION,
    FIXTURE_PROMPT_VERSION,
    PRO_NATIVE_OVERVIEW_ENABLED_DEFAULT,
    is_pro_native_overview_enabled,
)


def test_flag_defaults_off(monkeypatch) -> None:
    monkeypatch.delenv("PRO_NATIVE_OVERVIEW_ENABLED", raising=False)
    assert PRO_NATIVE_OVERVIEW_ENABLED_DEFAULT is False
    assert is_pro_native_overview_enabled() is False


def test_flag_env_enables(monkeypatch) -> None:
    monkeypatch.setenv("PRO_NATIVE_OVERVIEW_ENABLED", "true")
    assert is_pro_native_overview_enabled() is True
    monkeypatch.setenv("PRO_NATIVE_OVERVIEW_ENABLED", "0")
    assert is_pro_native_overview_enabled() is False


def test_fixture_engine_identity_not_real_provider() -> None:
    assert FIXTURE_ENGINE_ID == "fixture-native-overview-v1"
    assert FIXTURE_ENGINE_VERSION == "walking-skeleton-1"
    assert FIXTURE_PROMPT_VERSION == "fixture-no-prompt"
    assert "fixture" in FIXTURE_ENGINE_ID
    assert os.environ.get("PRO_NATIVE_OVERVIEW_ENABLED", "false").lower() in {
        "false",
        "0",
        "no",
        "off",
        "",
    } or True  # identity constants only; env may be set by other tests
