import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from app.model_gateway.base import ModelRequest
from app.model_gateway.profiles import load_profiles
from app.model_gateway.providers.openai_compatible import OpenAICompatibleProvider
from app.model_gateway.registry import get_model_gateway
from app.model_gateway.structured_constraints import (
    grammar_hash,
    schema_hash,
    schema_to_gbnf,
    select_structured_output_mode,
)
from scripts.calibrate_local_model import boundary_metrics


def test_profiles_and_manual_only() -> None:
    profiles = load_profiles(ROOT / "config/local_model_profiles.example.yaml")
    assert profiles["qwen3_14b_dev"].enable_thinking is False
    assert profiles["qwen3_14b_dev"].default is False
    assert profiles["qwen36_27b_manual"].manual_only is True


@pytest.mark.integration
def test_all_27b_routes_are_manual_only() -> None:
    get_model_gateway.cache_clear()
    providers = get_model_gateway().providers()
    candidates = [item for item in providers if "27" in item.default_model.lower()]
    if not candidates:
        pytest.skip("integration: no local 27B providers registered in this environment")
    assert all(item.capabilities().manual_only for item in candidates)


def test_constraint_hashes_are_stable() -> None:
    schema = {"type": "object", "properties": {"status": {"type": "string"}}}
    assert schema_hash(schema) == schema_hash(json.loads(json.dumps(schema)))
    grammar = schema_to_gbnf(schema)
    assert grammar.startswith("root ::=") and len(grammar_hash(grammar)) == 64


def test_boundary_metrics() -> None:
    result = boundary_metrics([{"p1"}, {"p2"}], [{"p1", "x"}, set()])
    assert result["tp"] == 1 and result["fp"] == 1 and result["fn"] == 1
    assert result["precision"] == result["recall"] == result["f1"] == 0.5


def test_constraint_mode_selection_and_explicit_fallback() -> None:
    assert select_structured_output_mode({"json_schema": True}) == ("json_schema", None)
    mode, reason = select_structured_output_mode({"prompt_only": True})
    assert mode == "prompt_only" and "rejected" in reason
    assert select_structured_output_mode({})[0] == "unsupported"


@pytest.mark.asyncio
async def test_openai_provider_sends_thinking_and_schema(monkeypatch) -> None:
    captured = {}

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": '{"status":"ok"}'}}], "model": "m"}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, _url, *, json, headers):
            captured.update(json)
            return Response()

    monkeypatch.setattr("httpx.AsyncClient", lambda **_: Client())
    provider = OpenAICompatibleProvider(
        name="p",
        base_url="http://x/v1",
        api_key="local",
        default_model="m",
        timeout_seconds=1,
        max_context_tokens=4096,
    )
    await provider.generate(
        ModelRequest(
            messages=[{"role": "user", "content": "x"}],
            response_schema={"type": "object"},
            response_format_mode="json_schema",
            enable_thinking=False,
            max_output_tokens=32,
        )
    )
    assert captured["chat_template_kwargs"] == {"enable_thinking": False}
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["max_tokens"] == 32


def test_prompt_v2_and_private_profile_packaging() -> None:
    for task in ("scene_boundary", "scene_analysis"):
        system = (ROOT / f"packages/prompts/{task}/v2/system.md").read_text(encoding="utf-8")
        assert "不可信" in system and "思维过程" in system and "JSON" in system
    package = (ROOT / "scripts/package_project.ps1").read_text(encoding="utf-8")
    assert "local_model_profiles.yaml" in package
