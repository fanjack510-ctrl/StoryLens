"""Closed vocabularies shared across the engine (01 §8.4, 02 §5, 03 §5.1, 04 §4.1).

Every enum here is a *contract*: the frozen documents enumerate its members, and code that
accepts a bare string instead of one of these is how a fifth topic or a sixth phase gets
invented by accident.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "UnitKind",
    "RunPhase",
    "Topic",
    "ReuseTier",
    "CarryStatus",
    "OutputFidelity",
    "MaxOutputTokensSource",
    "ChapterDiffClass",
]


class UnitKind(StrEnum):
    """Every kind of work item. ``REPAIR`` is here because a repair is a physically sent
    provider request; omitting it once made the phrase "every provider invocation" false."""

    PLAN = "plan"
    BLOCK = "block"
    PARTITION = "partition"
    STAGE = "stage"
    TOPIC = "topic"
    ASSESSMENT = "assessment"
    FINAL = "final"
    REPAIR = "repair"


class RunPhase(StrEnum):
    """Run phases, which double as write guards: each table has exactly one writer and one
    phase in which that writer may write (02 §6)."""

    PLANNED = "planned"
    EXTRACTING_BLOCKS = "extracting_blocks"
    CONSOLIDATING_STAGES = "consolidating_stages"
    SYNTHESIZING_TOPICS = "synthesizing_topics"
    FINAL_SYNTHESIS = "final_synthesis"
    COMPLETED = "completed"
    FAILED = "failed"


class Topic(StrEnum):
    """The six topic rows. Only four of them are provider calls.

    ``CHAPTERS`` is deterministic and costs nothing; ``ASSESSMENT`` is a provider unit of
    its own and is never counted inside "the topics". Counting it there double-counted it
    against ``max_provider_calls``, the cost planner and the consent gate.
    """

    STORY = "story"
    CHARACTERS = "characters"
    SUSPENSE = "suspense"
    PACING = "pacing"
    CHAPTERS = "chapters"
    ASSESSMENT = "assessment"

    @property
    def is_provider_backed(self) -> bool:
        return self is not Topic.CHAPTERS


class ReuseTier(StrEnum):
    """Which reuse predicate governs a unit (04 §4.1).

    Membership is decided by one question only: does the unit call a provider? If no, it is
    ``DETERMINISTIC`` — rebuilt free, carrying no provider input fingerprint. If yes, it is
    ``PROVIDER_BACKED``. Blocks are the only tier additionally bound to source text.
    """

    BLOCK = "block"
    DETERMINISTIC = "deterministic"
    PROVIDER_BACKED = "provider_backed"


class CarryStatus(StrEnum):
    CONVERGED = "converged"
    PROPAGATED = "propagated"
    UNCONVERGED = "unconverged"


class OutputFidelity(StrEnum):
    """Whether an asset is complete, or complete-shaped but known to have lost entries.

    ``REDUCED_BY_SATURATION`` does not block reuse — the result is real, merely incomplete —
    but it propagates to the run's completeness disclosure. A saturated extraction is either
    repaired by a bounded split or declared; it is never silently accepted as ordinary.
    """

    COMPLETE = "complete"
    REDUCED_BY_SATURATION = "reduced_by_saturation"


class MaxOutputTokensSource(StrEnum):
    """Where a model's output ceiling came from.

    The distinction is not cosmetic: it is the difference between 91 and 136 blocks for the
    reference book — roughly 0.38M input tokens — and between the ``D_HIGH`` and ``D_MIN``
    fidelity profiles.
    """

    PROBED = "probed"
    DECLARED = "declared"
    CONSERVATIVE_DEFAULT = "conservative_default"
    SUSPECT = "suspect"


class ChapterDiffClass(StrEnum):
    """Result of the identity-aligned snapshot diff (03 §7.1).

    ``MOVED`` exists so that a pure reordering is not mistaken for an edit. The diff aligns
    on ``source_chapter_id``; a positional join reports the entire tail as changed after a
    single insertion, which is the ordinal cliff the whole identity model removes.
    """

    UNCHANGED = "unchanged"
    MOVED = "moved"
    CONTENT_INVALID = "content_invalid"
    INSERTED = "inserted"
    DELETED = "deleted"
