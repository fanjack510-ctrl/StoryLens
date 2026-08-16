"""专项维度与工艺缺陷标记的校验 (CHG-20260815-100).

Two failures observed against the real model are pinned here.

The model invents axis keys when the field exists but no list is given: an unprompted run
returned ``mystery_hook`` and ``clue_fairness``, names that appear nowhere in the profile
vocabulary and therefore cannot be compared between two books or between two runs of the
same book.

And it will name a defect while leaving the corresponding score untouched — a craft flag
saying "第 12 段与第 3 段矛盾" printed directly above ``setup_consistency: 5``. Whichever of
the two is right, showing both is worse than showing either.
"""

from __future__ import annotations

import pytest

from app.schemas.reader_journey_v2 import SceneReaderJourneyBatchResultV2
from app.services.reader_journey_v2_execution import validate_scene_batch_result_v2
from app.services.validation_errors import StructuralValidationError

PIDS = [f"B0001-C0001-P{n:04d}" for n in range(1, 6)]

LEVEL_FIELDS = (
    "goal_progress conflict_change state_change information_gain character_agency "
    "causal_coherence curiosity tension emotional_investment pacing_speed hook payoff "
    "setup_consistency question_lifecycle emotional_valence_start emotional_valence_end "
    "arousal_start arousal_end clarity cognitive_load redundancy"
).split()


def _profile(**overrides):
    base = {
        "scene_id": 1,
        "scene_ordinal": 1,
        "scene_role": "setup",
        "scene_value_summary": "主角回到家中，父母见到他神色骤变。",
        "confidence": 0.8,
        "evidence_paragraph_ids": [PIDS[0]],
    }
    for name in LEVEL_FIELDS:
        base[name] = {
            "level": 3,
            "evidence_paragraph_ids": [PIDS[0]],
            "rationale": "有正文依据。",
            "confidence": 0.8,
        }
    base.update(overrides)
    return base


def _validate(profile, *, allowed_axis_keys=None, required_axis_keys=None):
    value = SceneReaderJourneyBatchResultV2.model_validate({"profiles": [profile]})
    validate_scene_batch_result_v2(
        value,
        expected_scene_ids={1},
        paragraph_ids_by_scene={1: set(PIDS)},
        allowed_axis_keys=allowed_axis_keys,
        required_axis_keys=required_axis_keys,
    )


def _axis(key="clue_placement", **kw):
    return {
        "key": key,
        "label": "线索投放",
        "level": 4,
        "evidence_paragraph_ids": [PIDS[1]],
        "rationale": "投放了父母反常这一条可推理线索。",
        **kw,
    }


def test_axis_from_the_books_own_list_passes() -> None:
    _validate(_profile(genre_axes=[_axis()]), allowed_axis_keys={"clue_placement", "fair_play"})


def test_invented_axis_key_is_rejected() -> None:
    with pytest.raises(StructuralValidationError) as err:
        _validate(
            _profile(genre_axes=[_axis(key="mystery_hook")]),
            allowed_axis_keys={"clue_placement", "fair_play"},
        )
    assert err.value.error_code == "JOURNEY_GENRE_AXIS_UNKNOWN"


def test_axis_evidence_must_come_from_this_scene() -> None:
    with pytest.raises(StructuralValidationError) as err:
        _validate(
            _profile(genre_axes=[_axis(evidence_paragraph_ids=["B0001-C0009-P0001"])]),
            allowed_axis_keys={"clue_placement"},
        )
    assert err.value.error_code == "JOURNEY_EVIDENCE_OUT_OF_SCENE"


def test_unprofiled_book_may_not_carry_axes_at_all() -> None:
    # No confirmed profile means no list was ever shown to the model, so anything it puts
    # here it made up.
    with pytest.raises(StructuralValidationError):
        _validate(_profile(genre_axes=[_axis()]), allowed_axis_keys=set())


def test_flag_without_the_matching_downgrade_is_rejected() -> None:
    flagged = _profile(
        craft_flags=[
            {
                "kind": "setup_contradiction",
                "evidence_paragraph_ids": [PIDS[2]],
                "detail": "第 3 段说他淋透了，第 5 段说衣服是干的。",
            }
        ],
    )
    flagged["setup_consistency"]["level"] = 5
    with pytest.raises(StructuralValidationError) as err:
        _validate(flagged)
    assert err.value.error_code == "JOURNEY_CRAFT_FLAG_INCONSISTENT"


def test_flag_with_the_matching_downgrade_passes() -> None:
    flagged = _profile(
        craft_flags=[
            {
                "kind": "setup_contradiction",
                "evidence_paragraph_ids": [PIDS[2]],
                "detail": "第 3 段说他淋透了，第 5 段说衣服是干的。",
            }
        ],
    )
    flagged["setup_consistency"]["level"] = 2
    _validate(flagged)


