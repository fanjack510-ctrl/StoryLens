"""Explicit question lifecycle for Reader Journey v2.0.

Replaces the legacy consecutive-no-payoff → dropoff floor rule for v2 runs.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from app.schemas.reader_journey_v2 import (
    QuestionLifecycleRecord,
    QuestionLifecycleStatus,
    SceneReaderJourneyProfileItemV2,
)
from app.services.reader_journey_v2_mapping import mapped_or_zero

_NORMALIZE = re.compile(r"\s+")


def _norm_question(text: str) -> str:
    return _NORMALIZE.sub("", (text or "").strip())


def make_question_id(text: str, setup_scene: int) -> str:
    digest = hashlib.sha1(f"{setup_scene}:{_norm_question(text)}".encode("utf-8")).hexdigest()[:10]
    return f"q{setup_scene}_{digest}"


def _extract_questions(profile: SceneReaderJourneyProfileItemV2) -> list[tuple[str, int]]:
    """Return (question_text, strength) candidates from v2 profile fields."""
    found: list[tuple[str, int]] = []
    # Prefer explicit question_lifecycle level rationale when it mentions a question.
    rationale = (profile.question_lifecycle.rationale or "").strip()
    if rationale and ("？" in rationale or "?" in rationale):
        strength = int(mapped_or_zero(profile.question_lifecycle))
        found.append((rationale[:200], strength))
    # Hook/payoff rationals often encode open questions.
    for field in (profile.hook, profile.payoff, profile.curiosity):
        text = (field.rationale or "").strip()
        if text and ("？" in text or "?" in text):
            found.append((text[:200], int(mapped_or_zero(field))))
    summary = (profile.scene_value_summary or "").strip()
    if summary and ("？" in summary or "?" in summary):
        found.append((summary[:200], int(mapped_or_zero(profile.curiosity))))
    # Deduplicate by normalized text, keep highest strength.
    best: dict[str, tuple[str, int]] = {}
    for text, strength in found:
        key = _norm_question(text)
        if not key:
            continue
        prior = best.get(key)
        if prior is None or strength > prior[1]:
            best[key] = (text, strength)
    return list(best.values())


def build_question_lifecycle(
    profiles: list[SceneReaderJourneyProfileItemV2],
    *,
    overdue_after_scenes: int = 4,
) -> list[QuestionLifecycleRecord]:
    ordered = sorted(profiles, key=lambda item: item.scene_ordinal)
    records: dict[str, dict[str, Any]] = {}
    active_keys: list[str] = []

    for profile in ordered:
        ordinal = int(profile.scene_ordinal)
        payoff_score = mapped_or_zero(profile.payoff)
        lifecycle_level = int(profile.question_lifecycle.level)
        candidates = _extract_questions(profile)

        # Progress existing open questions.
        for key in list(active_keys):
            record = records[key]
            if record["status"] in {"paid_off", "abandoned"}:
                continue
            if ordinal != record["setup_scene"] and ordinal not in record["development_scenes"]:
                record["development_scenes"].append(ordinal)
            # Payoff closes.
            if payoff_score >= 60 or lifecycle_level >= 4:
                record["payoff_scene"] = ordinal
                record["status"] = "paid_off"
                continue
            # Mark progressing when curiosity/hook stays alive.
            if mapped_or_zero(profile.curiosity) >= 50 or mapped_or_zero(profile.hook) >= 50:
                record["status"] = "progressing"
            # Overdue if open too long without payoff.
            span = ordinal - int(record["setup_scene"])
            if record["status"] in {"open", "progressing"} and span >= overdue_after_scenes:
                record["status"] = "overdue"

        # Create new questions from this scene when hook/curiosity opens them.
        for text, strength in candidates:
            key = _norm_question(text)
            if not key:
                continue
            if key in records:
                continue
            if mapped_or_zero(profile.hook) < 40 and mapped_or_zero(profile.curiosity) < 40:
                continue
            qid = make_question_id(text, ordinal)
            records[key] = {
                "question_id": qid,
                "question_text": text,
                "setup_scene": ordinal,
                "development_scenes": [],
                "payoff_scene": None,
                "status": "open",
                "strength": strength,
            }
            active_keys.append(key)
            # Same-scene immediate payoff.
            if payoff_score >= 60:
                records[key]["payoff_scene"] = ordinal
                records[key]["status"] = "paid_off"

        # Abandon stale overdue questions when chapter ends without payoff and
        # later scenes show no curiosity/hook carry.
        if mapped_or_zero(profile.curiosity) < 30 and mapped_or_zero(profile.hook) < 30:
            for key in active_keys:
                record = records[key]
                if record["status"] == "overdue" and record["payoff_scene"] is None:
                    record["status"] = "abandoned"

    out: list[QuestionLifecycleRecord] = []
    for key in active_keys:
        raw = records[key]
        out.append(
            QuestionLifecycleRecord(
                question_id=str(raw["question_id"]),
                question_text=str(raw["question_text"]),
                setup_scene=int(raw["setup_scene"]),
                development_scenes=list(raw["development_scenes"]),
                payoff_scene=raw["payoff_scene"],
                status=raw["status"],  # type: ignore[arg-type]
                strength=int(raw["strength"]),
            )
        )
    return out


def lifecycle_status_counts(records: list[QuestionLifecycleRecord]) -> dict[str, int]:
    counts: dict[str, int] = {
        "open": 0,
        "progressing": 0,
        "paid_off": 0,
        "abandoned": 0,
        "overdue": 0,
    }
    for item in records:
        counts[item.status] = counts.get(item.status, 0) + 1
    return counts
