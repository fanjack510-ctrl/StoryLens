"""L2 — carry propagation, partition reduction and entity resolution (03 §2.3, §4.5; 04 §5.3).

None of this reads prose. It works over the facts L1 produced, which is what keeps the cost
of re-deriving the whole upper structure at zero.

Two ideas carry most of the weight:

**Carry state is compared by *meaning*, not by wording.** Two re-extractions of an unchanged
block will phrase their continuity slate differently while describing the same open threads
and the same people. Hashing the prose would report drift forever and propagation would never
terminate; hashing the normalised key sets reaches a fixed point.

**Propagation stops at a genuine fixed point, and says so when it doesn't.** When an edit's
effect dies out, every later block is *exactly* valid — no flag, no disclosure, nothing to
re-interpret. When it does not die out within the ceiling, the run is marked
reduced-fidelity and the residual delta is persisted. It is never silently accepted as clean.
The ceiling is a safety guard against runaway cost, not a claim that twelve hops is enough.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Callable, Iterable, Sequence

from app.narrative_core.long_novel import constants as C
from app.narrative_core.long_novel import ids
from app.narrative_core.long_novel.contracts.enums import CarryStatus
from app.narrative_core.long_novel.contracts.l1 import BlockAsset, CarryForwardState

__all__ = [
    "carry_semantic_fingerprint",
    "build_carry_out",
    "PropagationOutcome",
    "propagate",
    "PartitionReduction",
    "reduce_partition",
    "resolve_entities",
    "ResolvedEntity",
]


# ----------------------------------------------------------------------- carry


def carry_semantic_fingerprint(carry: CarryForwardState, epoch_class: str = "") -> str:
    """Hash the *normalised key sets*, never the prose.

    Sorting each set makes the fingerprint independent of the order the engine happened to
    assemble it in, so two runs over the same facts agree.
    """
    return ids.sha256_fields(
        ids.canonical_json(
            {
                "threads": sorted(set(carry.open_thread_refs)),
                "arcs": sorted(set(carry.active_goal_refs)),
                "participants": sorted(set(carry.active_continuity_refs)),
                "epoch": epoch_class,
            }
        )
    )


#: Characters that carry no identifying weight when matching a thread label to the question
#: it refers to. Dropping them lets 「教堂低语声」 reach 「教堂中的低语声是否来自葛莫娜？」.
_THREAD_NOISE = "的了是否会与和在有为吗呢？?、，,。 　"

#: A shared core this long is enough that two different questions in the same book do not
#: collide, and short enough to survive the model rephrasing the rest.
_THREAD_MATCH_MIN = 4


def refers_to_thread(label: str, question: str) -> bool:
    """Does this thread label name that suspense question?

    Substring either way first, then again with filler characters removed. The model is
    consistent about *which* thread it means and inconsistent about how much of the question
    it repeats, so the match has to tolerate the second without inventing the first.

    Defined here rather than at the point of use because both the carry slate and the report
    assembly need it, and two copies of a matching rule drift — the L2–L4 prompts had two
    copies and did exactly that.
    """
    if not label or not question:
        return False
    if label in question or question in label:
        return True

    strip = str.maketrans("", "", _THREAD_NOISE)
    short, long = sorted((label.translate(strip), question.translate(strip)), key=len)
    if len(short) < _THREAD_MATCH_MIN:
        return False

    # Subsequence, not substring: the model abbreviates by *dropping* characters, so the
    # short form's characters survive in order inside the long one with other characters
    # between them — 「教堂低语声」 sits inside 「教堂中低语声来自葛莫娜」 that way, and a
    # substring test misses it over the single inserted 中. Requiring the order is what stops
    # this from matching two unrelated questions that happen to share some characters.
    iterator = iter(long)
    return all(character in iterator for character in short)


_refers_to_thread = refers_to_thread

#: How many open threads to show the next block. The slate grows with the book — an
#: 806-chapter novel accumulates hundreds — and an unbounded list would make the prompt grow
#: with book length, which the whole design exists to prevent. The most recently opened are
#: kept, because those are the ones a nearby block is most likely to be acting on.
CARRY_THREADS_SHOWN = 24


def render_carry_in(carry: CarryForwardState) -> str:
    """The open slate, written for the model that is about to extract the next block.

    Threads are listed as their own questions so the model can match an action to one by
    reading it. It is told explicitly to reuse the wording: a thread referred to by a fresh
    paraphrase is a new thread as far as every later step is concerned, and that is how a
    book ends up with hundreds of questions and no answers.
    """
    threads = [t for t in carry.open_thread_refs if t][-CARRY_THREADS_SHOWN:]
    if not threads and not carry.unresolved_note:
        return ""

    parts: list[str] = []
    if threads:
        listed = "\n".join(f"  - {question}" for question in threads)
        parts.append(
            "前面章节抛出、**至今仍未回答**的疑问：\n"
            f"{listed}\n"
            "如果本块里有内容推进或回答了上面某一条，`suspense_actions.thread_ref` "
            "必须**原样照抄那一条的文字**，不要改写、不要另起一个新说法；"
            "真正回答了的，`action_kind` 填 `resolve`。\n"
            "只有本块新抛出的疑问才写进 `suspense_threads`。"
        )
    if carry.unresolved_note:
        parts.append(f"上一块的遗留说明：{carry.unresolved_note}")
    return "\n\n".join(parts)


def build_carry_out(asset: BlockAsset, previous: CarryForwardState) -> CarryForwardState:
    """Assemble the next block's slate from this block's facts plus what was still open.

    Entity references are ``CENT-*`` continuity handles, not ``LENT-*``: a provisional entity
    is block-scoped and cannot resolve in the next block, so a slate built from them would
    change at every block edge by construction and convergence could never be detected.
    """
    # The thread is carried as its own question text, not as an opaque handle. Two reasons,
    # both found by looking at a real 806-chapter run where 40 of 40 threads finished
    # unresolved:
    #
    # A handle is unmatchable. This slate is shown to the model extracting the *next* block,
    # and it is asked to say which open thread an action belongs to. `THR-4821906337` names
    # nothing it can see in the text; the question does.
    #
    # And this particular handle was not even stable: `hash()` on a str is randomised per
    # process, so the same book produced different thread references on every run — the exact
    # class of nondeterminism the identity design forbids everywhere else (T0-18).
    threads = {t for t in previous.open_thread_refs}
    for thread in asset.suspense_threads:
        threads.add(thread.question)
    for action in asset.suspense_actions:
        if action.action_kind in {"resolve", "close"}:
            threads.discard(action.thread_ref)
            # An action naming a thread by a near-miss must still close it, or a thread
            # resolved in chapter 400 stays open because the model rephrased its question.
            for open_thread in list(threads):
                if _refers_to_thread(action.thread_ref, open_thread):
                    threads.discard(open_thread)

    goals = {g for g in previous.active_goal_refs}
    for change in asset.goal_changes:
        if change.change_kind in {"abandoned", "achieved"}:
            goals.discard(change.entity_ref)
        else:
            goals.add(change.entity_ref)

    participants = {p for p in previous.active_continuity_refs}
    for cluster in asset.provisional_entities:
        if cluster.continuity_ref:
            participants.add(cluster.continuity_ref)

    return CarryForwardState(
        open_thread_refs=sorted(threads),
        active_goal_refs=sorted(goals),
        active_continuity_refs=sorted(participants),
        unresolved_note=previous.unresolved_note,
    )


class PropagationVerdict(StrEnum):
    CONVERGED = "converged"
    UNCONVERGED = "unconverged"


@dataclass
class PropagationOutcome:
    verdict: PropagationVerdict
    re_extracted: list[str] = field(default_factory=list)
    stopped_at: str | None = None
    depth: int = 0
    residual_delta: dict[str, list[str]] = field(default_factory=dict)

    @property
    def carry_status(self) -> CarryStatus:
        if self.verdict is PropagationVerdict.CONVERGED:
            return CarryStatus.CONVERGED if not self.re_extracted else CarryStatus.PROPAGATED
        return CarryStatus.UNCONVERGED


def propagate(
    *,
    start_block_key: str,
    successor: Callable[[str], str | None],
    stored_carry_in_fingerprint: Callable[[str], str],
    re_extract: Callable[[str], CarryForwardState],
    ceiling: int = C.CARRY_PROPAGATION_CEILING,
) -> PropagationOutcome:
    """Walk forward from an edited block until the carry stops changing.

    Returns rather than raises on non-convergence: an unconverged tail is a *disclosed*
    outcome the user can act on (priced tail re-extraction), not an engine error.
    """
    outcome = PropagationOutcome(verdict=PropagationVerdict.CONVERGED)
    block = start_block_key
    while True:
        carry_out = re_extract(block)
        outcome.re_extracted.append(block)

        nxt = successor(block)
        if nxt is None:
            return outcome

        if carry_semantic_fingerprint(carry_out) == stored_carry_in_fingerprint(nxt):
            # Fixed point: every block after this one is exactly valid, with zero drift.
            return outcome

        outcome.depth += 1
        if outcome.depth >= ceiling:
            outcome.verdict = PropagationVerdict.UNCONVERGED
            outcome.stopped_at = nxt
            outcome.residual_delta = {
                "threads": sorted(carry_out.open_thread_refs),
                "arcs": sorted(carry_out.active_goal_refs),
            }
            return outcome
        block = nxt


# ----------------------------------------------------------------------- reduction


@dataclass(frozen=True)
class PartitionReduction:
    partition_key: str
    entry_state_json: dict[str, object]
    reduce_json: dict[str, object]
    reduce_hash: str


def reduce_partition(
    *,
    partition_key: str,
    assets: Sequence[BlockAsset],
    entry_state: dict[str, object] | None = None,
) -> PartitionReduction:
    """Fold one partition's facts, from an explicitly pinned entry state.

    Pinning the entry state is what bounds the recompute cascade: re-extracting one block
    changes its partition and the entry state of the ones after it, but a later partition
    whose folded values come out identical keeps its ``reduce_hash`` and needs no work. The
    cascade is bounded by actual state change, not by position in the book.

    Zero provider calls — this is why deleting every reduction and rebuilding is free.
    """
    entry = dict(entry_state or {})
    events: list[str] = []
    threads: set[str] = set(entry.get("open_threads", []) or [])  # type: ignore[arg-type]
    participants: set[str] = set(entry.get("participants", []) or [])  # type: ignore[arg-type]
    signals: list[dict[str, object]] = []

    for asset in assets:
        for signal in asset.chapter_signals:
            signals.append(
                {
                    "chapter_ref": signal.chapter_ref,
                    "dialogue": signal.dialogue_paragraphs,
                    "action": signal.action_paragraphs,
                    "interiority": signal.interiority_paragraphs,
                    "beats": signal.new_information_beats,
                    "hook": signal.hook_present,
                    "saturated": signal.cap_saturated,
                }
            )
        for event in asset.events:
            events.append(event.summary)
        for thread in asset.suspense_threads:
            threads.add(thread.question)
        for action in asset.suspense_actions:
            if action.action_kind in {"resolve", "close"}:
                threads.discard(action.thread_ref)
        for cluster in asset.provisional_entities:
            if cluster.continuity_ref:
                participants.add(cluster.continuity_ref)

    reduce_json = {
        "chapter_signals": signals,
        "event_count": len(events),
        "open_threads": sorted(threads),
        "participants": sorted(participants),
    }
    return PartitionReduction(
        partition_key=partition_key,
        entry_state_json=entry,
        reduce_json=reduce_json,
        reduce_hash=ids.reduce_hash(reduce_json),
    )


# ----------------------------------------------------------------------- entities


@dataclass(frozen=True)
class ResolvedEntity:
    entity_key: str
    anchor_mention_key: str
    anchor_provisional_key: str
    display_surface_norm: str
    member_provisional_keys: tuple[str, ...]
    decision: str


def resolve_entities(
    clusters: Iterable[tuple[str, Sequence[tuple[int, int, int, str]], str]],
    *,
    splits: dict[str, list[list[str]]] | None = None,
) -> list[ResolvedEntity]:
    """Resolve provisional clusters to canonical entities.

    ``clusters`` yields ``(provisional_key, member_mentions, display_surface)`` where each
    member mention is ``(chapter_order, paragraph_order, surface_index, mention_key)``.
    ``splits`` optionally maps a provisional key to disjoint mention groups when evidence
    says one cluster is really two people.

    Each resulting entity anchors on **its own** narrative-earliest member mention. That is
    what makes a split representable: the two sides own disjoint mention sets, so they have
    different earliest mentions and therefore different keys. Anchoring on the provisional
    cluster gave both sides the same hash and a split collided with itself.
    """
    split_map = splits or {}
    resolved: list[ResolvedEntity] = []

    for provisional_key, members, display in clusters:
        groups = split_map.get(provisional_key)
        if groups:
            for group in groups:
                subset = [m for m in members if m[3] in set(group)]
                if not subset:
                    continue
                anchor = ids.narrative_earliest_mention(subset)
                resolved.append(
                    ResolvedEntity(
                        entity_key=ids.entity_key(anchor),
                        anchor_mention_key=anchor,
                        anchor_provisional_key=provisional_key,
                        display_surface_norm=display,
                        member_provisional_keys=(provisional_key,),
                        decision="split",
                    )
                )
        else:
            anchor = ids.narrative_earliest_mention(list(members))
            resolved.append(
                ResolvedEntity(
                    entity_key=ids.entity_key(anchor),
                    anchor_mention_key=anchor,
                    anchor_provisional_key=provisional_key,
                    display_surface_norm=display,
                    member_provisional_keys=(provisional_key,),
                    decision="alias",
                )
            )
    return resolved
