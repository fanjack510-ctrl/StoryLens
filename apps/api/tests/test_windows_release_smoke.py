import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TAURI_CONF = REPO / "apps" / "desktop" / "src-tauri" / "tauri.conf.json"
BUILD_SCRIPT = REPO / "scripts" / "build_windows_release.ps1"
SMOKE_SCRIPT = REPO / "scripts" / "smoke_windows_release.ps1"
STOP_TREE_SCRIPT = REPO / "scripts" / "stop_owned_process_tree.ps1"
BACKEND_RS = REPO / "apps" / "desktop" / "src-tauri" / "src" / "backend.rs"
MAIN_RS = REPO / "apps" / "desktop" / "src-tauri" / "src" / "main.rs"
WIN_LIFE_RS = REPO / "apps" / "desktop" / "src-tauri" / "src" / "win_lifecycle.rs"
MAIN_PY = REPO / "apps" / "api" / "app" / "main.py"


def test_updater_config_loadable():
    raw = TAURI_CONF.read_text(encoding="utf-8")
    conf = json.loads(raw)
    updater = conf.get("plugins", {}).get("updater", {})
    assert updater.get("pubkey"), "updater pubkey must be configured"
    endpoints = updater.get("endpoints") or []
    assert endpoints, "updater endpoints required"
    assert all(str(url).startswith("https://") for url in endpoints)


def test_release_build_skips_signing_without_secret():
    text = BUILD_SCRIPT.read_text(encoding="utf-8")
    assert "createUpdaterArtifacts" in text
    assert "skipped_no_secret" in text
    assert "No updater signing key" in text
    assert "TAURI_SIGNING_PRIVATE_KEY" in text


def test_set_version_script_exists():
    script = REPO / "scripts" / "set_version.ps1"
    assert script.is_file()
    body = script.read_text(encoding="utf-8")
    assert "tauri.conf.json" in body
    assert "apps/api/app/main.py" in body or "apps\\api\\app\\main.py" in body


def test_no_private_key_patterns_in_tauri_conf():
    raw = TAURI_CONF.read_text(encoding="utf-8")
    assert "BEGIN PRIVATE KEY" not in raw
    assert "BEGIN RSA PRIVATE KEY" not in raw


def test_build_summary_schema_when_present():
    summary_path = REPO / "dist" / "release" / "build-summary.json"
    if not summary_path.is_file():
        return
    data = json.loads(summary_path.read_text(encoding="utf-8-sig"))
    assert data.get("version")
    assert data.get("sidecar") == "ok"
    assert data.get("tauri") == "ok"
    updater = data.get("updater_artifacts")
    assert updater in {"enabled", "skipped", "skipped_no_secret"}
    if not os.environ.get("TAURI_SIGNING_PRIVATE_KEY"):
        assert updater != "enabled", "local build must not claim signed updater without secret"


def test_smoke_cleans_sidecar_by_owned_pids_only():
    """Smoke must stop only PIDs it started; never batch-kill by process name."""
    smoke = SMOKE_SCRIPT.read_text(encoding="utf-8")
    stop_tree = STOP_TREE_SCRIPT.read_text(encoding="utf-8")

    assert STOP_TREE_SCRIPT.is_file()
    assert "stop_owned_process_tree.ps1" in smoke
    assert "Stop-Process -Id" in stop_tree
    assert "ExactProcessIds" in stop_tree
    assert "Get-PidsByExecutablePath" in smoke
    assert "Get-NewPidsByPath" in smoke
    assert "baselinePathPids" in smoke
    assert re.search(r"Stop-Process\s+-Name", smoke) is None
    assert re.search(r"Stop-Process\s+-Name", stop_tree) is None
    assert "taskkill" not in smoke.lower()
    assert re.search(r"Stop-Process\s+-Name", BUILD_SCRIPT.read_text(encoding="utf-8")) is None


def test_smoke_requires_residual_sidecar_gate():
    smoke = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "Residual sidecar" in smoke
    assert "finally" in smoke
    assert "Start-Process" in smoke
    assert "SMOKE OK" in smoke
    # Residual must fail the run before SMOKE OK can print.
    assert "smokeFailed" in smoke
    build = BUILD_SCRIPT.read_text(encoding="utf-8")
    assert "do not launch the sidecar process here" in build
    assert "smoke_windows_release.ps1" in build


def test_build_windows_release_does_not_launch_sidecar_process():
    build = BUILD_SCRIPT.read_text(encoding="utf-8")
    assert "Start-Process" not in build
    assert "build_sidecar.ps1" in build
    assert "smoke_windows_release.ps1" in build


def test_desktop_lifecycle_contracts():
    backend = BACKEND_RS.read_text(encoding="utf-8")
    main_rs = MAIN_RS.read_text(encoding="utf-8")
    main_py = MAIN_PY.read_text(encoding="utf-8")

    assert "SidecarLifecycle" in backend
    assert "stop_lifecycle" in backend
    assert "/internal/shutdown" in backend
    assert "path_delta_pids" in backend
    assert "owned_pids" in backend
    assert "STORYLENS_SHUTDOWN_TOKEN" in backend
    assert "KILL_ON_JOB_CLOSE" in WIN_LIFE_RS.read_text(encoding="utf-8") or "JobHandle" in backend
    assert "RunEvent::Exit" in main_rs
    assert "ExitRequested" in main_rs
    assert "CloseRequested" in main_rs
    assert "/internal/shutdown" in main_py
    assert "request_shutdown" in main_py


