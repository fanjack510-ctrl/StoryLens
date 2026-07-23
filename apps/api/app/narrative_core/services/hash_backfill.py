"""Content hash backfill and book aggregate hashing (Agent A).

Uses Phase 1P frozen ``canonicalize_text`` / ``calculate_text_hash``.
Does not modify live Book/Chapter/Paragraph text — only ``content_hash`` columns.
"""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Book, Chapter, Paragraph
from app.narrative_core.hash_canon import calculate_text_hash, canonicalize_text


def build_chapter_content_text(paragraphs: Sequence[Paragraph]) -> str:
    """Stable chapter body: normalized paragraphs joined by LF."""
    ordered = sorted(paragraphs, key=lambda item: item.paragraph_index)
    return "\n".join(item.normalized_text or "" for item in ordered)


def encode_chapter_aggregate_record(order: int, title: str, content_hash: str) -> str:
    """Length-prefixed chapter record to avoid cross-boundary hash ambiguity.

    Format: ``{order}:{title_len}:{title}:{content_hash}``
    """
    title_c = canonicalize_text(title or "")
    return f"{order}:{len(title_c)}:{title_c}:{content_hash}"


class ContentHashServiceImpl:
    """Implements ``ContentHashService`` Protocol plus book aggregate helper."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def canonicalize_text(self, text: str) -> str:
        return canonicalize_text(text)

    def calculate_text_hash(self, text: str) -> str:
        return calculate_text_hash(text)

    def calculate_book_content_hash(self, chapter_hashes: Sequence[str]) -> str:
        """Protocol method: aggregate ordered chapter content hashes with boundaries.

        Each hash is length-prefixed so ``["ab","c"]`` ≠ ``["a","bc"]``.
        """
        lines = [f"{len(item)}:{item}" for item in chapter_hashes]
        return calculate_text_hash("\n".join(lines))

    def calculate_book_aggregate_hash(
        self,
        chapters: Sequence[tuple[int, str, str]],
    ) -> str:
        """Book content hash from stable (order, title, content_hash) records.

        Required by Phase 1A snapshot rules. Protocol ``calculate_book_content_hash``
        only accepts hash strings; this richer form is the snapshot source of truth.
        """
        ordered = sorted(chapters, key=lambda item: item[0])
        lines = [
            encode_chapter_aggregate_record(order, title, content_hash)
            for order, title, content_hash in ordered
        ]
        return calculate_text_hash("\n".join(lines))

    def backfill_content_hashes(self, book_id: int | None = None) -> dict:
        """Persist paragraph/chapter content_hash values. Idempotent for unchanged text.

        Returns summary counts. Does not rewrite paragraph/chapter body text.
        """
        query = select(Chapter).options(selectinload(Chapter.paragraphs))
        if book_id is not None:
            query = query.where(Chapter.book_id == book_id)
        query = query.order_by(Chapter.book_id, Chapter.chapter_index)
        chapters = list(self._session.scalars(query))

        paragraph_updated = 0
        paragraph_unchanged = 0
        chapter_updated = 0
        chapter_unchanged = 0

        for chapter in chapters:
            paragraphs = sorted(chapter.paragraphs, key=lambda item: item.paragraph_index)
            for paragraph in paragraphs:
                digest = calculate_text_hash(paragraph.normalized_text or "")
                if paragraph.content_hash == digest:
                    paragraph_unchanged += 1
                else:
                    paragraph.content_hash = digest
                    paragraph_updated += 1

            content_text = build_chapter_content_text(paragraphs)
            chapter_digest = calculate_text_hash(content_text)
            if chapter.content_hash == chapter_digest:
                chapter_unchanged += 1
            else:
                chapter.content_hash = chapter_digest
                chapter_updated += 1

        self._session.flush()
        return {
            "chapters_scanned": len(chapters),
            "paragraph_updated": paragraph_updated,
            "paragraph_unchanged": paragraph_unchanged,
            "chapter_updated": chapter_updated,
            "chapter_unchanged": chapter_unchanged,
        }

    def compute_book_content_hash(self, book_id: int) -> str:
        """Ensure hashes are current, then return book aggregate content hash."""
        book = self._session.get(Book, book_id)
        if book is None:
            raise ValueError(f"book not found: {book_id}")
        self.backfill_content_hashes(book_id=book_id)
        chapters = list(
            self._session.scalars(
                select(Chapter)
                .where(Chapter.book_id == book_id)
                .order_by(Chapter.chapter_index)
            )
        )
        records: list[tuple[int, str, str]] = []
        for chapter in chapters:
            digest = chapter.content_hash
            if not digest:
                content_text = build_chapter_content_text(chapter.paragraphs)
                digest = calculate_text_hash(content_text)
                chapter.content_hash = digest
            title = chapter.display_title or chapter.title or ""
            records.append((chapter.chapter_index, title, digest))
        return self.calculate_book_aggregate_hash(records)

    def refresh_hashes_after_import_or_reparse(self, book_id: int) -> dict:
        """Public hook for import/reparse paths to refresh persisted hashes."""
        summary = self.backfill_content_hashes(book_id=book_id)
        summary["book_content_hash"] = self.compute_book_content_hash(book_id)
        return summary
