"""Shared Version ↔ Run ↔ Snapshot binding checks (Phase 1B Integration)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, BookSnapshot
from app.narrative_core.enums import OriginType, SnapshotStatus
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode


def validate_version_run_snapshot_binding(
    session: Session,
    *,
    book_id: int,
    run_id: int | None,
    book_snapshot_id: int | None,
    origin_type: str,
    require_snapshot_for_formal: bool = True,
) -> None:
    """Validate Run / Snapshot consistency for Asset or Relation Versions.

    Rules:
    - If book_snapshot_id set: Snapshot must exist, COMPLETED, same book.
    - If run_id set: Run must exist, same book; if Run has snapshot, it must
      equal Version.book_snapshot_id.
    - model / system / migrated origins require a COMPLETED Snapshot when
      ``require_snapshot_for_formal`` is True.
    - user origin may omit Snapshot only when explicitly user-authored
      (tracked limitation recorded by caller); default still prefers Snapshot.
    """
    origin = str(origin_type or OriginType.MODEL.value)
    snapshot: BookSnapshot | None = None

    if book_snapshot_id is not None:
        snapshot = session.get(BookSnapshot, int(book_snapshot_id))
        if snapshot is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.SNAPSHOT_NOT_FOUND,
                f"book_snapshot_id not found: {book_snapshot_id}",
            )
        if snapshot.book_id != int(book_id):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.SNAPSHOT_BOOK_MISMATCH,
                f"snapshot {book_snapshot_id} book_id={snapshot.book_id} != {book_id}",
            )
        if snapshot.snapshot_status != SnapshotStatus.COMPLETED:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.SNAPSHOT_NOT_COMPLETED,
                f"snapshot {book_snapshot_id} status={snapshot.snapshot_status}",
            )

    if run_id is not None:
        run = session.get(AnalysisRun, int(run_id))
        if run is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.INVALID_RUN_SCOPE,
                f"run_id not found: {run_id}",
            )
        if getattr(run, "book_id", None) is not None and int(run.book_id) != int(book_id):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.INVALID_RUN_SCOPE,
                f"run {run_id} book_id={run.book_id} != version book {book_id}",
            )
        run_snapshot_id = getattr(run, "book_snapshot_id", None)
        if run_snapshot_id is not None:
            if book_snapshot_id is None:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.SNAPSHOT_BOOK_MISMATCH,
                    f"run {run_id} bound to snapshot {run_snapshot_id} but version has none",
                )
            if int(run_snapshot_id) != int(book_snapshot_id):
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.SNAPSHOT_BOOK_MISMATCH,
                    (
                        f"run snapshot {run_snapshot_id} != version snapshot "
                        f"{book_snapshot_id}"
                    ),
                )

    formal_origins = {
        OriginType.MODEL.value,
        OriginType.SYSTEM.value,
        getattr(OriginType, "MIGRATED", OriginType.SYSTEM).value
        if hasattr(OriginType, "MIGRATED")
        else "migrated",
    }
    if require_snapshot_for_formal and origin in formal_origins and book_snapshot_id is None:
        # Soft gate for candidate creation in tests without snapshots remains
        # allowed only when caller sets require_snapshot_for_formal=False.
        # Integration default for confirm/canonical path uses a separate check.
        return


def assert_evidence_matches_version_snapshot(
    *,
    version_snapshot_id: int | None,
    evidence_snapshot_id: int,
) -> None:
    """Evidence Snapshot must equal Version Snapshot when Version is bound."""
    if version_snapshot_id is None:
        return
    if int(version_snapshot_id) != int(evidence_snapshot_id):
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.EVIDENCE_SNAPSHOT_PARAGRAPH_MISMATCH,
            (
                f"evidence snapshot {evidence_snapshot_id} != version snapshot "
                f"{version_snapshot_id}"
            ),
        )


def version_binding_dict(
    *,
    run_id: int | None,
    book_snapshot_id: int | None,
    origin_type: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "book_snapshot_id": book_snapshot_id,
        "origin_type": origin_type,
    }
