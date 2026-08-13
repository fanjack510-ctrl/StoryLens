"""L0-B and the draft/confirm flow (10_ADAPTIVE_PROFILE_LAYER §7, §8).

The profile layer answers "what kind of book is this" **before** anything expensive reads it.
That ordering is the whole point: the type judgement used to come out of the final synthesis
call, after 101 extraction calls had already been made and could no longer be influenced by
it (§1).

The work is split by what each side is good at:

* **Counting** — chapter length, dialogue ratio, how mentions of each name are spread across
  the book — is done in ``profile_stats`` over 100% of the text, for nothing.
* **Reading** — genre, who the book is written for, what pulls the reader — needs a model,
  but only over a sample: the opening three chapters, where a free-platform book lives or
  dies, plus an even spread across the rest.

Neither side decides alone, and neither side is final. A **draft** is assembled here with the
evidence behind every value, the user confirms or corrects it through closed dropdowns, and
**the user's answer is what becomes authoritative** (INV-P2). Later layers may report that
the facts disagree with it; they may not overrule it.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.narrative_core.long_novel.contracts.profile import (
    AXES,
    AXIS_LABELS,
    BookLength,
    is_legal,
)
from app.narrative_core.long_novel.profile_stats import (
    draft_profile as deterministic_draft,
)

__all__ = [
    "OPENING_CHAPTERS",
    "SPREAD_SAMPLES",
    "select_sample_chapters",
    "book_length",
    "merge_draft",
    "confirm",
    "presentation_options",
]

#: The opening is sampled in full because it is the part a free-platform reader decides on,
#: and because it is the only part where "how does this book start" is answerable at all.
OPENING_CHAPTERS = 3

#: Plus an even spread, so the sample is not a verdict about the first act. Eleven chapters
#: of ~3,000 characters is ~25K tokens — one call inside a 128K window.
SPREAD_SAMPLES = 8


def select_sample_chapters(chapter_count: int) -> list[int]:
    """Which chapters L0-B reads, as 1-based orders.

    Deterministic, so the same book always produces the same sample and therefore the same
    cache key: a profile that changed between runs would silently invalidate extraction.
    """
    if chapter_count <= 0:
        return []
    opening = list(range(1, min(OPENING_CHAPTERS, chapter_count) + 1))
    if chapter_count <= OPENING_CHAPTERS + SPREAD_SAMPLES:
        return list(range(1, chapter_count + 1))
    step = chapter_count / (SPREAD_SAMPLES + 1)
    spread = [round(step * (index + 1)) for index in range(SPREAD_SAMPLES)]
    return sorted(dict.fromkeys(opening + [c for c in spread if c not in opening]))


def book_length(total_chars: int) -> str:
    """Axis 5, counted rather than judged."""
    if total_chars < 500_000:
        return BookLength.SHORT.value
    if total_chars < 1_500_000:
        return BookLength.MEDIUM.value
    if total_chars < 4_000_000:
        return BookLength.LONG.value
    return BookLength.EPIC.value


#: Which side owns each axis when the counted signal and the sampled read disagree.
#:
#: ``monetization`` is settled by chapter length, which is objective, and the model's opinion
#: is kept only as a cross-check. ``pov`` is settled by the whole-book mention curve, because
#: that is the axis a sample provably gets wrong. ``audience`` and ``engine`` need reading and
#: go to the model — the vocabulary hit rates behind them are crude by construction (§6).
_AXIS_OWNER = {
    "monetization": "stats",
    "audience": "model",
    "engine": "model",
    "pov": "stats",
    "length": "stats",
}


def merge_draft(
    chapter_texts: Sequence[str],
    sample_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the draft profile from the counted half and the sampled read.

    Disagreements are recorded rather than resolved away. The user is the one being asked to
    decide, and "the statistics say ensemble, the sample read says single lead" is exactly
    the kind of thing they should be shown before they answer.
    """
    names = list((sample_result or {}).get("candidate_names", []) or [])
    stats_side = deterministic_draft(chapter_texts, names)
    statistics = stats_side["statistics"]

    values: dict[str, dict[str, Any]] = {
        "monetization": dict(stats_side["monetization"]),
        "engine": dict(stats_side["engine"]),
        "pov": dict(stats_side["pov"]),
        "length": {
            "value": book_length(statistics["total_chars"]),
            "source": "L0-A",
            "evidence": {"total_chars": statistics["total_chars"]},
        },
        "audience": {"value": "", "source": "", "evidence": {}},
    }

    disagreements: list[dict[str, str]] = []
    for axis, owner in _AXIS_OWNER.items():
        said = (sample_result or {}).get(axis if axis != "pov" else "pov_hint")
        if not isinstance(said, Mapping):
            continue
        model_value = str(said.get("value", ""))
        if not is_legal(axis, model_value):
            continue
        counted = values.get(axis, {}).get("value", "")
        if owner == "model":
            values[axis] = {
                "value": model_value,
                "source": "L0-B",
                "evidence": said.get("evidence", []),
                "confidence": said.get("confidence", 0.0),
            }
            if counted and counted != model_value:
                disagreements.append(
                    {"axis": axis, "counted": counted, "read": model_value, "kept": model_value}
                )
        elif counted and counted != model_value:
            # The counted side keeps the axis, but the disagreement is surfaced: it is the
            # single most useful thing to show a user at the confirmation step.
            disagreements.append(
                {"axis": axis, "counted": counted, "read": model_value, "kept": counted}
            )

    return {
        "axes": values,
        "disagreements": disagreements,
        "statistics": statistics,
        "name_deciles": stats_side["name_deciles"],
        "candidate_names": names,
        "opening_notes": (sample_result or {}).get("opening_notes", {}),
        "status": "draft",
    }


def confirm(draft: Mapping[str, Any], user_choice: Mapping[str, str]) -> dict[str, Any]:
    """Apply the user's dropdown selections and mark the profile authoritative.

    An illegal value is refused rather than stored. A profile carrying a value no delta
    recognises is worse than an unconfirmed one, because downstream it looks decided.
    """
    axes = {axis: dict(value) for axis, value in dict(draft.get("axes", {})).items()}
    for axis, value in user_choice.items():
        if axis not in AXES:
            raise ValueError(f"unknown profile axis: {axis}")
        if not is_legal(axis, value):
            raise ValueError(f"illegal value for {axis}: {value!r}")
        axes[axis] = {**axes.get(axis, {}), "value": value, "source": "user"}

    missing = [axis for axis in AXES if not axes.get(axis, {}).get("value")]
    if missing:
        raise ValueError(f"profile is incomplete: {missing}")

    return {**dict(draft), "axes": axes, "status": "confirmed"}


def presentation_options() -> list[dict[str, Any]]:
    """The dropdowns, as the confirmation screen should render them.

    Emitted by the backend so the rule lives in one place (INV-P4). The desktop client had
    two copies of the L2–L4 prompts and they drifted; a profile vocabulary duplicated in
    TypeScript would drift the same way.
    """
    return [
        {
            "axis": axis,
            "options": [
                {"value": member.value, "label": AXIS_LABELS[axis][member.value]}
                for member in enum
            ],
        }
        for axis, enum in AXES.items()
    ]
