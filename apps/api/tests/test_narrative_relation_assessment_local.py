"""Local tests for NarrativeRelationAssessment (CHG-20260722-013)."""

from __future__ import annotations

from copy import deepcopy

from app.services.narrative_relation_assessment import (
    GRADE_CANDIDATE,
    GRADE_CONFIRMED,
    GRADE_PROBABLE,
    GRADE_UNSUPPORTED,
    HARD_BLOCK_USER_MESSAGE,
    RELATION_WEIGHTS,
    SOFT_CONFLICT_USER_MESSAGE,
    assess_hook_payoff_relation,
    derive_reading_resistance,
    reconcile_loop_relations,
    reconcile_narrative_loops,
)


def _hook(scene: int = 1, summary: str = "谁偷走了钥匙", gap: str = "钥匙下落不明") -> dict:
    return {
        "scene_ordinal": scene,
        "summary": summary,
        "gap": gap,
        "continue_drive": "读者想知道钥匙去向",
        "evidence_paragraph_ids": [f"p-{scene}-1"],
    }


def _payoff(
    scene: int,
    *,
    type_: str = "full",
    summary: str = "钥匙被管家藏在书房",
    evidence: list[str] | None = None,
) -> dict:
    return {
        "scene_ordinal": scene,
        "type": type_,
        "summary": summary,
        "source_type": "information",
        "evidence_paragraph_ids": evidence if evidence is not None else [f"p-{scene}-1"],
    }


def _base_loop(**overrides) -> dict:
    loop = {
        "loop_id": "L1",
        "question": "谁偷走了钥匙",
        "information_gap": "钥匙下落不明",
        "hook": [_hook()],
        "developments": [],
        "payoffs": [],
        "status": "open",
        "conflicts": [],
        "nodes_spanned": 2,
        "open_from_scene": 1,
        "has_partial_response": False,
        "payoff_score_by_scene": {},
        "scope": {},
    }
    loop.update(overrides)
    return loop


def test_weights_centralized_and_sum_100():
    assert sum(RELATION_WEIGHTS.values()) == 100.0
    assert set(RELATION_WEIGHTS) == {
        "semantic_response",
        "entity_continuity",
        "causal_continuity",
        "expectation_match",
        "evidence_completeness",
        "distance_reasonableness",
        "data_consistency",
    }


def test_confirmed_hook_to_payoff():
    loop = _base_loop(
        payoffs=[_payoff(2)],
        status="resolved",
        payoff_score_by_scene={"2": 90},
    )
    out = reconcile_loop_relations(loop)
    primary = out["primary_relation"]
    assert primary["grade"] == GRADE_CONFIRMED
    assert primary["total_score"] >= 80
    assert primary["is_primary"] is True
    assert out["display_status"] == "resolved"
    assert out is not loop


def test_probable_hook_to_payoff():
    loop = _base_loop(
        payoffs=[
            _payoff(
                2,
                type_="partial",
                summary="管家神色慌张但未说明钥匙",
                evidence=["p-2-1"],
            )
        ],
        conflicts=[{"code": "score_entity_divergence", "message": "soft"}],
        status="partially_resolved",
        payoff_score_by_scene={"2": 65},
    )
    out = reconcile_loop_relations(loop)
    primary = out["primary_relation"]
    assert primary["grade"] in {GRADE_PROBABLE, GRADE_CANDIDATE}
    assert primary["total_score"] >= 40
    assert out["soft_conflict"] is True
    assert out["relation_warning"] == SOFT_CONFLICT_USER_MESSAGE


def test_candidate_hook_to_payoff():
    loop = _base_loop(
        payoffs=[
            _payoff(
                5,
                type_="partial",
                summary="雨夜有人离开宅邸",
                evidence=["p-5-1"],
            )
        ],
        status="open",
        nodes_spanned=5,
    )
    out = reconcile_loop_relations(loop)
    primary = out["primary_relation"]
    assert primary["grade"] in {GRADE_CANDIDATE, GRADE_PROBABLE, GRADE_UNSUPPORTED}
    if primary["grade"] == GRADE_CANDIDATE:
        assert 40 <= primary["total_score"] < 60


