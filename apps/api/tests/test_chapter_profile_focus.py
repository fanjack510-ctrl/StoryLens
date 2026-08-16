"""画像 → 单章侧重 (10_ADAPTIVE_PROFILE_LAYER §4.4, CHG-20260815-091).

What is worth pinning: the chapter stack's prompt is byte identical for any book without a
*confirmed* profile — a draft changes nothing (INV-P2), and the focus block only ever
appends (INV-P1). The trigger vocabulary is the same closed axis set the whole-book deltas
dispatch on, checked at import time by the dataclass itself.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Book
from app.narrative_core.long_novel.chapter_focus import (
    CHAPTER_FOCI,
    ChapterFocus,
    apply_chapter_focus,
    chapter_foci_for,
    chapter_focus_for_book,
    chapter_focus_prompt,
    MAX_GENRE_AXES,
    selected_axes,
    DEFAULT_HOOK_VOCABULARY,
    HOOK_VOCABULARY,
    hook_vocabulary,
    suppressed_diagnoses,
)
from app.narrative_core.long_novel.profile_repository import BookProfileRepository
from app.narrative_core.migrations.runner import apply_narrative_migrations
from app.services.prompt_service import load_prompt


@pytest.fixture()
def session():
    path = os.path.join(tempfile.mkdtemp(), "focus.db")
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(bind=engine)
    apply_narrative_migrations(engine)
    made = sessionmaker(bind=engine)()
    made.add(Book(id=1, title="书", source_file_name="x.txt", source_file_hash="h"))
    made.commit()
    return made


def _draft(session, axes):
    BookProfileRepository(session).save_draft(1, {"axes": axes})


def _confirm(session, axes):
    _draft(session, axes)
    BookProfileRepository(session).confirm(1, axes)


def test_no_profile_prompt_is_byte_identical(session) -> None:
    prompt = load_prompt("reader_journey_scene", "v2.0")
    out = apply_chapter_focus(prompt, session, 1)
    assert out is prompt  # same object: same bytes, same content_hash, cache untouched


def test_draft_profile_changes_nothing(session) -> None:
    # INV-P2: an inferred profile is not a decision. Only 确认 moves the prompt.
    _draft(session, {"engine": {"value": "mystery", "source": "L0-B"}})
    prompt = load_prompt("reader_journey_scene", "v2.0")
    assert apply_chapter_focus(prompt, session, 1) is prompt


def test_confirmed_mystery_appends_clue_focus(session) -> None:
    _confirm(session, {"engine": {"value": "mystery", "source": "user"}})
    prompt = load_prompt("reader_journey_scene", "v2.0")
    out = apply_chapter_focus(prompt, session, 1)
    assert out is not prompt
    # Additive only: the original system prompt survives verbatim at the front.
    assert out.system.startswith(prompt.system)
    assert "线索" in out.system and "公平" in out.system
    assert out.user_template == prompt.user_template
    assert out.content_hash != prompt.content_hash  # provenance follows the actual text


def test_gratification_focus_requires_both_axes(session) -> None:
    # §4 binds 爽点 to male_gratification AND progression — a conjunction, not either.
    both = chapter_foci_for(
        {"audience": {"value": "male_gratification"}, "engine": {"value": "progression"}}
    )
    assert any(f.key == "gratification_beats" for f in both)
    only_engine = chapter_foci_for({"engine": {"value": "progression"}})
    assert not any(f.key == "gratification_beats" for f in only_engine)


def test_multiple_axes_stack(session) -> None:
    foci = chapter_foci_for(
        {
            "monetization": {"value": "fast_food_free"},
            "engine": {"value": "mystery"},
            "pov": {"value": "ensemble"},
        }
    )
    keys = [f.key for f in foci]
    assert keys == ["fast_food_hooks", "mystery_clues", "ensemble_pov"]  # registry order
    block = chapter_focus_prompt(foci)
    assert sum(line.startswith("- 本书") for line in block.splitlines()) == 3
    assert "只增加观察点" in block


def test_the_cap_counts_only_what_every_scene_pays_for(session) -> None:
    """A 订阅制情感文 reaches six per-scene axes; the cap is five.

    The cap is on per-scene axes because a gated one is scored once per chapter — charging
    开篇抓力 against the same budget as 情绪质感 would price a nearly-free question like a
    per-scene one. On this profile that mattered: an earlier count-everything cap of four
    squeezed out 情绪质感, the axis that decides whether a slow chapter is worth its length.
    """
    foci = chapter_foci_for(
        {
            "monetization": {"value": "paid_subscription"},
            "audience": {"value": "female_romance"},
            "engine": {"value": "romance"},
        }
    )
    axes = selected_axes(foci)
    per_scene = [a.key for a in axes if a.scope == "scene"]
    assert len(per_scene) == MAX_GENRE_AXES
    assert "emotional_texture" in per_scene and "character_truth" in per_scene
    # relational_stake is the sixth per-scene candidate and is the one dropped.
    assert "relational_stake" not in per_scene
    # The gated axis rides along free of the cap.
    assert [a.key for a in axes if a.scope == "ending"] == ["return_pull"]


def test_a_gated_axis_does_not_consume_the_per_scene_budget(session) -> None:
    # 快餐免费 + 男频升级: two gated + two per-scene. Nothing is dropped, and the per-scene
    # count stays well under the cap even though four axes are returned.
    foci = chapter_foci_for(
        {
            "monetization": {"value": "fast_food_free"},
            "audience": {"value": "male_gratification"},
            "engine": {"value": "progression"},
        }
    )
    axes = selected_axes(foci)
    assert [axis.key for axis in axes] == [
        "opening_grip",
        "chapter_end_hook",
        "gratification_payoff",
        "frustration_control",
    ]
    assert len([a for a in axes if a.scope == "scene"]) == 2


def test_chapter_scoped_axes_are_gated_to_the_scene_that_carries_them() -> None:
    """开篇抓力 belongs to the chapter's first scene and 断章质量 to its last.

    Asked of every scene, the middle of a chapter scores 断章质量=1 — not a judgement about
    the writing, just a restatement that the scene is in the middle. The real run that
    produced exactly that is why the gate exists.
    """
    block = chapter_focus_prompt(chapter_foci_for({"monetization": {"value": "fast_food_free"}}))
    opening = next(line for line in block.splitlines() if "`opening_grip`" in line)
    ending = next(line for line in block.splitlines() if "`chapter_end_hook`" in line)
    assert "is_chapter_opening=true" in opening
    assert "is_chapter_ending=true" in ending
    # A per-scene axis carries no gate at all.
    clue = next(
        line
        for line in chapter_focus_prompt(
            chapter_foci_for({"engine": {"value": "mystery"}})
        ).splitlines()
        if "`clue_placement`" in line
    )
    assert "is_chapter_" not in clue


def test_axis_block_forbids_inventing_keys() -> None:
    """An unprompted run returned ``mystery_hook`` and ``clue_fairness``.

    Names outside the profile vocabulary can never be compared across books, so the block
    has to say the list is closed — and the validator rejects what slips through anyway.
    """
    block = chapter_focus_prompt(chapter_foci_for({"engine": {"value": "mystery"}}))
    assert "不得自造" in block


def test_empty_foci_render_empty_string() -> None:
    assert chapter_focus_prompt([]) == ""


def test_focus_for_book_reads_confirmed_axes(session) -> None:
    _confirm(session, {"audience": {"value": "female_romance", "source": "user"}})
    block = chapter_focus_for_book(session, 1)
    assert "感情节拍" in block and "糖" in block


def test_unknown_trigger_is_rejected_at_definition_time() -> None:
    # The trigger vocabulary is the same closed axis set as the whole-book deltas; a typo
    # here must fail the build, not silently never fire.
    with pytest.raises(ValueError):
        ChapterFocus(key="bad", triggers=(("engine", "xianxia"),), instruction="x")
    with pytest.raises(ValueError):
        ChapterFocus(key="bad2", triggers=(("flavour", "mystery"),), instruction="x")


def test_every_axis_value_is_either_covered_or_declared_uncovered() -> None:
    """A hole and a decision look the same in a registry; this makes them different.

    Reviewing the coverage is what surfaced that ``paid_subscription`` had no focus at all
    while ``fast_food_free`` had two — the whole type layer had been built for one
    monetization model. Anything genuinely not worth a focus goes in NO_FOCUS_BY_DESIGN with
    the reason, so the next reader sees the judgement instead of a gap.
    """
    from app.narrative_core.long_novel.chapter_focus import NO_FOCUS_BY_DESIGN
    from app.narrative_core.long_novel.contracts.profile import AXES

    triggered = {pair for focus in CHAPTER_FOCI for pair in focus.triggers}
    missing = []
    for axis, enum in AXES.items():
        for item in enum:
            pair = (axis, item.value)
            if pair not in triggered and pair not in NO_FOCUS_BY_DESIGN:
                missing.append(pair)
    assert not missing, f"未覆盖且未声明的画像取值：{missing}"


def test_length_modulates_expectation_rather_than_adding_an_axis() -> None:
    # A short book cannot afford a chapter that only sets up; an epic can. Same axes either
    # way, so length is a note for the prompt, not a scored dimension.
    from app.narrative_core.long_novel.chapter_focus import LENGTH_EXPECTATION
    from app.narrative_core.long_novel.contracts.profile import AXES

    assert set(LENGTH_EXPECTATION) == {item.value for item in AXES["length"]}
    assert LENGTH_EXPECTATION["short"] and LENGTH_EXPECTATION["epic"]
    assert LENGTH_EXPECTATION["medium"] == ""


def test_ensemble_politics_reads_position_not_protagonist(session) -> None:
    foci = chapter_foci_for({"engine": {"value": "ensemble_politics"}})
    keys = {a.key for f in foci for a in f.axes}
    assert keys == {"power_shift", "information_asymmetry"}
    block = chapter_focus_prompt(foci)
    assert "势力" in block and "谁知道什么" in block


def test_dual_lead_asks_whether_the_switch_earned_itself(session) -> None:
    foci = chapter_foci_for({"pov": {"value": "dual_lead"}})
    assert {a.key for f in foci for a in f.axes} == {"thread_necessity"}


def test_every_registered_focus_fires_for_its_axes() -> None:
    for focus in CHAPTER_FOCI:
        axes = {axis: {"value": value} for axis, value in focus.triggers}
        assert focus in chapter_foci_for(axes)


def test_every_vocabulary_answers_the_same_questions() -> None:
    """A missing key falls back silently, and a silent fallback mixes two vocabularies.

    ``hook_vocabulary`` returns the matched table as-is, so a table that omits ``lens`` puts
    a romance chapter's 「起了心结」 trajectory under a button reading 「钩子回收」 — exactly the
    half-renamed state this table exists to prevent. Cheaper to reject at import.
    """
    expected = set(DEFAULT_HOOK_VOCABULARY)
    assert expected == {"open", "deepen", "answer", "carry", "lens", "first_mark"}
    for triggers, table in HOOK_VOCABULARY:
        assert set(table) == expected, f"{triggers} is missing {expected - set(table)}"
        assert all(str(v).strip() for v in table.values()), triggers


def test_each_type_gets_its_own_words() -> None:
    cases = {
        "romance": ({"engine": {"value": "romance"}}, "心结与挑明", "第一处牵挂"),
        "ensemble": ({"engine": {"value": "ensemble_politics"}}, "布局与摊牌", "第一处布局"),
        "dual_lead": ({"pov": {"value": "dual_lead"}}, "错位与对上", "第一处错位"),
        "mystery": ({"engine": {"value": "mystery"}}, "钩子回收", "首钩位置"),
    }
    for name, (axes, lens, first_mark) in cases.items():
        table = hook_vocabulary(axes)
        assert table["lens"] == lens, name
        assert table["first_mark"] == first_mark, name


def test_an_unconfirmed_book_keeps_the_shipped_words() -> None:
    # INV-P2: a drafted profile is an inference, and naming the reader's experience off an
    # inference is the substitution the invariant forbids.
    assert hook_vocabulary({}) == DEFAULT_HOOK_VOCABULARY
    assert hook_vocabulary({"engine": {"value": "romance"}}) != DEFAULT_HOOK_VOCABULARY


def test_no_type_answers_to_the_shipped_default_by_accident() -> None:
    """A registered table must actually differ from the default it overrides.

    A row whose ``lens`` equals 「钩子回收」 is indistinguishable on screen from having no row
    at all, so it is either a copy-paste slip or a decision that belongs in the default —
    either way not a registered override.
    """
    for triggers, table in HOOK_VOCABULARY:
        assert table != DEFAULT_HOOK_VOCABULARY, triggers
        assert table["lens"] != DEFAULT_HOOK_VOCABULARY["lens"], triggers

    # Rows that intentionally share wording (female_romance and engine=romance are the same
    # book read two ways) must share all of it, or the same book gets two names depending on
    # which axis the reader happened to confirm.
    by_lens: dict[str, list[dict[str, str]]] = {}
    for _, table in HOOK_VOCABULARY:
        by_lens.setdefault(table["lens"], []).append(table)
    for lens, tables in by_lens.items():
        assert all(t == tables[0] for t in tables), lens


def test_a_romance_is_not_flagged_for_being_quiet() -> None:
    """The diagnoser fires on absolute thresholds, and those thresholds are suspense's.

    Measured on two real chapters (deduplicated, latest artifact per scene): 《再也不见》第一章
    drew 2 defect flags across 3 scenes — 「张力不足」 on the opening and 「好奇不足」 on the
    dorm-banter scene — while 《我不是戏神》第一章 drew 1 across 6, on the three-paragraph lull.
    A paid-subscription romance whose opening is quiet is not defective; a fast-food
    suspense chapter that goes quiet is.
    """
    romance = suppressed_diagnoses(
        chapter_foci_for(
            {"engine": {"value": "romance"}, "audience": {"value": "female_romance"}}
        )
    )
    assert {"weak_tension", "weak_curiosity"} <= romance
    # The axis that does carry the book stays armed — suppression is not a licence to be flabby.
    assert "weak_emotional_investment" not in romance


def test_suspense_suppresses_nothing() -> None:
    for axes in (
        {"engine": {"value": "mystery"}},
        {"monetization": {"value": "fast_food_free"}},
        {},  # unconfirmed: INV-P2, an inference must not withdraw a warning
    ):
        assert suppressed_diagnoses(chapter_foci_for(axes)) == frozenset()


def test_slice_of_life_also_stops_being_told_it_is_slow() -> None:
    codes = suppressed_diagnoses(chapter_foci_for({"engine": {"value": "slice_of_life"}}))
    assert "pacing_too_slow" in codes
    assert "weak_emotional_investment" not in codes


def test_a_misspelled_diagnosis_code_is_rejected_at_import() -> None:
    import pytest

    from app.narrative_core.long_novel.chapter_focus import ChapterFocus

    with pytest.raises(ValueError, match="unknown diagnosis code"):
        ChapterFocus(
            key="typo",
            triggers=(("engine", "romance"),),
            instruction="",
            suppressed_diagnoses=("weak_tensionn",),
        )