def test_redundancy_flag_reads_the_other_way_round() -> None:
    """redundancy is the one axis where a low level is the good outcome.

    A ``redundant_passage`` flag therefore has to push it **up**, and the bound that catches
    an inconsistent pair is a minimum, not a maximum.
    """
    flagged = _profile(
        craft_flags=[
            {
                "kind": "redundant_passage",
                "evidence_paragraph_ids": [PIDS[3]],
                "detail": "第 4 段与第 2 段逐字重复。",
            }
        ],
    )
    flagged["redundancy"]["level"] = 1
    with pytest.raises(StructuralValidationError):
        _validate(flagged)
    flagged["redundancy"]["level"] = 4
    _validate(flagged)


def test_no_axes_and_no_flags_is_the_ordinary_case() -> None:
    _validate(_profile())


def test_axes_and_flags_reach_the_visualization_bridge() -> None:
    """The scoring is invisible unless it crosses into deterministic_statistics_json.

    That bridge is where the earlier per-dimension insights already travel; adding two more
    keys there is what puts the axes on screen. A profile with neither must add no keys at
    all, so a legacy payload keeps its exact shape.
    """
    from app.schemas.reader_journey_v2 import SceneReaderJourneyProfileItemV2
    from app.services.reader_journey_v2_persist import build_v2_deterministic_statistics

    plain = SceneReaderJourneyProfileItemV2.model_validate(_profile())
    scored = SceneReaderJourneyProfileItemV2.model_validate(
        _profile(
            scene_id=2,
            scene_ordinal=2,
            genre_axes=[_axis()],
            craft_flags=[
                {
                    "kind": "redundant_passage",
                    "evidence_paragraph_ids": [PIDS[3]],
                    "detail": "第 4 段与第 2 段逐字重复。",
                }
            ],
        )
    )
    scored.redundancy.level = 4  # the flag and the field have to agree

    empty = build_v2_deterministic_statistics(derived=[plain], finalize_stats={})
    assert "v2_genre_axes" not in empty
    assert "v2_craft_flags" not in empty

    full = build_v2_deterministic_statistics(derived=[plain, scored], finalize_stats={})
    assert list(full["v2_genre_axes"]) == ["2"]  # keyed by scene ordinal, unprofiled absent
    assert full["v2_genre_axes"]["2"][0]["key"] == "clue_placement"
    assert full["v2_craft_flags"]["2"][0]["kind"] == "redundant_passage"


def test_a_scene_may_not_silently_omit_a_required_axis() -> None:
    """The first production run under this prompt dropped both axes on scene 5 of 6.

    A missing axis is not a low score — it is a hole in a curve the reader reads across
    scenes. The anchors already say what to do when a scene has nothing to show: give 0 and
    say why.
    """
    with pytest.raises(StructuralValidationError) as err:
        _validate(
            _profile(genre_axes=[_axis()]),
            allowed_axis_keys={"clue_placement", "fair_play"},
            required_axis_keys={"clue_placement", "fair_play"},
        )
    assert err.value.error_code == "JOURNEY_GENRE_AXIS_MISSING"


def test_gated_axes_are_not_required_of_every_scene() -> None:
    """开篇抓力 belongs to the chapter's first scene; demanding it everywhere reinstates the
    noise the scope gate removed."""
    from app.narrative_core.long_novel.chapter_focus import (
        chapter_foci_for,
        required_axis_keys,
        selected_axes,
    )

    axes = selected_axes(
        chapter_foci_for(
            {"monetization": {"value": "fast_food_free"}, "engine": {"value": "mystery"}}
        )
    )
    assert {axis.key for axis in axes} == {
        "opening_grip",
        "chapter_end_hook",
        "clue_placement",
        "fair_play",
    }
    assert required_axis_keys(axes) == {"clue_placement", "fair_play"}


def test_the_contract_cap_admits_every_answer_the_selector_can_ask_for() -> None:
    """The schema cap and the selector must not drift apart.

    They did: MAX_GENRE_AXES went to 5 while the contract still said 4, and three
    consecutive *correct* answers on 《再也不见》第一章 were rejected as too long. A cap that
    rejects what the prompt asked for is worse than no cap.
    """
    from app.narrative_core.long_novel.chapter_focus import (
        CHAPTER_FOCI,
        MAX_GENRE_AXES,
        chapter_foci_for,
        selected_axes,
    )

    # The widest legal answer: every per-scene axis the cap allows, plus every gated axis a
    # single scene could carry at once (a one-scene chapter is its own opening and ending).
    worst = 0
    for focus in CHAPTER_FOCI:
        axes = selected_axes(chapter_foci_for({a: {"value": v} for a, v in focus.triggers}))
        worst = max(worst, len([a for a in axes if a.scope != "scene"]))
    ceiling = MAX_GENRE_AXES + worst

    field = SceneReaderJourneyBatchResultV2.model_fields["profiles"]
    del field  # the constraint lives on the item model
    from app.schemas.reader_journey_v2 import SceneReaderJourneyProfileItemV2

    meta = SceneReaderJourneyProfileItemV2.model_fields["genre_axes"].metadata
    declared = next(getattr(m, "max_length") for m in meta if hasattr(m, "max_length"))
    assert declared >= ceiling
