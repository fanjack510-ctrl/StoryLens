"""Book snapshot service and Agent B validation gateway (Agent A).

Transaction rules:
- Snapshot creation runs in a DB transaction.
- BUILDING snapshots are not usable by runs.
- COMPLETED only after chapters, paragraphs, and integrity checks succeed.
- Same book_id + content_hash COMPLETED rows are reused (unique constraint + IntegrityError).
- Does not mutate live Book/Chapter/Paragraph body text or delete source files.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select

from app.db.models import (
    Book,
    BookSnapshot,
    BookSnapshotChapter,
    BookSnapshotParagraph,
    Chapter,
)
from app.narrative_core.enums import SnapshotStatus
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.hash_canon import BookHashChapterInput, calculate_text_hash
from app.narrative_core.services.hash_backfill import (
    ContentHashServiceImpl,
    build_chapter_content_text,
)
from app.narrative_core.services.snapshot_repository import BookSnapshotRepositoryImpl


#: One lock per book, so two requests for the same book queue instead of colliding. The
#: sidecar is a single process, so a threading lock is the whole scope of the problem.
_BUILD_LOCKS: dict[int, threading.Lock] = {}
_BUILD_LOCKS_GUARD = threading.Lock()


def _book_build_lock(book_id: int) -> threading.Lock:
    with _BUILD_LOCKS_GUARD:
        lock = _BUILD_LOCKS.get(int(book_id))
        if lock is None:
            lock = threading.Lock()
            _BUILD_LOCKS[int(book_id)] = lock
        return lock


class BookSnapshotServiceImpl:
    """Implements ``BookSnapshotService`` and ``SnapshotValidationGateway``."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = BookSnapshotRepositoryImpl(session)
        self._hashes = ContentHashServiceImpl(session)

    def create_or_reuse_snapshot(self, book_id: int) -> BookSnapshot:
        with _book_build_lock(book_id):
            return self._create_or_reuse_snapshot_locked(book_id)

    def _create_or_reuse_snapshot_locked(self, book_id: int) -> BookSnapshot:
        book = self._session.get(Book, book_id)
        if book is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.SNAPSHOT_NOT_FOUND,
                f"book not found: {book_id}",
            )

        content_hash = self._hashes.compute_book_content_hash(book_id)
        existing = self._repo.find_completed_snapshot(book_id, content_hash)
        if existing is not None:
            return existing

        prior = self._repo.find_by_book_and_hash(book_id, content_hash)
        if prior is not None:
            if prior.snapshot_status == SnapshotStatus.COMPLETED:
                return prior
            if prior.snapshot_status == SnapshotStatus.BUILDING:
                waited = self._wait_for_terminal(prior.id, timeout_s=5.0)
                if waited is not None and waited.snapshot_status == SnapshotStatus.COMPLETED:
                    return waited
                # Stale BUILDING — reset and rebuild in place.
                self._clear_snapshot_children(prior)
                return self._build_into_snapshot(prior, book_id, content_hash)
            # FAILED / INVALID — rebuild in place under same unique key.
            self._clear_snapshot_children(prior)
            prior.snapshot_status = SnapshotStatus.BUILDING
            prior.chapter_count = 0
            prior.paragraph_count = 0
            prior.character_count = 0
            prior.source_fingerprint = book.source_file_hash or ""
            prior.error_code = None
            prior.error_message = None
            self._session.flush()
            return self._build_into_snapshot(prior, book_id, content_hash)

        try:
            # Savepoint so unique-constraint races do not abort the outer transaction.
            with self._session.begin_nested():
                snapshot = self._repo.create_snapshot_record(
                    book_id,
                    content_hash,
                    snapshot_status=SnapshotStatus.BUILDING,
                    source_fingerprint=book.source_file_hash or "",
                )
        except IntegrityError:
            # Unique (book_id, content_hash) lost the race — reuse winner.
            winner = self._repo.find_by_book_and_hash(book_id, content_hash)
            if winner is None:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.SNAPSHOT_INTEGRITY_FAILED,
                    "unique conflict but snapshot row missing",
                )
            if winner.snapshot_status == SnapshotStatus.COMPLETED:
                return winner
            if winner.snapshot_status == SnapshotStatus.BUILDING:
                waited = self._wait_for_terminal(winner.id, timeout_s=5.0)
                if waited is not None and waited.snapshot_status == SnapshotStatus.COMPLETED:
                    return waited
            # Rebuild failed/stale row.
            self._clear_snapshot_children(winner)
            winner.snapshot_status = SnapshotStatus.BUILDING
            winner.source_fingerprint = book.source_file_hash or ""
            winner.error_code = None
            winner.error_message = None
            self._session.flush()
            return self._build_into_snapshot(winner, book_id, content_hash)

        return self._build_into_snapshot(snapshot, book_id, content_hash)

    def _wait_for_terminal(
        self, snapshot_id: int, *, timeout_s: float
    ) -> BookSnapshot | None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            self._session.expire_all()
            row = self._repo.get_snapshot(snapshot_id)
            if row is None:
                return None
            if row.snapshot_status != SnapshotStatus.BUILDING:
                return row
            time.sleep(0.05)
        return self._repo.get_snapshot(snapshot_id)

    def _clear_snapshot_children(self, snapshot: BookSnapshot) -> None:
        for chapter in list(snapshot.chapters):
            self._session.delete(chapter)
        self._session.flush()
        snapshot.chapters.clear()
        self._session.expire(snapshot, ["chapters"])

    def _build_into_snapshot(
        self, snapshot: BookSnapshot, book_id: int, content_hash: str
    ) -> BookSnapshot:
        try:
            chapters = list(
                self._session.scalars(
                    select(Chapter)
                    .where(Chapter.book_id == book_id)
                    .options(selectinload(Chapter.paragraphs))
                    .order_by(Chapter.chapter_index)
                )
            )
            paragraph_total = 0
            character_total = 0

            for chapter in chapters:
                paragraphs = sorted(
                    chapter.paragraphs, key=lambda item: item.paragraph_index
                )
                content_text = build_chapter_content_text(paragraphs)
                chapter_hash = chapter.content_hash or calculate_text_hash(content_text)
                title = chapter.display_title or chapter.title or ""
                snap_chapter = self._repo.add_snapshot_chapter(
                    snapshot.id,
                    source_chapter_id=chapter.id,
                    chapter_order=chapter.chapter_index,
                    title=title,
                    content_hash=chapter_hash,
                    content_text=content_text,
                )
                character_total += len(content_text)
                offset = 0
                for order, paragraph in enumerate(paragraphs, start=1):
                    text = paragraph.normalized_text or ""
                    start = offset
                    end = offset + len(text)
                    para_hash = paragraph.content_hash or calculate_text_hash(text)
                    self._repo.add_snapshot_paragraph(
                        snapshot.id,
                        snap_chapter.id,
                        source_paragraph_id=paragraph.id,
                        stable_paragraph_id=paragraph.id,
                        paragraph_order=order,
                        start_offset=start,
                        end_offset=end,
                        content_hash=para_hash,
                    )
                    paragraph_total += 1
                    offset = end + 1  # account for joining LF

            snapshot.chapter_count = len(chapters)
            snapshot.paragraph_count = paragraph_total
            snapshot.character_count = character_total
            snapshot.content_hash = content_hash
            self._session.flush()

            if not self._validate_snapshot_integrity(snapshot.id, mark_invalid=False):
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.SNAPSHOT_INTEGRITY_FAILED,
                    f"snapshot {snapshot.id} failed integrity before complete",
                )

            self._repo.mark_snapshot_completed(snapshot.id)
            self._session.flush()
            completed = self._repo.get_snapshot(snapshot.id)
            assert completed is not None
            return completed
        except Exception as exc:
            code = getattr(exc, "code", None)
            error_code = str(code) if code is not None else type(exc).__name__
            # Never persist full user body text in error fields.
            short_message = str(exc)
            if len(short_message) > 500:
                short_message = short_message[:497] + "..."
            try:
                self._repo.mark_snapshot_failed(
                    snapshot.id,
                    error_code=error_code,
                    error_message=short_message,
                )
                self._session.flush()
            except Exception:
                pass
            if isinstance(exc, NarrativeCoreError):
                raise
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.SNAPSHOT_INTEGRITY_FAILED,
                f"snapshot build failed: {exc}",
            ) from exc

    def validate_snapshot(self, snapshot_id: int) -> bool:
        return self._validate_snapshot_integrity(snapshot_id, mark_invalid=True)

    def _validate_snapshot_integrity(
        self, snapshot_id: int, *, mark_invalid: bool
    ) -> bool:
        snapshot = self._repo.get_snapshot(snapshot_id)
        if snapshot is None:
            return False

        chapters = sorted(snapshot.chapters, key=lambda item: item.chapter_order)
        if snapshot.chapter_count and snapshot.chapter_count != len(chapters):
            return self._fail_integrity(snapshot, mark_invalid)

        paragraph_count = 0
        aggregate_records: list[BookHashChapterInput] = []

        for chapter in chapters:
            paragraphs = sorted(chapter.paragraphs, key=lambda item: item.paragraph_order)
            paragraph_count += len(paragraphs)
            text = chapter.content_text or ""
            if calculate_text_hash(text) != chapter.content_hash:
                return self._fail_integrity(snapshot, mark_invalid)
            aggregate_records.append(
                BookHashChapterInput(
                    chapter_order=chapter.chapter_order,
                    title=chapter.title or "",
                    content_hash=chapter.content_hash,
                )
            )

            for paragraph in paragraphs:
                start = paragraph.start_offset
                end = paragraph.end_offset
                if start < 0 or end < start or end > len(text):
                    return self._fail_integrity(snapshot, mark_invalid)
                restored = text[start:end]
                if calculate_text_hash(restored) != paragraph.content_hash:
                    return self._fail_integrity(snapshot, mark_invalid)

        if snapshot.paragraph_count and snapshot.paragraph_count != paragraph_count:
            return self._fail_integrity(snapshot, mark_invalid)

        expected_hash = self._hashes.calculate_book_content_hash(aggregate_records)
        if expected_hash != snapshot.content_hash:
            return self._fail_integrity(snapshot, mark_invalid)

        return True

    def _fail_integrity(self, snapshot: BookSnapshot, mark_invalid: bool) -> bool:
        if mark_invalid and snapshot.snapshot_status == SnapshotStatus.COMPLETED:
            snapshot.snapshot_status = SnapshotStatus.INVALID
            snapshot.error_code = NarrativeCoreErrorCode.SNAPSHOT_INTEGRITY_FAILED.value
            snapshot.error_message = "snapshot integrity validation failed"
            self._session.flush()
        return False

    def get_snapshot_paragraph_text(self, snapshot_paragraph_id: int) -> str:
        paragraph = self._session.get(BookSnapshotParagraph, snapshot_paragraph_id)
        if paragraph is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.SNAPSHOT_NOT_FOUND,
                f"snapshot paragraph not found: {snapshot_paragraph_id}",
            )
        chapter = self._session.get(BookSnapshotChapter, paragraph.snapshot_chapter_id)
        if chapter is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.SNAPSHOT_INTEGRITY_FAILED,
                f"snapshot chapter missing for paragraph {snapshot_paragraph_id}",
            )
        text = chapter.content_text or ""
        start = paragraph.start_offset
        end = paragraph.end_offset
        if start < 0 or end < start or end > len(text):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.SNAPSHOT_INTEGRITY_FAILED,
                f"offset out of range for paragraph {snapshot_paragraph_id}",
            )
        restored = text[start:end]
        if calculate_text_hash(restored) != paragraph.content_hash:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.SNAPSHOT_INTEGRITY_FAILED,
                f"paragraph hash mismatch for {snapshot_paragraph_id}",
            )
        return restored

    def get_completed_snapshot(self, snapshot_id: int) -> BookSnapshot:
        snapshot = self._repo.get_snapshot(snapshot_id)
        if snapshot is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.SNAPSHOT_NOT_FOUND,
                f"snapshot not found: {snapshot_id}",
            )
        if snapshot.snapshot_status != SnapshotStatus.COMPLETED:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.SNAPSHOT_NOT_COMPLETED,
                f"snapshot {snapshot_id} status={snapshot.snapshot_status}",
            )
        if not self._validate_snapshot_integrity(snapshot_id, mark_invalid=True):
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.SNAPSHOT_INTEGRITY_FAILED,
                f"snapshot {snapshot_id} integrity failed",
            )
        refreshed = self._repo.get_snapshot(snapshot_id)
        assert refreshed is not None
        if refreshed.snapshot_status != SnapshotStatus.COMPLETED:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.SNAPSHOT_NOT_COMPLETED,
                f"snapshot {snapshot_id} status={refreshed.snapshot_status}",
            )
        return refreshed

    def validate_snapshot_for_book(self, snapshot_id: int, book_id: int) -> bool:
        snapshot = self.get_completed_snapshot(snapshot_id)
        if snapshot.book_id != book_id:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.SNAPSHOT_BOOK_MISMATCH,
                f"snapshot {snapshot_id} book_id={snapshot.book_id} expected={book_id}",
            )
        return True


# Alias for gateway consumers (Agent B).
SnapshotValidationGatewayImpl = BookSnapshotServiceImpl
