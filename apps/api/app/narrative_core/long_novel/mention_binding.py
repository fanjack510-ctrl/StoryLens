"""Bind emitted mentions to textual occurrences (03 §2.3a).

The provider emits ``{"s": <surface form>, "p": <block-local paragraph anchor>}`` and **no
occurrence index**. The engine derives one from the snapshot text, because an index taken
from the response array would put the provider's array order inside ``MEN-*`` — and hence
inside ``LENT-*``, ``CENT-*``, ``CHR-*`` and, through ``primary_evidence_id``, every
``fact_key``. Two responses identical except for the order of ``mn[]`` would then invalidate
the whole book.

So array order is **discarded before binding**: the binding is a function of the paragraph
text and the *multiset* of surfaces claimed for it.

That is safe only while the correspondence is recoverable from the text, and there is one
case where it is not. In 「老王看着老王说道」 two textual 老王 and two emitted 老王 assigned
to *different* provisional entities carry no textual signal for which is which. Binding by
position would silently swap two identities and propagate the swap up the entity chain while
passing every other invariant. The engine therefore refuses:
:class:`~app.narrative_core.long_novel.errors.LongNovelErrorCode.MENTION_OCCURRENCE_AMBIGUOUS`.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence

from app.narrative_core.long_novel.errors import LongNovelError, LongNovelErrorCode
from app.narrative_core.long_novel.ids import mention_key

__all__ = [
    "EmittedMention",
    "BoundMention",
    "RejectedMention",
    "textual_occurrences",
    "bind_mention_occurrences",
]


@dataclass(frozen=True)
class EmittedMention:
    """One mention as the provider emitted it, before the engine gives it an identity.

    ``cluster_ref`` is the provisional-entity grouping the model assigned (the ``le[].m``
    membership). It is what decides whether an ambiguous repetition is harmful: two
    identical surfaces in one paragraph that belong to the *same* cluster are
    interchangeable, two that belong to different clusters are not.
    """

    surface_norm: str
    paragraph_ref: int
    cluster_ref: str | None = None


@dataclass(frozen=True)
class RejectedMention:
    """A mention that could not be anchored, and why.

    Rejection is *not* silent loss: an unbindable mention produces **no identity at all**,
    so nothing downstream can be wrong because of it — but the count is carried up so a run
    whose entity coverage is degrading says so instead of looking clean.
    """

    surface_norm: str
    paragraph_ref: int
    reason: str


@dataclass(frozen=True)
class BoundMention:
    """An emitted mention that has been given a text-derived occurrence identity."""

    mention_key: str
    surface_norm: str
    paragraph_ref: int
    surface_occurrence_index_in_paragraph: int
    cluster_ref: str | None


def textual_occurrences(paragraph_text: str, surface_norm: str) -> list[int]:
    """Character offsets of every non-overlapping occurrence of ``surface_norm``, in order.

    ``paragraph_text`` must already be normalised with the run's ``normalization_version``,
    the same normalisation that produced ``surface_norm``; otherwise a surface that is
    present would look absent and be rejected.
    """
    if not surface_norm:
        raise ValueError("surface_norm must be non-empty")
    offsets: list[int] = []
    start = 0
    while True:
        found = paragraph_text.find(surface_norm, start)
        if found < 0:
            return offsets
        offsets.append(found)
        start = found + len(surface_norm)


def bind_mention_occurrences(
    emitted: Sequence[EmittedMention],
    paragraph_texts: dict[int, str],
    paragraph_occurrence_keys: dict[int, str],
) -> tuple[list[BoundMention], list[RejectedMention]]:
    """Give every emitted mention a text-derived occurrence identity, or reject it.

    ``paragraph_texts`` and ``paragraph_occurrence_keys`` are keyed by the block-local
    paragraph anchor ``[p:N]`` the provider was shown.

    Returns ``(bound, rejected)``. The two failure modes are handled differently on purpose,
    because they differ in what they can corrupt:

    * **A surface that is not in its paragraph** yields no identity at all, so it is dropped
      and reported. A real run rejected a whole block — every fact, every chapter signal and
      three correctly-anchored mentions — because one claimed surface sat in the wrong
      paragraph. That is punishing the innocent for the guilty.
    * **An ambiguous repetition** could bind the *wrong* person and propagate a swapped
      identity upward, so it still raises ``MENTION_OCCURRENCE_AMBIGUOUS``. Creating no
      identity is safe; creating a plausible wrong one is not.
    """
    groups: dict[tuple[int, str], list[EmittedMention]] = defaultdict(list)
    for item in emitted:
        groups[(item.paragraph_ref, item.surface_norm)].append(item)

    bound: list[BoundMention] = []
    rejected: list[RejectedMention] = []
    # Deterministic group order so the result list is reproducible; it does not affect any
    # key, since each key is derived only from its own paragraph, surface and index.
    for (paragraph_ref, surface_norm) in sorted(groups):
        group = groups[(paragraph_ref, surface_norm)]
        text = paragraph_texts.get(paragraph_ref)
        occurrence_key = paragraph_occurrence_keys.get(paragraph_ref)
        if text is None or occurrence_key is None:
            rejected.append(
                RejectedMention(surface_norm, paragraph_ref, "paragraph_out_of_range")
            )
            continue

        occurrences = textual_occurrences(text, surface_norm)
        if len(group) > len(occurrences):
            # The surface is not there (or not there often enough). No identity can be
            # created for the surplus, so nothing downstream can be wrong — but the block's
            # facts, chapter signals and correctly-anchored mentions are all still valid and
            # are worth far more than the one claim being dropped. Rejecting the whole block
            # for this threw away three good mentions and every fact to punish one bad one.
            for surplus in group[len(occurrences) :]:
                rejected.append(
                    RejectedMention(surface_norm, paragraph_ref, "surface_not_in_paragraph")
                )
            group = group[: len(occurrences)]
            if not group:
                continue

        if len(group) > 1 and len(occurrences) > 1:
            clusters = {item.cluster_ref for item in group}
            if len(clusters) > 1:
                raise LongNovelError(
                    LongNovelErrorCode.MENTION_OCCURRENCE_AMBIGUOUS,
                    (
                        f"{len(group)} occurrences of {surface_norm!r} in [p:{paragraph_ref}] are "
                        f"assigned to {len(clusters)} different provisional entities, and the text "
                        "does not say which is which; refusing to bind by position"
                    ),
                    detail={
                        "paragraph_ref": paragraph_ref,
                        "surface_norm": surface_norm,
                        "clusters": sorted(str(c) for c in clusters),
                        "resolutions": [
                            "re-emit distinguishing surface forms for the two entities",
                            "or place both mentions in one provisional entity if they are one person",
                        ],
                    },
                )

        # Safe to bind: either a single mention (no swap is possible), or several that are
        # interchangeable because they belong to one cluster — the resulting MEN-* set and
        # the cluster's member set are identical under any permutation.
        for index, item in enumerate(group):
            bound.append(
                BoundMention(
                    mention_key=mention_key(occurrence_key, surface_norm, index),
                    surface_norm=surface_norm,
                    paragraph_ref=paragraph_ref,
                    surface_occurrence_index_in_paragraph=index,
                    cluster_ref=item.cluster_ref,
                )
            )
    return bound, rejected
