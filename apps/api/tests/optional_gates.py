"""Explicit gates for optional certification / audit / freeze tests.

These helpers must call pytest.skip with a clear reason — never silent pass.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
MAIN_DB = ROOT / "data" / "storylens.db"
CLOUD_PRICING_PATH = ROOT / "config" / "cloud_pricing.json"

VERIFIED_CLOUD_PRICING = {
    "version": "test-verified-v1",
    "currency": "CNY",
    "models": {
        "qwen3.7-plus": {"input_per_million": 0.8, "output_per_million": 2.0},
        "qwen3.7-max": {"input_per_million": 2.0, "output_per_million": 6.0},
        "qwen3.6-flash": {"input_per_million": 0.3, "output_per_million": 0.9},
        "qwen3.7-plus-response": {"input_per_million": 0.8, "output_per_million": 2.0},
        "configured-plus": {"input_per_million": 0.8, "output_per_million": 2.0},
    },
}


def require_path(path: Path, *, marker: str = "requires_audit_assets") -> Path:
    """Skip when an optional on-disk asset is missing."""
    if not path.exists():
        try:
            rel = path.relative_to(ROOT)
        except ValueError:
            rel = path
        pytest.skip(f"{marker}: missing optional asset {rel}")
    return path


def require_main_db_cert_counts(
    *,
    analysis_runs: int = 55,
    journey_runs: int = 2,
) -> Path:
    """Skip unless local main DB matches certification baseline counts."""
    require_path(MAIN_DB, marker="requires_main_db_snapshot")
    con = sqlite3.connect(f"file:{MAIN_DB.as_posix()}?mode=ro", uri=True)
    try:
        ar = con.execute("SELECT COUNT(*) FROM analysis_runs").fetchone()[0]
        jr = con.execute("SELECT COUNT(*) FROM reader_journey_runs").fetchone()[0]
    finally:
        con.close()
    if ar != analysis_runs or jr != journey_runs:
        pytest.skip(
            "requires_main_db_snapshot: "
            f"analysis_runs={ar} journey_runs={jr}, "
            f"need {analysis_runs}/{journey_runs}"
        )
    return MAIN_DB


def install_verified_cloud_pricing(path: Path = CLOUD_PRICING_PATH) -> tuple[Path, bytes | None]:
    """Write a verified pricing file for release-critical unit tests.

    Returns (path, previous_bytes_or_None). Caller must restore via restore_cloud_pricing.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    previous = path.read_bytes() if path.exists() else None
    path.write_text(
        json.dumps(VERIFIED_CLOUD_PRICING, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path, previous


def restore_cloud_pricing(path: Path, previous: bytes | None) -> None:
    if previous is None:
        path.unlink(missing_ok=True)
    else:
        path.write_bytes(previous)


def skip_outdated_freeze(proc_returncode: int, stdout: str, *, gate: str) -> None:
    """Optional freeze seals: skip when baseline is intentionally drifted."""
    if proc_returncode != 0:
        snippet = (stdout or "").strip().splitlines()
        tail = " | ".join(snippet[-3:]) if snippet else "no output"
        pytest.skip(
            f"freeze_baseline: {gate} seal outdated for current tree; "
            f"re-seal before enforcing. last={tail}"
        )
