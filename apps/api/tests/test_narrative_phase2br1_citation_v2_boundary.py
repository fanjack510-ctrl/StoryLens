"""CHG-058 — Live citation V2 static boundary."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from app.narrative_core.services.citation_evidence_enrichment_v2 import (
    assert_v2_path_forbids_quote_fallback,
)


def test_live_citation_v2_boundary_script() -> None:
    root = Path(__file__).resolve().parents[3]
    script = root / "scripts" / "check_live_citation_v2_boundary.py"
    assert script.is_file()
    proc = subprocess.run(
        [sys.executable, str(script), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "LIVE CITATION V2 BOUNDARY OK" in proc.stdout


def test_assert_v2_path_forbids_quote_fallback() -> None:
    assert_v2_path_forbids_quote_fallback()