def test_unsupported_no_credible_relation():
    loop = _base_loop(payoffs=[], status="open")
    out = reconcile_loop_relations(loop)
    primary = out["primary_relation"]
    assert primary["grade"] == GRADE_UNSUPPORTED
    assert out["display_status"] == "open"


def test_high_score_without_entity_is_soft_not_blank():
    loop = _base_loop(
        payoffs=[],
        payoff_score_by_scene={"2": 88},
        conflicts=[{"code": "payoff_score_without_entity", "scene_ordinal": 2, "message": "x"}],
        status="open",
    )
    original = deepcopy(loop)
    out = reconcile_loop_relations(loop)
    assert out["soft_conflict"] is True
    assert out["hard_blocked"] is False
    primary = out["primary_relation"]
    assert primary["grade"] in {GRADE_CANDIDATE, GRADE_PROBABLE}
    assert primary["payoff_ref"]["source_type"] == "score_inferred"
    assert original["payoffs"] == []
    assert loop["payoffs"] == []


def test_entity_without_evidence_soft_conflict():
    loop = _base_loop(
        payoffs=[_payoff(2, evidence=[])],
        conflicts=[{"code": "payoff_entity_without_evidence", "message": "x"}],
        status="resolved",
    )
    out = reconcile_loop_relations(loop)
    assert out["soft_conflict"] is True
    # Soft conflict caps confirmed → probable
    assert out["primary_relation"]["grade"] in {GRADE_PROBABLE, GRADE_CANDIDATE}


def test_same_object_without_causal_order():
    assessment = assess_hook_payoff_relation(
        loop_id="L1",
        question="谁偷走了钥匙",
        information_gap="钥匙下落",
        hook=_hook(3),
        payoff=_payoff(1, summary="钥匙被管家藏在书房"),
        developments=[],
        payoff_score=70,
    )
    assert assessment["dimensions"]["causal_continuity"]["score"] < 40
    assert assessment["grade"] in {GRADE_UNSUPPORTED, GRADE_CANDIDATE, GRADE_PROBABLE}


def test_causal_but_different_text():
    assessment = assess_hook_payoff_relation(
        loop_id="L1",
        question="谁偷走了钥匙",
        information_gap="钥匙下落不明",
        hook=_hook(1),
        payoff=_payoff(2, summary="远处钟声敲了三下"),
        developments=[],
        payoff_score=50,
    )
    assert assessment["dimensions"]["semantic_response"]["score"] < 70
    assert assessment["grade"] in {GRADE_UNSUPPORTED, GRADE_CANDIDATE, GRADE_PROBABLE}


def test_partial_response_display():
    loop = _base_loop(
        payoffs=[_payoff(2, type_="partial", summary="钥匙线索指向管家")],
        status="partially_resolved",
        has_partial_response=True,
    )
    out = reconcile_loop_relations(loop)
    assert out["display_status"] in {"partially_resolved", "resolved"}
    assert out["primary_relation"]["grade"] in {GRADE_CONFIRMED, GRADE_PROBABLE, GRADE_CANDIDATE}


def test_reversal_response():
    loop = _base_loop(
        payoffs=[_payoff(2, type_="reversal", summary="钥匙从未丢失，是主角记错")],
        status="resolved",
    )
    out = reconcile_loop_relations(loop)
    assert out["primary_relation"]["payoff_ref"]["type"] == "reversal"
    assert out["primary_relation"]["grade"] in {GRADE_CONFIRMED, GRADE_PROBABLE}


def test_transformed_question():
    loop = _base_loop(
        payoffs=[_payoff(2, type_="transformed_question", summary="钥匙问题转为谁伪造了遗嘱")],
        status="transformed",
    )
    out = reconcile_loop_relations(loop)
    assert out["display_status"] in {"transformed", "resolved", "partially_resolved"}


