"""Local tests: uvicorn --ws none for StoryLens (no product WebSocket)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
START_WEB = ROOT / "scripts" / "start_storylens_web.ps1"
START_BACKEND = ROOT / "scripts" / "start_backend.ps1"
SIDECAR = ROOT / "apps" / "api" / "sidecar_main.py"


def test_start_storylens_web_disables_websocket_protocol() -> None:
    text = START_WEB.read_text(encoding="utf-8-sig")
    assert "--ws" in text
    assert "none" in text
    assert "WebSocket" in text or "websockets" in text
    assert "HasExited" in text
    assert "Fail-WebStart" in text
    assert "Clear-WebRuntimeState" in text
    assert "ws = 'none'" in text


def test_start_backend_disables_websocket_protocol() -> None:
    text = START_BACKEND.read_text(encoding="utf-8")
    assert "'--ws','none'" in text.replace(" ", "") or "'--ws', 'none'" in text


def test_sidecar_disables_websocket_protocol() -> None:
    text = SIDECAR.read_text(encoding="utf-8")
    assert 'ws="none"' in text or "ws='none'" in text


def test_websockets_exceptions_currently_broken_or_optional() -> None:
    """Document current env: product must not require websockets.exceptions."""
    try:
        import websockets.exceptions  # noqa: F401
    except ModuleNotFoundError:
        # Expected on broken installs; --ws none is the supported path.
        return
    # If present and healthy, still OK 鈥?product does not call it.
    assert True


def test_uvicorn_accepts_ws_none_without_importing_exceptions() -> None:
    """CLI help/config with --ws none must not need websockets.exceptions."""
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "from uvicorn.config import Config; c=Config('app.main:app', ws='none'); "
            "assert c.ws == 'none'",
        ],
        cwd=str(ROOT / "apps" / "api"),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_uvicorn_auto_ws_would_import_broken_package() -> None:
    """Reproduce root cause: auto WS protocol imports websockets.exceptions."""
    spec = importlib.util.find_spec("websockets")
    if spec is None:
        pytest.skip("websockets not installed at all")
    # Broken namespace package: no exceptions submodule.
    missing = importlib.util.find_spec("websockets.exceptions") is None
    if not missing:
        pytest.skip("websockets.exceptions is healthy in this environment")
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "from uvicorn.protocols.websockets.auto import AutoWebSocketsProtocol; "
            "AutoWebSocketsProtocol  # noqa: B018\n"
            "import importlib; "
            "importlib.import_module('uvicorn.protocols.websockets.websockets_sansio_impl')",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "websockets.exceptions" in (proc.stderr + proc.stdout)


def test_storylens_has_no_websocket_routes() -> None:
    from app.main import app

    paths = []
    for route in app.routes:
        path = getattr(route, "path", None)
        if path:
            paths.append(path)
    joined = " ".join(paths).lower()
    assert "websocket" not in joined

