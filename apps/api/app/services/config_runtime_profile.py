"""Describe which config environment the running backend is using.

Cloud switches and ProviderConfiguration live in SQLite (per data root).
API keys live in the OS credential vault (machine-scoped on Windows).
Browser-dev and packaged installs therefore can share credentials while
seeing different enablement flags — this profile makes that explicit.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from app.core import paths
from app.core.paths import (
    default_database_url,
    is_production_runtime,
    user_data_layout,
    user_data_root,
)
from app.services.credentials.base import CredentialStore

RuntimeMode = Literal["browser_dev", "desktop_dev", "packaged"]


def resolve_runtime_mode() -> RuntimeMode:
    if paths.is_frozen():
        return "packaged"
    env = os.environ.get("STORYLENS_APP_ENV", "").lower()
    if env in {"production", "prod", "packaged"}:
        # Tauri sidecar / desktop-dev uses production data roots without freezing.
        return "desktop_dev"
    return "browser_dev"


def packaged_data_root_hint() -> str:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return str(Path(local) / "StoryLens")
    return str(Path.home() / "AppData" / "Local" / "StoryLens")


def build_config_runtime_profile(store: CredentialStore | None = None) -> dict[str, object]:
    layout = user_data_layout()
    root = user_data_root()
    db_path = (layout["database"] / "storylens.db").resolve()
    mode = resolve_runtime_mode()
    production = is_production_runtime()
    store_available = bool(store.available()) if store is not None else False
    store_type = type(store).__name__ if store is not None else "unknown"
    machine_scoped = store_type == "KeyringCredentialStore"
    isolates_from_packaged = not production
    return {
        "runtime_mode": mode,
        "app_env": "production" if production else "development",
        "is_frozen": paths.is_frozen(),
        "data_directory": str(root),
        "database_path": str(db_path),
        "database_url": default_database_url(),
        "isolates_sqlite_from_packaged": isolates_from_packaged,
        "packaged_data_directory_hint": packaged_data_root_hint(),
        "credential_store": {
            "type": store_type,
            "available": store_available,
            "machine_scoped": machine_scoped,
            "returns_secret_to_api": False,
            "shares_with_packaged": machine_scoped,
            "desktop_parity": store_available and machine_scoped,
        },
        "user_message": _user_message(
            mode=mode,
            data_directory=str(root),
            isolates=isolates_from_packaged,
            credential_available=store_available,
            credential_machine_scoped=machine_scoped,
        ),
    }


def _user_message(
    *,
    mode: RuntimeMode,
    data_directory: str,
    isolates: bool,
    credential_available: bool,
    credential_machine_scoped: bool,
) -> str:
    if mode == "browser_dev":
        base = (
            "当前为浏览器开发模式。云端开关与 Provider 启用状态保存在本仓库开发配置库中，"
            f"目录：{data_directory}。"
        )
        if isolates:
            base += (
                f" 与正式版配置目录（{packaged_data_root_hint()}）相互隔离，"
                "开发版启动不会修改正式版已保存的云端/Provider 开关。"
            )
        if credential_available and credential_machine_scoped:
            base += (
                " API Key 存放在本机 Windows 凭据管理器，可能与正式版共用；"
                "因此可能出现「凭据已配置」但当前开发配置库中云端/Provider 仍关闭的情况，"
                "这不代表正式版配置丢失。"
            )
        elif not credential_available:
            base += " 当前凭据保险柜不可用，浏览器模式不会声称具备完整桌面凭据能力。"
        return base
    if mode == "desktop_dev":
        return (
            "当前为桌面开发模式（Tauri sidecar）。"
            f"配置目录：{data_directory}。"
            " 若使用正式版数据目录，请谨慎保存，以免覆盖正式版开关。"
        )
    return f"当前为正式安装版。配置目录：{data_directory}。"
