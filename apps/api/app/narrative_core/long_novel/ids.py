"""Deterministic identity derivation — THE ONLY IMPLEMENTATION IN THE ENGINE.

This module is the code counterpart of ``02_DATA_MODEL.md §3``, which is the only place the
formulas are defined in prose. Nothing else in the package may derive an identity; a second
implementation is how two formulas drift apart, which happened repeatedly in the design
rounds and is exactly what the frozen contract exists to prevent.

Two rules govern every function here, and both were bought expensively:

**No provider-array ordinal and no global chapter ordinal may enter a key.**
    Response array position, ``block_seq``, ``stage_seq`` and ``chapter_order`` are position
    metadata. If any of them entered a key, a re-extraction that merely reordered the
    model's output — or an unrelated chapter insertion — would rekey facts, entities and
    everything derived from them, invalidating a book that had not changed.
    Occurrence-scoped *local* ordinals do appear (``duplicate_index_within_chapter``,
    ``surface_occurrence_index_in_paragraph``); each is fixed by the snapshot text, does not
    shift when an unrelated chapter moves, and is the minimum needed to tell two otherwise
    identical things apart.

**Occurrence identity anchors on ``source_chapter_id``, never on position.**
    ``source_chapter_id`` is the durable author-side identity of a chapter and survives
    insertion, deletion and reordering.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence

from app.narrative_core.long_novel.constants import (
    FACT_KEY_ALGORITHM_VERSION,
    FIELD_SEP,
    RECORD_SEP,
    RESOLUTION_ALGORITHM_VERSION,
)
from app.narrative_core.long_novel.errors import LongNovelError, LongNovelErrorCode

__all__ = [
    "canonical_json",
    "canonical_semantic_payload",
    "sha256_fields",
    "block_content_key",
    "partition_content_key",
    "stage_content_key",
    "chapter_occurrence_key",
    "block_occurrence_key",
    "partition_occurrence_key",
    "stage_occurrence_key",
    "paragraph_occurrence_key",
    "block_key",
    "partition_key",
    "stage_key",
    "topic_key",
    "final_key",
    "evidence_id",
    "mention_key",
    "primary_evidence_id",
    "fact_key",
    "provisional_entity_key",
    "continuity_key",
    "entity_key",
    "plan_fingerprint",
    "semantic_compat_key",
    "provider_input_fingerprint",
    "reduce_hash",
    "projection_fingerprint",
    "digest_fingerprint",
]

# Fields that describe *where* a fact sits rather than *what it says*. They are stripped
# before hashing so that moving a fact does not change its identity, and so that identity
# never depends on an ordinal.
_NON_SEMANTIC_FACT_FIELDS: frozenset[str] = frozenset(
    {
        "evidence_ids",
        "evidence",
        "chapter_order",
        "paragraph_order",
        "block_seq",
        "stage_seq",
        "ordinal",
        "seq",
        "index",
        "position",
        "created_at",
        "updated_at",
        "provenance",
        "asset_revision",
        "run_id",
    }
)


def canonical_json(value: Any) -> str:
    """Canonical JSON: sorted keys, no incidental whitespace, Unicode preserved.

    Two payloads that differ only in key order or spacing must hash identically, or the
    same input would be billed twice. ``ensure_ascii=False`` keeps CJK text as itself so the
    encoding is stable across Python versions and platforms.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_semantic_payload(fact_body: Mapping[str, Any]) -> str:
    """Canonical JSON of a fact body with every non-semantic field removed.

    Strips recursively, because nested objects carry the same positional fields.
    """

    def strip(node: Any) -> Any:
        if isinstance(node, Mapping):
            return {k: strip(v) for k, v in node.items() if k not in _NON_SEMANTIC_FACT_FIELDS}
        if isinstance(node, (list, tuple)):
            return [strip(item) for item in node]
        return node

    return canonical_json(strip(fact_body))


def sha256_fields(*parts: str) -> str:
    """SHA-256 hex of ``parts`` joined by the unit separator.

    Joining with a control character that cannot occur in normalised text means no field
    value can forge a boundary — ``("ab", "c")`` and ``("a", "bc")`` hash differently.
    """
    for part in parts:
        if not isinstance(part, str):
            raise TypeError(f"hash components must be str, got {type(part).__name__}")
    return hashlib.sha256(FIELD_SEP.join(parts).encode("utf-8")).hexdigest()


def _join_records(items: Iterable[str]) -> str:
    return RECORD_SEP.join(items)


# --------------------------------------------------------------------------------------
# 3.1 Content identity — *what* the text is. Never sufficient for reuse on its own.
# --------------------------------------------------------------------------------------


