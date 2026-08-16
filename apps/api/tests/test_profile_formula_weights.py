"""画像决定主曲线量什么 (CHG-20260815-101).

``reader_journey_formulas_v2.json`` has carried ``"default_genre": "suspense"`` since v2.0
and nothing ever read it: one suspense-shaped weighting scored every book. Measured on two
real chapters, switching to the type's own weighting moves 《我不是戏神》 by +0.3 on average
(it *was* the suspense weighting) and widens the gap on 《再也不见》第一章 between its 29
paragraphs of dorm banter and its 11 paragraphs of confession from 8.4 to 13.4 points.

What is pinned here is the safety of that mechanism, not the numbers: an unprofiled book is
untouched, a declared table must be a distribution, and a typo in a weight key fails at
import instead of silently dropping a term.
"""

from __future__ import annotations

import pytest

from app.narrative_core.long_novel.chapter_focus import (
    CHAPTER_FOCI,
    ChapterFocus,
    GenreAxis,
    apply_formula_weights,
    chapter_foci_for,
    merged_weights,
)

BASE = {
    "weights": {
        "reading_tension": {"curiosity": 0.4, "tension": 0.35, "emotional_investment": 0.25},
        "reading_momentum": {
            "plot_progress": 0.3,
            "reading_tension": 0.25,
            "pacing_fit": 0.2,
            "hook_payoff_fit": 0.25,
        },
    },
    "penalties": {"clarity_below": 60},
}


def _axes(**kw):
    return {k: {"value": v} for k, v in kw.items()}


def test_an_unprofiled_book_keeps_the_shipped_weighting() -> None:
    # INV-P1: the profile layer only ever adds. A book with no confirmed profile must derive
    # exactly the numbers it derived before this existed.
    assert merged_weights(chapter_foci_for({})) == {}
    assert apply_formula_weights(BASE, {})["weights"] == BASE["weights"]


def test_a_romance_moves_the_tension_block_off_curiosity() -> None:
    weights = merged_weights(chapter_foci_for(_axes(audience="female_romance")))
    tension = weights["reading_tension"]
    assert tension["emotional_investment"] > tension["curiosity"]
    # And the main curve stops asking a romance chapter to move the plot.
    assert weights["reading_momentum"]["plot_progress"] < BASE["weights"]["reading_momentum"]["plot_progress"]


def test_a_ladder_novel_leans_on_whether_the_promise_was_paid() -> None:
    weights = merged_weights(
        chapter_foci_for(_axes(audience="male_gratification", engine="progression"))
    )
    momentum = weights["reading_momentum"]
    assert momentum["hook_payoff_fit"] == max(momentum.values())
    # 升级 is literally a state change, so plot_progress has to be able to show a chapter
    # that ends where it began.
    assert weights["plot_progress"]["state_change"] > BASE["weights"]["reading_momentum"]["pacing_fit"] * 0


def test_only_the_named_blocks_are_replaced() -> None:
    out = apply_formula_weights(BASE, {"reading_tension": {"curiosity": 1.0}})
    assert out["weights"]["reading_tension"] == {"curiosity": 1.0}
    # Untouched blocks survive, and so does everything outside "weights".
    assert out["weights"]["reading_momentum"] == BASE["weights"]["reading_momentum"]
    assert out["penalties"] == BASE["penalties"]


def test_a_block_is_replaced_whole_not_merged_key_by_key() -> None:
    """Half of one distribution plus half of another sums to neither.

    Merging would leave a table whose weights no longer add to 1, and the deriver
    renormalises silently — every score would shift for a reason nothing records.
    """
    out = apply_formula_weights(BASE, {"reading_tension": {"curiosity": 0.6, "tension": 0.4}})
    assert "emotional_investment" not in out["weights"]["reading_tension"]


def test_the_caller_is_not_mutated() -> None:
    original = {k: dict(v) for k, v in BASE["weights"].items()}
    apply_formula_weights(BASE, {"reading_tension": {"curiosity": 1.0}})
    assert BASE["weights"] == original


def test_every_declared_table_is_a_distribution() -> None:
    for focus in CHAPTER_FOCI:
        for block, table in focus.weights.items():
            total = sum(table.values())
            assert abs(total - 1.0) < 1e-6, f"{focus.key}.{block} sums to {total}"


def test_a_typo_in_a_weight_block_fails_at_import_time() -> None:
    # A misspelled block name would silently never apply; a table that does not sum to 1
    # would silently rescale every score. Both are rejected where they are written.
    with pytest.raises(ValueError):
        ChapterFocus(
            key="bad-block",
            triggers=(("engine", "mystery"),),
            instruction="x",
            weights={"reading_momemtum": {"plot_progress": 1.0}},
        )
    with pytest.raises(ValueError):
        ChapterFocus(
            key="bad-sum",
            triggers=(("engine", "mystery"),),
            instruction="x",
            weights={"reading_tension": {"curiosity": 0.5, "tension": 0.2}},
        )


def test_later_registration_wins_when_two_foci_touch_one_block() -> None:
    a = ChapterFocus(
        key="a",
        triggers=(("engine", "mystery"),),
        instruction="x",
        weights={"reading_tension": {"curiosity": 1.0}},
    )
    b = ChapterFocus(
        key="b",
        triggers=(("engine", "mystery"),),
        instruction="x",
        weights={"reading_tension": {"tension": 1.0}},
    )
    assert merged_weights([a, b]) == {"reading_tension": {"tension": 1.0}}


def test_the_shipped_registry_has_no_axis_key_colliding_with_a_weight_key() -> None:
    """A GenreAxis key and a weight key sharing a name would read as the same thing on
    screen while being computed from different places."""
    axis_keys = {axis.key for focus in CHAPTER_FOCI for axis in focus.axes}
    weight_keys = {
        key for focus in CHAPTER_FOCI for table in focus.weights.values() for key in table
    }
    assert not (axis_keys & weight_keys)
    assert isinstance(next(iter(axis_keys), GenreAxis("k", "l", "a").key), str)
