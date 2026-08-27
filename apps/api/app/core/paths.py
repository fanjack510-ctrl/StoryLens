"""Filesystem roots for development vs packaged desktop applications."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """Bundled read-only resources (prompts, default config)."""
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    # apps/api/app/core/paths.py → repo root
    return Path(__file__).resolve().parents[4]


def is_web_production_mode() -> bool:
    """Formal local web shell (browser → loopback FastAPI SPA)."""
    return os.environ.get("STORYLENS_WEB_MODE", "").lower() in {"1", "true", "yes", "web"}


def is_production_runtime() -> bool:
    if is_web_production_mode():
        return True
    env = os.environ.get("STORYLENS_APP_ENV", "").lower()
    if env in {"production", "prod", "packaged"}:
        return True
    if env in {"development", "dev", "test"}:
        return False
    return is_frozen()


def _production_data_root(
    *,
    platform_name: str | None = None,
    os_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the native per-user application-data root for this platform."""
    platform_name = platform_name or sys.platform
    os_name = os_name or os.name
    environ = environ if environ is not None else os.environ
    home = home or Path.home()
    if platform_name == "darwin":
        return home / "Library" / "Application Support" / "StoryLens"
    if os_name == "nt":
        local = environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "StoryLens"
        return home / "AppData" / "Local" / "StoryLens"
    xdg_data_home = environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home).expanduser() / "StoryLens"
    return home / ".local" / "share" / "StoryLens"


@lru_cache
def user_data_root() -> Path:
    override = os.environ.get("STORYLENS_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if is_production_runtime():
        return _production_data_root()
    return (resource_root() / "data").resolve()


def user_data_layout() -> dict[str, Path]:
    root = user_data_root()
    if is_production_runtime() or os.environ.get("STORYLENS_DATA_DIR"):
        return {
            "root": root,
            "database": root / "database",
            "logs": root / "logs",
            "uploads": root / "uploads",
            "exports": root / "exports",
            "config": root / "config",
        }
    return {
        "root": root,
        "database": root,
        "logs": root / "runtime" / "logs",
        "uploads": root / "uploads",
        "exports": root / "exports",
        "config": resource_root() / "config",
    }


def ensure_user_data_dirs() -> dict[str, Path]:
    layout = user_data_layout()
    for path in layout.values():
        path.mkdir(parents=True, exist_ok=True)
    return layout


def assert_data_dir_writable(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".storylens_write_probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        raise RuntimeError(
            f"DATA_DIR_NOT_WRITABLE: 无法写入数据目录 {path}: {exc}"
        ) from exc


def default_database_url() -> str:
    layout = ensure_user_data_dirs()
    db_path = (layout["database"] / "storylens.db").resolve()
    return f"sqlite:///{db_path.as_posix()}"


def default_prompt_root() -> str:
    return str((resource_root() / "packages" / "prompts").resolve())


def default_formula_path() -> str:
    bundled = resource_root() / "config" / "reader_journey_formulas.json"
    if bundled.is_file():
        return str(bundled.resolve())
    user_copy = user_data_layout()["config"] / "reader_journey_formulas.json"
    return str(user_copy.resolve())


def maybe_migrate_legacy_database(target: Path) -> None:
    """Copy legacy DB once when production path is empty and STORYLENS_LEGACY_DATABASE_PATH is set."""
    if target.exists():
        return
    legacy = os.environ.get("STORYLENS_LEGACY_DATABASE_PATH")
    if not legacy:
        return
    source = Path(legacy)
    if not source.is_file():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    import shutil

    shutil.copy2(source, target)


def apply_runtime_path_defaults() -> dict[str, Path]:
    """Set STORYLENS_* path env vars when unset. Safe to call before Settings load."""
    layout = ensure_user_data_dirs()
    assert_data_dir_writable(layout["root"])
    assert_data_dir_writable(layout["database"])
    assert_data_dir_writable(layout["logs"])

    db_path = layout["database"] / "storylens.db"
    maybe_migrate_legacy_database(db_path)

    os.environ.setdefault("STORYLENS_DATABASE_URL", default_database_url())
    os.environ.setdefault("STORYLENS_PROMPT_ROOT", default_prompt_root())
    os.environ.setdefault(
        "STORYLENS_READER_JOURNEY_FORMULA_PATH",
        default_formula_path(),
    )
    os.environ.setdefault("STORYLENS_DATA_DIR", str(layout["root"]))
    os.environ.setdefault("STORYLENS_LOG_DIR", str(layout["logs"]))
    os.environ.setdefault("STORYLENS_UPLOADS_DIR", str(layout["uploads"]))
    os.environ.setdefault("STORYLENS_EXPORTS_DIR", str(layout["exports"]))
    os.environ.setdefault("STORYLENS_CONFIG_DIR", str(layout["config"]))

    # Relative Path("config/...") lookups resolve against resource root in packaged mode.
    if is_frozen():
        os.chdir(resource_root())

    return layout


def get_project_root() -> Path:
    return resource_root()
