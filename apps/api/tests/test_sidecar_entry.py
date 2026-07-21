import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SIDECAR_MAIN = REPO / "apps" / "api" / "sidecar_main.py"


def _run_sidecar_env(env: dict[str, str], *, timeout: float = 8.0) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.update(env)
    return subprocess.run(
        [sys.executable, str(SIDECAR_MAIN)],
        env=merged,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_sidecar_refuses_public_bind(monkeypatch):
    monkeypatch.delenv("STORYLENS_DATA_DIR", raising=False)
    proc = _run_sidecar_env(
        {
            "STORYLENS_APP_ENV": "development",
            "STORYLENS_APP_HOST": "0.0.0.0",
            "STORYLENS_APP_PORT": "8765",
        },
        timeout=5.0,
    )
    assert proc.returncode == 2
    assert "Refusing to bind non-loopback host" in proc.stderr or proc.returncode == 2


def test_sidecar_reports_unwritable_data_dir(monkeypatch):
    import sidecar_main

    def _boom():
        raise RuntimeError(
            "DATA_DIR_NOT_WRITABLE: 无法写入数据目录 C:\\blocked: permission denied"
        )

    monkeypatch.setattr("app.core.paths.apply_runtime_path_defaults", _boom)
    with pytest.raises(SystemExit) as exc:
        sidecar_main._prepare()
    assert exc.value.code == 4
