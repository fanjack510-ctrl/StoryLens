"""Deterministic engagement score from scene profile dimensions."""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from app.schemas.reader_journey import EngagementBreakdown, SceneReaderJourneyProfileItem

DEFAULT_FORMULA_PATH = Path("config/reader_journey_formulas.json")


def load_formula_config(path: Path = DEFAULT_FORMULA_PATH) -> dict:
    if not path.exists():
        return {
            "version": "1.0",
            "default_genre": "suspense",
            "genres": {
                "suspense": {
                    "label": "悬疑",
                    "weights": {
                        "curiosity": 0.25,
                        "tension": 0.20,
                        "hook": 0.20,
                        "payoff": 0.15,
                        "information_gain": 0.10,
                        "emotional_resonance": 0.10,
                        "cognitive_load": -0.10,
                        "dropoff_risk": -0.15,
                    },
                }
            },
        }
    return json.loads(path.read_text(encoding="utf-8"))


def compute_engagement(
    profile: SceneReaderJourneyProfileItem,
    *,
    genre: str | None = None,
    formula_path: Path = DEFAULT_FORMULA_PATH,
) -> EngagementBreakdown:
    config = load_formula_config(formula_path)
    version = str(config.get("version", "1.0"))
    genre_key = genre or str(config.get("default_genre", "suspense"))
    genres = config.get("genres") or {}
    genre_cfg = genres.get(genre_key) or genres.get(str(config.get("default_genre", "suspense")))
    weights: dict[str, float] = dict((genre_cfg or {}).get("weights") or {})

    scores = {
        "curiosity": profile.curiosity_score,
        "tension": profile.tension_score,
        "hook": profile.hook_score,
        "payoff": profile.payoff_score,
        "information_gain": profile.information_gain_score,
        "emotional_resonance": profile.emotional_resonance_score,
        "cognitive_load": profile.cognitive_load_score,
        "dropoff_risk": profile.dropoff_risk_score,
    }
    total = Decimal("0")
    for key, weight in weights.items():
        value = Decimal(str(scores.get(key, 0)))
        total += value * Decimal(str(weight))
    clamped = int(
        max(0, min(100, total.quantize(Decimal("1"), rounding=ROUND_HALF_UP)))
    )
    return EngagementBreakdown(
        curiosity=profile.curiosity_score,
        tension=profile.tension_score,
        hook=profile.hook_score,
        payoff=profile.payoff_score,
        information_gain=profile.information_gain_score,
        emotional_resonance=profile.emotional_resonance_score,
        cognitive_load=profile.cognitive_load_score,
        dropoff_risk=profile.dropoff_risk_score,
        engagement_score=clamped,
        formula_version=version,
        genre=genre_key,
        weights=weights,
    )
