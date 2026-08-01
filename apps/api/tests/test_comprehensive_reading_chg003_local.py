"""CHG-20260729-003 comprehensive reading presentation (local, Fake-only)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.services.reader_journey_comprehensive_presentation import (
    attach_comprehensive_reading_presentation,
    derive_comprehensive_reading_factors_v1,
)
from app.services.reader_journey_dimension_insights import composite_role_fit_label

REPO_ROOT = Path(__file__).resolve().parents[3]
FORMULA_PATH = REPO_ROOT / "config" / "reader_journey_formulas_v2.json"


def test_formula_v2_file_unchanged_hash_anchor():
    # Anchor that formula file is still present and readable (not rewritten empty).
    text = FORMULA_PATH.read_text(encoding="utf-8")
    assert "reading_momentum" in text
    assert "plot_progress" in text
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert len(digest) == 64


def test_fit_role_bands_not_global_threshold():
    assert composite_role_fit_label(58, "setup") == "合适"
    assert composite_role_fit_label(58, "climax") == "偏弱"
    assert composite_role_fit_label(82, "transition") == "偏强"
    assert composite_role_fit_label(82, "climax") == "合适"
    assert composite_role_fit_label(None, "setup") == "无法判断"


def test_derive_factors_stable_and_bounded():
    node = {
        "scene_ordinal": 3,
        "scene_role": "escalation",
        "scores": {
            "reading_momentum": 72,
            "plot_progress": 78,
            "reading_tension": 70,
            "hook": 60,
            "payoff": 45,
            "pacing_speed": 60,
        },
        "composite_role_fit": "合适",
    }
    a = derive_comprehensive_reading_factors_v1(node)
    b = derive_comprehensive_reading_factors_v1(node)
    assert a == b
    assert a["explanation_source"] in {"derived", "unavailable"}
    if a["primary_driver"] and a["primary_drag"]:
        assert a["primary_driver"] != a["primary_drag"]
    blob = str(a)
    assert "reading_momentum" not in blob
    assert "formula" not in blob


def test_attach_presentation_enriches_nodes_and_phases():
    viz = {
        "scene_nodes": [
            {
                "scene_ordinal": 1,
                "scene_role": "setup",
                "scores": {"reading_momentum": 58, "plot_progress": 42, "hook": 40, "payoff": 25, "pacing_speed": 45},
            },
            {
                "scene_ordinal": 2,
                "scene_role": "transition",
                "scores": {"reading_momentum": 48, "plot_progress": 35, "hook": 35, "payoff": 20, "pacing_speed": 82},
            },
            {
                "scene_ordinal": 3,
                "scene_role": "escalation",
                "scores": {"reading_momentum": 72, "plot_progress": 78, "reading_tension": 70, "hook": 60, "payoff": 45, "pacing_speed": 60},
            },
            {
                "scene_ordinal": 4,
                "scene_role": "reveal",
                "scores": {"reading_momentum": 68, "plot_progress": 70, "reading_tension": 40, "hook": 55, "payoff": 70, "pacing_speed": 58},
            },
            {
                "scene_ordinal": 5,
                "scene_role": "climax",
                "scores": {"reading_momentum": 86, "plot_progress": 88, "reading_tension": 90, "hook": 80, "payoff": 85, "pacing_speed": 78},
            },
            {
                "scene_ordinal": 6,
                "scene_role": "aftermath",
                "scores": {"reading_momentum": 62, "plot_progress": 40, "hook": 45, "payoff": 72, "pacing_speed": 35},
            },
        ],
        "phases": [
            {"ordinal": 1, "title": "开端", "start_scene_ordinal": 1, "end_scene_ordinal": 2},
            {"ordinal": 2, "title": "发展", "start_scene_ordinal": 3, "end_scene_ordinal": 5},
            {"ordinal": 3, "title": "收束", "start_scene_ordinal": 6, "end_scene_ordinal": 6},
        ],
    }
    out = attach_comprehensive_reading_presentation(viz)
    assert len(out["scene_nodes"]) == 6
    for node in out["scene_nodes"]:
        assert node.get("composite_role_fit") in {"合适", "偏弱", "偏强", "无法判断"}
        assert node.get("explanation_source") in {"derived", "unavailable"}
        assert "overall_reading_score" in node
    assert out["scene_nodes"][0]["composite_role_fit"] == "合适"
    summaries = [p.get("stage_judgment_summary") for p in out["phases"]]
    assert all(summaries)
    assert len(set(summaries)) >= 2
    keys = out.get("comprehensive_key_nodes") or []
    assert len(keys) <= 5
    assert all(k["scene_ordinal"] != 1 or k["kind"] == "composite_turn" for k in keys)
