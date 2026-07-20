# -*- coding: utf-8 -*-
"""Phase 1C-C.2.5.2-Hygiene: CRLF restore, thaw v2-2, readonly audit side-effect tests."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.freeze_hygiene_lf import (  # noqa: E402
    RestoreRejected,
    restore_file_to_lf,
    sha256_bytes,
    validate_crlf_only_restore,
)
from tests.optional_gates import require_main_db_cert_counts, skip_outdated_freeze


def test_crlf_normalize_matching_baseline_allows_restore(tmp_path: Path) -> None:
    baseline_text = b"hello\nworld\n"
    baseline_sha = sha256_bytes(baseline_text)
    path = tmp_path / "sample.py"
    path.write_bytes(b"hello\r\nworld\r\n")
    assert sha256_bytes(path.read_bytes()) != baseline_sha
    report = restore_file_to_lf(path, baseline_sha)
    assert report["after_sha256"] == baseline_sha
    assert path.read_bytes() == baseline_text


def test_visible_char_change_rejects_restore(tmp_path: Path) -> None:
    baseline = b"alpha\n"
    baseline_sha = sha256_bytes(baseline)
    path = tmp_path / "changed.py"
    path.write_bytes(b"beta\r\n")
    with pytest.raises(RestoreRejected):
        validate_crlf_only_restore(path.read_bytes(), baseline_sha256=baseline_sha)


def test_bom_change_rejects_restore() -> None:
    # LF body matches baseline but adding UTF-8 BOM must not be accepted as CRLF-only.
    body = b"line\n"
    baseline_sha = sha256_bytes(body)
    with_bom_crlf = b"\xef\xbb\xbf" + b"line\r\n"
    # LF-normalized still has BOM → hash != baseline without BOM
    with pytest.raises(RestoreRejected):
        validate_crlf_only_restore(with_bom_crlf, baseline_sha256=baseline_sha)


@pytest.mark.freeze_baseline
def test_check_core_freeze_raw_pass() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_core_freeze.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    skip_outdated_freeze(proc.returncode, proc.stdout, gate="check_core_freeze")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "RESULT: PASS" in proc.stdout
    assert "FROZEN_CORE: unchanged=" in proc.stdout
    assert "modified=0" in proc.stdout.split("FROZEN_CORE:")[1].splitlines()[0]


@pytest.mark.freeze_baseline
def test_thaw_checker_reads_v2_2() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_ui_presentation_thaw.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    skip_outdated_freeze(proc.returncode, proc.stdout, gate="check_ui_presentation_thaw")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "ui-presentation-thaw-v2-2.json" in proc.stdout
    assert "ui-presentation-thaw-v2-3.json" in proc.stdout
    assert "ui-presentation-thaw-v2-6.json" in proc.stdout
    assert "RESULT: PASS" in proc.stdout


def test_frozen_core_cannot_enter_ui_thaw(tmp_path: Path) -> None:
    bad = {
        "thaw_id": "ui-presentation-thaw-v2-2-bad",
        "allowed_files": [
            {
                "path": "apps/api/app/services/reader_journey_semantic_calibrate.py",
                "before_sha256": None,
                "reason": "illegal",
                "allowed_change": "none",
                "new_file": True,
            }
        ],
    }
    path = tmp_path / "bad-thaw.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "check_ui_presentation_thaw.py"),
            "--thaw-manifest",
            str(ROOT / "audits/mvp-functional-baseline-v1/ui-presentation-thaw-v1.json"),
            "--thaw-manifest",
            str(path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "must not list FROZEN_CORE/CONTRACT" in proc.stdout


@pytest.mark.freeze_baseline
def test_readonly_audit_default_zero_file_writes(tmp_path: Path) -> None:
    require_main_db_cert_counts()
    baseline = ROOT / "audits/mvp-functional-baseline-v1/database-baseline.json"
    before_sha = sha256_bytes(baseline.read_bytes())
    before_mtime = baseline.stat().st_mtime_ns
    db = ROOT / "data" / "storylens.db"
    db_mtime = db.stat().st_mtime_ns
    db_sha = sha256_bytes(db.read_bytes())

    proc = subprocess.run(
        [sys.executable, str(ROOT / "audits/mvp-functional-baseline-v1/_readonly_audit.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "zero file writes" in proc.stdout
    assert sha256_bytes(baseline.read_bytes()) == before_sha
    assert baseline.stat().st_mtime_ns == before_mtime
    assert db.stat().st_mtime_ns == db_mtime
    assert sha256_bytes(db.read_bytes()) == db_sha


@pytest.mark.freeze_baseline
def test_readonly_audit_output_writes_new_and_refuses_overwrite(tmp_path: Path) -> None:
    require_main_db_cert_counts()
    out = tmp_path / "audit-out.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "audits/mvp-functional-baseline-v1/_readonly_audit.py"),
            "--output",
            str(out),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert out.exists()
    first = out.read_bytes()

    proc2 = subprocess.run(
        [
            sys.executable,
            str(ROOT / "audits/mvp-functional-baseline-v1/_readonly_audit.py"),
            "--output",
            str(out),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc2.returncode != 0
    assert "refusing overwrite" in proc2.stdout
    assert out.read_bytes() == first
