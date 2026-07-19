import json

from fastapi.testclient import TestClient

from app.services.cloud_budget import cloud_block_reasons
from app.services.cloud_pricing import pricing_status


def test_cloud_budget_defaults(client: TestClient) -> None:
    value = client.get("/api/v1/settings/cloud-budget").json()
    assert value["cloud_max_input_tokens_per_request"] == 16000
    assert value["cloud_max_output_tokens_per_request"] == 4000
    # Real Canary v13 max HTTP/run=41 → defaults raised with ledger evidence.
    assert value["cloud_daily_request_limit"] == 50
    assert value["cloud_max_requests_per_run"] == 50
    assert value["cloud_daily_estimated_cost_limit"] == 1.0
    assert value["currency"] == "CNY"


def test_cloud_budget_update_is_persistent(client: TestClient) -> None:
    value = client.get("/api/v1/settings/cloud-budget").json()
    value["cloud_daily_request_limit"] = 12
    value["cloud_daily_estimated_cost_limit"] = 2.5
    saved = client.put("/api/v1/settings/cloud-budget", json=value)
    assert saved.status_code == 200
    assert client.get("/api/v1/settings/cloud-budget").json()["cloud_daily_request_limit"] == 12


def test_cloud_budget_rejects_negative_and_zero_values(client: TestClient) -> None:
    value = client.get("/api/v1/settings/cloud-budget").json()
    for field, invalid in [("cloud_daily_token_limit", -1),
                           ("cloud_max_input_tokens_per_request", 0),
                           ("cloud_daily_estimated_cost_limit", 0)]:
        payload = dict(value)
        payload[field] = invalid
        assert client.put("/api/v1/settings/cloud-budget", json=payload).status_code == 422


def test_cloud_pricing_missing_and_invalid(tmp_path) -> None:
    missing = pricing_status(tmp_path / "missing.json")
    assert missing["configured"] is False
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("not-json", encoding="utf-8")
    assert pricing_status(invalid_path)["error_code"] == "CLOUD_PRICING_INVALID"


def test_cloud_pricing_unverified_is_not_enabled(tmp_path) -> None:
    path = tmp_path / "pricing.json"
    path.write_text(json.dumps({"version": "unconfigured", "currency": "CNY",
                                "models": {"demo": {"input_per_million": None,
                                                       "output_per_million": None}}}), encoding="utf-8")
    status = pricing_status(path)
    assert status["valid"] is True
    assert status["enabled"] is False
    assert status["error_code"] == "CLOUD_PRICING_UNVERIFIED"


def test_unknown_pricing_and_cloud_switch_are_hard_gates() -> None:
    budget = {"cloud_request_budget_enabled": True, "cloud_stop_on_unknown_pricing": True,
              "cloud_daily_request_limit": 30, "cloud_daily_token_limit": 200000,
              "cloud_daily_estimated_cost_limit": 1.0}
    pricing = {"enabled": False}
    reasons = cloud_block_reasons(False, budget, pricing)
    assert "云端总开关已关闭" in reasons
    assert "价格未知或尚未验证" in reasons


def test_cloud_usage_summary_is_zero_and_blocked(client: TestClient) -> None:
    response = client.get("/api/v1/cloud-usage/summary")
    assert response.status_code == 200
    value = response.json()
    assert value["request_count"] == value["total_tokens"] == 0
    assert value["estimated_cost"] == 0
    assert value["within_budget"] is False


def test_budget_responses_never_expose_credentials(client: TestClient) -> None:
    text = "".join([
        client.get("/api/v1/settings/cloud-budget").text,
        client.get("/api/v1/cloud-pricing/status").text,
        client.get("/api/v1/cloud-usage/summary").text,
    ]).lower()
    assert "api_key" not in text and "workspace_id" not in text and "base_url" not in text