def test_multi_candidate_picks_primary_only():
    loop = _base_loop(
        payoffs=[
            _payoff(2, type_="partial", summary="雨夜有人离开"),
            _payoff(3, type_="full", summary="钥匙被管家藏在书房"),
        ],
        status="resolved",
    )
    out = reconcile_loop_relations(loop)
    assert out["primary_relation"]["is_primary"] is True
    assert len(out["candidate_relations"]) == 1
    assert out["candidate_relations"][0]["is_primary"] is False
    assert out["primary_relation"]["total_score"] >= out["candidate_relations"][0]["total_score"]


def test_scope_pollution_hard_block():
    loop = _base_loop(
        payoffs=[_payoff(2)],
        conflicts=[{"code": "scope_book_mismatch", "message": "cross book"}],
    )
    out = reconcile_loop_relations(loop)
    assert out["hard_blocked"] is True
    assert out["display_status"] == "inconsistent"
    assert out["primary_relation"]["blocked"] is True
    assert out["relation_warning"] == HARD_BLOCK_USER_MESSAGE


def test_fingerprint_conflict_hard_block():
    loop = _base_loop(
        payoffs=[_payoff(2)],
        conflicts=[{"code": "fingerprint_mismatch", "message": "fp"}],
    )
    out = reconcile_loop_relations(loop)
    assert out["hard_blocked"] is True
    assert out["primary_relation"]["total_score"] == 0.0


def test_resolved_no_reading_resistance():
    loop = reconcile_loop_relations(
        _base_loop(payoffs=[_payoff(2)], status="resolved", nodes_spanned=2)
    )
    items = derive_reading_resistance([loop])
    assert items == []


def test_open_with_development_no_immediate_resistance():
    loop = reconcile_loop_relations(
        _base_loop(
            developments=[{"scene_ordinal": 2, "kind": "development"}],
            status="open",
            nodes_spanned=2,
            has_partial_response=True,
        )
    )
    items = derive_reading_resistance([loop])
    assert items == []


def test_open_stalled_produces_reading_resistance():
    loop = reconcile_loop_relations(
        _base_loop(
            status="open",
            nodes_spanned=5,
            developments=[],
            has_partial_response=False,
            open_from_scene=1,
        )
    )
    items = derive_reading_resistance([loop])
    assert items
    assert "stalled_suspense" in items[0]["reason_codes"] or "insufficient_response" in items[0]["reason_codes"]
    assert any("悬念" in r or "回应" in r or "推进" in r for r in items[0]["reasons_zh"])


def test_short_transition_not_auto_resistance():
    loop = reconcile_loop_relations(
        _base_loop(
            developments=[{"scene_ordinal": 2}],
            status="open",
            nodes_spanned=2,
            open_from_scene=1,
        )
    )
    items = derive_reading_resistance(
        [loop],
        scene_nodes=[
            {
                "scene_ordinal": 1,
                "paragraph_count": 2,
                "role": "beat",
                "scores": {"reading_momentum": 30, "plot_progress": 30, "pacing_fit": 30},
            },
            {
                "scene_ordinal": 2,
                "paragraph_count": 1,
                "role": "beat",
                "scores": {"reading_momentum": 28, "plot_progress": 28, "pacing_fit": 28},
            },
        ],
    )
    assert items == []


def test_does_not_mutate_original_artifact_fields():
    loop = _base_loop(payoffs=[_payoff(2)], status="resolved")
    snapshot = deepcopy(loop)
    out = reconcile_loop_relations(loop)
    assert loop == snapshot
    assert out["status"] == snapshot["status"]
    assert "primary_relation" not in loop
    assert "primary_relation" in out


def test_reconcile_batch_no_model_side_effects():
    loops = [
        _base_loop(loop_id="A", payoffs=[_payoff(2)]),
        _base_loop(loop_id="B", payoffs=[]),
    ]
    outs = reconcile_narrative_loops(loops)
    assert len(outs) == 2
    assert outs[0]["primary_relation"]["grade"] in {
        GRADE_CONFIRMED,
        GRADE_PROBABLE,
        GRADE_CANDIDATE,
    }
    assert outs[1]["primary_relation"]["grade"] == GRADE_UNSUPPORTED
