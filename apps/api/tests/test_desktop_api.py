from fastapi.testclient import TestClient

from app.main import app
from app.services.credentials.fake_store import FakeCredentialStore
from app.services.credentials.service import get_credential_store
from tests.test_scene_pipeline import import_chapter


def test_dashboard_and_run_list(client: TestClient) -> None:
    import_chapter(client)
    dashboard = client.get("/api/v1/dashboard/summary")
    assert dashboard.status_code == 200
    assert dashboard.json()["books"] == 1
    assert client.get("/api/v1/analysis-runs").status_code == 200


def test_cloud_master_switch(client: TestClient) -> None:
    assert client.get("/api/v1/settings/cloud").json()["enabled"] is False
    enabled = client.put("/api/v1/settings/cloud", json={"enabled": True})
    assert enabled.json()["enabled"] is True
    assert (
        client.put("/api/v1/settings/cloud", json={"enabled": False}).json()["state"] == "disabled"
    )


def test_provider_configuration_never_returns_key(client: TestClient) -> None:
    store = FakeCredentialStore()
    app.dependency_overrides[get_credential_store] = lambda: store
    payload = {
        "display_name": "测试百炼",
        "region": "cn-beijing",
        "workspace_id": "workspace-demo",
        "base_url": "https://workspace-demo.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        "api_key": "sk-test-secret-value",
        "enabled": True,
        "disconnected": True,
    }
    response = client.put("/api/v1/model-providers/aliyun_qwen_plus/configuration", json=payload)
    assert response.status_code == 200
    text = response.text
    assert "sk-test-secret-value" not in text
    assert response.json()["credential_state"] == "configured"
    client.post("/api/v1/model-providers/aliyun_qwen_plus/disconnect")
    assert store.get("aliyun_qwen_plus") == "sk-test-secret-value"
    deleted = client.delete("/api/v1/model-providers/aliyun_qwen_plus/credentials")
    assert deleted.json()["credential_state"] == "missing"
    assert store.get("aliyun_qwen_plus") is None


def test_paid_test_requires_confirmation(client: TestClient) -> None:
    response = client.post(
        "/api/v1/model-providers/fake/test", json={"confirm_paid_request": False}
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "PAID_TEST_CONFIRMATION_REQUIRED"


def test_diagnostics_is_redacted(client: TestClient) -> None:
    response = client.get("/api/v1/system/diagnostics")
    assert response.status_code == 200
    text = response.text.lower()
    assert "authorization" not in text and "api_key" not in text
