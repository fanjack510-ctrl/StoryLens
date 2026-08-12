"""Extraction density profiles and the L1 output-budget arithmetic (03 §2.5.2–2.5.4).

Caps are quantised into three closed profiles. The **profile**, never the raw output budget,
enters ``semantic_compat_key`` and is pinned at run creation, so a user changing their cap
cannot silently alter extraction semantics halfway through a book.

On the two totals carried on each profile: ``per_chapter_output_tokens`` and
``per_block_fixed_output_tokens`` are the frozen published values from the profile table.
They are authoritative because ``MAX_CHAPTERS_PER_BLOCK`` is published as a table of
integers derived from them, and a floor division is sensitive at the boundary — recomputing
the totals field-by-field lands within ±1 % but flips one cell of that table. The
field-by-field derivation is kept as :func:`derive_per_chapter_tokens` /
:func:`derive_per_block_fixed_tokens` and checked against the published totals by T0-25.

These are CONSERVATIVE ESTIMATED SERIALIZED TOKEN BOUNDS, not physical tokenizer bounds. The
planner is safe because of four layers — the estimate, the 20 % utilisation margin, the
plan-time preflight, and calibration plus truncation escalation — not because any single
number is exact. Do not re-tune them to chase a few tokens.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from app.narrative_core.long_novel import constants as C

__all__ = ["DensityProfileName", "DensityProfile", "PROFILES", "profile", "max_chapters_per_block"]


class DensityProfileName(StrEnum):
    D_HIGH = "D_HIGH"
    D_STD = "D_STD"
    D_MIN = "D_MIN"


@dataclass(frozen=True)
class DensityProfile:
    """One closed set of extraction caps, plus its two published token totals."""

    name: DensityProfileName
    #: fidelity rank: higher is more faithful, and the joint search prefers it
    density_rank: int

    # per-chapter caps
    events_per_chapter: int
    state_changes_per_chapter: int
    causal_per_chapter: int
    suspense_actions_per_chapter: int
    mentions_per_chapter: int
    evidence_refs_per_fact: int

    # per-block caps — these kinds do not occur in every chapter of a novel, and capping
    # them per chapter made the worst case roughly twice what reality can produce
    relationships_per_block: int
    goals_per_block: int
    choices_per_block: int
    threads_per_block: int
    identities_per_block: int
    max_provisional_entities: int

    carry_forward_max_tokens: int
    per_chapter_output_tokens: int
    per_block_fixed_output_tokens: int


PROFILES: Final[dict[DensityProfileName, DensityProfile]] = {
    DensityProfileName.D_HIGH: DensityProfile(
        name=DensityProfileName.D_HIGH,
        density_rank=3,
        events_per_chapter=3,
        state_changes_per_chapter=2,
        causal_per_chapter=1,
        suspense_actions_per_chapter=1,
        mentions_per_chapter=4,
        evidence_refs_per_fact=2,
        relationships_per_block=8,
        goals_per_block=6,
        choices_per_block=6,
        threads_per_block=5,
        identities_per_block=3,
        max_provisional_entities=12,
        carry_forward_max_tokens=900,
        per_chapter_output_tokens=489,
        per_block_fixed_output_tokens=2_154,
    ),
    DensityProfileName.D_STD: DensityProfile(
        name=DensityProfileName.D_STD,
        density_rank=2,
        events_per_chapter=2,
        state_changes_per_chapter=2,
        causal_per_chapter=1,
        suspense_actions_per_chapter=1,
        mentions_per_chapter=3,
        evidence_refs_per_fact=2,
        relationships_per_block=6,
        goals_per_block=4,
        choices_per_block=4,
        threads_per_block=4,
        identities_per_block=2,
        max_provisional_entities=8,
        carry_forward_max_tokens=700,
        per_chapter_output_tokens=406,
        per_block_fixed_output_tokens=1_506,
    ),
    DensityProfileName.D_MIN: DensityProfile(
        name=DensityProfileName.D_MIN,
        density_rank=1,
        events_per_chapter=2,
        state_changes_per_chapter=1,
        causal_per_chapter=1,
        suspense_actions_per_chapter=1,
        mentions_per_chapter=2,
        evidence_refs_per_fact=1,
        relationships_per_block=4,
        goals_per_block=3,
        choices_per_block=3,
        threads_per_block=3,
        identities_per_block=2,
        max_provisional_entities=6,
        carry_forward_max_tokens=500,
        per_chapter_output_tokens=317,
        per_block_fixed_output_tokens=1_082,
    ),
}


def profile(name: DensityProfileName | str) -> DensityProfile:
    return PROFILES[DensityProfileName(name)]


def derive_per_chapter_tokens(p: DensityProfile) -> int:
    """Field-by-field derivation of the per-chapter worst case (03 §2.5.2).

    Mentions are substrate, not facts, so they cost their own tokens but carry no evidence
    refs of their own.
    """
    facts_per_chapter = (
        1  # the mandatory ChapterSignal
        + p.events_per_chapter
        + p.state_changes_per_chapter
        + p.causal_per_chapter
        + p.suspense_actions_per_chapter
    )
    return (
        C.TOK_SIGNAL
        + p.events_per_chapter * C.TOK_EVENT
        + p.state_changes_per_chapter * C.TOK_STATE
        + p.causal_per_chapter * C.TOK_CAUSAL
        + p.suspense_actions_per_chapter * C.TOK_SUSPENSE_ACTION
        + p.mentions_per_chapter * C.TOK_MENTION
        + facts_per_chapter * p.evidence_refs_per_fact * C.TOK_EVIDENCE_REF
    )


def derive_per_block_fixed_tokens(p: DensityProfile) -> int:
    """Field-by-field derivation of the per-block fixed worst case (03 §2.5.2)."""
    facts_per_block = (
        p.relationships_per_block
        + p.goals_per_block
        + p.choices_per_block
        + p.threads_per_block
        + p.identities_per_block
    )
    return (
        p.relationships_per_block * C.TOK_RELATIONSHIP
        + p.goals_per_block * C.TOK_GOAL
        + p.choices_per_block * C.TOK_CHOICE
        + p.threads_per_block * C.TOK_THREAD
        + p.identities_per_block * C.TOK_IDENTITY
        + p.max_provisional_entities * C.TOK_PROVISIONAL_ENTITY
        + facts_per_block * p.evidence_refs_per_fact * C.TOK_EVIDENCE_REF
    )


def max_chapters_per_block(p: DensityProfile, output_budget: int) -> int:
    """How many chapters fit in one block's output budget (03 §2.5.4).

    Returns 0 when the profile's fixed cost alone exhausts the budget — that is a real
    answer, not an error: it is how the joint search discovers that a high-fidelity profile
    is unaffordable at a small output budget and steps down.
    """
    if output_budget <= 0:
        return 0
    usable = int(C.OUTPUT_UTILISATION * output_budget)
    room = (
        usable
        - p.carry_forward_max_tokens
        - C.JSON_ENVELOPE_TOKENS
        - p.per_block_fixed_output_tokens
    )
    if room <= 0:
        return 0
    return room // p.per_chapter_output_tokens
