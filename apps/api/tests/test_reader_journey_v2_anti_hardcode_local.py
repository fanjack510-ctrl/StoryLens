"""Anti-hardcoding guards for Reader Journey v2 diagnosis (CHG-20260721-012).

These tests assert diagnoses follow metrics / lifecycle relationships — not
fixed scene_id, ordinal labels, or fixture Chinese prose. They do not call models.
"""

from __future__ import annotations

from pathlib import Path

from app.schemas.reader_journey_v2 import SceneReaderJourneyProfileItemV2
from app.services.reader_journey_v2_derivation import derive_chapter_profiles
from app.services.reader_journey_v2_diagnosis import diagnose_scene
from app.services.reader_journey_v2_finalize import finalize_v2_profiles
from app.services.reader_journey_v2_mapping import apply_profile_mapped_scores
from app.services.reader_journey_v2_question_lifecycle import build_question_lifecycle
from tests.test_reader_journey_v2_local import _profile

REPO_ROOT = Path(__file__).resolve().parents[3]
PRODUCT_SOURCE_GLOBS = (
    "apps/api/app/**/*.py",
    "apps/desktop/src/**/*.{ts,tsx}",
    "packages/prompts/**/*",
)
# Exact / distinctive fixture phrases from the synthetic V2 preview chapter.
FORBIDDEN_FIXTURE_PHRASES = (
    "走了两圈",
    "客厅陷入死寂",
    "动作又急又碎",
    "威胁被轻易放过",
    "威胁感被轻易放过",
    "迟迟不兑现",
    "鞋印和钥匙",
    "牛角坳样例",
    "V2本地验证 · 牛角坳",
)
FORBIDDEN_ORDINAL_BRANCH_SNIPPETS = (
    "scene_ordinal == 2",
    "scene_ordinal == 3",
    "scene_ordinal == 4",
)


def _stagnation_levels() -> dict[str, int]:
    return {
        "goal_progress": 0,
        "conflict_change": 0,
        "state_change": 0,
        "information_gain": 0,
        "character_agency": 1,
        "causal_coherence": 2,
        "curiosity": 2,
        "tension": 1,
        "emotional_investment": 1,
        "pacing_speed": 2,
        "hook": 1,
        "payoff": 0,
        "setup_consistency": 3,
        "question_lifecycle": 2,
    }


def _empty_fast_levels() -> dict[str, int]:
    return {
        "goal_progress": 0,
        "conflict_change": 1,
        "state_change": 1,
        "information_gain": 1,
        "character_agency": 2,
        "causal_coherence": 2,
        "curiosity": 2,
        "tension": 3,
        "emotional_investment": 2,
        "pacing_speed": 5,
        "hook": 2,
        "payoff": 0,
        "setup_consistency": 3,
        "question_lifecycle": 2,
    }


def _strong_payoff_levels() -> dict[str, int]:
    return {
        "goal_progress": 5,
        "conflict_change": 4,
        "state_change": 4,
        "information_gain": 5,
        "character_agency": 4,
        "causal_coherence": 4,
        "curiosity": 3,
        "tension": 4,
        "emotional_investment": 4,
        "pacing_speed": 3,
        "hook": 3,
        "payoff": 5,
        "setup_consistency": 4,
        "question_lifecycle": 5,
    }


def _with_derived(profile: SceneReaderJourneyProfileItemV2) -> SceneReaderJourneyProfileItemV2:
    mapped = apply_profile_mapped_scores(profile)
    return derive_chapter_profiles([mapped])[0]


def test_stagnation_diagnosis_follows_metrics_not_scene_id():
    """Move original S2-like metrics to ordinal 8 — diagnosis must follow data."""
    at_s2 = _with_derived(_profile(2, levels=_stagnation_levels(), evidence=["P0002"]))
    at_s8 = _with_derived(_profile(8, levels=_stagnation_levels(), evidence=["P0008"]))
    d2 = diagnose_scene(at_s2)
    d8 = diagnose_scene(at_s8)
    assert d2.primary_diagnosis in {"plot_stagnation", "weak_progress"}
    assert d8.primary_diagnosis == d2.primary_diagnosis
    assert d8.scene_ordinal == 8
    assert d2.scene_ordinal == 2


