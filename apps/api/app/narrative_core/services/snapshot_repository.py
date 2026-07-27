"""Book snapshot repository (Agent A).

Persistence helpers only; business rules live in ``snapshot_service``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import BookSnapshot, BookSnapshotChapter, BookSnapshotParagraph
from app.db.models import utc_now
from app.narrative_core.enums import SnapshotStatus


def _sanitize_error_message(message: str | None, *, max_len: int = 500) -> str | None:
    """Store a short diagnostic message — never full user body text."""
    if message is None:
        return None
    text = str(message).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return None
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


class BookSnapshotRepositoryImpl:
    """Implements ``BookSnapshotRepository`` Protocol."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_snapshot_record(
        self, book_id: int, content_hash: str, **fields: Any
    ) -> BookSnapshot:
        snapshot = BookSnapshot(
            book_id=book_id,
            content_hash=content_hash,
            chapter_count=int(fields.get("chapter_count", 0)),
            paragraph_count=int(fields.get("paragraph_count", 0)),
            character_count=int(fields.get("character_count", 0)),
            snapshot_status=str(fields.get("snapshot_status", SnapshotStatus.BUILDING)),
            source_fingerprint=str(fields.get("source_fingerprint", "")),
            error_code=fields.get("error_code"),
            error_message=_sanitize_error_message(fields.get("error_message")),
            created_at=fields.get("created_at") or utc_now(),
        )
        self._session.add(snapshot)
        self._session.flush()
        return snapshot

    def add_snapshot_chapter(self, snapshot_id: int, **fields: Any) -> BookSnapshotChapter:
        chapter = BookSnapshotChapter(
            snapshot_id=snapshot_id,
            source_chapter_id=fields.get("source_chapter_id"),
            chapter_order=int(fields["chapter_order"]),
            title=str(fields.get("title", "")),
            content_hash=str(fields["content_hash"]),
            content_text=str(fields.get("content_text", "")),
        )
        self._session.add(chapter)
        self._session.flush()
        return chapter

    def add_snapshot_paragraph(
        self, snapshot_id: int, snapshot_chapter_id: int, **fields: Any
    ) -> BookSnapshotParagraph:
        paragraph = BookSnapshotParagraph(
            snapshot_id=snapshot_id,
            snapshot_chapter_id=snapshot_chapter_id,
            source_paragraph_id=fields.get("source_paragraph_id"),
            stable_paragraph_id=str(fields["stable_paragraph_id"]),
            paragraph_order=int(fields["paragraph_order"]),
            start_offset=int(fields.get("start_offset", 0)),
            end_offset=int(fields.get("end_offset", 0)),
            content_hash=str(fields["content_hash"]),
        )
        self._session.add(paragraph)
        self._session.flush()
        return paragraph

    def get_snapshot(self, snapshot_id: int) -> BookSnapshot | None:
        return self._session.scalar(
            select(BookSnapshot)
            .where(BookSnapshot.id == snapshot_id)
            .options(
                selectinload(BookSnapshot.chapters).selectinload(
                    BookSnapshotChapter.paragraphs
                )
            )
            .execution_options(populate_existing=True)
        )

    def find_completed_snapshot(
        self, book_id: int, content_hash: str
    ) -> BookSnapshot | None:
        return self._session.scalar(
            select(BookSnapshot)
            .where(
                BookSnapshot.book_id == book_id,
                BookSnapshot.content_hash == content_hash,
                BookSnapshot.snapshot_status == SnapshotStatus.COMPLETED,
            )
            .options(
                selectinload(BookSnapshot.chapters).selectinload(
                    BookSnapshotChapter.paragraphs
                )
            )
            .execution_options(populate_existing=True)
        )

    def find_by_book_and_hash(
        self, book_id: int, content_hash: str
    ) -> BookSnapshot | None:
        return self._session.scalar(
            select(BookSnapshot)
            .where(
                BookSnapshot.book_id == book_id,
                BookSnapshot.content_hash == content_hash,
            )
            .options(
                selectinload(BookSnapshot.chapters).selectinload(
                    BookSnapshotChapter.paragraphs
                )
            )
            .execution_options(populate_existing=True)
        )

    def validate_completed_snapshot(self, snapshot_id: int) -> bool:
        snapshot = self.get_snapshot(snapshot_id)
        if snapshot is None:
            return False
        if snapshot.snapshot_status != SnapshotStatus.COMPLETED:
            return False
        return True

    def mark_snapshot_completed(self, snapshot_id: int) -> BookSnapshot:
        snapshot = self.get_snapshot(snapshot_id)
        if snapshot is None:
            raise ValueError(f"snapshot not found: {snapshot_id}")
        snapshot.snapshot_status = SnapshotStatus.COMPLETED
        snapshot.error_code = None
        snapshot.error_message = None
        self._session.flush()
        return snapshot

    def mark_snapshot_failed(
        self,
        snapshot_id: int,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> BookSnapshot:
        snapshot = self.get_snapshot(snapshot_id)
        if snapshot is None:
            raise ValueError(f"snapshot not found: {snapshot_id}")
        snapshot.snapshot_status = SnapshotStatus.FAILED
        if error_code:
            snapshot.error_code = str(error_code)[:100]
        if error_message is not None:
            snapshot.error_message = _sanitize_error_message(error_message)
        elif error_code and not snapshot.error_message:
            snapshot.error_message = _sanitize_error_message(str(error_code))
        # source_fingerprint remains the source fingerprint only.
        self._session.flush()
        return snapshot

    def mark_snapshot_invalid(
        self,
        snapshot_id: int,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> BookSnapshot:
        snapshot = self.get_snapshot(snapshot_id)
        if snapshot is None:
            raise ValueError(f"snapshot not found: {snapshot_id}")
        snapshot.snapshot_status = SnapshotStatus.INVALID
        if error_code:
            snapshot.error_code = str(error_code)[:100]
        if error_message is not None:
            snapshot.error_message = _sanitize_error_message(error_message)
        self._session.flush()
        return snapshot

    def clear_snapshot_errors(self, snapshot_id: int) -> BookSnapshot:
        snapshot = self.get_snapshot(snapshot_id)
        if snapshot is None:
            raise ValueError(f"snapshot not found: {snapshot_id}")
        snapshot.error_code = None
        snapshot.error_message = None
        self._session.flush()
        return snapshot

    def delete_snapshot(self, snapshot_id: int) -> None:
        snapshot = self._session.get(BookSnapshot, snapshot_id)
        if snapshot is not None:
            self._session.delete(snapshot)
            self._session.flush()
