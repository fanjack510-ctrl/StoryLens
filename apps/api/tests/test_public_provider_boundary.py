"""CHG-057 — Public provider boundary static scan."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_public_provider_boundary_script() -> None:
    root = Path(__file__).resolve().parents[3]
    script = root / "scripts" / "check_public_provider_boundary.py"
    assert script.is_file()
    proc = subprocess.run(
        [sys.executable, str(script), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PUBLIC PROVIDER BOUNDARY OK" in proc.stdout
