"""Reader Journey question chain lifecycle — deterministic program tracking."""

from __future__ import annotations

import hashlib
from typing import Any

from app.schemas.reader_journey import SceneReaderJourneyProfileItem

QuestionStatus = str  # created|carried|partially_answered|transformed|answered|dropped

HIGH_STRENGTH_THRESHOLD = 60


def _question_chain_id(question: str, created_scene_ordinal: int) -> str:
    digest = hashlib.sha256(f"{created_scene_ordinal}:{question}".encode()).hexdigest()[:16]
    return f"qc-{digest}"


def build_question_chains(profiles: list[SceneReaderJourneyProfileItem]) -> list[dict[str, Any]]:
    """Build question chains across scene profiles in ordinal order."""
    ordered = sorted(profiles, key=lambda item: item.scene_ordinal)
    chains: dict[str, dict[str, Any]] = {}

    for profile in ordered:
        ordinal = profile.scene_ordinal
        for created in profile.reader_question_created:
            qid = _question_chain_id(created.question, ordinal)
            chains[qid] = {
                "question_chain_id": qid,
                "question_summary": created.question,
                "created_scene_ordinal": ordinal,
                "carried_scene_ordinals": [],
                "answered_scene_ordinal": None,
                "status": "created",
                "strength": created.strength,
            }
        for carried in profile.reader_question_in:
            matched = None
            for chain in chains.values():
                if chain["question_summary"] == carried.question and chain["status"] not in {
                    "answered",
                    "dropped",
                }:
                    matched = chain
                    break
            if matched is None:
                qid = _question_chain_id(carried.question, ordinal)
                chains[qid] = {
                    "question_chain_id": qid,
                    "question_summary": carried.question,
                    "created_scene_ordinal": ordinal,
                    "carried_scene_ordinals": [],
                    "answered_scene_ordinal": None,
                    "status": "carried",
                    "strength": 50,
                }
                matched = chains[qid]
            if ordinal not in matched["carried_scene_ordinals"]:
                matched["carried_scene_ordinals"].append(ordinal)
            if matched["status"] == "created":
                matched["status"] = "carried"
        for answered in profile.reader_question_answered:
            for chain in chains.values():
                if chain["question_summary"] == answered.question:
                    chain["answered_scene_ordinal"] = ordinal
                    if answered.answer_degree == "partial":
                        chain["status"] = "partially_answered"
                    elif answered.answer_degree == "misleading":
                        chain["status"] = "transformed"
                    else:
                        chain["status"] = "answered"
        for out_item in profile.reader_question_out:
            if out_item.origin == "transformed":
                for chain in chains.values():
                    if chain["question_summary"] == out_item.question:
                        chain["status"] = "transformed"
            elif out_item.origin == "created_here":
                qid = _question_chain_id(out_item.question, ordinal)
                if qid not in chains:
                    chains[qid] = {
                        "question_chain_id": qid,
                        "question_summary": out_item.question,
                        "created_scene_ordinal": ordinal,
                        "carried_scene_ordinals": [],
                        "answered_scene_ordinal": None,
                        "status": "created",
                        "strength": out_item.strength,
                    }

    return sorted(chains.values(), key=lambda item: (item["created_scene_ordinal"], item["question_chain_id"]))


def diagnose_dropped_high_strength_questions(
    profiles: list[SceneReaderJourneyProfileItem],
) -> list[dict[str, Any]]:
    """Detect high-strength outs that were not carried forward."""
    ordered = sorted(profiles, key=lambda item: item.scene_ordinal)
    diagnostics: list[dict[str, Any]] = []
    for index, profile in enumerate(ordered[:-1]):
        next_profile = ordered[index + 1]
        if next_profile.scene_ordinal != profile.scene_ordinal + 1:
            continue
        carried = {item.question.strip() for item in next_profile.reader_question_in}
        created = {item.question.strip() for item in next_profile.reader_question_created}
        for out_item in profile.reader_question_out:
            if out_item.strength < HIGH_STRENGTH_THRESHOLD:
                continue
            question = out_item.question.strip()
            if question not in carried and question not in created:
                answered_here = any(
                    item.question.strip() == question for item in profile.reader_question_answered
                )
                if not answered_here:
                    diagnostics.append(
                        {
                            "code": "JOURNEY_HIGH_STRENGTH_QUESTION_DROPPED",
                            "scene_ordinal": profile.scene_ordinal,
                            "question": question,
                            "strength": out_item.strength,
                        }
                    )
    return diagnostics
