"""Release guard baselines and updater policy gates."""

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


def _seed_minimal(tmp: Path, version: str = "1.0.3") -> None:
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
        json.dumps(
            {
                "productName": "StoryLens",
                "version": version,
                "plugins": {
                    "updater": {
                        "pubkey": "test",
                        "endpoints": [
                            "https://github.com/fanjack510-ctrl/StoryLens/releases/latest/download/latest.json"
                        ],
                        "windows": {"installMode": "basic"},
                    }
                },
            },
            indent=2,
        )
        + "\n",
    )
    _write(
        tmp / "apps/desktop/src-tauri/Cargo.toml",
        f'[package]\nname = "storylens-desktop"\nversion = "{version}"\n',
    )
    _write(
        tmp / "apps/desktop/src-tauri/Cargo.lock",
        (
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
        '{\n  "version": "{{VERSION}}"\n}\n',
    )
    _write(tmp / "scripts/set_version.ps1", "Write-Host ok\n")
    _write(tmp / "scripts/build_windows_release.ps1", "Write-Host ok\n")
    _write(
        tmp / "apps/desktop/src/components/layout/AppShell.tsx",
        "export function AppShell() { return null }\n",
    )
    _write(
        tmp / "apps/desktop/src/services/updater/preferences.ts",
        "export const DEFAULT_UPDATER_PREFERENCES = {\n"
        "  automatic_check: true,\n"
        "  automatic_download: false,\n"
        "  automatic_install: false,\n"
        "};\n",
    )
    _write(
        tmp / "apps/desktop/src/services/updater/channels.ts",
        'export const STABLE_UPDATE_ENDPOINT = "https://github.com/fanjack510-ctrl/StoryLens/releases/latest/download/latest.json";\n'
        'export const STAGING_UPDATE_ENDPOINT = "https://github.com/fanjack510-ctrl/StoryLens/releases/download/staging/latest.json";\n',
    )
    _write(
        tmp / "apps/desktop/src/services/updaterService.ts",
        "export async function checkForAppUpdate() { return { kind: 'latest' }; }\n"
        "export async function startDownload() { return {}; }\n",
    )


def test_release_guard_fails_when_baseline_missing(tmp_path: Path) -> None:
    _seed_minimal(tmp_path, "1.0.3")
    # Initialize a throwaway git repo so dirty/tag checks are defined.
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=tmp_path, check=True, capture_output=True)

    result = _run(tmp_path, "release-guard")
    assert result.returncode != 0
    assert "missing release baseline" in result.stdout


def test_release_guard_mentions_missing_required_commit(tmp_path: Path) -> None:
    _seed_minimal(tmp_path, "1.0.3")
    _write(
        tmp_path / "docs/releases/1.0.3.md",
        "# 1.0.3\n\nStatus: Unreleased\n",
    )
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=tmp_path, check=True, capture_output=True)

    result = _run(tmp_path, "release-guard")
    assert result.returncode != 0
    assert "required commit MISSING" in result.stdout


def test_repo_baseline_1_0_3_exists() -> None:
    path = ROOT / "docs" / "releases" / "1.0.3.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "Unreleased" in text
    assert "1.0.3" in text


def test_updater_channels_documented() -> None:
    channels = (
        ROOT / "apps/desktop/src/services/updater/channels.ts"
    ).read_text(encoding="utf-8")
    assert "STABLE_UPDATE_ENDPOINT" in channels
    assert "STAGING_UPDATE_ENDPOINT" in channels
    assert channels.count("https://") >= 2
