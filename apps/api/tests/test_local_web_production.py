"""Local tests for StoryLens local web production mode (CHG-20260721-015)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _set_database_url_from_layout() -> None:
    from app.core.paths import ensure_user_data_dirs

    layout = ensure_user_data_dirs()
    db_path = (layout["database"] / "storylens.db").resolve()
    os.environ["STORYLENS_DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"


def _refresh_app_runtime_bindings() -> None:
    """Point session/engine at current env without reloading modules (keeps Depends identities)."""
    from app.core import paths
    import app.core.config as config_mod
    import app.db.session as session_mod

    paths.user_data_root.cache_clear()
    config_mod.get_settings.cache_clear()
    _set_database_url_from_layout()
    config_mod.get_settings.cache_clear()
    settings = config_mod.get_settings()

    session_mod.settings = settings
    session_mod.engine.dispose()
    session_mod._ensure_sqlite_parent(settings.database_url)
    connect_args = (
        {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    )
    engine = create_engine(settings.database_url, connect_args=connect_args)
    session_mod.engine = engine
    session_mod.SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _ensure_spa_mounted(app) -> None:
    if getattr(app.state, "storylens_spa_mounted", False):
        return
    from app.services.spa_static import mount_spa

    mount_spa(app)
    app.state.storylens_spa_mounted = True


def _configure_web_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **env: str):
    """Configure env + DB bindings for local web production tests (no importlib.reload)."""
    monkeypatch.setenv("STORYLENS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("STORYLENS_DISABLE_INSTANCE_LOCK", "1")
    monkeypatch.setenv("STORYLENS_WEB_MODE", "1")
    monkeypatch.setenv("STORYLENS_APP_ENV", "production")
    monkeypatch.setenv("STORYLENS_SERVE_FRONTEND", "1")
    monkeypatch.setenv("STORYLENS_WEB_PORT", "8765")
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    _refresh_app_runtime_bindings()
    from app.main import app

    _ensure_spa_mounted(app)
    return app


@pytest.fixture()
def _restore_app_runtime_after_web_tests():
    """Restore default runtime env + DB bindings after web production tests."""
    yield
    for key in (
        "STORYLENS_DATA_DIR",
        "STORYLENS_DISABLE_INSTANCE_LOCK",
        "STORYLENS_WEB_MODE",
        "STORYLENS_APP_ENV",
        "STORYLENS_SERVE_FRONTEND",
        "STORYLENS_WEB_PORT",
        "STORYLENS_FRONTEND_DIST",
        "STORYLENS_DATABASE_URL",
    ):
        os.environ.pop(key, None)

    _refresh_app_runtime_bindings()


@pytest.fixture()
def web_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><html><body><div id='root'>StoryLens</div></body></html>",
        encoding="utf-8",
    )
    (assets / "app.js").write_text("console.log('ok')", encoding="utf-8")
    return dist


@pytest.fixture()
def web_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    web_dist: Path,
    _restore_app_runtime_after_web_tests,
):
    app = _configure_web_app(
        monkeypatch,
        tmp_path,
        STORYLENS_FRONTEND_DIST=str(web_dist),
    )
    with TestClient(app) as client:
        yield client


def test_runtime_mode_browser_local_production(web_client: TestClient) -> None:
    payload = web_client.get("/api/v1/runtime").json()
    assert payload["runtime_mode"] == "browser_local_production"
    assert payload["shell"] == "browser_local_production"
    assert payload["user_label"] == "本地网页版"
    assert payload["bind_host"] == "127.0.0.1"
    assert payload["desktop_capabilities"]["native_updater"] is False
    assert payload["web_capabilities"]["browser_zoom"] is True
    assert "StoryLens" in payload["data_directory"] or payload["data_directory"]


def test_health_endpoint(web_client: TestClient) -> None:
    assert web_client.get("/health").json()["status"] == "ok"


def test_spa_index_and_assets(web_client: TestClient) -> None:
    index = web_client.get("/")
    assert index.status_code == 200
    assert "StoryLens" in index.text
    asset = web_client.get("/assets/app.js")
    assert asset.status_code == 200
    assert "console.log" in asset.text


def test_spa_history_fallback(web_client: TestClient) -> None:
    page = web_client.get("/library")
    assert page.status_code == 200
    assert "StoryLens" in page.text
    nested = web_client.get("/books/1/journey")
    assert nested.status_code == 200
    assert "id='root'" in nested.text or 'id="root"' in nested.text or "StoryLens" in nested.text


def test_loopback_origin_allowed(web_client: TestClient) -> None:
    response = web_client.post(
        "/api/v1/settings/cloud",
        headers={"Origin": "http://127.0.0.1:8765"},
        json={"enabled": False},
    )
    # May be 200 or validation — must not be origin rejection
    assert response.status_code != 403
    assert response.json().get("error_code") != "ORIGIN_NOT_ALLOWED"


def test_remote_origin_rejected(web_client: TestClient) -> None:
    response = web_client.post(
        "/api/v1/settings/cloud",
        headers={"Origin": "https://evil.example"},
        json={"enabled": False},
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "ORIGIN_NOT_ALLOWED"


def test_api_key_not_returned_on_runtime_and_setup(web_client: TestClient) -> None:
    runtime = web_client.get("/api/v1/runtime").json()
    blob = json.dumps(runtime)
    assert '"api_key"' not in blob
    assert "sk-" not in blob
    setup = web_client.get("/api/v1/desktop/ai-setup/recommended-qwen").json()
    setup_blob = json.dumps(setup)
    assert '"api_key"' not in setup_blob
    assert "sk-" not in setup_blob
    assert setup.get("credential_configured") in {True, False}


def test_production_data_directory(web_client: TestClient, tmp_path: Path) -> None:
    payload = web_client.get("/api/v1/runtime").json()
    assert str(tmp_path / "data") in payload["data_directory"].replace("/", "\\") or str(
        tmp_path / "data"
    ) in payload["data_directory"]
    assert Path(payload["database_path"]).name == "storylens.db"


def test_browser_file_import(web_client: TestClient) -> None:
    import uuid

    token = uuid.uuid4().hex
    content = f"第一章 测试{token}\n\n这是一段用于本地网页导入的正文 {token}。\n".encode("utf-8")
    response = web_client.post(
        "/api/v1/books/import",
        files={"file": (f"local_web_{token}.txt", content, "text/plain")},
        headers={"Origin": "http://127.0.0.1:8765"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["book_id"] > 0
    assert body["status"] == "imported"


def test_instance_lock_idempotent_same_pid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORYLENS_DATA_DIR", str(tmp_path / "lockdata"))
    from app.core import paths

    paths.user_data_root.cache_clear()
    from app.services.instance_lock import acquire_instance_lock, read_lock, release_instance_lock

    first = acquire_instance_lock(port=8765, shell="browser_local_production")
    second = acquire_instance_lock(port=8765, shell="browser_local_production")
    assert first["pid"] == second["pid"]
    assert read_lock()["port"] == 8765
    release_instance_lock()


def test_spa_cannot_read_arbitrary_files(
    web_client: TestClient, tmp_path: Path, web_dist: Path
) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("top-secret", encoding="utf-8")
    # Attempt path traversal style request — should not leak secret contents
    response = web_client.get("/../secret.txt")
    assert "top-secret" not in response.text


def test_desktop_api_still_available(web_client: TestClient) -> None:
    caps = web_client.get("/api/v1/system/capabilities").json()
    assert caps["capability_schema_version"] == "1c-a-2"
    profile = web_client.get("/api/v1/settings/config-profile").json()
    assert profile["runtime_mode"] == "browser_local_production"
