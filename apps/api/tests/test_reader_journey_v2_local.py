"""Local tests for Reader Journey v2.0 contract, derivation, Scene/Beat, lifecycle, diagnosis, legacy."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.reader_journey import SCENE_CONTRACT_VERSION, SCENE_PROMPT_VERSION
from app.schemas.reader_journey_v2 import (
    CHAPTER_PROMPT_VERSION_V2,
    FORMULA_VERSION_V2,
    SCENE_CONTRACT_VERSION_V2,
    SCENE_PROMPT_VERSION_V2,
    SCENE_ROLE_TARGETS_VERSION,
    ScoredLevelField,
    SceneReaderJourneyBatchResultV2,
    SceneReaderJourneyProfileItemV2,
)
from app.services.reader_journey_v2_compatibility import (
    calibration_label,
    enrich_result_compatibility,
    is_legacy_contract,
    is_v2_contract,
)
from app.services.reader_journey_v2_derivation import (
    chapter_mean_reading_momentum,
    derive_chapter_profiles,
    derive_scene_metrics,
    fit_to_band,
    load_scene_role_targets,
)
from app.services.reader_journey_v2_diagnosis import diagnose_scene
from app.services.reader_journey_v2_finalize import finalize_v2_profiles
from app.services.reader_journey_v2_mapping import (
    apply_mapped_scores,
    level_to_mapped_score,
    load_formula_v2_config,
)
from app.services.reader_journey_v2_question_lifecycle import build_question_lifecycle
from app.services.scene_fragment_consolidation import (
    BoundaryMeta,
    consolidate_boundary_ids,
    looks_like_silence_reaction_or_environment_beat,
)
from app.services.scene_pipeline import scene_ranges


def _level(
    level: int,
    *,
    evidence: list[str] | None = None,
    rationale: str = "ok",
    confidence: float = 0.8,
) -> ScoredLevelField:
    return ScoredLevelField(
        level=level,
        evidence_paragraph_ids=list(evidence or []),
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
    hook_rationale: str = "",
    confidence: float = 0.8,
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
    fields = {
        key: _level(
            value,
            evidence=evidence,
            rationale=hook_rationale if key == "hook" and hook_rationale else f"{key}:{value}",
        )
        for key, value in base.items()
    }
    return SceneReaderJourneyProfileItemV2(
        scene_id=ordinal,
        scene_ordinal=ordinal,
        node_type=node_type,  # type: ignore[arg-type]
        scene_role=scene_role,  # type: ignore[arg-type]
        scene_value_summary=f"Scene {ordinal} summary",
        confidence=confidence,
        evidence_paragraph_ids=list(evidence or []),
        **fields,
    )


def _paras(texts: list[str]):
    return [
        SimpleNamespace(id=f"P{i:04d}", paragraph_index=i, normalized_text=text)
        for i, text in enumerate(texts)
    ]


def _range_texts(paragraphs, boundary_ids, boundary_meta=None):
    kept = consolidate_boundary_ids(paragraphs, boundary_ids, boundary_meta)
    ranges = scene_ranges(paragraphs, kept, consolidate_short_fragments=False)
    out = []
    for start, end in ranges:
        chunk = [
            item.normalized_text
            for item in paragraphs
            if start.paragraph_index <= item.paragraph_index <= end.paragraph_index
        ]
        out.append(chunk)
    return out, kept


# --- Schema ---


def test_v2_schema_versions_and_required_fields():
    assert SCENE_CONTRACT_VERSION_V2 == "2.0"
    # Prompt v2.2 under contract 2.0: the two versions move independently, and this pair
    # is the assertion that keeps them honest. v2.2 adds reader_questions_opened /
    # reader_questions_answered / first_hook_paragraph_id — all optional with empty
    # defaults, so the contract version does not move.
    assert SCENE_PROMPT_VERSION_V2 == "v2.2"
    assert CHAPTER_PROMPT_VERSION_V2 == "v2.0"
    assert FORMULA_VERSION_V2 == "2.0"
    assert SCENE_ROLE_TARGETS_VERSION == "1.0"
    # v1 defaults remain untouched.
    assert SCENE_CONTRACT_VERSION == "1.3"
    assert SCENE_PROMPT_VERSION == "v1.6"

    profile = _profile(1, evidence=["P0001"])
    batch = SceneReaderJourneyBatchResultV2(profiles=[profile])
    assert batch.contract_version == "2.0"
    assert profile.node_type == "scene"
    assert profile.include_in_main_curve is True

    beat = _profile(2, node_type="beat", evidence=["P0002"])
    assert beat.include_in_main_curve is False
    assert beat.include_in_chapter_mean is False


def test_v2_schema_rejects_invalid_level():
    with pytest.raises(ValidationError):
        _level(6)


def test_model_mapped_score_is_overwritten_by_program():
    field = ScoredLevelField(
        level=5,
        mapped_score=99,  # model attempt — ignored
        evidence_paragraph_ids=["P0001"],
        rationale="strong",
        confidence=0.9,
    )
    fixed = apply_mapped_scores(field)
    assert fixed.mapped_score == 95


# --- Mapping / formulas ---


def test_level_to_mapped_score_table_and_no_evidence_cap():
    cfg = load_formula_v2_config()
    assert cfg["version"] == "2.0"
    assert level_to_mapped_score(0, has_evidence=True) == 10
    assert level_to_mapped_score(1, has_evidence=True) == 30
    assert level_to_mapped_score(2, has_evidence=True) == 50
    assert level_to_mapped_score(3, has_evidence=True) == 65
    assert level_to_mapped_score(4, has_evidence=True) == 80
    assert level_to_mapped_score(5, has_evidence=True) == 95
    assert level_to_mapped_score(5, has_evidence=False) == 40
    assert level_to_mapped_score(3, has_evidence=False) == 40


def test_fit_to_band_and_derived_formulas():
    cfg = load_formula_v2_config()
    assert fit_to_band(50, [40, 60], config=cfg) == 90
    assert fit_to_band(35, [40, 60], config=cfg) == 80  # 5 points * 2
    assert fit_to_band(70, [40, 60], config=cfg) == 70

    roles = load_scene_role_targets()
    assert roles["version"] == "1.0"
    assert "setup" in roles["roles"]

    profile = _profile(
        1,
        scene_role="open_end",
        levels={"hook": 5, "payoff": 1, "pacing_speed": 3, "clarity": 4, "cognitive_load": 2, "redundancy": 1},
        evidence=["P0001"],
    )
    updated, derived = derive_scene_metrics(profile)
    assert updated.hook.mapped_score == 95
    assert derived.formula_version == "2.0"
    assert 0 <= derived.plot_progress <= 100
    assert 0 <= derived.reading_tension <= 100
    assert 0 <= derived.pacing_fit <= 100
    assert 0 <= derived.hook_payoff_fit <= 100
    assert 0 <= derived.reading_momentum <= 100
    assert abs(derived.dropoff_risk - (100 - derived.reading_momentum)) < 0.2
    # open_end expects high hook / low payoff — both can fit their bands.
    assert derived.hook_payoff_fit >= 70


def test_penalties_and_dropoff_rules_without_legacy_floor():
    low_clarity = _profile(
        1,
        levels={"clarity": 1, "cognitive_load": 5, "redundancy": 5},
        evidence=["P0001"],
    )
    _, derived = derive_scene_metrics(low_clarity)
    assert derived.clarity_penalty > 0
    assert derived.cognitive_load_penalty > 0
    assert derived.redundancy_penalty > 0

    # Declining momentum should raise dropoff without applying legacy 55 floor from no-payoff.
    p1 = _profile(1, levels={"goal_progress": 4, "curiosity": 4, "tension": 4}, evidence=["P1"])
    p2 = _profile(2, levels={"goal_progress": 2, "curiosity": 2, "tension": 2}, evidence=["P2"])
    p3 = _profile(3, levels={"goal_progress": 0, "curiosity": 0, "tension": 0}, evidence=["P3"])
    derived = derive_chapter_profiles([p1, p2, p3])
    assert all(item.dropoff_risk is not None for item in derived)
    # Legacy rule must not force a hard 55 floor solely for missing payoff.
    assert not any(
        abs(float(item.dropoff_risk) - 55.0) < 0.01 and float(item.reading_momentum or 0) > 50
        for item in derived
    )
    # Consecutive declines add bonus on later scenes.
    assert float(derived[-1].dropoff_risk) >= base_expected(derived[-1])


def base_expected(profile: SceneReaderJourneyProfileItemV2) -> float:
    return 100.0 - float(profile.reading_momentum or 0.0)


def test_beats_excluded_from_chapter_mean():
    scene = _profile(1, node_type="scene", evidence=["P1"])
    beat = _profile(2, node_type="beat", evidence=["P2"])
    derived = derive_chapter_profiles([scene, beat])
    mean = chapter_mean_reading_momentum(derived)
    scene_only = [item for item in derived if item.node_type == "scene"][0]
    assert mean == pytest.approx(float(scene_only.reading_momentum), abs=0.2)
    assert derived[1].include_in_main_curve is False


# --- Scene / Beat consolidation ---


def test_living_room_silence_does_not_create_independent_main_curve_v_shape():
    """“客厅陷入死寂。” must not remain an independent Scene that V-bends the curve."""
    assert looks_like_silence_reaction_or_environment_beat("客厅陷入死寂。")
    paragraphs = _paras(
        [
            "林舟盯着沙发上的信封，呼吸忽然乱了。",
            "他想开口问，却发现喉咙发紧。",
            "客厅陷入死寂。",
            "门外传来极其轻微的脚步声，像有人贴着墙路过。",
            "林舟终于把信封翻过来。",
        ]
    )
    # Fake strong labels around the silence sentence (as in the audit sample).
    meta = {
        paragraphs[1].id: BoundaryMeta(
            reason_codes=frozenset({"viewpoint_change"}),
            concise_reason="视角变化（误标）",
        ),
        paragraphs[2].id: BoundaryMeta(
            reason_codes=frozenset({"time_jump"}),
            concise_reason="时间跳跃（误标）",
        ),
    }
    scenes, kept = _range_texts(
        paragraphs, [paragraphs[1].id, paragraphs[2].id], meta
    )
    assert all(scene != ["客厅陷入死寂。"] for scene in scenes)
    assert "客厅陷入死寂。" in "".join(scenes[0]) or "客厅陷入死寂。" in "".join(
        "".join(part) for part in scenes
    )
    # Opening boundary into the silence beat should be dropped (merge into previous).
    assert paragraphs[1].id not in kept or paragraphs[2].id not in kept


# --- Question lifecycle ---


def test_question_lifecycle_statuses():
    profiles = [
        _profile(
            1,
            scene_role="open_end",
            levels={"hook": 5, "curiosity": 4, "payoff": 1},
            evidence=["P1"],
            hook_rationale="他究竟是谁？",
        ),
        _profile(
            2,
            scene_role="investigation",
            levels={"hook": 4, "curiosity": 4, "payoff": 2},
            evidence=["P2"],
            hook_rationale="他究竟是谁？",
        ),
        _profile(
            3,
            scene_role="reveal",
            levels={"hook": 2, "curiosity": 2, "payoff": 5, "question_lifecycle": 5},
            evidence=["P3"],
        ),
    ]
    derived = derive_chapter_profiles(profiles)
    records = build_question_lifecycle(derived)
    assert records
    assert records[0].question_id.startswith("q")
    assert records[0].setup_scene == 1
    assert records[0].status in {"paid_off", "progressing", "open", "overdue"}
    # After reveal with high payoff, expect paid_off.
    assert any(item.status == "paid_off" for item in records)


# --- Diagnosis ---


def test_diagnosis_engine_codes():
    stagnant = _profile(
        1,
        levels={
            "goal_progress": 0,
            "conflict_change": 0,
            "state_change": 0,
            "information_gain": 0,
            "character_agency": 0,
            "causal_coherence": 0,
            "pacing_speed": 5,
            "clarity": 1,
            "hook": 1,
            "curiosity": 1,
            "tension": 1,
            "emotional_investment": 1,
        },
        evidence=["P1"],
        confidence=0.3,
    )
    derived, _ = derive_scene_metrics(stagnant)
    diag = diagnose_scene(derived)
    assert diag.primary_diagnosis is not None
    assert diag.primary_diagnosis in {
        "empty_fast_pacing",
        "plot_stagnation",
        "weak_progress",
        "unclear_expression",
        "pacing_too_fast",
        "low_confidence",
    }
    assert diag.severity in {"info", "low", "medium", "high", "critical"}
    assert diag.diagnostic_evidence.scene_ordinals == [1]

    beat = _profile(2, node_type="beat", evidence=[])
    beat_derived, _ = derive_scene_metrics(beat)
    beat_diag = diagnose_scene(beat_derived)
    assert "scene_boundary_anomaly" in (
        [beat_diag.primary_diagnosis] + beat_diag.secondary_diagnoses
    )
    assert beat_diag.data_quality_issue == "scene_boundary_anomaly"


def test_finalize_bundles_lifecycle_and_diagnosis():
    profiles = [_profile(1, evidence=["P1"]), _profile(2, node_type="beat", evidence=["P2"])]
    derived, stats = finalize_v2_profiles(profiles)
    assert stats["formula_version"] == "2.0"
    assert stats["legacy_consecutive_no_payoff_floor_applied"] is False
    assert stats["beat_count"] == 1
    assert isinstance(stats["question_lifecycle"], list)
    assert isinstance(stats["scene_diagnoses"], list)
    assert len(derived) == 2


# --- Legacy compatibility ---


def test_legacy_compatibility_markers():
    assert is_legacy_contract("1.3") is True
    assert is_legacy_contract("1.2") is True
    assert is_v2_contract("2.0") is True
    assert calibration_label("1.3", prompt_version="v1.6") == "legacy_uncalibrated"
    assert calibration_label("2.0", prompt_version="v2.0") == "v2_calibrated"
    payload = enrich_result_compatibility(
        {"ok": True},
        scene_contract_version="1.3",
        scene_prompt_version="v1.6",
        formula_version="1.0",
    )
    assert payload["legacy_uncalibrated"] is True
    assert payload["display_mode"] == "legacy_v1"
    assert payload["contract_version"] == "1.3"
    payload_v2 = enrich_result_compatibility(
        {},
        scene_contract_version="2.0",
        scene_prompt_version="v2.0",
        formula_version="2.0",
    )
    assert payload_v2["legacy_uncalibrated"] is False
    assert payload_v2["display_mode"] == "v2"


# --- CHG-20260721-012 verification matrix (no new product behavior) ---


def test_verify_plot_low_pacing_low_is_stagnation():
    profile = _profile(
        1,
        levels={
            "goal_progress": 0,
            "conflict_change": 0,
            "state_change": 0,
            "information_gain": 0,
            "character_agency": 0,
            "causal_coherence": 0,
            "pacing_speed": 1,
            "curiosity": 2,
            "tension": 2,
            "emotional_investment": 2,
            "clarity": 4,
        },
        evidence=["P1"],
    )
    derived, _ = derive_scene_metrics(profile)
    assert float(derived.plot_progress or 0) < 30
    assert mapped_pace(derived) < 40
    diag = diagnose_scene(derived)
    codes = [diag.primary_diagnosis, *diag.secondary_diagnoses]
    assert "plot_stagnation" in codes or "weak_progress" in codes
    assert "empty_fast_pacing" not in codes


def test_verify_plot_low_pacing_high_is_empty_spin():
    profile = _profile(
        1,
        levels={
            "goal_progress": 0,
            "conflict_change": 0,
            "state_change": 0,
            "information_gain": 0,
            "character_agency": 0,
            "causal_coherence": 0,
            "pacing_speed": 5,
            "curiosity": 2,
            "tension": 2,
            "emotional_investment": 2,
            "clarity": 4,
        },
        evidence=["P1"],
    )
    derived, _ = derive_scene_metrics(profile)
    assert float(derived.plot_progress or 0) < 35
    assert mapped_pace(derived) > 70
    diag = diagnose_scene(derived)
    codes = [diag.primary_diagnosis, *diag.secondary_diagnoses]
    assert "empty_fast_pacing" in codes


def test_verify_high_hook_without_payoff_is_empty_or_delayed():
    first = _profile(
        1,
        scene_role="open_end",
        levels={"hook": 5, "payoff": 0, "curiosity": 4, "clarity": 4},
        evidence=["P1"],
        hook_rationale="他究竟是谁？",
    )
    second = _profile(
        2,
        scene_role="investigation",
        levels={"hook": 4, "payoff": 0, "curiosity": 3, "clarity": 4},
        evidence=["P2"],
    )
    derived = derive_chapter_profiles([first, second])
    lifecycle = build_question_lifecycle(derived)
    diag2 = diagnose_scene(derived[1], previous=derived[0], lifecycle=lifecycle)
    codes = [diag2.primary_diagnosis, *diag2.secondary_diagnoses]
    assert any(code in {"empty_hook", "delayed_payoff", "weak_hook"} for code in codes if code)


def test_verify_metrics_are_deterministic_recomputable_from_base_fields():
    from app.services.reader_journey_v2_derivation import (
        compute_plot_progress,
        compute_reading_tension,
        load_scene_role_targets,
    )
    from app.services.reader_journey_v2_mapping import (
        apply_profile_mapped_scores,
        load_formula_v2_config,
    )

    profile = _profile(
        1,
        scene_role="escalation",
        levels={
            "goal_progress": 4,
            "conflict_change": 3,
            "state_change": 3,
            "information_gain": 4,
            "character_agency": 3,
            "causal_coherence": 3,
            "curiosity": 4,
            "tension": 4,
            "emotional_investment": 3,
            "pacing_speed": 3,
            "hook": 4,
            "payoff": 2,
            "clarity": 4,
            "cognitive_load": 2,
            "redundancy": 1,
        },
        evidence=["P1", "P2"],
    )
    cfg = load_formula_v2_config()
    roles = load_scene_role_targets()
    updated, derived = derive_scene_metrics(profile, formula_config=cfg, role_targets=roles)
    scored = apply_profile_mapped_scores(profile, config=cfg)
    plot = compute_plot_progress(scored, weights=cfg["weights"]["plot_progress"])
    tension = compute_reading_tension(scored, weights=cfg["weights"]["reading_tension"])
    assert float(derived.plot_progress or 0) == pytest.approx(plot, abs=0.2)
    assert float(derived.reading_tension or 0) == pytest.approx(tension, abs=0.2)
    # Re-derive must be stable (no chapter min-max normalization side effects).
    again, derived2 = derive_scene_metrics(profile, formula_config=cfg, role_targets=roles)
    assert derived2.reading_momentum == derived.reading_momentum
    assert again.goal_progress.mapped_score == updated.goal_progress.mapped_score

def test_verify_no_chapter_minmax_normalization_in_v2_formula():
    low = _profile(1, levels={"goal_progress": 1, "curiosity": 1, "tension": 1}, evidence=["A"])
    high = _profile(2, levels={"goal_progress": 5, "curiosity": 5, "tension": 5}, evidence=["B"])
    alone_high, d_high = derive_scene_metrics(high)
    chapter = derive_chapter_profiles([low, high])
    # Absolute scores must not be rescaled by other scenes in the chapter.
    assert chapter[1].reading_momentum == pytest.approx(float(d_high.reading_momentum), abs=0.2)
    assert chapter[1].plot_progress == pytest.approx(float(alone_high.plot_progress or 0), abs=0.2)


def test_verify_sqlite_legacy_sample_is_uncalibrated_contract():
    import os
    import sqlite3
    from pathlib import Path

    from app.services.reader_journey_v2_compatibility import calibration_label

    paths = [
        Path("data/storylens.db"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "StoryLens" / "database" / "storylens.db",
    ]
    found = False
    for path in paths:
        if not path.exists():
            continue
        con = sqlite3.connect(str(path))
        cur = con.cursor()
        row = cur.execute(
            "SELECT scene_contract_version, scene_prompt_version FROM reader_journey_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        con.close()
        if not row:
            continue
        contract, prompt = row
        if not str(contract).startswith("1."):
            continue
        found = True
        assert calibration_label(str(contract), prompt_version=str(prompt)) == "legacy_uncalibrated"
        break
    if not found:
        pytest.skip("no legacy 1.x reader_journey_runs sample in local SQLite")


def mapped_pace(profile):
    from app.services.reader_journey_v2_mapping import mapped_or_zero

    return mapped_or_zero(profile.pacing_speed)