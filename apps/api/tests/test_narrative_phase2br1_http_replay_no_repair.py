"""CHG-057 Public — BookOverview provider output contract HTTP replay."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

if "keyring" not in sys.modules:
    _keyring = ModuleType("keyring")
    _keyring.get_password = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    _keyring.set_password = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    _keyring.delete_password = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    _keyring.get_keyring = lambda: SimpleNamespace(priority=1)  # type: ignore[attr-defined]
    _errors = ModuleType("keyring.errors")

    class KeyringError(Exception):
        pass

    class PasswordDeleteError(KeyringError):
        pass

    _errors.KeyringError = KeyringError  # type: ignore[attr-defined]
    _errors.PasswordDeleteError = PasswordDeleteError  # type: ignore[attr-defined]
    sys.modules["keyring.errors"] = _errors
    sys.modules["keyring"] = _keyring

import pytest

from app.narrative_core.private_engine_contract.errors import PrivateEngineError
from app.narrative_core.private_engine_contract.provider_gateway import ProviderInferenceRequest
from app.narrative_core.private_engine_contract.provider_input import ResolvedProviderPayload
from app.narrative_core.services.book_overview_output_contract import (
    FAILURE_UNDECLARED_TOP_LEVEL,
    book_overview_result_json_schema,
    validate_book_overview_provider_output,
)
from app.narrative_core.services.provider_transport_kind import FakeHttpProviderTransport
from app.narrative_core.services.whole_book_provider_gateway import (
    BailianOpenAICompatibleProviderAdapter,
    PAYLOAD_REGISTRY,
    _parse_structured_text,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "provider_http"


def _content_from_http_fixture(name: str) -> str:
    envelope = json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
    content = envelope["choices"][0]["message"]["content"]
    assert isinstance(content, str) and content.strip()
    parsed = _parse_structured_text(content)
    assert isinstance(parsed, dict)
    return content


def _execute(adapter, req_id: str):
    messages = (
        {"role": "system", "content": "Return flat BookOverviewResultDto only."},
        {"role": "user", "content": "Analyze synthetic context."},
    )
    payload = ResolvedProviderPayload(
        messages=messages,
        input_bundle=SimpleNamespace(
            module_key="book_overview",
            response_schema_ref="dto://BookOverviewResultDto",
        ),
        response_format_mode="json_object",
        response_schema=book_overview_result_json_schema(),
        allow_schema_repair=True,
        max_repair_count=1,
    )
    PAYLOAD_REGISTRY.bind(req_id, payload)
    request = ProviderInferenceRequest(
        request_id=req_id,
        provider_kind="bailian",
        model_route="qwen3.7-plus",
        task_type="book_overview",
        system_instruction_ref="ref://system",
        prompt_pack_ref="ref://pack",
        input_bundle_ref="ref://bundle",
        response_schema_ref="dto://BookOverviewResultDto",
        temperature_policy={},
        token_budget=1200,
        cost_budget=None,
        timeout_policy={"timeout_seconds": 30},
        retry_policy={},
        cancellation_ref=None,
        data_handling_policy={},
        metadata={"environment": "test", "explicit_test_transport_override": True},
    )
    os.environ["WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE"] = "1"
    try:
        return adapter._execute_live(request, api_key="fake-credential")
    finally:
        os.environ.pop("WHOLE_BOOK_PRIVATE_PROVIDER_LIVE_PROBE", None)


def test_schema_generated_from_dto_only() -> None:
    schema = book_overview_result_json_schema()
    assert "evidence_map" not in schema["properties"]
    assert "book_overview" not in schema["properties"]
    assert set(schema["properties"]) >= {
        "logline",
        "premise",
        "evidence_refs",
        "protagonist_asset_id",
        "major_storyline_ids",
    }


def test_fixture_shapes_match_contract() -> None:
    flat = _parse_structured_text(_content_from_http_fixture("book_overview_http_valid_flat_v1.json"))
    assert validate_book_overview_provider_output(flat).ok
    bad = _parse_structured_text(
        _content_from_http_fixture("book_overview_http_invalid_envelope_v1.json")
    )
    result = validate_book_overview_provider_output(bad)
    assert not result.ok
    assert result.failure_code == FAILURE_UNDECLARED_TOP_LEVEL


def test_http_replay_no_repair() -> None:
    content = _content_from_http_fixture("book_overview_http_valid_flat_v1.json")
    transport = FakeHttpProviderTransport(stub_text=content, request_id="fake-http-valid-1")
    adapter = BailianOpenAICompatibleProviderAdapter(
        dry_run=False,
        allow_network=True,
        transport=transport,
        payload_registry=PAYLOAD_REGISTRY,
    )
    resp = _execute(adapter, "chg057-norepair")
    assert resp.status == "success"
    assert resp.retry_count == 0
    assert len(transport.calls) == 1
    out = dict(resp.structured_output or {})
    contract = (out.get("_provider_audit") or {}).get("output_contract") or {}
    assert contract.get("repair_count") == 0
    assert contract.get("dto_validation_status") == "SUCCESS"
    assert contract.get("schema_label_verified") is True
    assert "evidence_map" not in out
    assert "book_overview" not in out
    assert out.get("logline")
    assert resp.finish_reason
    assert (out.get("_provider_audit") or {}).get("host")
    assert (out.get("_provider_audit") or {}).get("http_status") == 200
    assert (out.get("_provider_audit") or {}).get("usage_source") == "provider_response"


def test_http_replay_single_repair() -> None:
    bad = _content_from_http_fixture("book_overview_http_invalid_envelope_v1.json")
    good = _content_from_http_fixture("book_overview_http_repair_valid_flat_v1.json")
    transport = FakeHttpProviderTransport(
        stub_texts=[bad, good],
        request_ids=["fake-http-invalid-1", "fake-http-repair-1"],
    )
    adapter = BailianOpenAICompatibleProviderAdapter(
        dry_run=False,
        allow_network=True,
        transport=transport,
        payload_registry=PAYLOAD_REGISTRY,
    )
    resp = _execute(adapter, "chg057-repair")
    assert resp.status == "success"
    assert resp.retry_count == 1
    assert len(transport.calls) == 2
    out = dict(resp.structured_output or {})
    contract = (out.get("_provider_audit") or {}).get("output_contract") or {}
    assert contract.get("initial_contract_failure_code") == FAILURE_UNDECLARED_TOP_LEVEL
    assert contract.get("repair_status") == "SUCCESS"
    assert "evidence_map" not in out
    assert out.get("logline")


def test_http_replay_repair_failed() -> None:
    bad = _content_from_http_fixture("book_overview_http_invalid_envelope_v1.json")
    transport = FakeHttpProviderTransport(
        stub_texts=[bad, bad],
        request_ids=["fake-http-invalid-1", "fake-http-invalid-2"],
    )
    adapter = BailianOpenAICompatibleProviderAdapter(
        dry_run=False,
        allow_network=True,
        transport=transport,
        payload_registry=PAYLOAD_REGISTRY,
    )
    with pytest.raises(PrivateEngineError):
        _execute(adapter, "chg057-repair-fail")
    assert len(transport.calls) == 2
