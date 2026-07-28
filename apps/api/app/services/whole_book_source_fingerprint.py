"""Unified whole-book source fingerprint + paragraph segmentation (Wave B).

Shared by Cost Estimate and Book Snapshot — one hash algorithm only.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Book, Chapter, Paragraph
from app.services.transition_batch_planner import conservative_token_estimate

BOOK_REVISION_VERSION = "book_revision_v1"
_BLANK_LINE_SPLIT = re.compile(r"\n\s*\n+")


def normalize_line_endings_v1(text: str) -> str:
    """Only CRLF/CR → LF. No other mutation."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def sha256_utf8(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def segment_snapshot_paragraphs_v1(text: str) -> list[str]:
    """Split chapter text into paragraphs for Snapshot when no live paragraphs exist."""
    normalized = normalize_line_endings_v1(text)
    parts = _BLANK_LINE_SPLIT.split(normalized)
    out: list[str] = []
    for part in parts:
        # Preserve internal text; drop pure-whitespace segments only.
        if part.strip() == "":
            continue
        out.append(part)
    if not out and normalized.strip():
        # Single block without blank-line separators.
        out = [normalized]
    return out


def load_ordered_chapter_texts(session: Session, book_id: int) -> list[dict[str, Any]]:
    """Return chapters in reading order with canonical full chapter text."""
    book = session.get(Book, book_id)
    if book is None:
        raise ValueError(f"book not found: {book_id}")
    chapters = session.scalars(
        select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.chapter_index.asc())
    ).all()
    rows: list[dict[str, Any]] = []
    for ch in chapters:
        paras = session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == ch.id)
            .order_by(Paragraph.paragraph_index.asc())
        ).all()
        if paras:
            texts = [
                normalize_line_endings_v1(p.normalized_text or p.raw_text or "")
                for p in paras
            ]
            # Join with single LF between existing paragraphs (stable chapter body).
            chapter_text = "\n".join(texts)
            paragraph_texts = texts
        else:
            # No paragraph rows — treat empty chapter text.
            chapter_text = ""
            paragraph_texts = []
        rows.append(
            {
                "chapter_id": ch.id,
                "chapter_index": int(ch.chapter_index),
                "title": ch.title or "",
                "text": chapter_text,
                "paragraph_texts": paragraph_texts,
            }
        )
    return rows


def compute_book_revision_hash_v1(session: Session, book_id: int) -> str:
    """Deterministic book revision fingerprint (Cost Estimate + Snapshot shared)."""
    chapters = load_ordered_chapter_texts(session, book_id)
    payload = {
        "version": BOOK_REVISION_VERSION,
        "book_id": book_id,
        "chapters": [
            {
                "chapter_id": row["chapter_id"],
                "chapter_index": row["chapter_index"],
                "title": row["title"],
                "text_sha256": sha256_utf8(row["text"]),
            }
            for row in chapters
        ],
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def estimate_paragraph_tokens_v1(text: str) -> int:
    """Same estimator family as Wave A cost estimate (conservative_token_estimate)."""
    return int(conservative_token_estimate(text))