@pytest.mark.skipif(sys.platform != "win32", reason="Windows process-tree helper")
def test_stop_owned_process_tree_stops_recorded_pid_only():
    """Runtime check: helper ends the started PID tree and leaves no residual."""
    child = subprocess.Popen(
        ["powershell", "-NoProfile", "-Command", "Start-Sleep -Seconds 120"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    root_pid = child.pid
    try:
        assert child.poll() is None
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(STOP_TREE_SCRIPT),
                "-RootProcessId",
                str(root_pid),
                "-WaitMs",
                "8000",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr or completed.stdout
        deadline = time.time() + 5
        while time.time() < deadline and child.poll() is None:
            time.sleep(0.1)
        assert child.poll() is not None, f"residual test process PID {root_pid}"
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows onefile orphan simulation")
def test_path_delta_cleanup_stops_orphan_after_wrapper_exit(tmp_path):
    """Simulate PyInstaller onefile: wrapper exits, service child remains; path-delta cleanup must stop it.

    Does not kill a pre-existing baseline process with a different identity.
    """
    marker = tmp_path / "service_alive.txt"
    service_py = tmp_path / "service.py"
    wrapper_py = tmp_path / "wrapper.py"
    service_py.write_text(
        "import time\n"
        f"from pathlib import Path\n"
        f"Path(r'''{marker}''').write_text('1')\n"
        "time.sleep(120)\n",
        encoding="utf-8",
    )
    wrapper_py.write_text(
        "import subprocess, sys, time\n"
        f"child = subprocess.Popen([sys.executable, r'''{service_py}'''])\n"
        "time.sleep(0.8)\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )

    py = sys.executable
    baseline = _pids_for_path(py)

    other = subprocess.Popen(
        [py, "-c", "import time; time.sleep(120)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.3)
        baseline_with_other = set(_pids_for_path(py))

        wrapper = subprocess.Popen(
            [py, str(wrapper_py)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        wrapper.wait(timeout=15)
        assert wrapper.returncode == 0

        deadline = time.time() + 10
        while time.time() < deadline and not marker.is_file():
            time.sleep(0.1)
        assert marker.is_file(), "orphan service child did not start"

        current = _pids_for_path(py)
        owned_new = [p for p in current if p not in baseline_with_other]
        assert owned_new, "expected new same-path PID(s) for orphan service"
        assert other.pid not in owned_new

        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(STOP_TREE_SCRIPT),
                "-ExactProcessIds",
                ",".join(str(p) for p in owned_new),
                "-WaitMs",
                "10000",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr or completed.stdout

        for pid in owned_new:
            assert not _pid_alive(pid), f"orphan PID {pid} still alive after path-delta cleanup"

        assert other.poll() is None, "cleanup must not stop pre-existing baseline process"
    finally:
        if other.poll() is None:
            other.kill()
            other.wait(timeout=5)
        leftover = [p for p in _pids_for_path(py) if p not in set(baseline) and p != other.pid]
        if leftover:
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(STOP_TREE_SCRIPT),
                    "-ExactProcessIds",
                    ",".join(str(p) for p in leftover),
                    "-WaitMs",
                    "5000",
                ],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )


def _pids_for_path(exe: str) -> list[int]:
    ps = f"""
$ErrorActionPreference = 'Stop'
$target = [System.IO.Path]::GetFullPath('{exe}').TrimEnd('\\','/').ToLowerInvariant()
$ids = @()
foreach ($row in @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)) {{
  if (-not $row.ExecutablePath) {{ continue }}
  try {{ $ep = [System.IO.Path]::GetFullPath([string]$row.ExecutablePath) }} catch {{ $ep = [string]$row.ExecutablePath }}
  if ($ep.TrimEnd('\\','/').ToLowerInvariant() -eq $target) {{ $ids += [int]$row.ProcessId }}
}}
$ids -join ','
"""
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    raw = (completed.stdout or "").strip()
    if not raw:
        return []
    return [int(x) for x in raw.split(",") if x.strip()]


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{ '1' }} else {{ '0' }}",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return (completed.stdout or "").strip() == "1"


def test_internal_shutdown_endpoint_contract():
    from fastapi.testclient import TestClient

    from app.core.sidecar_control import reset_shutdown_state_for_tests
    from app.main import app

    reset_shutdown_state_for_tests()
    client = TestClient(app)
    os.environ["STORYLENS_SHUTDOWN_TOKEN"] = "test-token-xyz"
    try:
        denied = client.post("/internal/shutdown")
        assert denied.status_code == 401
        ok = client.post(
            "/internal/shutdown",
            headers={"Authorization": "Bearer test-token-xyz"},
        )
        assert ok.status_code == 200
        assert ok.json().get("status") == "shutting_down"
    finally:
        os.environ.pop("STORYLENS_SHUTDOWN_TOKEN", None)
        reset_shutdown_state_for_tests()
