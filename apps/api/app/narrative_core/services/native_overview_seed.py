"""Seed walking-skeleton short book from packages/contracts fixtures."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import Book, Chapter, Paragraph
from app.narrative_core.hash_canon import calculate_text_hash

_SHORT_BOOK_REL = Path("packages") / "contracts" / "fixtures" / "walking_skeleton" / "short_book_v1.json"


def short_book_fixture_path() -> Path:
    # apps/api/app/narrative_core/services → repo root is parents[5]
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / _SHORT_BOOK_REL
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"short_book_v1.json not found from {here}")


def load_short_book_fixture() -> dict:
    return json.loads(short_book_fixture_path().read_text(encoding="utf-8"))


def seed_short_book_v1(session: Session) -> Book:
    """Insert the 2-chapter × 2-paragraph walking-skeleton book. Commits caller-side."""

    payload = load_short_book_fixture()
    book_meta = payload["book"]
    chapters_payload = payload["chapters"]

    all_text = "\n".join(
        p for ch in chapters_payload for p in ch.get("paragraphs", [])
    )
    content_hash = calculate_text_hash(all_text)

    book = Book(
        title=str(book_meta.get("title") or "行走骨架短篇"),
        source_file_name="short_book_v1.json",
        source_file_hash=content_hash,
        import_status="ready",
    )
    session.add(book)
    session.flush()

    global_para_index = 0
    for chapter_index, ch in enumerate(chapters_payload, start=1):
        title = str(ch.get("title") or f"第{chapter_index}章")
        chapter = Chapter(
            book_id=book.id,
            chapter_index=chapter_index,
            title=title,
            chapter_title=title,
            display_title=title,
            section_type="chapter",
        )
        session.add(chapter)
        session.flush()

        offset = 0
        for para_index, raw in enumerate(ch.get("paragraphs") or [], start=1):
            text = str(raw)
            global_para_index += 1
            para_id = f"B{book.id:04d}-C{chapter_index:04d}-P{para_index:04d}"
            paragraph = Paragraph(
                id=para_id,
                book_id=book.id,
                chapter_id=chapter.id,
                paragraph_index=para_index,
                raw_text=text,
                normalized_text=text,
                char_start=offset,
                char_end=offset + len(text),
            )
            session.add(paragraph)
            offset += len(text) + 1

    session.flush()
    return book
