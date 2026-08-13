"""L0-A / L0-C — the deterministic profile statistics.

The property worth pinning is the one that decided the design: a viewpoint verdict taken
from a book's opening disagrees with the same verdict taken from the whole book, and the
whole-book one is right. Measured on 深海余烬 (806 chapters, 2.4M characters):

    whole book      share(1) = 0.393  ->  ensemble
    first tenth     share(1) = 0.538  ->  single_lead

Everything here is counted, so these tests need no provider and no fixture file.
"""

from __future__ import annotations

from app.narrative_core.long_novel.profile_stats import (
    book_statistics,
    draft_profile,
    engine_prior,
    merge_confirmed,
    monetization_prior,
    name_distribution,
    pov_from_distribution,
)


CAST = ("凡娜", "雪莉", "阿加莎", "妮娜", "莫里斯", "提瑞安")


def _book(lead_share: float, chapters: int = 100, chapter_chars: int = 3000):
    """A synthetic book where the lead holds a chosen share of the mentions.

    The remainder is spread across six characters rather than one or two: a cast of two
    near-equal names is a *dual-lead* book, not an ensemble, and the distinction is exactly
    what the thresholds exist to make.
    """
    lines = 60
    lead_lines = max(1, round(lines * lead_share))
    rest = lines - lead_lines
    body = ["「甲说话。」邓肯走进房间。"] * lead_lines
    for index in range(rest):
        body.append(f"「乙说话。」{CAST[index % len(CAST)]}看着窗外。")
    text = "\n".join(body)
    text += "。" * max(0, chapter_chars - len(text))
    return [text] * chapters


def test_chapter_length_separates_fast_food_from_paid():
    assert monetization_prior(book_statistics(_book(0.5, chapter_chars=2000))) == "fast_food_free"
    assert monetization_prior(book_statistics(_book(0.5, chapter_chars=3500))) == "paid_subscription"


def test_dialogue_ratio_counts_paragraphs_not_characters():
    stats = book_statistics(["「有对话」\n没有对话\n「又一句对话」"])
    assert abs(stats.dialogue_ratio - 2 / 3) < 0.01


def test_vocabulary_prior_picks_the_densest_family_and_is_empty_when_none_hit():
    mystery = book_statistics(["线索与真相和证据" * 50])
    assert engine_prior(mystery) == "mystery"
    assert engine_prior(book_statistics(["。" * 500])) == ""


def test_viewpoint_from_the_whole_book_disagrees_with_the_opening():
    """The measurement the adaptive-profile design rests on.

    A book that opens on one character and widens into an ensemble must be read as an
    ensemble. Judging it from the opening gives the opposite answer, which is why this
    axis is decided by a whole-book count rather than by a sampled model read.
    """
    names = ["邓肯", *CAST]
    opening = _book(0.85, chapters=10)          # lead dominates
    remainder = _book(0.25, chapters=90)        # cast takes over
    whole = opening + remainder

    assert pov_from_distribution(name_distribution(opening, names)) == "single_lead"
    assert pov_from_distribution(name_distribution(whole, names)) == "ensemble"


def test_deciles_place_a_late_arriving_character_late():
    """A character absent from the first half must show an empty first half in the curve."""
    early = ["邓肯走过。" + "。" * 200] * 50
    late = ["邓肯走过。阿加莎出现了。" + "。" * 200] * 50
    curve = name_distribution(early + late, ["邓肯", "阿加莎"]).per_name_deciles
    assert sum(curve["阿加莎"][:5]) == 0
    assert sum(curve["阿加莎"][5:]) > 0


def test_name_distribution_survives_an_empty_candidate_list():
    distribution = name_distribution(_book(0.5), [])
    assert distribution.per_name_total == {}
    assert pov_from_distribution(distribution) == ""


def test_every_drafted_axis_carries_the_evidence_behind_it():
    """The user is asked to confirm these, and cannot confirm a bare verdict."""
    draft = draft_profile(_book(0.5), ["邓肯", *CAST])
    for axis in ("monetization", "engine", "pov"):
        assert draft[axis]["evidence"], axis
        assert draft[axis]["source"].startswith("L0")


def test_user_confirmation_outranks_every_inference():
    draft = draft_profile(_book(0.2), ["邓肯", *CAST])
    assert draft["pov"]["value"] == "ensemble"
    confirmed = merge_confirmed(draft, {"pov": "single_lead"})
    assert confirmed["pov"]["value"] == "single_lead"
    assert confirmed["pov"]["source"] == "user"
    # An axis the user left alone keeps its inferred value and its source.
    assert confirmed["monetization"]["source"] == "L0-A"
