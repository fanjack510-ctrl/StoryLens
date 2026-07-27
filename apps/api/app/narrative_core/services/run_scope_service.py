"""AnalysisRun scope creation and validation (Agent B).

Consumes SnapshotValidationGateway for book-scope checks only.
Does not implement snapshot SQL or a second snapshot service.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, Book, BookSnapshot, Chapter, utc_now
from app.narrative_core.contracts.snapshot import SnapshotValidationGateway
from app.narrative_core.enums import AnalysisScopeType, AnalysisType, SnapshotStatus
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode


def _as_scope(value: AnalysisScopeType | str | None) -> AnalysisScopeType | None:
    if value is None:
        return None
    return AnalysisScopeType(value)


def _as_analysis_type(value: AnalysisType | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, AnalysisType):
        return value.value
    # Accept known enum values; allow legacy free-form strings without inventing new enums.
    try:
        return AnalysisType(value).value
    except ValueError:
        return str(value)


class RunScopeService:
    """Create / validate / bind AnalysisRun scope fields."""

    def __init__(
        self,
        session: Session,
        *,
        snapshot_gateway: SnapshotValidationGateway | None = None,
    ) -> None:
        self._session = session
        self._snapshot_gateway = snapshot_gateway

    def create_scoped_run(
        self,
        *,
        scope_type: AnalysisScopeType | str,
        analysis_type: AnalysisType | str,
        book_id: int | None = None,
        start_chapter_id: int | None = None,
        end_chapter_id: int | None = None,
        book_snapshot_id: int | None = None,
        **fields: Any,
    ) -> AnalysisRun:
        """Create a scoped run. Book scope creates a simulated run only (no model calls)."""
        scope = AnalysisScopeType(scope_type)
        analysis_type_value = _as_analysis_type(analysis_type)
        if analysis_type_value is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.INVALID_RUN_SCOPE,
                "analysis_type is required for scoped runs",
            )

        subject_type = str(fields.pop("subject_type", "") or "")
        subject_id = str(fields.pop("subject_id", "") or "")

        if scope == AnalysisScopeType.CHAPTER:
            chapter_id = fields.pop("chapter_id", None)
            if chapter_id is not None:
                # Compatibility: bind via subject_type/subject_id — never invent a chapter_id column.
                subject_type = subject_type or "chapter"
                subject_id = subject_id or str(int(chapter_id))
                if book_id is None:
                    chapter = self._session.get(Chapter, int(chapter_id))
                    if chapter is not None:
                        book_id = chapter.book_id
            if not subject_type:
                subject_type = "chapter"
            if start_chapter_id is not None or end_chapter_id is not None:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.INVALID_RUN_SCOPE,
                    "chapter scope must not set start_chapter_id/end_chapter_id",
                )
        elif scope == AnalysisScopeType.CHAPTER_RANGE:
            subject_type = subject_type or "chapter_range"
            subject_id = subject_id or (str(book_id) if book_id is not None else "")
        elif scope == AnalysisScopeType.BOOK:
            subject_type = subject_type or "book"
            subject_id = subject_id or (str(book_id) if book_id is not None else "")
            # Simulated book-scope run only — do not execute analysis.
            fields.setdefault("status", "queued")
            fields.setdefault("task_type", "whole_book_simulated")

        provider = str(fields.pop("provider", "local"))
        model = str(fields.pop("model", "narrative-phase1a-stub"))
        prompt_version = str(fields.pop("prompt_version", "phase1a-scope-v1"))
        schema_version = str(fields.pop("schema_version", "phase1a-scope-v1"))
        input_hash = str(fields.pop("input_hash", "0" * 64))
        status = str(fields.pop("status", "queued"))
        task_type = str(fields.pop("task_type", "scene_pipeline"))
        configuration_fingerprint = fields.pop("configuration_fingerprint", None)

        run = AnalysisRun(
            task_type=task_type,
            subject_type=subject_type,
            subject_id=subject_id,
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            schema_version=schema_version,
            input_hash=input_hash,
            status=status,
            analysis_type=analysis_type_value,
            scope_type=scope.value,
            book_id=book_id,
            start_chapter_id=start_chapter_id,
            end_chapter_id=end_chapter_id,
            book_snapshot_id=book_snapshot_id,
            configuration_fingerprint=configuration_fingerprint,
            **fields,
        )
        self.validate_run_scope(run)
        if scope == AnalysisScopeType.BOOK and book_snapshot_id is not None:
            # Re-validate bind path through gateway (validate_run_scope already checks).
            self._require_gateway().validate_snapshot_for_book(book_snapshot_id, int(book_id))

        self._session.add(run)
        self._session.flush()
        return run

    def validate_run_scope(self, run: Any) -> None:
        """Validate scope fields. Legacy NULL scope_type + chapter subject remains readable."""
        scope = _as_scope(getattr(run, "scope_type", None))
        if scope is None:
            # Legacy 1.0.5 rows: subject_type/subject_id only — no chapter_id column.
            subject_type = getattr(run, "subject_type", None)
            if subject_type in (None, "", "chapter"):
                return
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.INVALID_RUN_SCOPE,
                f"legacy run with unknown subject_type={subject_type!r} and null scope_type",
            )

        book_id = getattr(run, "book_id", None)
        start_id = getattr(run, "start_chapter_id", None)
        end_id = getattr(run, "end_chapter_id", None)
        snapshot_id = getattr(run, "book_snapshot_id", None)

        if scope == AnalysisScopeType.CHAPTER:
            if start_id is not None or end_id is not None:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.INVALID_RUN_SCOPE,
                    "chapter scope cannot include chapter range bounds",
                )
            # Snapshot not required for chapter scope.
            return

        if scope == AnalysisScopeType.CHAPTER_RANGE:
            if book_id is None or start_id is None or end_id is None:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.RANGE_SCOPE_REQUIRES_BOUNDS,
                    "chapter_range requires book_id, start_chapter_id, and end_chapter_id",
                )
            start = self._session.get(Chapter, int(start_id))
            end = self._session.get(Chapter, int(end_id))
            if start is None or end is None:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.RANGE_SCOPE_REQUIRES_BOUNDS,
                    "chapter_range bounds must reference existing chapters",
                )
            if start.book_id != end.book_id:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.INVALID_RUN_SCOPE,
                    "chapter_range start/end chapters must belong to the same book",
                )
            if int(start.book_id) != int(book_id):
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.INVALID_RUN_SCOPE,
                    "chapter_range chapters must belong to run.book_id",
                )
            if int(start.chapter_index) > int(end.chapter_index):
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.RANGE_SCOPE_INVALID_ORDER,
                    "start chapter order must not exceed end chapter order",
                )
            return

        if scope == AnalysisScopeType.BOOK:
            if book_id is None:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.INVALID_RUN_SCOPE,
                    "book scope requires book_id",
                )
            if self._session.get(Book, int(book_id)) is None:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.INVALID_RUN_SCOPE,
                    f"book_id={book_id} does not exist",
                )
            if snapshot_id is None:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.BOOK_SCOPE_REQUIRES_SNAPSHOT,
                    "book scope requires a completed book_snapshot_id",
                )
            gateway = self._require_gateway()
            gateway.get_completed_snapshot(int(snapshot_id))
            if not gateway.validate_snapshot_for_book(int(snapshot_id), int(book_id)):
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.SNAPSHOT_BOOK_MISMATCH,
                    f"snapshot {snapshot_id} does not belong to book {book_id}",
                )
            return

        raise NarrativeCoreError(
            NarrativeCoreErrorCode.INVALID_RUN_SCOPE,
            f"unsupported scope_type={scope!r}",
        )

    def bind_run_snapshot(self, run_id: int, book_snapshot_id: int) -> AnalysisRun:
        """Bind a COMPLETED snapshot to a book-scoped run via SnapshotValidationGateway."""
        run = self._session.get(AnalysisRun, run_id)
        if run is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.INVALID_RUN_SCOPE,
                f"run_id={run_id} not found",
            )
        scope = _as_scope(run.scope_type)
        if scope != AnalysisScopeType.BOOK:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.INVALID_RUN_SCOPE,
                "bind_run_snapshot is only valid for book scope",
            )
        if run.book_id is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.INVALID_RUN_SCOPE,
                "book scope run missing book_id",
            )

        gateway = self._require_gateway()
        gateway.get_completed_snapshot(int(book_snapshot_id))
        if not gateway.validate_snapshot_for_book(int(book_snapshot_id), int(run.book_id)):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.SNAPSHOT_BOOK_MISMATCH,
                f"snapshot {book_snapshot_id} does not belong to book {run.book_id}",
            )

        run.book_snapshot_id = int(book_snapshot_id)
        self.validate_run_scope(run)
        self._session.flush()
        return run

    def _require_gateway(self) -> SnapshotValidationGateway:
        if self._snapshot_gateway is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.BOOK_SCOPE_REQUIRES_SNAPSHOT,
                "SnapshotValidationGateway is required for book-scope snapshot operations",
            )
        return self._snapshot_gateway


class StubSnapshotValidationGateway:
    """Test-only gateway stub. Production must use SnapshotValidationGatewayImpl.

    Reads BookSnapshot rows only; does not build snapshots or fork snapshot business logic.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_completed_snapshot(self, snapshot_id: int) -> BookSnapshot:
        snapshot = self._session.get(BookSnapshot, snapshot_id)
        if snapshot is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.SNAPSHOT_NOT_FOUND,
                f"snapshot_id={snapshot_id} not found",
            )
        status = SnapshotStatus(snapshot.snapshot_status)
        if status != SnapshotStatus.COMPLETED:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.SNAPSHOT_NOT_COMPLETED,
                f"snapshot_id={snapshot_id} status={snapshot.snapshot_status}",
            )
        return snapshot

    def validate_snapshot_for_book(self, snapshot_id: int, book_id: int) -> bool:
        snapshot = self.get_completed_snapshot(snapshot_id)
        if int(snapshot.book_id) != int(book_id):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.SNAPSHOT_BOOK_MISMATCH,
                f"snapshot book_id={snapshot.book_id} != book_id={book_id}",
            )
        return True


def make_stub_completed_snapshot(
    session: Session,
    *,
    book_id: int,
    content_hash: str = "a" * 64,
    snapshot_status: str = SnapshotStatus.COMPLETED.value,
) -> BookSnapshot:
    """Test helper: insert a BookSnapshot row without Agent A builder."""
    snapshot = BookSnapshot(
        book_id=book_id,
        content_hash=content_hash,
        chapter_count=0,
        paragraph_count=0,
        character_count=0,
        snapshot_status=snapshot_status,
        source_fingerprint="",
        created_at=utc_now(),
    )
    session.add(snapshot)
    session.flush()
    return snapshot
