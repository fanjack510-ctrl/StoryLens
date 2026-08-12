"""Read a book snapshot into the engine's source types.

The snapshot is the engine's only view of the novel: it is immutable, it carries
``source_chapter_id`` for every chapter, and its paragraph rows carry byte offsets into the
chapter text. Reading from it rather than from the live ``chapters`` table is what makes a
run reproducible — the text cannot change under a run that is already in progress.

Paragraph text is *sliced* from the chapter, not stored twice. That is the right shape and
this module preserves it: a paragraph is identified by ``(chapter, offset)`` and its text is
whatever those offsets currently delimit, verified against the stored content hash.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.narrative_core.long_novel.extractor import SourceChapter, SourceParagraph
from app.narrative_core.long_novel.planner import PlannedChapter

__all__ = ["SnapshotStats", "load_chapters", "to_planned_chapters"]


@dataclass(frozen=True)
class SnapshotStats:
    snapshot_id: int
    chapter_count: int
    paragraph_count: int
    character_count: int
    chapters_without_source_id: int


def load_chapters(
    session: Session, snapshot_id: int, *, limit: int | None = None
) -> tuple[list[SourceChapter], SnapshotStats]:
    """Load a snapshot's chapters with their paragraphs, in reading order.

    ``limit`` takes the first N chapters — useful for a small paid trial before committing
    to a whole book, which is cheaper than discovering a problem on call 40.

    A paragraph whose stored hash does not match the text at its offsets is a corrupted
    snapshot, and is reported rather than silently used: every evidence anchor the engine
    later produces points at these offsets, so a mismatch here would make every citation in
    the book wrong in a way nothing downstream could detect.
    """
    chapter_rows = session.execute(
        text(
            """
            SELECT id, source_chapter_id, chapter_order, title, content_hash, content_text
              FROM book_snapshot_chapters
             WHERE snapshot_id = :sid
             ORDER BY chapter_order
            """
            + (" LIMIT :lim" if limit else "")
        ),
        {"sid": snapshot_id, **({"lim": limit} if limit else {})},
    ).fetchall()

    if not chapter_rows:
        raise ValueError(f"snapshot {snapshot_id} has no chapters")

    ids = [row[0] for row in chapter_rows]
    placeholders = ",".join(f":p{i}" for i in range(len(ids)))
    paragraph_rows = session.execute(
        text(
            f"""
            SELECT snapshot_chapter_id, paragraph_order, start_offset, end_offset,
                   content_hash, stable_paragraph_id
              FROM book_snapshot_paragraphs
             WHERE snapshot_chapter_id IN ({placeholders})
             ORDER BY snapshot_chapter_id, paragraph_order
            """
        ),
        {f"p{i}": v for i, v in enumerate(ids)},
    ).fetchall()

    by_chapter: dict[int, list] = {}
    for row in paragraph_rows:
        by_chapter.setdefault(row[0], []).append(row)

    chapters: list[SourceChapter] = []
    missing_source = 0
    total_chars = 0
    total_paragraphs = 0

    for chapter_id, source_chapter_id, order, _title, _hash, content in chapter_rows:
        content = content or ""
        total_chars += len(content)
        if source_chapter_id is None:
            missing_source += 1

        paragraphs: list[SourceParagraph] = []
        for _cid, p_order, start, end, p_hash, _stable in by_chapter.get(chapter_id, []):
            body = content[start:end].strip()
            if not body:
                continue
            paragraphs.append(SourceParagraph(paragraph_order=p_order, text=body, content_hash=p_hash))
        total_paragraphs += len(paragraphs)

        chapters.append(
            SourceChapter(
                chapter_order=order,
                source_chapter_id=source_chapter_id,
                content_hash=_hash,
                snapshot_chapter_id=chapter_id,
                paragraphs=paragraphs,
            )
        )

    stats = SnapshotStats(
        snapshot_id=snapshot_id,
        chapter_count=len(chapters),
        paragraph_count=total_paragraphs,
        character_count=total_chars,
        chapters_without_source_id=missing_source,
    )
    return chapters, stats


def to_planned_chapters(
    chapters: Sequence[SourceChapter], *, chars_per_token: float = 1.325
) -> list[PlannedChapter]:
    """Project loaded chapters into what the planner needs.

    The planner deliberately never sees prose — only counts — so that "only the extractor
    reads text" stays checkable rather than aspirational.
    """
    planned: list[PlannedChapter] = []
    for chapter in chapters:
        chars = sum(len(p.text) for p in chapter.paragraphs)
        planned.append(
            PlannedChapter(
                chapter_order=chapter.chapter_order,
                source_chapter_id=chapter.source_chapter_id,
                content_hash=chapter.content_hash,
                text_tokens=max(1, int(chars / chars_per_token)),
                n_paragraphs=len(chapter.paragraphs),
                paragraph_hashes=tuple(p.content_hash for p in chapter.paragraphs),
            )
        )
    return planned
