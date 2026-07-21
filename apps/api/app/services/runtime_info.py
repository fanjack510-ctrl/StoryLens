"""Unified runtime introspection for desktop and local web shells."""

from __future__ import annotations

import os
from typing import Any

from app import __version__
from app.core import paths
from app.services.config_runtime_profile import (
    build_config_runtime_profile,
    resolve_runtime_mode,
)
from app.services.credentials.base import CredentialStore


def _shell_kind() -> str:
    """Client-facing shell classification."""
    mode = resolve_runtime_mode()
    if mode == "browser_local_production":
        return "browser_local_production"
    if mode == "packaged":
        return "tauri_desktop"
    if mode == "desktop_dev":
        return "tauri_desktop"
    return "browser_local_dev"


def _frontend_origin() -> str:
    override = os.environ.get("STORYLENS_FRONTEND_ORIGIN", "").strip()
    if override:
        return override.rstrip("/")
    port = os.environ.get("STORYLENS_WEB_PORT", "8765").strip() or "8765"
    if resolve_runtime_mode() == "browser_local_production":
        return f"http://127.0.0.1:{port}"
    return "http://127.0.0.1:1420"


def build_runtime_payload(store: CredentialStore | None = None) -> dict[str, Any]:
    profile = build_config_runtime_profile(store)
    mode = resolve_runtime_mode()
    shell = _shell_kind()
    web = shell.startswith("browser_")
    production_web = shell == "browser_local_production"
    return {
        "runtime_mode": mode,
        "shell": shell,
        "application_version": __version__,
        "data_directory": profile["data_directory"],
        "database_path": profile["database_path"],
        "frontend_origin": _frontend_origin(),
        "serve_frontend": os.environ.get("STORYLENS_SERVE_FRONTEND", "").lower()
        in {"1", "true", "yes"},
        "bind_host": "127.0.0.1",
        "user_label": "本地网页版" if web else "StoryLens",
        "desktop_capabilities": {
            "tauri_shell": not web,
            "native_updater": not web,
            "native_window_controls": not web,
            "sidecar_lifecycle": not web,
        },
        "web_capabilities": {
            "browser_zoom": web,
            "file_picker_import": True,
            "drag_drop_import": True,
            "open_data_folder_via_api": True,
            "clipboard_copy": True,
            "local_only": True,
        },
        "security": {
            "loopback_only": True,
            "credentials_never_returned": True,
            "body_not_persisted_in_browser": True,
        },
        "config_profile": profile,
        "is_local_web_production": production_web,
    }
