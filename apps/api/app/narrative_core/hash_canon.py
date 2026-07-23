"""Canonical text hashing for narrative content (Phase 1P / Phase 1A).

Rules (frozen for body text):
- Normalize CRLF and CR to LF only.
- Do not strip semantically meaningful whitespace.
- Do not apply Unicode NFC/NFKC (CJK presentation must remain byte-stable
  relative to stored DB text after newline normalization only).
- Do not use Python's built-in hash().
- Digest algorithm: SHA-256, lowercase hex.

Book content hash (Phase 1A unified contract):
- Single public entry: ``calculate_book_content_hash(chapters)``.
- Input includes chapter_order, title length, title, and chapter content_hash.
- Records are length/order bounded to avoid concatenation ambiguity.
- Sorted by chapter_order for stability.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Sequence


def canonicalize_text(text: str) -> str:
    """Return platform-stable text for hashing."""
    if text is None:
        raise TypeError("text must be str, not None")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def calculate_text_hash(text: str) -> str:
    """SHA-256 hex digest of canonicalize_text(text) encoded as UTF-8."""
    canonical = canonicalize_text(text)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class BookHashChapterInput:
    """One chapter contribution to the book aggregate content hash."""

    chapter_order: int
    title: str
    content_hash: str


def encode_book_hash_chapter_record(chapter: BookHashChapterInput) -> str:
    """Length-prefixed chapter record to avoid cross-boundary hash ambiguity.

    Format: ``{order}:{title_len}:{title}:{content_hash}``
    """
    title_c = canonicalize_text(chapter.title or "")
    return f"{chapter.chapter_order}:{len(title_c)}:{title_c}:{chapter.content_hash}"


def calculate_book_content_hash(chapters: Sequence[BookHashChapterInput]) -> str:
    """Sole public book-level content hash entry.

    Title changes, chapter order changes, and chapter body hash changes
    all alter the digest. Input is sorted by ``chapter_order``.
    """
    ordered = sorted(chapters, key=lambda item: item.chapter_order)
    lines = [encode_book_hash_chapter_record(item) for item in ordered]
    return calculate_text_hash("\n".join(lines))
