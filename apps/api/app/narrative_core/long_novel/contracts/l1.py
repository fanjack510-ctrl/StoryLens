"""``BlockAsset v1`` — the L1 wire and storage contract (03 §2.1–2.4).

The classification of each field as **fact** or **interpretation** is the load-bearing part
of this module. L1 emits facts: things a reader could point at in the text. Anything that
requires whole-book knowledge — normalised pacing scores, canonical character identity,
act structure — is *not* available to a single block and is not asked for here. Every fact
kind carries at least one evidence reference, which is what makes the claim traceable and
what ``fact_key`` anchors on.

Interpretation happens at L2 and above, over facts, never over re-read prose.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.narrative_core.long_novel.contracts.enums import OutputFidelity

__all__ = [
    "EvidenceRef",
    "Mention",
    "ProvisionalEntity",
    "ChapterSignal",
    "EventFact",
    "CharacterStateChange",
    "CausalLink",
    "SuspenseAction",
    "RelationshipChange",
    "GoalChange",
    "Choice",
    "SuspenseThread",
    "IdentityAssertion",
    "CarryForwardState",
    "BlockAsset",
]


class _Strict(BaseModel):
    """Reject unknown fields.

    A silently accepted extra key is how an interpretation field arrives at L1 without
    anyone deciding to allow it.
    """

    model_config = ConfigDict(extra="forbid")


class EvidenceRef(_Strict):
    """A pointer to exactly one paragraph occurrence.

    ``paragraph_ref`` is the **block-local** anchor the provider was shown (``[p:N]``,
    N = 1..n in reading order within this block's rendered text). It is not a snapshot
    paragraph id: a snapshot-assigned number would renumber on every insertion, changing the
    rendered payload and the provider input fingerprint of every later block, and destroying
    the incremental reuse of an unchanged tail. The engine resolves it to a
    ``paragraph_occurrence_key`` through the block's render map, and only that is stored.

    ``start_offset``/``end_offset`` are filled by the **engine** with the paragraph's own
    bounds. Sub-paragraph precision is not claimed and is not asked of the model.
    """

    paragraph_ref: int = Field(ge=1)
    paragraph_content_hash: str = ""
    start_offset: int | None = None
    end_offset: int | None = None


class Mention(_Strict):
    """A surface form as it appears at one point in the text.

    Deliberately not a person: ``surface_norm`` is *data*, never an identity. One surface
    may denote several people and one person may carry several surfaces, so any key derived
    from the string alone would give every 「老王」 in a book the same identity.
    """

    surface_norm: str = Field(min_length=1, max_length=120)
    paragraph_ref: int = Field(ge=1)
    evidence: list[EvidenceRef] = Field(default_factory=list)


class ProvisionalEntity(_Strict):
    """A block-local cluster of mentions the model believes are one person.

    Provisional in the strict sense: a hypothesis from one block's view. ``continuity_ref``
    optionally binds it to a cross-block continuity chain (``CENT-*``), which is likewise a
    hypothesis — L2 may split or merge it when resolving canonical entities.
    """

    member_mention_indexes: list[int] = Field(default_factory=list)
    display_surface_norm: str = Field(default="", max_length=120)
    role_hint: str = Field(default="", max_length=40)
    continuity_ref: str | None = None


class ChapterSignal(_Strict):
    """Exactly one per chapter, mandatory. Countable signals only.

    Pacing values are **raw counters**, not 0–100 scores: a 0–100 score requires whole-book
    normalisation, which one block cannot do. Normalisation happens deterministically at the
    pacing projection, which is why the provider is never asked to guess a number here.
    """

    chapter_ref: int = Field(ge=1)
    dialogue_paragraphs: int = Field(default=0, ge=0)
    action_paragraphs: int = Field(default=0, ge=0)
    interiority_paragraphs: int = Field(default=0, ge=0)
    scene_breaks: int = Field(default=0, ge=0)
    new_information_beats: int = Field(default=0, ge=0)
    hook_present: bool = False
    cap_saturated: bool = False
    #: PROFILE DELTA — axis 4 `ensemble` (10_ADAPTIVE_PROFILE_LAYER §9). The surface form of
    #: the character whose viewpoint the chapter is told from. Empty when the profile does not
    #: ask for it, so the core schema is unchanged for every other book (INV-P1: a profile may
    #: add, never remove). Dispatch is not built yet; the POC fills it unconditionally.
    pov_entity: str = Field(default="", max_length=120)
    evidence: list[EvidenceRef] = Field(default_factory=list)


class _Fact(_Strict):
    """Base for every fact kind: at least one evidence reference is structural.

    Without it the claim is untraceable and ``fact_key`` has nothing to anchor on, so two
    genuinely different facts sharing a payload would collide.
    """

    evidence: list[EvidenceRef] = Field(min_length=1)


class EventFact(_Fact):
    """One thing that happened.

    ``actors`` was capped at 3 to hold down the output budget. On an ensemble novel that cap
    is simply wrong: a scene with 「邓肯、凡娜、露克蕾西娅、莫里斯、雪莉」 present is ordinary
    writing, and ten blocks of a real 806-chapter book — 190 chapters of analysis — were
    rejected outright because the model reported the cast honestly. The cap is raised to 6,
    which costs about 3 extra tokens per event against a per-chapter budget of ~490, and
    surplus names are truncated with a record rather than failing the block (`03 §2.5.2`).
    """

    summary: str = Field(min_length=1, max_length=50)
    actors: list[str] = Field(default_factory=list, max_length=6)
    chapter_ref: int = Field(ge=1)


class CharacterStateChange(_Fact):
    entity_ref: str
    from_state: str = Field(max_length=24)
    to_state: str = Field(max_length=24)
    chapter_ref: int = Field(ge=1)


class CausalLink(_Fact):
    cause_fact_ref: str
    effect_fact_ref: str


class SuspenseAction(_Fact):
    thread_ref: str
    action_kind: str
    information_added: str = Field(default="", max_length=40)
    chapter_ref: int = Field(ge=1)


class RelationshipChange(_Fact):
    from_entity_ref: str
    to_entity_ref: str
    relation: str = Field(max_length=24)


class GoalChange(_Fact):
    entity_ref: str
    goal_text: str = Field(max_length=40)
    change_kind: str


class Choice(_Fact):
    entity_ref: str
    decision: str = Field(max_length=40)
    costs: list[str] = Field(default_factory=list, max_length=2)
    gains: list[str] = Field(default_factory=list, max_length=2)


class SuspenseThread(_Fact):
    question: str = Field(max_length=40)
    opened_chapter_ref: int = Field(ge=1)


class PowerBeat(_Fact):
    """PROFILE DELTA — axis 3 ``progression`` (10_ADAPTIVE_PROFILE_LAYER §9).

    One reading of where a character stands on the book's own advancement ladder, plus what
    moved them. The list is empty for every book whose profile does not ask for it, so the
    core schema is unchanged (INV-P1).

    ``level`` is free text on purpose. Every book names its ladder differently — 境界 in 修仙,
    「阶位」in 《我不是戏神》, 序列 elsewhere — and a closed enum here would force the model to
    map an unseen ladder onto 练气/筑基, which is how a whole axis silently becomes fiction.
    Ordering is recovered downstream by first appearance, not by parsing the name.

    ``kind`` is closed, because it dispatches: the up kinds raise the curve, the down kinds
    drop it. The vocabulary is enumerated in the prompt rather than implied, for the reason
    296 of 297 ``suspense_actions`` came back ``advance`` when it was not.
    """

    entity_ref: str
    chapter_ref: int = Field(ge=1)
    #: ``promote`` 晋升 | ``gain`` 获得 | ``faceslap`` 打脸压制 | ``setback`` 受挫 | ``demote`` 跌落
    kind: str = Field(max_length=16)
    level: str = Field(default="", max_length=24)
    why: str = Field(default="", max_length=40)


#: Which way each beat moves the curve. Deliberately **not** a pydantic enum on ``kind``:
#: rejecting the whole block because the model wrote 「晋升」instead of ``promote`` would throw
#: away eight chapters of paid extraction, and that exact failure is on record. A word this
#: table does not know returns 0 — counted, visible, and never silently read as a rise.
POWER_DIRECTION: dict[str, int] = {
    "promote": 1, "gain": 1, "faceslap": 1,
    "setback": -1, "demote": -1,
}


def power_direction(kind: str) -> int:
    """+1 up, -1 down, 0 when the kind is not one this engine knows."""
    return POWER_DIRECTION.get((kind or "").strip().lower(), 0)


class IdentityAssertion(_Fact):
    left_entity_ref: str
    right_entity_ref: str
    #: ``same_person`` | ``not_same_person`` | ``uncertain``. ``not_same_person`` is what
    #: lets L2 split one provisional cluster into two canonical entities, so it must be
    #: expressible even though it asserts a negative.
    assertion: str


class CarryForwardState(_Strict):
    """Bounded continuity slate handed from one block to the next.

    Engine-assembled, never model-authored, and bounded by the profile's
    ``CARRY_FORWARD_MAX_TOKENS``. Entity references here are ``CENT-*`` continuity handles,
    not ``LENT-*``: a provisional entity is block-scoped and cannot resolve in the next
    block, so hashing one into the carry fingerprint would change it at every block edge by
    construction and convergence could never be detected.
    """

    open_thread_refs: list[str] = Field(default_factory=list)
    active_goal_refs: list[str] = Field(default_factory=list)
    active_continuity_refs: list[str] = Field(default_factory=list)
    unresolved_note: str = Field(default="", max_length=200)


class BlockAsset(_Strict):
    """Everything one L1 extraction call returns, for one block.

    Every list is bounded by the density profile; no list is unbounded. When a chapter hits
    a cap the extractor marks ``cap_saturated`` on that signal, which flows to the run's
    quality metrics and, past the replan threshold, shrinks later blocks — and the saturated
    block itself is either re-extracted as a bounded split or marked
    ``reduced_by_saturation``, never persisted as an ordinary complete result.
    """

    asset_schema_version: str
    chapter_signals: list[ChapterSignal] = Field(default_factory=list)
    events: list[EventFact] = Field(default_factory=list)
    character_state_changes: list[CharacterStateChange] = Field(default_factory=list)
    causal_links: list[CausalLink] = Field(default_factory=list)
    suspense_actions: list[SuspenseAction] = Field(default_factory=list)
    relationship_changes: list[RelationshipChange] = Field(default_factory=list)
    goal_changes: list[GoalChange] = Field(default_factory=list)
    choices: list[Choice] = Field(default_factory=list)
    suspense_threads: list[SuspenseThread] = Field(default_factory=list)
    #: PROFILE DELTA — empty unless axis 3 is ``progression``.
    power_beats: list[PowerBeat] = Field(default_factory=list)
    identity_assertions: list[IdentityAssertion] = Field(default_factory=list)
    mentions: list[Mention] = Field(default_factory=list)
    provisional_entities: list[ProvisionalEntity] = Field(default_factory=list)
    carry_forward_out: CarryForwardState = Field(default_factory=CarryForwardState)
    output_fidelity: OutputFidelity = OutputFidelity.COMPLETE