def test_empty_fast_pacing_unchanged_when_renamed_to_s1():
    """S4-like empty-fast metrics labeled as S1 must still diagnose empty_fast_pacing."""
    as_s4 = _with_derived(_profile(4, levels=_empty_fast_levels(), evidence=["P0004"]))
    as_s1 = _with_derived(_profile(1, levels=_empty_fast_levels(), evidence=["P0001"]))
    d4 = diagnose_scene(as_s4)
    d1 = diagnose_scene(as_s1)
    assert "empty_fast_pacing" in ([d4.primary_diagnosis] + list(d4.secondary_diagnoses))
    assert "empty_fast_pacing" in ([d1.primary_diagnosis] + list(d1.secondary_diagnoses))
    assert d1.scene_ordinal == 1


def test_same_scene_id_diagnosis_changes_when_metrics_change():
    """Keep scene_id/ordinal fixed; swapping metrics must change diagnosis."""
    scene_id = 42
    stagnant = _with_derived(
        _profile(scene_id, levels=_stagnation_levels(), evidence=["P0042"])
    )
    payoff = _with_derived(
        _profile(
            scene_id,
            levels=_strong_payoff_levels(),
            evidence=["P0042"],
            scene_role="reveal",
        )
    )
    # Force identical scene_id field as well as ordinal.
    stagnant = stagnant.model_copy(update={"scene_id": scene_id})
    payoff = payoff.model_copy(update={"scene_id": scene_id})
    d_low = diagnose_scene(stagnant)
    d_high = diagnose_scene(payoff)
    assert d_low.primary_diagnosis in {"plot_stagnation", "weak_progress"}
    assert d_high.positive_mechanism == "effective_payoff" or d_high.primary_diagnosis != d_low.primary_diagnosis
    assert d_low.primary_diagnosis != d_high.primary_diagnosis or (
        d_high.positive_mechanism == "effective_payoff"
        and d_low.positive_mechanism != "effective_payoff"
    )


def test_diagnoses_rederived_from_levels_without_preset_diagnoses():
    """No preset diagnoses — finalize must recompute from levels / formulas."""
    raw = [
        _profile(1, levels=_stagnation_levels(), evidence=["P0001"]),
        _profile(2, levels=_empty_fast_levels(), evidence=["P0002"]),
        _profile(
            3,
            levels=_strong_payoff_levels(),
            evidence=["P0003"],
            scene_role="reveal",
            hook_rationale="文书为何要动铁锁？",
        ),
    ]
    # Ensure profiles carry no pre-baked diagnosis fields (schema has none).
    for item in raw:
        assert not hasattr(item, "primary_diagnosis") or getattr(item, "primary_diagnosis", None) is None

    derived, stats = finalize_v2_profiles(raw)
    diagnoses = stats["scene_diagnoses"]
    assert len(diagnoses) == 3
    assert diagnoses[0]["primary_diagnosis"] in {"plot_stagnation", "weak_progress"}
    codes_s2 = [diagnoses[1]["primary_diagnosis"], *diagnoses[1]["secondary_diagnoses"]]
    assert "empty_fast_pacing" in codes_s2
    assert any(item.reading_momentum is not None for item in derived)
    assert any(item.plot_progress is not None for item in derived)


def test_question_lifecycle_recomputes_after_shuffle():
    """Lifecycle setup/payoff must follow question text relationships, not list order."""
    setup = _profile(
        1,
        levels={"hook": 4, "curiosity": 4, "payoff": 1, "question_lifecycle": 4},
        evidence=["P0001"],
        hook_rationale="井口铁锁为什么被人动过？",
    )
    develop = _profile(
        2,
        levels={"hook": 3, "curiosity": 3, "payoff": 1, "question_lifecycle": 3},
        evidence=["P0002"],
        hook_rationale="井口铁锁为什么被人动过？",
    )
    payoff = _profile(
        3,
        levels={"hook": 2, "curiosity": 2, "payoff": 5, "question_lifecycle": 5},
        evidence=["P0003"],
        scene_role="reveal",
        hook_rationale="井口铁锁为什么被人动过？",
    )
    natural, _ = finalize_v2_profiles([setup, develop, payoff])
    natural_life = build_question_lifecycle(natural)
    assert natural_life
    paid = [item for item in natural_life if item.status == "paid_off"]
    assert paid
    assert paid[0].setup_scene == 1
    assert paid[0].payoff_scene == 3

    # Same ordinals / relationships, but feed profiles in shuffled list order.
    shuffled_input = [payoff, setup, develop]
    shuffled, _ = finalize_v2_profiles(shuffled_input)
    shuffled_life = build_question_lifecycle(shuffled)
    paid2 = [item for item in shuffled_life if item.status == "paid_off"]
    assert paid2
    assert paid2[0].setup_scene == 1
    assert paid2[0].payoff_scene == 3
    assert paid2[0].setup_scene == paid[0].setup_scene
    assert paid2[0].payoff_scene == paid[0].payoff_scene


