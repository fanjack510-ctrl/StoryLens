# -*- coding: utf-8 -*-
"""Phase 1D-A: single-chapter journey template governance gate tests."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_single_chapter_template_checker_pass() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_single_chapter_journey_template.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "RESULT: PASS" in proc.stdout
    assert "canonical_entry:" in proc.stdout


def test_single_chapter_template_checker_json() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "check_single_chapter_journey_template.py"),
            "--json",
            "--no-write-report",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["result"] == "PASS"
    assert payload["template_version"] == "2.7"
    assert payload["canonical_entry"].endswith("ReaderJourneyWorkspace.tsx")
    assert payload["production_template_entry_count"] == 1
    assert payload["duplicated_template"] is False
    assert payload["checks"]["books_points_to_canonical"] is True
    assert payload["checks"]["standalone_points_to_canonical"] is True
    assert payload["pipeline_reliability_certification_allowed"] is True


def test_template_description_and_report_exist() -> None:
    template = (
        ROOT
        / "audits"
        / "mvp-functional-baseline-v1"
        / "single-chapter-journey-template-v2.7.json"
    )
    assert template.exists()
    data = json.loads(template.read_text(encoding="utf-8"))
    assert data["template_id"] == "reader-journey-single-chapter"
    assert data["template_version"] == "2.7"
    assert len(data["route_adapters"]) == 2
    assert "book-specific-layout" in data["forbidden_special_cases"]

    # Ensure checker writes conformance report
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_single_chapter_journey_template.py")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = (
        ROOT
        / "audits"
        / "mvp-functional-baseline-v1"
        / "single-chapter-template-conformance-report-v2.7.json"
    )
    assert report.exists()
    report_data = json.loads(report.read_text(encoding="utf-8"))
    assert report_data["result"] == "PASS"
    assert report_data["data_independence"]["ui_template_change_requires_model_rerun"] is False


def test_journey_ui_final_freeze_still_pass() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_reader_journey_ui_freeze.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "RESULT: PASS" in proc.stdout
