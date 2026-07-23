"""Build-gate / stale-dist tests for scripts/start_storylens_web.ps1."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
START_WEB = ROOT / "scripts" / "start_storylens_web.ps1"
PWSH = shutil.which("pwsh") or shutil.which("powershell")


def _port_listening(port: int) -> bool:
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"(Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | Measure-Object).Count",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return int((proc.stdout or "0").strip() or "0") > 0
    except ValueError:
        return False


@pytest.fixture(scope="module")
def require_pwsh() -> str:
    if not PWSH:
        pytest.skip("PowerShell not available")
    return PWSH


def _write_failing_desktop(tmp: Path) -> None:
    desktop = tmp / "apps" / "desktop"
    desktop.mkdir(parents=True)
    (desktop / "package.json").write_text(
        json.dumps(
            {
                "name": "storylens-desktop-gate-test",
                "private": True,
                "scripts": {"build": "node -e \"process.exit(2)\""},
            }
        ),
        encoding="utf-8",
    )
    dist = desktop / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>stale</title>", encoding="utf-8")
    (dist / "storylens-frontend-build.json").write_text(
        json.dumps(
            {
                "source_commit": "stale-commit",
                "build_time": "2020-01-01T00:00:00Z",
                "application_version": "1.0.4",
            }
        ),
        encoding="utf-8",
    )


def _link_venv(tmp: Path) -> None:
    src = ROOT / ".venv"
    if not src.is_dir():
        pytest.skip("project .venv missing")
    dest = tmp / ".venv"
    try:
        os.symlink(src, dest, target_is_directory=True)
    except OSError:
        # Windows without symlink privilege: junction via cmd
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(dest), str(src)],
            check=True,
            capture_output=True,
            text=True,
        )


def test_script_fail_fast_patterns(require_pwsh: str) -> None:
    text = START_WEB.read_text(encoding="utf-8-sig")
    assert "LASTEXITCODE" in text
    assert "前端构建失败，未启动StoryLens" in text
    assert "storylens-frontend-build.json" in text
    assert "Assert-FrontendDistFresh" in text
    assert "ProjectRoot" in text
    # Must not treat "dist exists" as success after failed build.
    assert "exit $buildExit" in text


def test_build_failure_does_not_start_or_listen(tmp_path: Path, require_pwsh: str) -> None:
    port = 18765
    if _port_listening(port):
        pytest.skip(f"port {port} already in use")
    _write_failing_desktop(tmp_path)
    _link_venv(tmp_path)
    # Ensure git identity exists for later stale checks in other tests.
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "--allow-empty", "-m", "t"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    proc = subprocess.run(
        [
            require_pwsh,
            "-NoProfile",
            "-File",
            str(START_WEB),
            "-Port",
            str(port),
            "-NoBrowser",
            "-ProjectRoot",
            str(tmp_path),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode != 0
    assert "前端构建失败，未启动StoryLens" in combined
    assert "StoryLens local web started." not in combined
    time.sleep(0.5)
    assert not _port_listening(port)


def test_stale_dist_skip_build_does_not_start(tmp_path: Path, require_pwsh: str) -> None:
    port = 18766
    if _port_listening(port):
        pytest.skip(f"port {port} already in use")
    _write_failing_desktop(tmp_path)
    _link_venv(tmp_path)
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "--allow-empty", "-m", "t"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    # Keep stale meta different from HEAD
    meta_path = tmp_path / "apps" / "desktop" / "dist" / "storylens-frontend-build.json"
    meta_path.write_text(
        json.dumps(
            {
                "source_commit": "not-" + head,
                "build_time": "2020-01-01T00:00:00Z",
                "application_version": "1.0.4",
            }
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            require_pwsh,
            "-NoProfile",
            "-File",
            str(START_WEB),
            "-Port",
            str(port),
            "-NoBrowser",
            "-SkipBuild",
            "-ProjectRoot",
            str(tmp_path),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode != 0
    assert "不是当前源码" in combined or "未启动 StoryLens" in combined
    assert "StoryLens local web started." not in combined
    time.sleep(0.5)
    assert not _port_listening(port)


def test_idempotent_healthy_reuse_still_short_circuits(require_pwsh: str) -> None:
    """If 8765 is already healthy StoryLens, script must exit 0 without rebuild."""
    try:
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=2) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        if body.get("status") != "ok":
            pytest.skip("8765 not healthy StoryLens")
    except Exception:
        pytest.skip("8765 not running")

    proc = subprocess.run(
        [
            require_pwsh,
            "-NoProfile",
            "-File",
            str(START_WEB),
            "-Port",
            "8765",
            "-NoBrowser",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0
    assert "already running" in combined.lower() or "already healthy" in combined.lower()