def block_content_key(
    chapter_content_hashes: Sequence[str],
    *,
    part_index: int | None = None,
    part_count: int | None = None,
    first_paragraph_hash: str | None = None,
    last_paragraph_hash: str | None = None,
    paragraph_count_in_part: int | None = None,
) -> str:
    """Content key of a block, in reading order.

    The optional part fields are supplied only for a *split* block. Without them two parts
    of one chapter would share a content key; ``stable_paragraph_id`` is deliberately absent
    because it is snapshot-scoped positional binding, not content.
    """
    if not chapter_content_hashes:
        raise ValueError("a block needs at least one chapter content hash")
    parts = ["blk", _join_records(chapter_content_hashes)]
    if part_index is not None:
        if None in (part_count, first_paragraph_hash, last_paragraph_hash, paragraph_count_in_part):
            raise ValueError(
                "a partial block needs part_count, both paragraph boundary hashes "
                "and paragraph_count_in_part — without them two parts collide"
            )
        parts += [
            "part",
            str(part_index),
            str(part_count),
            str(first_paragraph_hash),
            str(last_paragraph_hash),
            str(paragraph_count_in_part),
        ]
    return sha256_fields(*parts)


def partition_content_key(member_block_content_keys: Sequence[str]) -> str:
    """Content key of a Reduction Partition, from its member blocks in order."""
    if not member_block_content_keys:
        raise ValueError("a partition needs at least one member block")
    return sha256_fields("prt", _join_records(member_block_content_keys))


def stage_content_key(member_partition_content_keys: Sequence[str]) -> str:
    """Content key of a Narrative Stage, from its member partitions in order."""
    if not member_partition_content_keys:
        raise ValueError("a stage needs at least one member partition")
    return sha256_fields("stg", _join_records(member_partition_content_keys))


# --------------------------------------------------------------------------------------
# 3.2 Occurrence identity — *which instance*, stable across snapshots.
# --------------------------------------------------------------------------------------


def chapter_occurrence_key(chapter_content_hash: str, source_chapter_id: int | str) -> str:
    """Occurrence key of a chapter.

    ``source_chapter_id`` does not renumber when other chapters are inserted, deleted or
    reordered, which is the whole reason it and not ``chapter_order`` is the anchor.
    """
    if source_chapter_id is None or source_chapter_id == "":
        raise LongNovelError(
            LongNovelErrorCode.OCCURRENCE_LINEAGE_UNVERIFIED,
            "source_chapter_id is required for occurrence identity; a NULL value must be "
            "handled by marking the block oid_provisional, not by substituting a position",
        )
    return sha256_fields("cho", chapter_content_hash, str(source_chapter_id))


def block_occurrence_key(
    content_key: str,
    source_chapter_ids: Sequence[int | str],
    *,
    part_index: int | None = None,
) -> str:
    """Occurrence key of a block.

    Source chapter ids are **sorted** so the key does not depend on the order the planner
    happened to collect them in; the reading order that matters is already fixed by
    ``content_key``.
    """
    if not source_chapter_ids:
        raise ValueError("a block occurrence needs at least one source chapter id")
    ordered = _join_records(sorted(str(cid) for cid in source_chapter_ids))
    parts = [content_key, ordered]
    if part_index is not None:
        parts += ["part", str(part_index)]
    return sha256_fields(*parts)


def partition_occurrence_key(member_block_occurrence_keys: Sequence[str]) -> str:
    if not member_block_occurrence_keys:
        raise ValueError("a partition needs at least one member block")
    return sha256_fields("prt", _join_records(member_block_occurrence_keys))


def stage_occurrence_key(member_partition_occurrence_keys: Sequence[str]) -> str:
    if not member_partition_occurrence_keys:
        raise ValueError("a stage needs at least one member partition")
    return sha256_fields("stg", _join_records(member_partition_occurrence_keys))


def paragraph_occurrence_key(
    chapter_occurrence_key_value: str,
    paragraph_content_hash: str,
    duplicate_index_within_chapter: int,
) -> str:
    """Occurrence key of a paragraph.

    ``duplicate_index_within_chapter`` disambiguates byte-identical paragraphs inside one
    chapter — a repeated refrain, a quoted document. It is scoped to the chapter, so an
    unrelated edit elsewhere in the book cannot shift it.
    """
    if duplicate_index_within_chapter < 0:
        raise ValueError("duplicate_index_within_chapter is 0-based and non-negative")
    return sha256_fields(
        chapter_occurrence_key_value,
        paragraph_content_hash,
        str(duplicate_index_within_chapter),
    )