def _iter_product_source_files() -> list[Path]:
    files: list[Path] = []
    for pattern in PRODUCT_SOURCE_GLOBS:
        files.extend(REPO_ROOT.glob(pattern))
    out: list[Path] = []
    for path in files:
        if not path.is_file():
            continue
        name = path.name
        if name.endswith((".test.ts", ".test.tsx", "_test.py")):
            continue
        if "/tests/" in path.as_posix() or "\\tests\\" in str(path):
            continue
        out.append(path)
    return out


def test_product_source_has_no_fixture_chinese_prose():
    hits: list[str] = []
    for path in _iter_product_source_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for phrase in FORBIDDEN_FIXTURE_PHRASES:
            if phrase in text:
                hits.append(f"{path.relative_to(REPO_ROOT)}: {phrase}")
    assert hits == [], "Fixture Chinese prose leaked into product source:\n" + "\n".join(hits)


def test_product_source_has_no_fixed_s2_s3_s4_branches():
    """No diagnosis special-cases for synthetic ordinals 2/3/4."""
    # Narrow scan to diagnosis / visualization / derivation services + frontend diagnosis UI.
    targets = [
        REPO_ROOT / "apps/api/app/services/reader_journey_v2_diagnosis.py",
        REPO_ROOT / "apps/api/app/services/reader_journey_v2_derivation.py",
        REPO_ROOT / "apps/api/app/services/reader_journey_v2_finalize.py",
        REPO_ROOT / "apps/api/app/services/reader_journey_v2_question_lifecycle.py",
        REPO_ROOT / "apps/api/app/services/reader_journey_visualization.py",
        REPO_ROOT / "apps/desktop/src/components/readerJourney/diagnosisBandModel.ts",
        REPO_ROOT / "apps/desktop/src/components/readerJourney/journeyNodeDiagnosisStyle.ts",
        REPO_ROOT / "apps/desktop/src/components/readerJourney/observationLenses.ts",
    ]
    forbidden = (
        "scene_ordinal == 2",
        "scene_ordinal == 3",
        "scene_ordinal == 4",
        "scene_ordinal===2",
        "scene_ordinal===3",
        "scene_ordinal===4",
        'ordinal == 2',
        'ordinal == 3',
        'ordinal == 4',
        '== "S2"',
        "== 'S2'",
        '== "S3"',
        "== 'S3'",
        '== "S4"',
        "== 'S4'",
    )
    hits: list[str] = []
    for path in targets:
        text = path.read_text(encoding="utf-8")
        for snippet in forbidden:
            if snippet in text:
                hits.append(f"{path.name}: {snippet}")
    assert hits == [], "Fixed S2/S3/S4 branches found:\n" + "\n".join(hits)


def test_weak_tension_follows_tension_level_not_prose():
    low = _with_derived(
        _profile(7, levels={**_stagnation_levels(), "tension": 0, "curiosity": 3}, evidence=["P0007"])
    )
    high = _with_derived(
        _profile(7, levels={**_stagnation_levels(), "tension": 5, "curiosity": 3}, evidence=["P0007"])
    )
    d_low = diagnose_scene(low)
    d_high = diagnose_scene(high)
    assert "weak_tension" in ([d_low.primary_diagnosis] + list(d_low.secondary_diagnoses))
    assert "weak_tension" not in ([d_high.primary_diagnosis] + list(d_high.secondary_diagnoses))
