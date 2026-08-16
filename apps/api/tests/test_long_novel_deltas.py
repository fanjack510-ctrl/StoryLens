"""Profile deltas: what each axis value adds, and what it must never touch.

INV-P1 says a delta may add and never remove. INV-P5 says every registered delta carries a
fixture — the two extraction fields that shipped broken (all-zero counters, all-``advance``
action kinds) were both paths nothing had exercised, so a delta with no test is treated here
as a delta that does not exist.

The load-bearing assertion is the first one: with no delta active the prompt must be *byte
identical* to the core prompt. It is not tidiness. The prompt hash gates extraction reuse, so
a stray space would invalidate every cached block on every book — measured once at ¥0.77 when
``pov_entity`` was put in the core skeleton instead of behind its delta.
"""

from app.narrative_core.long_novel.contracts.l1 import (
    BlockAsset,
    PowerBeat,
    power_direction,
)
from app.narrative_core.long_novel.deltas import (
    DELTAS,
    delta_fields,
    delta_prompt,
    deltas_for,
)


def test_no_profile_means_no_prompt_change_at_all():
    assert delta_prompt(deltas_for({})) == ""
    assert delta_prompt(deltas_for({"engine": "mystery", "pov": "single_lead"})) == ""
    assert delta_fields(deltas_for({"engine": "mystery"})) == ()


def test_progression_switches_on_power_beats_and_nothing_else():
    active = deltas_for({"engine": "progression", "pov": "single_lead"})
    assert [delta.key for delta in active] == ["power_beats"]
    assert delta_fields(active) == ("power_beats",)


def test_ensemble_switches_on_pov_entity_and_nothing_else():
    active = deltas_for({"engine": "mystery", "pov": "ensemble"})
    assert [delta.key for delta in active] == ["pov_entity"]


def test_two_axes_can_be_active_together():
    active = deltas_for({"engine": "progression", "pov": "ensemble"})
    assert set(delta_fields(active)) == {"pov_entity", "power_beats"}


def test_the_stored_axis_shape_is_accepted_as_well_as_a_plain_mapping():
    stored = {"engine": {"value": "progression", "source": "confirmed"}}
    assert [delta.key for delta in deltas_for(stored)] == ["power_beats"]


def test_every_registered_delta_names_the_fields_it_adds():
    for delta in DELTAS:
        assert delta.fields, f"{delta.key} adds no field"
        assert delta.instruction.strip(), f"{delta.key} has no prompt text"
        assert BlockAsset.model_fields.keys() >= {
            field for field in delta.fields if field in BlockAsset.model_fields
        }


def test_a_book_without_the_delta_carries_an_empty_list_not_a_missing_field():
    asset = BlockAsset(asset_schema_version="1")
    assert asset.power_beats == []


def test_a_power_beat_round_trips_with_the_level_named_by_the_book():
    beat = PowerBeat(
        entity_ref="李一",
        chapter_ref=312,
        kind="demote",
        level="三阶",
        why="被夺去戏本，阶位跌落",
        evidence=[{"paragraph_ref": 14}],
    )
    assert beat.level == "三阶"
    assert power_direction(beat.kind) == -1


def test_an_unknown_kind_is_not_silently_read_as_a_rise():
    # A book whose ladder only ever goes up is the failure this guards: an unrecognised word
    # must read as "we do not know", never as progress.
    assert power_direction("晋升") == 0
    assert power_direction("") == 0
    assert power_direction("promote") == 1
    assert power_direction("PROMOTE ") == 1


def test_every_delta_shows_the_shape_and_not_only_the_prose():
    """Measured: a delta that only describes its field in prose does not get filled.

    ``pov_entity`` asked, in words, for an extra key on every ``chapter_signals`` entry. The
    core schema skeleton — which the model can see — lists that object *without* the key, and
    the skeleton won: 7 chapters of 806 came back filled, on the one delta the design document
    calls implemented and tested. ``power_beats``, whose instruction carries an explicit JSON
    fragment, filled 403 rows across 163 blocks of a comparable book.

    So a field name has to appear as a JSON key in the instruction, not merely be mentioned.
    """
    for delta in DELTAS:
        for field in delta.fields:
            assert f'"{field}"' in delta.instruction, (
                f"{delta.key}: the instruction never shows {field} as a JSON key, so the core "
                f"skeleton is the only shape the model sees"
            )
