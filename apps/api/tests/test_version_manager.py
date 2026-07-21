"""Tests for scripts/version_manager.py — always use a temp fixture tree."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
VM = ROOT / "scripts" / "version_manager.py"


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VM), "--root", str(root), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _seed_fixture(tmp: Path, version: str = "1.0.1") -> None:
    _write(tmp / "VERSION", f"{version}\n")
    _write(
        tmp / "apps/desktop/package.json",
        json.dumps({"name": "storylens-desktop", "version": version}, indent=2) + "\n",
    )
    lock = {
        "name": "storylens-desktop",
        "version": version,
        "lockfileVersion": 3,
        "packages": {"": {"name": "storylens-desktop", "version": version}},
    }
    _write(tmp / "apps/desktop/package-lock.json", json.dumps(lock, indent=2) + "\n")
    _write(
        tmp / "apps/desktop/src-tauri/tauri.conf.json",
        json.dumps({"productName": "StoryLens", "version": version}, indent=2) + "\n",
    )
    _write(
        tmp / "apps/desktop/src-tauri/Cargo.toml",
        f'[package]\nname = "storylens-desktop"\nversion = "{version}"\n',
    )
    _write(
        tmp / "apps/desktop/src-tauri/Cargo.lock",
        (
            "[[package]]\n"
            'name = "other"\n'
            'version = "9.9.9"\n\n'
            "[[package]]\n"
            'name = "storylens-desktop"\n'
            f'version = "{version}"\n'
            "dependencies = []\n"
        ),
    )
    _write(tmp / "pyproject.toml", f'[project]\nname = "storylens"\nversion = "{version}"\n')
    _write(tmp / "apps/api/app/__init__.py", f'__version__ = "{version}"\n')
    _write(
        tmp / "apps/api/app/main.py",
        'from app import __version__\n\napp = FastAPI(title="StoryLens API", version=__version__)\n',
    )
    _write(
        tmp / "packaging/updater/latest.json.template",
        '{\n  "version": "{{VERSION}}",\n  "notes": "StoryLens {{VERSION}}"\n}\n',
    )
    _write(
        tmp / "scripts/set_version.ps1",
        'Write-Host "delegates to version_manager.py"\n',
    )
    _write(
        tmp / "scripts/build_windows_release.ps1",
        'Write-Host "runs version_manager.py check before build"\n',
    )
    _write(
        tmp / "apps/desktop/src/components/layout/AppShell.tsx",
        'export function AppShell() { return <p>StoryLens</p>; }\n',
    )


@pytest.fixture()
def fixture_root(tmp_path: Path) -> Path:
    _seed_fixture(tmp_path, "1.0.1")
    return tmp_path


def test_show_returns_1_0_1(fixture_root: Path) -> None:
    result = _run(fixture_root, "show")
    assert result.returncode == 0, result.stderr
    assert "Current version: 1.0.1" in result.stdout


def test_check_passes_when_consistent(fixture_root: Path) -> None:
    result = _run(fixture_root, "check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Version check passed: 1.0.1" in result.stdout


def test_check_fails_on_single_file_mismatch(fixture_root: Path) -> None:
    pkg = fixture_root / "apps/desktop/package.json"
    pkg.write_text(
        json.dumps({"name": "storylens-desktop", "version": "9.9.9"}, indent=2) + "\n",
        encoding="utf-8",
    )
    result = _run(fixture_root, "check")
    assert result.returncode != 0
    assert "package.json" in result.stdout
    assert "expected: 1.0.1" in result.stdout
    assert "actual:   9.9.9" in result.stdout


def test_bump_patch_minor_major(fixture_root: Path) -> None:
    r1 = _run(fixture_root, "bump", "patch")
    assert r1.returncode == 0, r1.stdout + r1.stderr
    assert (fixture_root / "VERSION").read_text(encoding="utf-8").strip() == "1.0.2"
    assert '"version": "1.0.2"' in (fixture_root / "apps/desktop/package.json").read_text(
        encoding="utf-8"
    )

    r2 = _run(fixture_root, "bump", "minor")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert (fixture_root / "VERSION").read_text(encoding="utf-8").strip() == "1.1.0"

    r3 = _run(fixture_root, "bump", "major")
    assert r3.returncode == 0, r3.stdout + r3.stderr
    assert (fixture_root / "VERSION").read_text(encoding="utf-8").strip() == "2.0.0"


def test_rejects_illegal_semver(fixture_root: Path) -> None:
    for bad in ("", "v1.2.0", "1.2", "not-a-version"):
        result = _run(fixture_root, "set", bad)
        assert result.returncode != 0, bad
    # Fixture must remain unchanged.
    assert (fixture_root / "VERSION").read_text(encoding="utf-8").strip() == "1.0.1"


def test_rejects_downgrade_without_flag(fixture_root: Path) -> None:
    result = _run(fixture_root, "set", "1.0.0")
    assert result.returncode != 0
    assert "downgrade" in (result.stdout + result.stderr).lower()
    assert (fixture_root / "VERSION").read_text(encoding="utf-8").strip() == "1.0.1"


def test_sync_only_touches_version_fields(fixture_root: Path) -> None:
    tauri = fixture_root / "apps/desktop/src-tauri/tauri.conf.json"
    original = {
        "productName": "StoryLens",
        "version": "1.0.1",
        "bundle": {"active": True, "extra": "keep-me"},
    }
    tauri.write_text(json.dumps(original, indent=2) + "\n", encoding="utf-8")
    cargo_lock = fixture_root / "apps/desktop/src-tauri/Cargo.lock"
    before_lock = cargo_lock.read_text(encoding="utf-8")
    assert 'name = "other"\nversion = "9.9.9"' in before_lock

    (fixture_root / "VERSION").write_text("1.0.2\n", encoding="utf-8")
    result = _run(fixture_root, "sync")
    assert result.returncode == 0, result.stdout + result.stderr

    after = json.loads(tauri.read_text(encoding="utf-8"))
    assert after["version"] == "1.0.2"
    assert after["productName"] == "StoryLens"
    assert after["bundle"]["extra"] == "keep-me"
    after_lock = cargo_lock.read_text(encoding="utf-8")
    assert 'name = "other"\nversion = "9.9.9"' in after_lock
    assert 'name = "storylens-desktop"\nversion = "1.0.2"' in after_lock


def test_release_info_output(fixture_root: Path) -> None:
    result = _run(fixture_root, "release-info")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {
        "current_version": "1.0.1",
        "next_patch": "1.0.2",
        "next_minor": "1.1.0",
        "next_major": "2.0.0",
        "tag": "v1.0.1",
        "installer_name": "StoryLens_1.0.1_x64-setup.exe",
    }


def test_build_gate_intercepts_version_conflict(fixture_root: Path) -> None:
    """Mirrors check_project / release build gate: check must fail on conflict."""
    pkg = fixture_root / "apps/desktop/src-tauri/Cargo.toml"
    pkg.write_text('[package]\nname = "storylens-desktop"\nversion = "0.1.0"\n', encoding="utf-8")
    result = _run(fixture_root, "check")
    assert result.returncode != 0
    assert "Cargo.toml" in result.stdout


def test_ui_hardcode_detection(fixture_root: Path) -> None:
    shell = fixture_root / "apps/desktop/src/components/layout/AppShell.tsx"
    shell.write_text('export const x = "1.0.0-rc1";\n', encoding="utf-8")
    result = _run(fixture_root, "check")
    assert result.returncode != 0
    assert "UI hardcode" in result.stdout
    assert "1.0.0-rc1" in result.stdout


def test_bump_does_not_mutate_real_repo() -> None:
    """Safety: real VERSION stays 1.0.1 after suite (fixture-only bumps)."""
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "1.0.1"


def test_real_repo_check_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(VM), "check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
