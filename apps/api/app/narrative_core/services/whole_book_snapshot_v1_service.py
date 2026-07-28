"""Immutable Book Snapshot v1 (WB-1.2) — shared revision hash, no chapter analysis input."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Book,
    BookSnapshot,
    BookSnapshotChapter,
    BookSnapshotParagraph,
    Paragraph,
    utc_now,
)
from app.narrative_core.contracts.whole_book_contract_v1 import SnapshotStatus as ContractSnapshotStatus
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)
from app.services.whole_book_source_fingerprint import (
    canonical_json_bytes,
    compute_book_revision_hash_v1,
    load_ordered_chapter_texts,
    normalize_line_endings_v1,
    segment_snapshot_paragraphs_v1,
    sha256_utf8,
)

UPDATE_COMPLETED_FORBIDDEN = WholeBookFoundationErrorCode.UPDATE_COMPLETED_FORBIDDEN.value


def _chapter_hash_payload(
    *,
    chapter_id: int,
    chapter_index: int,
    title: str,
    paragraph_specs: list[tuple[int, str]],
) -> str:
    payload = {
        "chapter_id": chapter_id,
        "chapter_index": chapter_index,
        "title": title,
        "paragraphs": [
            {"paragraph_index": idx, "text_hash": text_hash}
            for idx, text_hash in paragraph_specs
        ],
    }
    return sha256_utf8(canonical_json_bytes(payload).decode("utf-8"))


def _assert_snapshot_mutable(snapshot: BookSnapshot) -> None:
    if snapshot.snapshot_status == ContractSnapshotStatus.completed.value:
        raise WholeBookFoundationError(
            UPDATE_COMPLETED_FORBIDDEN,
            f"snapshot {snapshot.id} is completed and immutable",
        )


def to_metadata_dict(snapshot: BookSnapshot) -> dict[str, Any]:
    created = snapshot.created_at
    completed = snapshot.completed_at
    return {
        "snapshot_id": snapshot.id,
        "book_id": snapshot.book_id,
        "snapshot_version": snapshot.snapshot_version,
        "status": snapshot.snapshot_status,
        "content_hash": snapshot.content_hash,
        "chapter_count": snapshot.chapter_count,
        "paragraph_count": snapshot.paragraph_count,
        "character_count": snapshot.character_count,
        "created_at": created.isoformat() if created else None,
        "completed_at": completed.isoformat() if completed else None,
    }


def get_snapshot_paragraph_text(session: Session, snapshot_paragraph_id: int) -> str:
    paragraph = session.get(BookSnapshotParagraph, snapshot_paragraph_id)
    if paragraph is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_FOUND,
            f"snapshot paragraph not found: {snapshot_paragraph_id}",
        )
    chapter = session.get(BookSnapshotChapter, paragraph.snapshot_chapter_id)
    if chapter is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_FOUND,
            f"snapshot chapter missing for paragraph {snapshot_paragraph_id}",
        )
    text = chapter.content_text or ""
    start = paragraph.start_offset
    end = paragraph.end_offset
    if start < 0 or end < start or end > len(text):
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_FOUND,
            f"offset out of range for paragraph {snapshot_paragraph_id}",
        )
    restored = text[start:end]
    if sha256_utf8(restored) != paragraph.content_hash:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_FOUND,
            f"paragraph hash mismatch for {snapshot_paragraph_id}",
        )
    return restored


def list_snapshots_for_book(session: Session, book_id: int) -> list[BookSnapshot]:
    return list(
        session.scalars(
            select(BookSnapshot)
            .where(BookSnapshot.book_id == book_id)
            .order_by(BookSnapshot.snapshot_version.desc(), BookSnapshot.id.desc())
        ).all()
    )


def get_snapshot(session: Session, snapshot_id: int) -> BookSnapshot:
    snapshot = session.get(BookSnapshot, snapshot_id)
    if snapshot is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_FOUND,
            f"snapshot not found: {snapshot_id}",
        )
    return snapshot


def list_chapters(session: Session, snapshot_id: int) -> list[BookSnapshotChapter]:
    get_snapshot(session, snapshot_id)
    return list(
        session.scalars(
            select(BookSnapshotChapter)
            .where(BookSnapshotChapter.snapshot_id == snapshot_id)
            .order_by(BookSnapshotChapter.chapter_order.asc())
        ).all()
    )


def list_paragraphs(
    session: Session,
    snapshot_id: int,
    *,
    offset: int = 0,
    limit: int = 50,
    chapter_index: int | None = None,
) -> tuple[list[dict[str, Any]], int]:
    get_snapshot(session, snapshot_id)
    query = (
        select(BookSnapshotParagraph, BookSnapshotChapter)
        .join(
            BookSnapshotChapter,
            BookSnapshotChapter.id == BookSnapshotParagraph.snapshot_chapter_id,
        )
        .where(BookSnapshotParagraph.snapshot_id == snapshot_id)
    )
    if chapter_index is not None:
        query = query.where(BookSnapshotChapter.chapter_order == chapter_index)
    query = query.order_by(BookSnapshotParagraph.global_paragraph_index.asc())
    rows = session.execute(query).all()
    total = len(rows)
    sliced = rows[offset : offset + limit]
    items: list[dict[str, Any]] = []
    for para, chapter in sliced:
        text = get_snapshot_paragraph_text(session, para.id)
        items.append(
            {
                "snapshot_paragraph_id": para.id,
                "snapshot_id": para.snapshot_id,
                "snapshot_chapter_id": para.snapshot_chapter_id,
                "chapter_id": chapter.source_chapter_id,
                "chapter_index": chapter.chapter_order,
                "paragraph_index": para.paragraph_order - 1,
                "global_paragraph_index": para.global_paragraph_index,
                "text": text,
                "text_hash": para.content_hash,
                "character_count": len(text),
            }
        )
    return items, total


def _next_snapshot_version(session: Session, book_id: int) -> int:
    current = session.scalar(
        select(func.max(BookSnapshot.snapshot_version)).where(BookSnapshot.book_id == book_id)
    )
    return 1 if current is None else int(current) + 1


def _resolve_paragraph_texts(
    session: Session,
    *,
    chapter_id: int,
    chapter_text: str,
    paragraph_texts: list[str],
) -> list[tuple[str, str | None]]:
    """Return (text, source_paragraph_id) pairs in chapter order."""
    if paragraph_texts:
        paras = session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == chapter_id)
            .order_by(Paragraph.paragraph_index.asc())
        ).all()
        out: list[tuple[str, str | None]] = []
        for idx, text in enumerate(paragraph_texts):
            source_id = paras[idx].id if idx < len(paras) else None
            out.append((text, source_id))
        return out
    segmented = segment_snapshot_paragraphs_v1(chapter_text)
    return [(text, None) for text in segmented]


def create_or_reuse_book_snapshot_v1(session: Session, book_id: int) -> dict[str, Any]:
    book = session.get(Book, book_id)
    if book is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_BOOK_CHANGED,
            f"book not found: {book_id}",
        )

    content_hash = compute_book_revision_hash_v1(session, book_id)
    existing = session.scalar(
        select(BookSnapshot).where(
            BookSnapshot.book_id == book_id,
            BookSnapshot.content_hash == content_hash,
            BookSnapshot.snapshot_status == ContractSnapshotStatus.completed.value,
        )
    )
    if existing is not None:
        return {"snapshot": existing, "reused": True}

    snapshot_version = _next_snapshot_version(session, book_id)
    now = utc_now()
    snapshot = BookSnapshot(
        book_id=book_id,
        content_hash=content_hash,
        snapshot_version=snapshot_version,
        chapter_count=0,
        paragraph_count=0,
        character_count=0,
        snapshot_status=ContractSnapshotStatus.building.value,
        source_fingerprint=content_hash,
        created_at=now,
        completed_at=None,
    )
    session.add(snapshot)
    session.flush()

    chapter_rows = load_ordered_chapter_texts(session, book_id)
    global_index = 0
    paragraph_total = 0
    character_total = 0

    for row in chapter_rows:
        chapter_id = int(row["chapter_id"])
        chapter_index = int(row["chapter_index"])
        title = str(row["title"])
        chapter_text = normalize_line_endings_v1(str(row["text"]))
        para_specs = _resolve_paragraph_texts(
            session,
            chapter_id=chapter_id,
            chapter_text=chapter_text,
            paragraph_texts=list(row.get("paragraph_texts") or []),
        )
        if not para_specs and chapter_text.strip():
            para_specs = [(chapter_text, None)]

        hash_specs: list[tuple[int, str]] = []
        built_text_parts: list[str] = []
        for para_idx, (para_text, _source_id) in enumerate(para_specs):
            hash_specs.append((para_idx, sha256_utf8(para_text)))
            built_text_parts.append(para_text)
        if built_text_parts:
            chapter_text = "\n".join(built_text_parts)
        else:
            chapter_text = ""

        chapter_hash = _chapter_hash_payload(
            chapter_id=chapter_id,
            chapter_index=chapter_index,
            title=title,
            paragraph_specs=hash_specs,
        )
        snap_chapter = BookSnapshotChapter(
            snapshot_id=snapshot.id,
            source_chapter_id=chapter_id,
            chapter_order=chapter_index,
            title=title,
            content_hash=chapter_hash,
            content_text=chapter_text,
        )
        session.add(snap_chapter)
        session.flush()

        offset = 0
        for para_idx, (para_text, source_id) in enumerate(para_specs):
            start = offset
            end = offset + len(para_text)
            stable_id = source_id or f"seg-{chapter_id}-{para_idx}"
            session.add(
                BookSnapshotParagraph(
                    snapshot_id=snapshot.id,
                    snapshot_chapter_id=snap_chapter.id,
                    source_paragraph_id=source_id,
                    stable_paragraph_id=stable_id,
                    paragraph_order=para_idx + 1,
                    global_paragraph_index=global_index,
                    start_offset=start,
                    end_offset=end,
                    content_hash=sha256_utf8(para_text),
                )
            )
            global_index += 1
            paragraph_total += 1
            character_total += len(para_text)
            offset = end + (1 if para_idx + 1 < len(para_specs) else 0)

    recomputed = compute_book_revision_hash_v1(session, book_id)
    if recomputed != content_hash:
        snapshot.snapshot_status = ContractSnapshotStatus.invalid.value
        session.flush()
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_FOUND,
            "snapshot content_hash mismatch after build",
        )

    snapshot.chapter_count = len(chapter_rows)
    snapshot.paragraph_count = paragraph_total
    snapshot.character_count = character_total
    snapshot.content_hash = content_hash
    snapshot.snapshot_status = ContractSnapshotStatus.completed.value
    snapshot.completed_at = datetime.now(timezone.utc)
    session.flush()
    return {"snapshot": snapshot, "reused": False}


def chapter_to_dict(chapter: BookSnapshotChapter) -> dict[str, Any]:
    para_count = len(chapter.paragraphs) if chapter.paragraphs else 0
    char_count = len(chapter.content_text or "")
    return {
        "snapshot_chapter_id": chapter.id,
        "snapshot_id": chapter.snapshot_id,
        "chapter_id": chapter.source_chapter_id,
        "chapter_index": chapter.chapter_order,
        "title": chapter.title,
        "chapter_hash": chapter.content_hash,
        "paragraph_count": para_count,
        "character_count": char_count,
    }
