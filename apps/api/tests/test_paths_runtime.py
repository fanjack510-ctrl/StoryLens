from pathlib import Path

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


def test_data_dir_override(monkeypatch, tmp_path):
    monkeypatch.setenv("STORYLENS_DATA_DIR", str(tmp_path / "custom"))
    paths.user_data_root.cache_clear()
    assert paths.user_data_root() == (tmp_path / "custom").resolve()
