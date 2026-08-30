from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = REPO_ROOT / "infra" / "online" / "docker-compose.yml"
ENV_EXAMPLE = REPO_ROOT / "infra" / "online" / ".env.example"
API_DOCKERFILE = REPO_ROOT / "infra" / "online" / "Dockerfile.api"
PROVIDER_SECRET = "storylens_online_deepseek_api_key"


def test_provider_secret_is_mounted_only_into_worker() -> None:
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    services = compose["services"]

    assert services["online-worker"]["secrets"] == [
        {"source": PROVIDER_SECRET, "target": PROVIDER_SECRET}
    ]
    for service_name, service in services.items():
        if service_name != "online-worker":
            mounted = service.get("secrets", [])
            assert PROVIDER_SECRET not in mounted
            assert all(
                not isinstance(item, dict) or item.get("source") != PROVIDER_SECRET
                for item in mounted
            )

    worker_environment = services["online-worker"]["environment"]
    assert worker_environment["STORYLENS_ONLINE_PHASE2B1_API_KEY_FILE"] == (
        "/run/secrets/storylens_online_deepseek_api_key"
    )
    for service in services.values():
        environment_text = str(service.get("environment", {})).lower()
        assert "phase2b1_api_key=" not in environment_text
        assert "bearer " not in environment_text


def test_only_worker_network_boundary_changes_for_provider_egress() -> None:
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    services = compose["services"]

    assert services["online-worker"]["networks"] == ["private", "egress"]
    assert services["online-api"]["networks"] == ["private", "egress"]
    assert services["online-web"]["networks"] == ["private"]
    assert services["gateway"]["networks"] == ["edge", "private"]
    assert services["pocketbase"]["networks"] == ["private", "egress"]
    assert services["pocketbase-init"]["network_mode"] == "none"
    assert "ports" not in services["online-worker"]


def test_api_receives_only_gate_allowlist_and_limits() -> None:
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    api_environment = compose["services"]["online-api"]["environment"]
    worker_environment = compose["services"]["online-worker"]["environment"]

    assert "STORYLENS_ONLINE_PHASE2B1_ENABLED" in api_environment
    assert "STORYLENS_ONLINE_PHASE2B1_ALLOWLISTED_USER_IDS_CSV" in api_environment
    assert "STORYLENS_ONLINE_PHASE2B1_TEXT_MAX_BYTES" in api_environment
    assert "STORYLENS_ONLINE_PHASE2B1_BASE_URL" not in api_environment
    assert "STORYLENS_ONLINE_PHASE2B1_API_KEY_FILE" not in api_environment
    assert "STORYLENS_ONLINE_PHASE2B1_PRICING_VERSION" not in api_environment

    assert worker_environment["STORYLENS_ONLINE_PHASE2B1_BASE_URL"] == ("https://api.deepseek.com")
    assert "STORYLENS_ONLINE_PHASE2B1_API_KEY_FILE" in worker_environment
    assert "STORYLENS_ONLINE_PHASE2B1_PRICING_VERSION" not in worker_environment


def test_secret_value_is_absent_from_tracked_configuration_and_image() -> None:
    env_example = ENV_EXAMPLE.read_text(encoding="utf-8")
    dockerfile = API_DOCKERFILE.read_text(encoding="utf-8")
    compose = COMPOSE_FILE.read_text(encoding="utf-8")

    assert "PHASE2B1_API_KEY=" not in env_example
    assert "PHASE2B1_API_KEY_FILE=" in env_example
    assert "FAKE_PHASE2B1_KEY" not in env_example
    assert "API_KEY" not in dockerfile
    assert "ARG STORYLENS_ONLINE_PHASE2B1" not in dockerfile
    assert "Authorization" not in compose


def test_superseded_provider_has_no_runtime_test_or_deployment_reference() -> None:
    roots = (
        REPO_ROOT / "apps" / "online_api",
        REPO_ROOT / "apps" / "online_web" / "src",
        REPO_ROOT / "infra" / "online",
        REPO_ROOT / "docs" / "online",
    )
    banned = ("ali" + "yun", "bai" + "lian", "qw" + "en")
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            if path.suffix not in {".py", ".ts", ".tsx", ".yml", ".yaml", ".md", ".example"}:
                continue
            lowered = path.read_text(encoding="utf-8").lower()
            assert not any(marker in lowered for marker in banned), path
