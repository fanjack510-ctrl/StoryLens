"""L0-B sampling and the draft → confirm flow.

The rules under test are the ones that keep a profile actionable:

* the axes are closed sets, because they dispatch extraction deltas and report modules — a
  value nothing recognises is worse than no value, since downstream it looks decided;
* the user's answer outranks every inference, including the whole-book one (INV-P2);
* where the counted signal and the sampled read disagree, the disagreement is *recorded*
  rather than resolved away, because that is what the person confirming needs to see.
"""

from __future__ import annotations

import pytest

from app.narrative_core.long_novel.contracts.profile import AXES, AXIS_LABELS, is_legal
from app.narrative_core.long_novel.profile import (
    OPENING_CHAPTERS,
    book_length,
    confirm,
    merge_draft,
    presentation_options,
    select_sample_chapters,
)

CAST = ("凡娜", "雪莉", "阿加莎", "妮娜", "莫里斯", "提瑞安")


def _book(lead_share: float, chapters: int = 100, chapter_chars: int = 3000):
    lines = 60
    lead_lines = max(1, round(lines * lead_share))
    body = ["「甲说话。」邓肯走进房间。"] * lead_lines
    for index in range(lines - lead_lines):
        body.append(f"「乙说话。」{CAST[index % len(CAST)]}看着窗外。")
    text = "\n".join(body)
    return [text + "。" * max(0, chapter_chars - len(text))] * chapters


# ------------------------------------------------------------------ sampling

def test_the_sample_always_covers_the_opening():
    """A free-platform book is decided in its first chapters; the sample must contain them."""
    for count in (5, 40, 806, 3000):
        sample = select_sample_chapters(count)
        assert sample[:OPENING_CHAPTERS] == [1, 2, 3][: min(OPENING_CHAPTERS, count)]


def test_the_sample_is_deterministic_and_spans_the_book():
    first = select_sample_chapters(806)
    assert first == select_sample_chapters(806), "同一本书必须给出同一份抽样，否则缓存键会漂移"
    assert len(first) == 11
    assert max(first) > 700, "抽样必须覆盖到全书末尾，否则只是对第一幕的判断"


def test_a_short_book_is_read_whole_rather_than_sampled():
    assert select_sample_chapters(6) == [1, 2, 3, 4, 5, 6]
    assert select_sample_chapters(0) == []


def test_length_axis_is_counted():
    assert book_length(300_000) == "short"
    assert book_length(1_000_000) == "medium"
    assert book_length(2_402_385) == "long"      # 深海余烬
    assert book_length(5_000_000) == "epic"


# ------------------------------------------------------------------ closed vocabulary

def test_every_axis_value_has_a_label_and_nothing_else_is_legal():
    for axis, enum in AXES.items():
        for member in enum:
            assert AXIS_LABELS[axis][member.value], f"{axis}.{member.value} 缺少下拉标签"
            assert is_legal(axis, member.value)
        assert not is_legal(axis, "都市异能")


def test_presentation_options_cover_all_five_axes():
    options = {row["axis"] for row in presentation_options()}
    assert options == set(AXES)


# ------------------------------------------------------------------ merge and confirm

def test_the_counted_axes_are_not_overridden_by_the_sampled_read():
    """The viewpoint axis is the one a sample provably gets wrong, so counting keeps it."""
    draft = merge_draft(
        _book(0.2),
        {
            "candidate_names": ["邓肯", *CAST],
            "pov_hint": {"value": "single_lead", "confidence": 0.9, "evidence": [1]},
        },
    )
    assert draft["axes"]["pov"]["value"] == "ensemble"
    assert draft["axes"]["pov"]["source"] == "L0-C"
    shift = [d for d in draft["disagreements"] if d["axis"] == "pov"]
    assert shift and shift[0]["kept"] == "ensemble" and shift[0]["read"] == "single_lead"


def test_the_read_axes_take_the_model_and_record_no_false_disagreement():
    draft = merge_draft(
        _book(0.5),
        {
            "candidate_names": ["邓肯"],
            "audience": {"value": "female_romance", "confidence": 0.8, "evidence": [3]},
        },
    )
    assert draft["axes"]["audience"]["value"] == "female_romance"
    assert draft["axes"]["audience"]["source"] == "L0-B"
    assert not [d for d in draft["disagreements"] if d["axis"] == "audience"]


def test_an_invented_value_is_dropped_rather_than_stored():
    draft = merge_draft(
        _book(0.5), {"candidate_names": ["邓肯"], "engine": {"value": "都市异能"}}
    )
    assert draft["axes"]["engine"]["value"] != "都市异能"


def test_confirmation_outranks_every_inference_and_marks_the_source():
    draft = merge_draft(_book(0.2), {"candidate_names": ["邓肯", *CAST]})
    assert draft["status"] == "draft"
    assert draft["axes"]["pov"]["value"] == "ensemble"

    confirmed = confirm(
        draft,
        {"pov": "single_lead", "audience": "male_gratification", "engine": "progression"},
    )
    assert confirmed["status"] == "confirmed"
    assert confirmed["axes"]["pov"]["value"] == "single_lead"
    assert confirmed["axes"]["pov"]["source"] == "user"
    # An axis the user did not touch keeps what it was inferred from.
    assert confirmed["axes"]["length"]["source"] == "L0-A"


def test_confirmation_refuses_an_illegal_or_incomplete_profile():
    draft = merge_draft(_book(0.5), {"candidate_names": ["邓肯"]})
    with pytest.raises(ValueError, match="illegal value"):
        confirm(draft, {"engine": "都市异能"})
    with pytest.raises(ValueError, match="unknown profile axis"):
        confirm(draft, {"platform": "qidian"})
    # `audience` cannot be inferred without a model read, so an unconfirmed profile is
    # incomplete and must not pass as decided.
    with pytest.raises(ValueError, match="incomplete"):
        confirm(draft, {"engine": "mystery"})