# --------------------------------------------------------------------------------------
# 3.3 Logical unit identity — addressing.
# --------------------------------------------------------------------------------------


def block_key(block_occurrence_key_value: str) -> str:
    return "BLK-" + block_occurrence_key_value[:16]


def partition_key(partition_occurrence_key_value: str) -> str:
    return "PRT-" + partition_occurrence_key_value[:12]


def stage_key(stage_occurrence_key_value: str) -> str:
    return "STG-" + stage_occurrence_key_value[:12]


def topic_key(run_id: int, topic: str) -> str:
    """Topic addressing is run-scoped: topics are never adopted across runs."""
    return f"TOP-{run_id}-{topic}"


def final_key(run_id: int) -> str:
    return f"FIN-{run_id}"


# --------------------------------------------------------------------------------------
# 3.4 Fact, evidence and mention identity — all occurrence-scoped.
# --------------------------------------------------------------------------------------


def evidence_id(paragraph_occurrence_key_value: str) -> str:
    """Evidence is exactly one paragraph occurrence — there is nothing finer to identify.

    The provider returns a paragraph anchor and no span, and the engine fills offsets with
    the paragraph's own bounds, so no sub-paragraph ordinal exists to hash. One row per
    paragraph occurrence, shared by every fact that cites it.
    """
    return "EVD-" + sha256_fields(paragraph_occurrence_key_value)[:12]


def mention_key(
    paragraph_occurrence_key_value: str,
    surface_norm: str,
    surface_occurrence_index_in_paragraph: int,
) -> str:
    """Identity of one mention occurrence.

    ``surface_occurrence_index_in_paragraph`` is text-derived and engine-computed: the index
    of this mention among the *textual* occurrences of ``surface_norm`` in that paragraph,
    in reading order. It never comes from the provider's response array — see
    ``mention_binding.bind_mention_occurrences``, which discards array order before binding
    and refuses outright when the correspondence is not recoverable from the text.
    """
    if surface_occurrence_index_in_paragraph < 0:
        raise ValueError("surface_occurrence_index_in_paragraph is 0-based and non-negative")
    if not surface_norm:
        raise ValueError("surface_norm must be a non-empty normalised surface form")
    return "MEN-" + sha256_fields(
        paragraph_occurrence_key_value,
        surface_norm,
        str(surface_occurrence_index_in_paragraph),
    )[:12]


def primary_evidence_id(evidence_ids: Sequence[str]) -> str:
    """Lexicographic minimum of the fact's evidence ids — deterministic, order-free."""
    if not evidence_ids:
        raise LongNovelError(
            LongNovelErrorCode.EVIDENCE_REFERENCE_INVALID,
            "every fact kind requires at least one evidence id",
        )
    return min(evidence_ids)


def fact_key(
    fact_kind: str,
    fact_body: Mapping[str, Any],
    evidence_ids: Sequence[str],
    *,
    prefix: str,
) -> str:
    """Identity of a fact: kind + semantic payload + the primary evidence occurrence.

    Both inputs matter. Payload alone would collide two genuinely different facts that
    happen to phrase the same thing at different points in the book; evidence alone would
    collide two different facts drawn from one paragraph. There is no ``-2``/``-3`` suffix:
    same kind, same payload and same primary evidence *is* the same fact and is deduplicated
    to one row. A suffix counter would silently re-bind whenever a new duplicate appeared
    earlier on re-extraction — the ordinal-rebinding defect under another name.
    """
    if not prefix:
        raise ValueError("fact prefix is required (e.g. EVT, CST, REL)")
    digest = sha256_fields(
        fact_kind,
        canonical_semantic_payload(fact_body),
        primary_evidence_id(evidence_ids),
        FACT_KEY_ALGORITHM_VERSION,
    )
    return f"{prefix}-{digest[:12]}"


# --------------------------------------------------------------------------------------
# 3.5 Entity identity — three L1-local tiers, one canonical.
# --------------------------------------------------------------------------------------


def provisional_entity_key(
    block_occurrence_key_value: str, member_mention_keys: Iterable[str]
) -> str:
    """Block-scoped provisional entity, derived from its member *set*.

    Sorting the members makes the key independent of the provider's response order: a
    re-extraction that merely reorders its output produces the same ``LENT-*``. The same
    surface form in two blocks correctly yields two different keys — it is a local cluster,
    not a person.
    """
    members = sorted(set(member_mention_keys))
    if not members:
        raise ValueError("a provisional entity needs at least one member mention")
    return "LENT-" + sha256_fields(block_occurrence_key_value, _join_records(members))[:12]


