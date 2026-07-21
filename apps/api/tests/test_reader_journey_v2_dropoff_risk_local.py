"""Local tests for V2 dropoff risk intervals (CHG-20260721-012)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.reader_journey_visualization import (
    build_v2_dropoff_risk_intervals,
    _is_v2_native_presentation,
)


def _node(
    ordinal: int,
    *,
    momentum: float,
    hook: float = 40,
    payoff: float = 40,
    dropoff: float | None = None,
) -> dict:
    risk = dropoff if dropoff is not None else round(100.0 - momentum, 1)
    return {
        "scene_ordinal": ordinal,
        "role": "core",
        "node_type": "scene",
        "engagement": {"engagement_score": int(momentum)},
        "scores": {
            "reading_momentum": momentum,
            "hook": hook,
            "payoff": payoff,
            "dropoff_risk": risk,
        },
    }


def test_v2_dropoff_never_uses_engagement_threshold_copy():
    nodes = [
        _node(1, momentum=30),
        _node(2, momentum=32),
        _node(3, momentum=28),
        _node(4, momentum=70, hook=80, payoff=20),
    ]
    intervals = build_v2_dropoff_risk_intervals(nodes)
    assert intervals
    for item in intervals:
        assert item.get("field_used") == "reading_momentum"
        assert "engagement<" not in str(item.get("trigger") or "")
        assert "engagement<" not in str(item.get("summary") or "")
        assert "field_used" in item
        assert "final_risk" in item
        assert "penalties" in item
        assert item["start_scene_ordinal"] <= item["end_scene_ordinal"]


def test_v2_dropoff_applies_decline_low_and_unpaid_hook_penalties():
    # Clear two-step decline ending at S3; low streak S3-S5; unpaid hook at S6.
    nodes = [
        _node(1, momentum=70),
        _node(2, momentum=55),
        _node(3, momentum=40),
        _node(4, momentum=35),
        _node(5, momentum=30),
        _node(6, momentum=55, hook=80, payoff=10),
        _node(7, momentum=56, hook=20, payoff=10),
        _node(8, momentum=57, hook=20, payoff=10),
        _node(9, momentum=58, hook=20, payoff=10),
    ]
    intervals = build_v2_dropoff_risk_intervals(nodes)
    types = {item["risk_type"] for item in intervals}
    assert "momentum_decline" in types
    assert "low_reading_momentum" in types
    unpaid = [item for item in intervals if item["risk_type"] == "unpaid_hook"]
    assert unpaid
    assert any(penalty.get("amount") == 10 for penalty in unpaid[0]["penalties"])
    assert any(penalty.get("amount") == 8 for item in intervals for penalty in item["penalties"])
    assert any(penalty.get("amount") == 15 for item in intervals for penalty in item["penalties"])


def test_is_v2_native_presentation_flags():
    assert _is_v2_native_presentation(
        SimpleNamespace(
            failure_details_json=json.dumps({"source_mode": "v2_native"}),
            scene_contract_version="1.3",
        )
    )
    assert _is_v2_native_presentation(
        SimpleNamespace(failure_details_json="{}", scene_contract_version="2.0")
    )
    assert not _is_v2_native_presentation(
        SimpleNamespace(failure_details_json="{}", scene_contract_version="1.3")
    )


@pytest.mark.parametrize("ordinal", [4, 7, 11])
def test_run_id_2_db_api_field_consistency_local(ordinal: int):
    """Read-only consistency for 我不是戏神 run_id=2 (no model calls)."""
    db_path = (
        Path(__file__).resolve().parents[3]
        / "data"
        / "runtime"
        / "rj-v2-native-verify"
        / "database"
        / "storylens.db"
    )
    if not db_path.exists():
        pytest.skip("run_id=2 verify DB not present")

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    from app.db.models import ReaderJourneyRun, SceneReaderJourneyProfile
    from app.services.reader_journey_visualization import build_reader_journey_visualization

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    Session = sessionmaker(bind=engine)
    with Session() as session:
        journey = session.get(ReaderJourneyRun, 2)
        if journey is None:
            pytest.skip("reader_journey_runs.id=2 missing")
        profile = session.scalar(
            select(SceneReaderJourneyProfile).where(
                SceneReaderJourneyProfile.reader_journey_run_id == 2,
                SceneReaderJourneyProfile.scene_ordinal == ordinal,
            )
        )
        assert profile is not None
        viz = build_reader_journey_visualization(session, journey)
        node = next(
            item for item in viz["scene_nodes"] if int(item["scene_ordinal"]) == ordinal
        )
        scores = node.get("scores") or {}

        # DB → API consistency for native columns.
        assert int(node["engagement"]["engagement_score"]) == int(profile.engagement_score)
        assert int(scores["hook"]) == int(profile.hook_score)
        assert int(scores["payoff"]) == int(profile.payoff_score)
        assert int(scores["dropoff_risk"]) == int(profile.dropoff_risk_score)

        # V2 fields: when absent in DB payload, API must not invent conflicting values
        # silently under engagement terminology for v2_native-only formulas.
        payload = json.loads(profile.payload_json or "{}")
        payload_scores = payload.get("scores") if isinstance(payload.get("scores"), dict) else {}
        for key in (
            "reading_momentum",
            "plot_progress",
            "reading_tension",
            "pacing_speed",
            "pacing_fit",
        ):
            if key in payload_scores and payload_scores[key] is not None:
                assert scores.get(key) == payload_scores[key]

        # Risk intervals on legacy run_id=2 may still include low_engagement;
        # v2_native presentation must never emit engagement<40 trigger.
        if _is_v2_native_presentation(journey):
            for item in viz.get("risk_intervals") or []:
                assert "engagement<" not in str(item.get("trigger") or "")
                if item.get("risk_type") in {
                    "low_reading_momentum",
                    "momentum_decline",
                    "unpaid_hook",
                    "high_dropoff_risk",
                }:
                    assert item.get("field_used") == "reading_momentum"
