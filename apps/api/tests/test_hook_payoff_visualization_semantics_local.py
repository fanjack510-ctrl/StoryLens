"""Local tests: hook/payoff visualization semantics (CHG-20260721-012).

Presentation/passthrough only — does not retune weights or formulas.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from app.services.reader_journey_visualization import (
    _question_lifecycle_from_summary,
)
from tests.paths import repo_file


def test_question_lifecycle_passthrough_from_deterministic_statistics():
    summary = SimpleNamespace(
        deterministic_statistics_json=json.dumps(
            {
                "question_lifecycle": [
                    {
                        "question_id": "Q1",
                        "question_text": "why?",
                        "setup_scene": 1,
                        "development_scenes": [2, 3],
                        "payoff_scene": 5,
                        "status": "paid_off",
                        "strength": 0.8,
                    }
                ]
            }
        )
    )
    life = _question_lifecycle_from_summary(summary)
    assert len(life) == 1
    assert life[0]["question_id"] == "Q1"
    assert life[0]["setup_scene"] == 1
    assert life[0]["payoff_scene"] == 5
    assert life[0]["status"] == "paid_off"


def test_question_lifecycle_empty_when_missing_or_invalid():
    assert _question_lifecycle_from_summary(None) == []
    assert (
        _question_lifecycle_from_summary(
            SimpleNamespace(deterministic_statistics_json="{")
        )
        == []
    )
    assert (
        _question_lifecycle_from_summary(
            SimpleNamespace(deterministic_statistics_json=json.dumps({"question_lifecycle": {}}))
        )
        == []
    )


def test_scene_score_dict_uses_per_scene_payoff_not_cumulative_alias():
    """scores.payoff must remain the scene's own payoff_score field name."""
    # Guard against accidental rename to cumulative fields in visualization builder.
    from pathlib import Path

    text = repo_file("apps", "api", "app", "services", "reader_journey_visualization.py").read_text(
        encoding="utf-8"
    )
    assert '"payoff": profile.payoff_score' in text
    assert '"hook": profile.hook_score' in text
    assert "cumulative_payoff" not in text
    assert "carry_forward" not in text.lower()
    assert "question_lifecycle" in text
