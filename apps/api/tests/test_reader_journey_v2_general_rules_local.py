"""General, work-agnostic Reader Journey V2 rule verification (CHG-20260721-012).

Uses anonymous fixtures only. Named novels are external validation — never product inputs.
Does not call cloud models. Does not retune weights/thresholds.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.schemas.reader_journey_v2 import ScoredLevelField, SceneReaderJourneyProfileItemV2
from app.services.reader_journey_v2_derivation import (
    derive_chapter_profiles,
    derive_scene_metrics,
)
from app.services.reader_journey_v2_diagnosis import diagnose_scene
from app.services.scene_fragment_consolidation import looks_like_silence_reaction_or_environment_beat

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = REPO_ROOT / "data" / "fixtures" / "reader_journey_v2_general"
CONTRAST_PATH = FIXTURE_DIR / "contrast_pairs.json"
CROSS_PATH = FIXTURE_DIR / "cross_type_matrix.json"
SPLITS_PATH = FIXTURE_DIR / "test_set_splits.json"

# Absolute score tolerance for identity mutations (must be exact for pure level inputs).
MUTATION_ABS_TOL = 1e-9
# Ordering / degradation: allow tiny float noise after rounding.
ORDER_EPS = 0.05

FORBIDDEN_INSTANCE_TOKENS = (
    "牛角坳",
    "我不是戏神",
    "周山禾",
    "石牛顶",
    "陈伶",
    "戏鬼回家",
)

V2_PRODUCT_GLOBS = (
    "apps/api/app/schemas/reader_journey_v2.py",
    "apps/api/app/services/reader_journey_v2_*.py",
    "apps/api/app/services/scene_fragment_consolidation.py",
    "config/reader_journey_formulas_v2.json",
    "config/scene_role_targets.json",
    # v2.* rather than v2.0: a new prompt version under the same contract is still a product
    # module, and pinning the glob to one directory let v2.1 ship outside this audit.
    "packages/prompts/reader_journey_scene/v2.*/*",
    "packages/prompts/reader_journey_chapter/v2.*/*",
    "apps/desktop/src/components/readerJourney/lensMetricBinding.ts",
    "apps/desktop/src/components/readerJourney/observationLenses.ts",
    "apps/desktop/src/components/readerJourney/diagnosisBandModel.ts",
)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _splits() -> dict:
    return _load_json(SPLITS_PATH)


def _active_contrast_ids() -> set[str]:
    splits = _splits()
    active = set(splits["splits"]["development"]) | set(splits["splits"]["regression"])
    if os.environ.get("RUN_V2_HOLDOUT") == "1":
        active |= set(splits["splits"]["holdout"])
    return active


def _level(
    level: int,
    *,
    evidence: list[str] | None = None,
    rationale: str = "generic",
    confidence: float = 0.85,
) -> ScoredLevelField:
    return ScoredLevelField(
        level=level,
        evidence_paragraph_ids=list(evidence or ["P_GENERIC_01"]),
        rationale=rationale,
        confidence=confidence,
    )


def _profile(
    ordinal: int,
    *,
    node_type: str = "scene",
    scene_role: str = "escalation",
    levels: dict[str, int] | None = None,
    evidence: list[str] | None = None,
    summary: str = "Anonymous scene summary.",
    confidence: float = 0.85,
    scene_id: int | None = None,
) -> SceneReaderJourneyProfileItemV2:
    base = {
        "goal_progress": 3,
        "conflict_change": 3,
        "state_change": 3,
        "information_gain": 3,
        "character_agency": 3,
        "causal_coherence": 3,
        "curiosity": 3,
        "tension": 3,
        "emotional_investment": 3,
        "pacing_speed": 3,
        "hook": 3,
        "payoff": 3,
        "setup_consistency": 3,
        "question_lifecycle": 3,
        "emotional_valence_start": 3,
        "emotional_valence_end": 3,
        "arousal_start": 3,
        "arousal_end": 3,
        "clarity": 4,
        "cognitive_load": 2,
        "redundancy": 1,
    }
    if levels:
        base.update(levels)
    evid = list(evidence or [f"P{ordinal:04d}"])
    fields = {
        key: _level(value, evidence=evid, rationale=f"{key}:{value}")
        for key, value in base.items()
    }
    return SceneReaderJourneyProfileItemV2(
        scene_id=scene_id if scene_id is not None else ordinal,
        scene_ordinal=ordinal,
        node_type=node_type,  # type: ignore[arg-type]
        scene_role=scene_role,  # type: ignore[arg-type]
        scene_value_summary=summary,
        confidence=confidence,
        evidence_paragraph_ids=evid,
        **fields,
    )


def _derive_one(profile: SceneReaderJourneyProfileItemV2) -> SceneReaderJourneyProfileItemV2:
    updated, _ = derive_scene_metrics(profile)
    return updated


def _metric(profile: SceneReaderJourneyProfileItemV2, key: str) -> float:
    value = getattr(profile, key)
    assert value is not None, f"missing derived metric {key}"
    return float(value)


# ---------------------------------------------------------------------------
# 1) Product hardcode audit (V2 modules)
# ---------------------------------------------------------------------------


def test_v2_product_modules_have_no_instance_tokens():
    hits: list[str] = []
    for pattern in V2_PRODUCT_GLOBS:
        for path in REPO_ROOT.glob(pattern):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            for token in FORBIDDEN_INSTANCE_TOKENS:
                if token in text:
                    hits.append(f"{path.relative_to(REPO_ROOT)}:{token}")
    assert hits == [], f"Instance tokens in V2 product modules: {hits}"


def test_general_fixtures_are_anonymous():
    for path in FIXTURE_DIR.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_INSTANCE_TOKENS:
            assert token not in text, f"{path.name} contains {token}"
        assert "牛角" not in text and "戏神" not in text


# ---------------------------------------------------------------------------
# 2) Minimal contrast ordering (≥90%)
# ---------------------------------------------------------------------------


def _run_contrast_pair(pair: dict) -> bool:
    if pair.get("kind") == "node_type":
        low = _derive_one(
            _profile(1, node_type=pair["low_node_type"], summary="短暂静默。")
        )
        high = _derive_one(
            _profile(2, node_type=pair["high_node_type"], summary="Anonymous scene summary.")
        )
        if pair.get("expect_high_in_main_curve"):
            return high.include_in_main_curve is True and low.include_in_main_curve is False
        return True

    role = pair.get("scene_role") or "escalation"
    low = _derive_one(_profile(1, scene_role=role, levels=pair["low"]))
    high = _derive_one(_profile(2, scene_role=role, levels=pair["high"]))
    ok = True
    for key in pair.get("expect_higher") or []:
        if _metric(high, key) + ORDER_EPS < _metric(low, key):
            ok = False
    if pair.get("expect_lower_or_equal_risk_on_high"):
        # Compare chapter-adjusted dropoff on a two-scene chapter.
        chapter = derive_chapter_profiles(
            [
                _profile(1, scene_role=role, levels=pair["low"]),
                _profile(2, scene_role=role, levels=pair["high"]),
            ]
        )
        if float(chapter[1].dropoff_risk or 0) > float(chapter[0].dropoff_risk or 0) + ORDER_EPS:
            # High payoff side should not be riskier than unpaid hook side when alone;
            # compare single-scene base risks instead.
            if _metric(high, "dropoff_risk") > _metric(low, "dropoff_risk") + ORDER_EPS:
                ok = False
    expected_diag = pair.get("expect_diagnosis_on_low")
    if expected_diag:
        diag = diagnose_scene(low)
        if diag.primary_diagnosis != expected_diag and expected_diag not in (
            diag.secondary_diagnoses or []
        ):
            ok = False
    return ok


def test_minimal_contrast_ordering_at_least_90_percent():
    payload = _load_json(CONTRAST_PATH)
    active = _active_contrast_ids()
    pairs = [p for p in payload["pairs"] if p["id"] in active]
    assert pairs, "no active contrast pairs"
    results = [(p["id"], _run_contrast_pair(p)) for p in pairs]
    passed = sum(1 for _, ok in results if ok)
    rate = passed / len(results)
    failed = [pid for pid, ok in results if not ok]
    assert rate >= 0.90, f"contrast pass rate {rate:.2%} < 90%; failed={failed}"


def test_holdout_pairs_are_not_executed_by_default():
    splits = _splits()
    holdout = set(splits["splits"]["holdout"])
    assert holdout
    if os.environ.get("RUN_V2_HOLDOUT") == "1":
        pytest.skip("holdout explicitly enabled")
    payload = _load_json(CONTRAST_PATH)
    executed = {p["id"] for p in payload["pairs"] if p["id"] in _active_contrast_ids()}
    assert executed.isdisjoint(holdout)


# ---------------------------------------------------------------------------
# 3) Mutation / identity stability (100%)
# ---------------------------------------------------------------------------


def test_identity_mutations_do_not_change_derived_metrics():
    base = _profile(
        3,
        scene_role="investigation",
        levels={"curiosity": 4, "hook": 4, "payoff": 2},
        evidence=["P0003A"],
        summary="Protagonist finds a locked door and a missing key.",
        scene_id=30,
    )
    derived_base, metrics_base = derive_scene_metrics(base)

    mutated = _profile(
        99,
        scene_role="investigation",
        levels={"curiosity": 4, "hook": 4, "payoff": 2},
        evidence=["PX_OTHER_99"],
        summary="Heroine discovers a sealed gate and an absent token.",
        scene_id=99001,
    )
    # Same levels; different names/ids/summary — metrics must match.
    derived_mut, metrics_mut = derive_scene_metrics(mutated)

    for key in (
        "plot_progress",
        "reading_tension",
        "pacing_fit",
        "hook_payoff_fit",
        "reading_momentum",
        "dropoff_risk",
        "clarity_penalty",
        "cognitive_load_penalty",
        "redundancy_penalty",
    ):
        assert abs(float(getattr(metrics_base, key)) - float(getattr(metrics_mut, key))) <= MUTATION_ABS_TOL
    for key in (
        "plot_progress",
        "reading_tension",
        "pacing_fit",
        "hook_payoff_fit",
        "reading_momentum",
        "dropoff_risk",
    ):
        assert abs(float(getattr(derived_base, key)) - float(getattr(derived_mut, key))) <= MUTATION_ABS_TOL


def test_reordering_then_resorting_by_sequence_is_stable():
    profiles = [
        _profile(1, levels={"state_change": 2}),
        _profile(2, levels={"state_change": 4}),
        _profile(3, levels={"state_change": 3}),
    ]
    forward = derive_chapter_profiles(profiles)
    shuffled = derive_chapter_profiles([profiles[2], profiles[0], profiles[1]])
    by_ord_f = {p.scene_ordinal: p for p in forward}
    by_ord_s = {p.scene_ordinal: p for p in shuffled}
    for ordinal in (1, 2, 3):
        assert abs(
            float(by_ord_f[ordinal].reading_momentum)
            - float(by_ord_s[ordinal].reading_momentum)
        ) <= MUTATION_ABS_TOL


def test_moving_same_levels_to_another_ordinal_keeps_single_scene_metrics():
    a = _derive_one(_profile(4, levels={"tension": 5, "curiosity": 4}))
    b = _derive_one(_profile(11, levels={"tension": 5, "curiosity": 4}))
    assert abs(float(a.reading_tension) - float(b.reading_tension)) <= MUTATION_ABS_TOL
    assert abs(float(a.plot_progress) - float(b.plot_progress)) <= MUTATION_ABS_TOL


# ---------------------------------------------------------------------------
# 4) Degradation monotonicity (≥90%)
# ---------------------------------------------------------------------------


def test_degradation_directions_at_least_90_percent():
    """Start from an effective sample; apply successive generic degradations."""
    steps: list[tuple[str, dict[str, int], str]] = [
        ("base", {}, "reading_momentum"),
        ("remove_action_result", {"character_agency": 1, "goal_progress": 1}, "plot_progress"),
        (
            "remove_consequence",
            {
                "character_agency": 1,
                "goal_progress": 1,
                "conflict_change": 1,
                "tension": 1,
            },
            "reading_tension",
        ),
        (
            "remove_reaction",
            {
                "character_agency": 1,
                "goal_progress": 1,
                "conflict_change": 1,
                "tension": 1,
                "emotional_investment": 1,
            },
            "reading_tension",
        ),
        (
            "remove_setup",
            {
                "character_agency": 1,
                "goal_progress": 1,
                "conflict_change": 1,
                "tension": 1,
                "emotional_investment": 1,
                "setup_consistency": 1,
            },
            "hook_payoff_fit",
        ),
        (
            "add_redundancy",
            {
                "character_agency": 1,
                "goal_progress": 1,
                "conflict_change": 1,
                "tension": 1,
                "emotional_investment": 1,
                "setup_consistency": 1,
                "redundancy": 5,
                "information_gain": 1,
            },
            "reading_momentum",
        ),
        (
            "blur_question",
            {
                "character_agency": 1,
                "goal_progress": 1,
                "conflict_change": 1,
                "tension": 1,
                "emotional_investment": 1,
                "setup_consistency": 1,
                "redundancy": 5,
                "information_gain": 1,
                "curiosity": 1,
            },
            "reading_tension",
        ),
        (
            "remove_payoff",
            {
                "character_agency": 1,
                "goal_progress": 1,
                "conflict_change": 1,
                "tension": 1,
                "emotional_investment": 1,
                "setup_consistency": 1,
                "redundancy": 5,
                "information_gain": 1,
                "curiosity": 1,
                "hook": 5,
                "payoff": 0,
            },
            "dropoff_risk",
        ),
    ]

    derived = [_derive_one(_profile(i + 1, levels=levels)) for i, (_, levels, _) in enumerate(steps)]
    checks: list[bool] = []

    # plot / tension / emotion / payoff / momentum should not rise across early degradations
    checks.append(_metric(derived[1], "plot_progress") <= _metric(derived[0], "plot_progress") + ORDER_EPS)
    checks.append(_metric(derived[2], "reading_tension") <= _metric(derived[1], "reading_tension") + ORDER_EPS)
    checks.append(
        _metric(derived[3], "reading_tension") <= _metric(derived[2], "reading_tension") + ORDER_EPS
    )
    checks.append(_metric(derived[5], "reading_momentum") <= _metric(derived[4], "reading_momentum") + ORDER_EPS)
    checks.append(_metric(derived[6], "reading_tension") <= _metric(derived[5], "reading_tension") + ORDER_EPS)
    # redundancy mapped should be higher after add_redundancy
    from app.services.reader_journey_v2_mapping import mapped_or_zero

    checks.append(mapped_or_zero(derived[5].redundancy) >= mapped_or_zero(derived[4].redundancy))
    # unpaid high hook raises dropoff vs base
    checks.append(_metric(derived[7], "dropoff_risk") >= _metric(derived[0], "dropoff_risk") - ORDER_EPS)
    # curiosity quality lower
    checks.append(mapped_or_zero(derived[6].curiosity) < mapped_or_zero(derived[0].curiosity))

    # Beat insert must not steal main-curve membership from neighbors
    chapter = derive_chapter_profiles(
        [
            _profile(1, levels={"state_change": 4}),
            _profile(2, node_type="beat", summary="陷入沉默。", levels={"state_change": 0}),
            _profile(3, levels={"state_change": 4}),
        ]
    )
    checks.append(chapter[0].include_in_main_curve is True)
    checks.append(chapter[1].include_in_main_curve is False)
    checks.append(chapter[2].include_in_main_curve is True)
    checks.append(looks_like_silence_reaction_or_environment_beat("陷入沉默。"))

    rate = sum(1 for ok in checks if ok) / len(checks)
    assert rate >= 0.90, f"degradation pass rate {rate:.2%} < 90%; checks={checks}"


# ---------------------------------------------------------------------------
# 5) Cross-type matrix: role only affects fit metrics
# ---------------------------------------------------------------------------


def test_cross_type_role_does_not_change_base_metric_meanings():
    matrix = _load_json(CROSS_PATH)
    base_levels = matrix["base_levels"]
    derived = [
        _derive_one(_profile(index + 1, scene_role=cat["scene_role"], levels=base_levels))
        for index, cat in enumerate(matrix["categories"])
    ]
    plot0 = _metric(derived[0], "plot_progress")
    tension0 = _metric(derived[0], "reading_tension")
    for item in derived[1:]:
        assert abs(_metric(item, "plot_progress") - plot0) <= MUTATION_ABS_TOL
        assert abs(_metric(item, "reading_tension") - tension0) <= MUTATION_ABS_TOL

    # At least one role should differ in pacing_fit or hook_payoff_fit (bands differ).
    fits = {(round(_metric(d, "pacing_fit"), 1), round(_metric(d, "hook_payoff_fit"), 1)) for d in derived}
    assert len(fits) >= 2


def test_no_chapter_minmax_normalization_in_derivation():
    """Absolute mapping: low and high chapters keep absolute scores."""
    low_chapter = derive_chapter_profiles(
        [_profile(1, levels={"goal_progress": 1, "state_change": 1, "conflict_change": 1})]
    )
    high_chapter = derive_chapter_profiles(
        [_profile(1, levels={"goal_progress": 5, "state_change": 5, "conflict_change": 5})]
    )
    # If min-max were applied per chapter, both might collapse toward similar display ranges.
    assert _metric(high_chapter[0], "plot_progress") > _metric(low_chapter[0], "plot_progress") + 10


# ---------------------------------------------------------------------------
# 6) Deterministic recalculation
# ---------------------------------------------------------------------------


def test_formula_is_deterministically_recomputable():
    profile = _profile(5, levels={"hook": 4, "payoff": 2, "curiosity": 4})
    first, m1 = derive_scene_metrics(profile)
    second, m2 = derive_scene_metrics(profile)
    assert m1.model_dump() == m2.model_dump()
    assert first.model_dump() == second.model_dump()
