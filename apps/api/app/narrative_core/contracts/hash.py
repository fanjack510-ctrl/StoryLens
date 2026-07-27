"""Content hash Protocol (Agent A implements; pure helpers already in hash_canon)."""

from __future__ import annotations

from typing import Protocol, Sequence

from app.narrative_core.hash_canon import BookHashChapterInput


class ContentHashService(Protocol):
    def canonicalize_text(self, text: str) -> str:
        ...

    def calculate_text_hash(self, text: str) -> str:
        ...

    def calculate_book_content_hash(
        self,
        chapters: Sequence[BookHashChapterInput],
    ) -> str:
        """Aggregate ordered chapter records into a book content hash.

        Each chapter contributes order, title length, title, and content_hash
        with explicit record boundaries. Sorted by chapter_order.
        """

    def backfill_content_hashes(self, book_id: int | None = None) -> dict:
        """Persist paragraph/chapter hashes. Returns summary counts. Not Phase 1P."""
