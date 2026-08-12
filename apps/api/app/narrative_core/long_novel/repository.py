"""``LongNovelRepository`` — phase-guarded writers and the two persistence models.

Every table has exactly one writer and exactly one phase in which that writer may write
(02 §6). The guard is here rather than in a code review checklist because "no upward write"
is an invariant, and an invariant enforced only by convention is a hope.

The two persistence models are the load-bearing part of this module (ADR-03):

**L1 facts and evidence are insert-only.** Re-extraction inserts ``asset_revision + 1`` and
marks the previous revision superseded. This is required, not stylistic: facts and evidence
hold foreign keys into a *specific* block revision and must still resolve against the
superseded one while a rebase is in progress.

**Tier-3 derived views are replaced in place, atomically.** Stage interpretations, topic
results and the final result are UNIQUE on their logical unit and are referenced by no
foreign key. Making them insert-only too would leave a re-executed unit with **no legal
destination**: the insert violates the constraint, there is no supersession column, and no
UPDATE is permitted. The strictest possible rule would produce the least recoverable system.

The replacement writes result, ``PIF``, ``ELR`` and ``SCI`` in **one** transaction. A torn
write that left a new result beside an old fingerprint would authorise reuse of an output
that was never produced from that input — which is the exact failure the fingerprint exists
to prevent. History is not lost: every attempt lives in the insert-only
``long_novel_unit_attempts`` and ``model_invocations``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.narrative_core.long_novel.contracts.enums import RunPhase, Topic, UnitKind
from app.narrative_core.long_novel.errors import LongNovelError, LongNovelErrorCode
from app.narrative_core.long_novel.ids import evidence_id as derive_evidence_id

__all__ = ["TABLE_WRITERS", "LongNovelRepository", "DerivedIndex"]


@dataclass(frozen=True)
class _Writer:
    component: str
    phase: RunPhase
    insert_only: bool


#: One writer, one phase, one persistence model per table. The table is the contract; the
#: repository methods below are only its enforcement.
TABLE_WRITERS: dict[str, _Writer] = {
    "long_novel_block_plans": _Writer("BlockPlanner", RunPhase.PLANNED, True),
    "long_novel_plan_blocks": _Writer("BlockPlanner", RunPhase.PLANNED, True),
    "long_novel_blocks": _Writer("BlockExtractor", RunPhase.EXTRACTING_BLOCKS, True),
    "long_novel_facts": _Writer("LongNovelRepository", RunPhase.EXTRACTING_BLOCKS, True),
    "long_novel_evidence": _Writer("LongNovelRepository", RunPhase.EXTRACTING_BLOCKS, True),
    "long_novel_partitions": _Writer("StageReducer", RunPhase.CONSOLIDATING_STAGES, False),
    "long_novel_stages": _Writer("StageInterpreter", RunPhase.CONSOLIDATING_STAGES, False),
    "long_novel_entities": _Writer("EntityResolver", RunPhase.CONSOLIDATING_STAGES, False),
    "long_novel_entity_aliases": _Writer("EntityResolver", RunPhase.CONSOLIDATING_STAGES, False),
    "long_novel_topic_results": _Writer("TopicSynthesizer", RunPhase.SYNTHESIZING_TOPICS, False),
    "long_novel_final_results": _Writer("FinalSynthesizer", RunPhase.FINAL_SYNTHESIS, False),
    "long_novel_unit_attempts": _Writer("ProviderIO", RunPhase.PLANNED, True),
    "long_novel_invalidations": _Writer("InvalidationGraph", RunPhase.PLANNED, True),
    "long_novel_snapshot_retentions": _Writer("RunCoordinator", RunPhase.PLANNED, True),
}

#: Tier-3 derived views: replaced in place, never superseded.
_REPLACEABLE = {
    "long_novel_stages": "stage_key",
    "long_novel_topic_results": "topic",
    "long_novel_final_results": "run_id",
}


@dataclass
class DerivedIndex:
    """The fact and evidence rows implied by one block asset."""

    facts: list[dict[str, Any]]
    evidence: list[dict[str, Any]]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LongNovelRepository:
    """All persistence for the engine. Nothing else writes ``long_novel_*``."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------ guards
    def _guard(self, table: str, current_phase: RunPhase) -> _Writer:
        writer = TABLE_WRITERS.get(table)
        if writer is None:
            raise LongNovelError(
                LongNovelErrorCode.PHASE_WRITE_FORBIDDEN,
                f"{table} has no declared writer; every table needs exactly one",
            )
        # `unit_attempts`, `invalidations` and `snapshot_retentions` are run-lifecycle
        # tables and are legitimately written in any phase — an attempt row must be
        # writable precisely when something is going wrong.
        if table in {
            "long_novel_unit_attempts",
            "long_novel_invalidations",
            "long_novel_snapshot_retentions",
        }:
            return writer
        if writer.phase is not current_phase:
            raise LongNovelError(
                LongNovelErrorCode.PHASE_WRITE_FORBIDDEN,
                f"{table} is written by {writer.component} in phase {writer.phase.value}, "
                f"but the run is in {current_phase.value}",
                detail={"table": table, "expected_phase": writer.phase.value},
            )
        return writer

    # ------------------------------------------------------------------ L1: insert-only
    def insert_block_revision(
        self, *, current_phase: RunPhase, row: Mapping[str, Any]
    ) -> int:
        """Insert a new block revision. Never updates an existing one."""
        self._guard("long_novel_blocks", current_phase)
        if row.get("origin") != "real_provider" and not row.get("non_formal_run"):
            # A scaffolded or placeholder asset must never be persisted as a formal result:
            # it validates, it reuses, and it is not what the user paid for.
            raise LongNovelError(
                LongNovelErrorCode.SCAFFOLD_FORBIDDEN,
                "a block asset that did not come from a real provider cannot be stored in a formal run",
            )
        columns = [k for k in row if k != "non_formal_run"]
        placeholders = ", ".join(f":{c}" for c in columns)
        result = self._session.execute(
            text(
                f"INSERT INTO long_novel_blocks ({', '.join(columns)}, created_at) "
                f"VALUES ({placeholders}, :created_at)"
            ),
            {**{c: row[c] for c in columns}, "created_at": _utc_now()},
        )
        return int(result.lastrowid or 0)

    def supersede_block(self, *, run_id: int, block_key: str, old_revision: int, new_revision: int) -> None:
        """The only UPDATE a block row ever receives."""
        self._session.execute(
            text(
                """
                UPDATE long_novel_blocks
                   SET superseded_by_revision = :new_revision
                 WHERE run_id = :run_id AND block_key = :block_key AND asset_revision = :old_revision
                """
            ),
            {
                "run_id": run_id,
                "block_key": block_key,
                "old_revision": old_revision,
                "new_revision": new_revision,
            },
        )
        # Derived rows for the superseded revision stop being live but are never deleted:
        # a rebase still needs to read them.
        for table in ("long_novel_facts", "long_novel_evidence"):
            self._session.execute(
                text(
                    f"UPDATE {table} SET is_live = 0 "
                    f"WHERE run_id = :run_id AND asset_revision = :old_revision"
                ),
                {"run_id": run_id, "old_revision": old_revision},
            )

    # ------------------------------------------------------------------ Tier-3: replace in place
    def replace_derived_view(
        self,
        *,
        table: str,
        current_phase: RunPhase,
        run_id: int,
        unit_identifier: str | int,
        result_column: str,
        result_value: str,
        provider_input_fingerprint: str,
        execution_legality_json: str,
        semantic_compat_key: str,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        """Atomically replace a Tier-3 asset, or insert it if it is not there yet.

        Result, fingerprint, legality record and compatibility key move together in one
        statement. ``asset_revision`` increments and ``invalidated_at`` is cleared **only**
        on success, so a failed re-execution leaves the row invalidated and writes nothing —
        a partially-failed unit never returns to a reusable state.
        """
        self._guard(table, current_phase)
        key_column = _REPLACEABLE.get(table)
        if key_column is None:
            raise LongNovelError(
                LongNovelErrorCode.ASSET_NOT_REPLACEABLE,
                f"{table} is insert-only; in-place replacement is only legal for Tier-3 derived views",
                detail={"table": table},
            )

        where = "run_id = :run_id" if key_column == "run_id" else f"run_id = :run_id AND {key_column} = :unit"
        params: dict[str, Any] = {
            "run_id": run_id,
            "result": result_value,
            "pif": provider_input_fingerprint,
            "elr": execution_legality_json,
            "sci": semantic_compat_key,
        }
        if key_column != "run_id":
            params["unit"] = unit_identifier

        extra_sets = ""
        if extra:
            extra_sets = "".join(f", {col} = :x_{col}" for col in extra)
            params.update({f"x_{col}": value for col, value in extra.items()})

        updated = self._session.execute(
            text(
                f"""
                UPDATE {table}
                   SET {result_column} = :result,
                       provider_input_fingerprint = :pif,
                       execution_legality_json = :elr,
                       semantic_compat_key = :sci,
                       asset_revision = asset_revision + 1,
                       invalidated_at = NULL
                       {extra_sets}
                 WHERE {where}
                """
            ),
            params,
        ).rowcount
        if updated == 0:
            raise LongNovelError(
                LongNovelErrorCode.ASSET_NOT_REPLACEABLE,
                f"no {table} row for run {run_id} / {unit_identifier!r} to replace; "
                "insert it first, then replacement is the re-execution path",
                detail={"table": table, "unit": str(unit_identifier)},
            )

    # ------------------------------------------------------------------ derived index
    def build_derived_index(
        self,
        *,
        run_id: int,
        block_row_id: int,
        asset_revision: int,
        snapshot_id: int,
        asset: Mapping[str, Any],
        paragraph_occurrence_keys: Mapping[int, str],
        paragraph_metadata: Mapping[int, Mapping[str, Any]],
    ) -> DerivedIndex:
        """Derive fact and evidence rows from one block asset.

        Pure and deterministic on purpose: INV-9 requires that dropping the derived tables
        and rebuilding them from ``long_novel_blocks`` reproduces them byte-identically, and
        that is only checkable if the derivation reads nothing but the asset.

        Evidence is deduplicated by ``evidence_id``, because evidence identity is one
        paragraph occurrence and many facts legitimately cite the same paragraph.
        """
        facts: list[dict[str, Any]] = []
        evidence: dict[str, dict[str, Any]] = {}

        kind_fields = (
            ("chapter_signal", "chapter_signals"),
            ("event", "events"),
            ("character_state_change", "character_state_changes"),
            ("causal_link", "causal_links"),
            ("suspense_action", "suspense_actions"),
            ("relationship_change", "relationship_changes"),
            ("goal_change", "goal_changes"),
            ("choice", "choices"),
            ("suspense_thread", "suspense_threads"),
            ("identity_assertion", "identity_assertions"),
            ("mention", "mentions"),
            ("provisional_entity", "provisional_entities"),
        )

        for fact_kind, field_name in kind_fields:
            for position, item in enumerate(asset.get(field_name) or []):
                evidence_ids: list[str] = []
                for ref in item.get("evidence") or []:
                    paragraph_ref = ref.get("paragraph_ref")
                    occurrence_key = paragraph_occurrence_keys.get(paragraph_ref)
                    if occurrence_key is None:
                        raise LongNovelError(
                            LongNovelErrorCode.EVIDENCE_ANCHOR_MISMATCH,
                            f"[p:{paragraph_ref}] is outside the block's rendered range",
                            detail={"paragraph_ref": paragraph_ref, "fact_kind": fact_kind},
                        )
                    eid = derive_evidence_id(occurrence_key)
                    evidence_ids.append(eid)
                    if eid not in evidence:
                        meta = paragraph_metadata.get(paragraph_ref, {})
                        evidence[eid] = {
                            "run_id": run_id,
                            "evidence_id": eid,
                            "asset_revision": asset_revision,
                            "block_row_id": block_row_id,
                            "snapshot_id": snapshot_id,
                            "snapshot_chapter_id": meta.get("snapshot_chapter_id"),
                            "chapter_order": meta.get("chapter_order", 0),
                            "stable_paragraph_id": str(meta.get("stable_paragraph_id", "")),
                            "start_offset": meta.get("start_offset", 0),
                            "end_offset": meta.get("end_offset", 0),
                            "paragraph_content_hash": meta.get("paragraph_content_hash", ""),
                            "reason": "",
                            "is_live": 1,
                        }
                facts.append(
                    {
                        "run_id": run_id,
                        "fact_key": item.get("fact_key", ""),
                        "asset_revision": asset_revision,
                        "block_row_id": block_row_id,
                        "fact_kind": fact_kind,
                        "subject_key": item.get("subject_key"),
                        "chapter_order": item.get("chapter_order"),
                        # position_ordinal is DISPLAY metadata only; no key is derived from
                        # it, which is why re-ordering a response cannot rekey a fact.
                        "position_ordinal": position,
                        "payload_json": json.dumps(item, sort_keys=True, ensure_ascii=False),
                        "evidence_ids_json": json.dumps(sorted(evidence_ids)),
                        "is_live": 1,
                    }
                )

        return DerivedIndex(facts=facts, evidence=sorted(evidence.values(), key=lambda r: r["evidence_id"]))

    # ------------------------------------------------------------------ retention
    def retain_snapshot(self, *, run_id: int, snapshot_id: int, holder_kind: str) -> None:
        """Take the snapshot lock. The row *is* the lock."""
        self._session.execute(
            text(
                """
                INSERT OR IGNORE INTO long_novel_snapshot_retentions
                    (run_id, snapshot_id, holder_kind, retained_at)
                VALUES (:run_id, :snapshot_id, :holder_kind, :now)
                """
            ),
            {"run_id": run_id, "snapshot_id": snapshot_id, "holder_kind": holder_kind, "now": _utc_now()},
        )

    def release_snapshot(self, *, run_id: int, snapshot_id: int, holder_kind: str) -> None:
        """Release the lock by deleting the row. There is no ``released_at``.

        A nullable release timestamp gives two representations of "released" and eventually
        they disagree; a deleted row has exactly one.
        """
        self._session.execute(
            text(
                """
                DELETE FROM long_novel_snapshot_retentions
                 WHERE run_id = :run_id AND snapshot_id = :snapshot_id AND holder_kind = :holder_kind
                """
            ),
            {"run_id": run_id, "snapshot_id": snapshot_id, "holder_kind": holder_kind},
        )
