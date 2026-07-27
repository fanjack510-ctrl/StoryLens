"""HTTP factory: Private product default; Fixture opt-in; no silent fallback."""

from __future__ import annotations

import os

import pytest

from app.narrative_core.contracts.pro_native_overview_flags import (
    FIXTURE_ENGINE_ID,
    PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
)
from app.narrative_core.services.native_overview_http_factory import (
    resolve_native_overview_engine_id,
)


@pytest.mark.parametrize(
    "provider_id,model_id,expected",
    [
        (None, None, PRIVATE_NATIVE_OVERVIEW_ENGINE_ID),
        ("aliyun_qwen_plus", "qwen3.7-plus", PRIVATE_NATIVE_OVERVIEW_ENGINE_ID),
        (PRIVATE_NATIVE_OVERVIEW_ENGINE_ID, "native-overview-1", PRIVATE_NATIVE_OVERVIEW_ENGINE_ID),
        (FIXTURE_ENGINE_ID, FIXTURE_ENGINE_ID, FIXTURE_ENGINE_ID),
        ("fixture", "x", FIXTURE_ENGINE_ID),
    ],
)
def test_resolve_engine_id(provider_id, model_id, expected):
    assert resolve_native_overview_engine_id(provider_id, model_id) == expected


def test_smoke_fake_env_gate(monkeypatch: pytest.MonkeyPatch):
    from app.narrative_core.services.native_overview_smoke_fake_transport import (
        is_native_overview_smoke_fake_enabled,
    )

    monkeypatch.delenv("STORYLENS_NATIVE_OVERVIEW_SMOKE_FAKE", raising=False)
    assert is_native_overview_smoke_fake_enabled() is False
    monkeypatch.setenv("STORYLENS_NATIVE_OVERVIEW_SMOKE_FAKE", "1")
    assert is_native_overview_smoke_fake_enabled() is True
    # Ensure warehouse default remains unset in this process after test
    monkeypatch.delenv("STORYLENS_NATIVE_OVERVIEW_SMOKE_FAKE", raising=False)
    assert os.environ.get("STORYLENS_NATIVE_OVERVIEW_SMOKE_FAKE") in (None, "")
