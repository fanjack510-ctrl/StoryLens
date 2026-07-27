"""Local tests for NarrativeLoopView adapter (CHG-20260722-011)."""

from __future__ import annotations

from app.schemas.reader_journey import SceneReaderJourneyProfileItem
from app.services.narrative_loop_view import (
    INCONSISTENT_USER_MESSAGE,
    build_narrative_loop_bundle,
    derive_loop_risks,
    scene_payoff_claim,
)


def _profile(
    ordinal: int,
    *,
    payoff_score: int = 20,
    hook_score: int = 40,
    hooks: list[dict] | None = None,
    payoffs: list[dict] | None = None,
    created: list[dict] | None = None,
    answered: list[dict] | None = None,
    carried: list[dict] | None = None,
    out: list[dict] | None = None,
) -> SceneReaderJourneyProfileItem:
    payload = {
        "scene_id": ordinal,
        "scene_ordinal": ordinal,
        "scene_value_summary": f"Scene {ordinal} anonymous summary text",
        "dominant_emotion": "??",
        "curiosity_score": 40,
        "tension_score": 40,
        "payoff_score": payoff_score,
        "hook_score": hook_score,
        "information_gain_score": 40,
        "emotional_resonance_score": 40,
        "cognitive_load_score": 40,
        "dropoff_risk_score": 40,
        "confidence": 0.7,
        "evidence_paragraph_ids": [f"p-{ordinal}-1"],
        "hooks": hooks or [],
        "payoffs": payoffs or [],
        "reader_question_created": created or [],
        "reader_question_answered": answered or [],
        "reader_question_in": carried or [],
        "reader_question_out": out or [],
    }
    return SceneReaderJourneyProfileItem.model_validate(payload)


def test_hook_to_full_payoff_loop():
    profiles = [
        _profile(
            1,
            hook_score=80,
            hooks=[
                {
                    "type": "information",
                    "summary": "??????",
                    "strength": 80,
                    "gap": "????????",
                    "continue_drive": "?????",
                    "next_handoff": "???????",
                    "evidence_paragraph_ids": ["p-1-1"],
                }
            ],
            created=[
                {
                    "question": "????????",
                    "trigger_summary": "?????",
                    "strength": 80,
                    "evidence_paragraph_ids": ["p-1-1"],
                }
            ],
            out=[
                {
                    "question": "????????",
                    "origin": "created_here",
                    "strength": 80,
                    "evidence_paragraph_ids": ["p-1-1"],
                }
            ],
        ),
        _profile(
            2,
            payoff_score=85,
            payoffs=[
                {
                    "type": "information",
                    "summary": "??????",
                    "strength": 85,
                    "evidence_paragraph_ids": ["p-2-1"],
                }
            ],
            answered=[
                {
                    "question": "????????",
                    "answer_summary": "??????",
                    "answer_degree": "full",
                    "evidence_paragraph_ids": ["p-2-1"],
                }
            ],
            carried=[
                {
                    "question": "????????",
                    "source": "carried_from_previous",
                    "confidence": 0.8,
                }
            ],
        ),
    ]
    chains = [
        {
            "question_chain_id": "qc-1",
            "question_summary": "????????",
            "created_scene_ordinal": 1,
            "carried_scene_ordinals": [2],
            "answered_scene_ordinal": 2,
            "status": "answered",
            "strength": 80,
            "confidence": 0.8,
        }
    ]
    bundle = build_narrative_loop_bundle(
        profiles, question_chains=chains, book_id=1, chapter_id=1, analysis_run_id=9
    )
    loops = bundle["narrative_loops"]
    assert loops
    loop = loops[0]
    assert loop["status"] == "resolved"
    assert any(p["type"] == "full" for p in loop["payoffs"])
    claim = scene_payoff_claim(loops, 2, payoff_score=85)
    assert claim["deterministic"] is True
    assert claim["claim"] == "full"
    assert claim["label"] == "\u6709\u6548\u5151\u73b0"
    risks = derive_loop_risks(loops)
    assert not any(r["risk_type"] == "open_narrative_loop" for r in risks)


