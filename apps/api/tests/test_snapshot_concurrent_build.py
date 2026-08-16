"""并发建快照必须串行，不能互相清空 (CHG-20260815-098).

Two requests for the same book used to race: the loser waited a flat 5s, decided a build
still in flight was stale, and cleared the chapter rows the winner was writing — so BOTH
ended with an empty snapshot and the caller got SNAPSHOT_HAS_NO_CHAPTERS or
BOOK_HAS_NO_SNAPSHOT. A 1299-chapter novel takes far longer than 5s to snapshot, and React
StrictMode double-firing the profile draft is enough to trigger it.
"""

from __future__ import annotations

import os
import tempfile
import threading

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Book, Chapter, Paragraph
from app.narrative_core.migrations.runner import apply_narrative_migrations
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl

CHAPTERS = 12
PARAS_PER_CHAPTER = 6


@pytest.fixture()
def factory():
    path = os.path.join(tempfile.mkdtemp(), "snap.db")
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(bind=engine)
    apply_narrative_migrations(engine)
    make = sessionmaker(bind=engine)
    with make() as session:
        session.add(Book(id=1, title="并发测试", source_file_name="x.txt", source_file_hash="h"))
        session.flush()
        offset = 0
        for c in range(1, CHAPTERS + 1):
            chapter = Chapter(
                book_id=1,
                chapter_index=c,
                title=f"第 {c} 章",
                section_type="chapter",
            )
            session.add(chapter)
            session.flush()
            for p in range(1, PARAS_PER_CHAPTER + 1):
                text_value = f"第 {c} 章第 {p} 段的正文内容，足够长以便统计。"
                session.add(
                    Paragraph(
                        id=f"B0001-C{c:04d}-P{p:04d}",
                        book_id=1,
                        chapter_id=chapter.id,
                        paragraph_index=p,
                        raw_text=text_value,
                        normalized_text=text_value,
                        char_start=offset,
                        char_end=offset + len(text_value),
                    )
                )
                offset += len(text_value)
        session.commit()
    return make


def _build(factory, results: list, index: int) -> None:
    with factory() as session:
        try:
            snapshot = BookSnapshotServiceImpl(session).create_or_reuse_snapshot(1)
            session.commit()
            results[index] = ("ok", snapshot.id, int(snapshot.chapter_count or 0))
        except Exception as exc:  # noqa: BLE001 — the failure is the finding
            session.rollback()
            results[index] = ("error", type(exc).__name__, str(exc)[:120])


def test_concurrent_builders_produce_one_complete_snapshot(factory) -> None:
    results: list = [None, None]
    threads = [threading.Thread(target=_build, args=(factory, results, i)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)

    assert all(r is not None for r in results), f"a builder never finished: {results}"
    assert all(r[0] == "ok" for r in results), f"a builder failed: {results}"
    # Same snapshot reused, and it holds every chapter — the bug produced 0.
    assert results[0][1] == results[1][1]
    assert results[0][2] == CHAPTERS
    assert results[1][2] == CHAPTERS


def test_snapshot_rows_are_readable_after_concurrent_build(factory) -> None:
    results: list = [None, None]
    threads = [threading.Thread(target=_build, args=(factory, results, i)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)

    from sqlalchemy import text

    with factory() as session:
        snapshot_id = results[0][1]
        # This is exactly what the profile draft reads; it returned zero rows before.
        rows = session.execute(
            text(
                "SELECT content_text FROM book_snapshot_chapters "
                "WHERE snapshot_id = :sid ORDER BY chapter_order"
            ),
            {"sid": snapshot_id},
        ).all()
        assert len(rows) == CHAPTERS
        assert all((row[0] or "").strip() for row in rows)
