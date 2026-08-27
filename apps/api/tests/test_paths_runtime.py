from pathlib import Path

import os

import pytest

from app.core import paths


def test_development_data_root_under_repo(monkeypatch, tmp_path):
    monkeypatch.delenv("STORYLENS_DATA_DIR", raising=False)
    monkeypatch.delenv("STORYLENS_APP_ENV", raising=False)
    monkeypatch.setattr(paths, "is_frozen", lambda: False)
    monkeypatch.setattr(paths, "resource_root", lambda: tmp_path)
    paths.user_data_root.cache_clear()

    root = paths.user_data_root()
    assert root == (tmp_path / "data").resolve()
    layout = paths.user_data_layout()
    assert layout["database"] == root
    assert layout["exports"] == root / "exports"


@pytest.mark.skipif(os.name != "nt", reason="Windows LOCALAPPDATA contract")
def test_production_layout_uses_localappdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("STORYLENS_APP_ENV", "production")
    monkeypatch.delenv("STORYLENS_DATA_DIR", raising=False)
    monkeypatch.setattr(paths, "is_frozen", lambda: False)
    paths.user_data_root.cache_clear()

    root = paths.user_data_root()
    assert root == tmp_path / "StoryLens"
    layout = paths.ensure_user_data_dirs()
    assert (layout["database"] / "storylens.db").parent == layout["database"]
    for key in ("database", "logs", "uploads", "exports", "config"):
        assert layout[key].is_dir()


def test_assert_data_dir_writable_fails(monkeypatch, tmp_path):
    monkeypatch.setenv("STORYLENS_DATA_DIR", str(tmp_path / "custom"))
    monkeypatch.setenv("STORYLENS_APP_ENV", "production")
    paths.user_data_root.cache_clear()

    def _raise(path):
        raise RuntimeError(f"DATA_DIR_NOT_WRITABLE: cannot write {path}")

    monkeypatch.setattr(paths, "assert_data_dir_writable", _raise)
    with pytest.raises(RuntimeError, match="DATA_DIR_NOT_WRITABLE"):
        paths.apply_runtime_path_defaults()


def test_data_dir_override(monkeypatch, tmp_path):
    monkeypatch.setenv("STORYLENS_DATA_DIR", str(tmp_path / "custom"))
    paths.user_data_root.cache_clear()
    assert paths.user_data_root() == (tmp_path / "custom").resolve()


def test_macos_production_root_uses_application_support(tmp_path):
    root = paths._production_data_root(
        platform_name="darwin",
        os_name="posix",
        environ={},
        home=tmp_path,
    )
    assert root == tmp_path / "Library" / "Application Support" / "StoryLens"


def test_linux_production_root_honors_xdg_data_home(tmp_path):
    root = paths._production_data_root(
        platform_name="linux",
        os_name="posix",
        environ={"XDG_DATA_HOME": str(tmp_path / "xdg")},
        home=tmp_path,
    )
    assert root == tmp_path / "xdg" / "StoryLens"
