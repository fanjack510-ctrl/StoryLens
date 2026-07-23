"""Content hash Protocol (Agent A implements; pure helpers already in hash_canon)."""

from __future__ import annotations

from typing import Protocol, Sequence


class ContentHashService(Protocol):
    def canonicalize_text(self, text: str) -> str:
        ...

    def calculate_text_hash(self, text: str) -> str:
        ...

    def calculate_book_content_hash(
        self,
        chapter_hashes: Sequence[str],
    ) -> str:
        """Aggregate ordered chapter content hashes into a book content hash."""

    def backfill_content_hashes(self, book_id: int | None = None) -> dict:
        """Persist paragraph/chapter hashes. Returns summary counts. Not Phase 1P."""