def continuity_key(anchor_mention_key: str) -> str:
    """Cross-block continuity handle, anchored on the first mention ever seen for the chain.

    A continuity *hypothesis* from L1's local view, never proof of a person: L2 may split or
    merge these chains when it resolves canonical entities.
    """
    if not anchor_mention_key.startswith("MEN-"):
        raise ValueError("a continuity chain is anchored on a mention key")
    return "CENT-" + anchor_mention_key[4:16]


def entity_key(anchor_mention_key: str) -> str:
    """Canonical entity, anchored on its narrative-earliest **member mention**.

    Anchoring on the mention rather than on the provisional entity is what makes ``split``
    representable: the two sides of a split own disjoint mention subsets, so they have
    different earliest mentions and therefore distinct keys. Anchoring on the ``LENT-*``
    gave both sides the same hash, so a split collided with itself.

    Use :func:`narrative_earliest_mention` to pick the anchor; a late-discovered alias
    contributes a *later* mention and cannot move it, so the key stays stable.
    """
    if not anchor_mention_key.startswith("MEN-"):
        raise ValueError("a canonical entity is anchored on a mention key, not on a LENT")
    return "CHR-" + sha256_fields(anchor_mention_key, RESOLUTION_ALGORITHM_VERSION)[:12]


def narrative_earliest_mention(
    candidates: Iterable[tuple[int, int, int, str]],
) -> str:
    """Pick the anchor mention from ``(chapter_order, paragraph_order, surface_index, key)``.

    The ordering triple is snapshot-derived and is used only to *order* candidates; none of
    it enters the resulting key. Entity resolution is recomputed per ``resolution_revision``
    from the block set, so this ordering is stable for the resolution it governs.
    """
    ordered = sorted(candidates)
    if not ordered:
        raise ValueError("an entity needs at least one member mention to anchor on")
    return ordered[0][3]


# --------------------------------------------------------------------------------------
# 3.7 Fingerprints.
# --------------------------------------------------------------------------------------


def plan_fingerprint(
    *,
    snapshot_id: int,
    revision_hash: str,
    provider_name: str,
    model_name: str,
    resolved_output_budget: int,
    density_profile: str,
    chapters_per_block_cap: int,
    calibration_ratio: float,
    engine_semantics_version: str,
) -> str:
    return sha256_fields(
        str(snapshot_id),
        revision_hash,
        provider_name,
        model_name,
        str(resolved_output_budget),
        density_profile,
        str(chapters_per_block_cap),
        f"{round(calibration_ratio, 3):.3f}",
        engine_semantics_version,
    )


def semantic_compat_key(
    *,
    engine_semantics_version: str,
    asset_schema_version: str,
    prompt_template_content_hash: str,
    normalization_version: str,
    fact_key_algorithm_version: str,
    projection_algorithm_version: str,
    resolution_algorithm_version: str,
    provider_name: str,
    model_name: str,
    density_profile: str,
) -> str:
    """What must match for a stored asset to still *mean* the same thing.

    The density profile is in here, not the raw output budget: the profile is what changes
    extraction semantics, and it is pinned at run creation so a user's cap change cannot
    silently alter them mid-run.
    """
    return sha256_fields(
        engine_semantics_version,
        asset_schema_version,
        prompt_template_content_hash,
        normalization_version,
        fact_key_algorithm_version,
        projection_algorithm_version,
        resolution_algorithm_version,
        provider_name,
        model_name,
        density_profile,
    )


def provider_input_fingerprint(
    unit_kind: str, semantic_contract_version: str, semantic_payload: Any
) -> str:
    """Hash of the EXACT semantic payload that will be sent.

    This is the only value that may authorise skipping a paid call. Component hashes —
    ``projection_fingerprint``, ``reduce_hash``, ``digest_fingerprint`` — are invalidation
    *hints* and may never substitute for it: they describe which inputs were selected, not
    what was actually assembled and sent.
    """
    return sha256_fields(unit_kind, semantic_contract_version, canonical_json(semantic_payload))


def reduce_hash(reduction: Any) -> str:
    return sha256_fields(canonical_json(reduction))


def projection_fingerprint(selected_input_keys: Iterable[str], algorithm_version: str) -> str:
    """INVALIDATION OPTIMISATION HINT ONLY — never a reuse authorisation."""
    return sha256_fields(_join_records(sorted(selected_input_keys)), algorithm_version)


def digest_fingerprint(serialised_digest: Any) -> str:
    return sha256_fields(canonical_json(serialised_digest))