def test_partial_and_transformed_and_open_loops():
    profiles = [
        _profile(
            1,
            hook_score=70,
            hooks=[
                {
                    "type": "danger",
                    "summary": "????",
                    "strength": 70,
                    "gap": "????",
                    "evidence_paragraph_ids": ["p-1-1"],
                }
            ],
            created=[
                {
                    "question": "????",
                    "trigger_summary": "???",
                    "strength": 70,
                    "evidence_paragraph_ids": ["p-1-1"],
                }
            ],
        ),
        _profile(
            2,
            payoff_score=50,
            answered=[
                {
                    "question": "????",
                    "answer_summary": "?????",
                    "answer_degree": "partial",
                    "evidence_paragraph_ids": ["p-2-1"],
                }
            ],
            carried=[
                {"question": "????", "source": "carried_from_previous", "confidence": 0.7}
            ],
            out=[
                {
                    "question": "????",
                    "origin": "carried",
                    "strength": 60,
                    "evidence_paragraph_ids": ["p-2-1"],
                }
            ],
        ),
        _profile(
            3,
            payoff_score=40,
            answered=[
                {
                    "question": "????",
                    "answer_summary": "????????",
                    "answer_degree": "misleading",
                    "evidence_paragraph_ids": ["p-3-1"],
                }
            ],
            carried=[
                {"question": "????", "source": "carried_from_previous", "confidence": 0.6}
            ],
        ),
        _profile(
            4,
            hook_score=75,
            hooks=[
                {
                    "type": "identity",
                    "summary": "????????",
                    "strength": 75,
                    "gap": "??????",
                    "evidence_paragraph_ids": ["p-4-1"],
                }
            ],
            created=[
                {
                    "question": "??????",
                    "trigger_summary": "????",
                    "strength": 75,
                    "evidence_paragraph_ids": ["p-4-1"],
                }
            ],
            out=[
                {
                    "question": "??????",
                    "origin": "created_here",
                    "strength": 75,
                    "evidence_paragraph_ids": ["p-4-1"],
                }
            ],
        ),
        _profile(
            5,
            carried=[
                {
                    "question": "??????",
                    "source": "carried_from_previous",
                    "confidence": 0.7,
                }
            ],
            out=[
                {
                    "question": "??????",
                    "origin": "carried",
                    "strength": 70,
                    "evidence_paragraph_ids": ["p-5-1"],
                }
            ],
        ),
    ]
    chains = [
        {
            "question_chain_id": "qc-a",
            "question_summary": "????",
            "created_scene_ordinal": 1,
            "carried_scene_ordinals": [2, 3],
            "answered_scene_ordinal": 3,
            "status": "transformed",
            "strength": 70,
        },
        {
            "question_chain_id": "qc-b",
            "question_summary": "??????",
            "created_scene_ordinal": 4,
            "carried_scene_ordinals": [5],
            "answered_scene_ordinal": None,
            "status": "carried",
            "strength": 75,
        },
    ]
    bundle = build_narrative_loop_bundle(profiles, question_chains=chains)
    by_q = {loop["question"]: loop for loop in bundle["narrative_loops"]}
    assert by_q["????"]["status"] in {"transformed", "inconsistent"}
    open_loop = by_q["??????"]
    assert open_loop["status"] in {"open", "inconsistent"}
    risks = bundle["narrative_loop_risks"]
    open_risks = [r for r in risks if r["risk_type"] == "open_narrative_loop"]
    assert open_risks
    assert open_risks[0]["question"] == "??????"
    assert open_risks[0]["start_scene_ordinal"] == 4
    assert open_risks[0]["span"] >= 2


def test_score_without_entity_is_soft_conflict_not_effective_payoff():
    profiles = [
        _profile(1, payoff_score=88, payoffs=[]),
        _profile(2, payoff_score=90, payoffs=[]),
    ]
    bundle = build_narrative_loop_bundle(
        profiles,
        legacy_risk_intervals=[
            {
                "risk_type": "consecutive_no_payoff",
                "start_scene_ordinal": 1,
                "end_scene_ordinal": 2,
                "span": 2,
                "summary": "payoffs empty",
            }
        ],
    )
    report = bundle["consistency_report"]
    assert report["status"] == "soft_conflict"
    assert any(c["code"] == "payoff_score_without_entity" for c in report["conflicts"])
    claim = bundle["scene_payoff_claims"]["1"]
    assert claim["deterministic"] is False
    assert claim.get("soft_conflict") is True or "??" in claim["label"] or "??" in claim["label"]
    # Soft conflict still attaches ranked primary relation on loops when score-inferred.
    assert "reading_resistance" in bundle
    for loop in bundle["narrative_loops"]:
        assert "primary_relation" in loop
        assert loop.get("hard_blocked") is not True


def test_entity_without_evidence_flagged():
    profiles = [
        _profile(
            1,
            payoff_score=80,
            payoffs=[
                {
                    "type": "information",
                    "summary": "????",
                    "strength": 80,
                    "evidence_paragraph_ids": [],
                }
            ],
        )
    ]
    bundle = build_narrative_loop_bundle(profiles)
    assert any(
        c["code"] == "payoff_entity_without_evidence"
        for c in bundle["consistency_report"]["conflicts"]
    )


def test_resolved_loop_suppresses_open_risk_even_if_legacy_says_empty():
    profiles = [
        _profile(
            1,
            created=[
                {
                    "question": "????",
                    "trigger_summary": "????",
                    "strength": 70,
                    "evidence_paragraph_ids": ["p-1-1"],
                }
            ],
        ),
        _profile(
            2,
            payoff_score=80,
            payoffs=[
                {
                    "type": "goal",
                    "summary": "?????",
                    "strength": 80,
                    "evidence_paragraph_ids": ["p-2-1"],
                }
            ],
            answered=[
                {
                    "question": "????",
                    "answer_summary": "???",
                    "answer_degree": "full",
                    "evidence_paragraph_ids": ["p-2-1"],
                }
            ],
        ),
    ]
    chains = [
        {
            "question_chain_id": "qc-key",
            "question_summary": "????",
            "created_scene_ordinal": 1,
            "carried_scene_ordinals": [],
            "answered_scene_ordinal": 2,
            "status": "answered",
            "strength": 70,
        }
    ]
    bundle = build_narrative_loop_bundle(
        profiles,
        question_chains=chains,
        legacy_risk_intervals=[
            {
                "risk_type": "consecutive_no_payoff",
                "start_scene_ordinal": 1,
                "end_scene_ordinal": 2,
                "span": 2,
            }
        ],
    )
    assert not any(r["risk_type"] == "open_narrative_loop" for r in bundle["narrative_loop_risks"])
    resolved = [loop for loop in bundle["narrative_loops"] if loop["question"] == "????"]
    assert resolved


def test_lifecycle_preferred_and_scope_fields_present():
    profiles = [
        _profile(1),
        _profile(
            2,
            payoff_score=75,
            payoffs=[
                {
                    "type": "information",
                    "summary": "????",
                    "strength": 75,
                    "evidence_paragraph_ids": ["p-2-1"],
                }
            ],
        ),
    ]
    lifecycle = [
        {
            "question_id": "Q1",
            "question_text": "?????",
            "setup_scene": 1,
            "development_scenes": [],
            "payoff_scene": 2,
            "status": "paid_off",
            "strength": 80,
        }
    ]
    bundle = build_narrative_loop_bundle(
        profiles,
        question_lifecycle=lifecycle,
        book_id=3,
        chapter_id=5,
        analysis_run_id=11,
        journey_run_id=22,
        scene_contract_version="2.0",
        artifact_fingerprint="abc",
    )
    assert bundle["narrative_loops"][0]["scope"]["book_id"] == 3
    assert bundle["narrative_loops"][0]["scope"]["chapter_id"] == 5
    assert bundle["narrative_loops"][0]["scope"]["analysis_run_id"] == 11
    assert bundle["narrative_loop_view_version"]
    claim = bundle["scene_payoff_claims"]["2"]
    assert claim["claim"] == "full"


def test_bundle_never_includes_full_paragraph_text():
    profiles = [
        _profile(
            1,
            hooks=[
                {
                    "type": "information",
                    "summary": "???",
                    "strength": 60,
                    "evidence_paragraph_ids": ["p-1-1"],
                }
            ],
        )
    ]
    bundle = build_narrative_loop_bundle(profiles)
    dumped = str(bundle)
    assert "paragraph_text" not in dumped
    assert "full_text" not in dumped
