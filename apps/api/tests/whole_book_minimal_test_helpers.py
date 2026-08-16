"""Shared Sample S test helpers for Wave C."""

from __future__ import annotations

import uuid

from sqlalchemy import create_engine, event
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Book, BookSnapshotParagraph, Chapter, Paragraph, ProviderConfiguration, WholeBookWindow
from app.narrative_core.migrations.runner import apply_narrative_migrations
from app.narrative_core.services.fixture_window_analysis_sample_s import SAMPLE_S_PARAGRAPH_TEXTS
from app.narrative_core.services.whole_book_consent_service import create_whole_book_consent
from app.narrative_core.services.whole_book_cost_estimate_service import estimate_whole_book_analysis
from app.narrative_core.services.whole_book_run_v1_service import create_whole_book_run_v1, start_whole_book_run_v1
from app.narrative_core.services.whole_book_snapshot_v1_service import create_or_reuse_book_snapshot_v1
from app.services.whole_book_source_fingerprint import sha256_utf8


def make_engine(tmp_path, name: str = "wb-minimal.db"):
    engine = create_engine(f"sqlite:///{tmp_path / name}")

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _record) -> None:
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    apply_narrative_migrations(engine)
    return engine


def seed_sample_s_book(session: Session, *, chapter_count: int = 3) -> tuple[Book, int]:
    """Seed the Sample S fixture book.

    ``chapter_count`` defaults to 3, which is what every existing caller has always got.
    Raise it only where the test needs to clear ``MIN_VIABLE_CHAPTERS_PER_BLOCK`` (4): the
    long-novel dispatch predicate refuses a book that cannot be planned in one block, so a
    3-chapter fixture makes a *correctly* confirmed book report as not-dispatched. The
    fixture only carries 9 paragraphs, so chapters past the ninth paragraph cycle through
    them again — enough to exist and be counted, which is all the block floor asks.
    """
    if chapter_count < 1:
        raise ValueError("chapter_count must be at least 1")
    book = Book(title="Sample S", source_file_name="sample-s.txt", source_file_hash=sha256_utf8("sample-s"))
    session.add(book)
    session.flush()
    chapters: list[Chapter] = []
    for idx in range(chapter_count):
        ch = Chapter(book_id=book.id, chapter_index=idx, title=f"第{idx + 1}章")
        session.add(ch)
        session.flush()
        chapters.append(ch)
    global_idx = 0
    total = len(SAMPLE_S_PARAGRAPH_TEXTS)
    for ch_idx, ch in enumerate(chapters):
        window = [
            SAMPLE_S_PARAGRAPH_TEXTS[(ch_idx * 3 + offset) % total] for offset in range(3)
        ]
        for para_idx, text in enumerate(window):
            session.add(
                Paragraph(
                    id=f"p-{book.id}-{global_idx}",
                    book_id=book.id,
                    chapter_id=ch.id,
                    paragraph_index=para_idx,
                    raw_text=text,
                    normalized_text=text,
                    char_start=0,
                    char_end=len(text),
                    content_hash=sha256_utf8(text),
                )
            )
            global_idx += 1
    session.flush()
    snap = create_or_reuse_book_snapshot_v1(session, book.id)["snapshot"]
    return book, snap.id


def seed_three_windows(session: Session, run_id: int, snapshot_id: int) -> list[WholeBookWindow]:
    paragraphs = list(
        session.scalars(
            select(BookSnapshotParagraph)
            .where(BookSnapshotParagraph.snapshot_id == snapshot_id)
            .order_by(BookSnapshotParagraph.global_paragraph_index.asc())
        ).all()
    )
    windows: list[WholeBookWindow] = []
    for idx in range(3):
        chunk = paragraphs[idx * 3 : idx * 3 + 3]
        first_g = chunk[0].global_paragraph_index
        last_g = chunk[-1].global_paragraph_index
        w = WholeBookWindow(
            run_id=run_id,
            snapshot_id=snapshot_id,
            window_index=idx,
            first_global_paragraph_index=first_g,
            last_global_paragraph_index=last_g,
            chapter_start_index=idx,
            chapter_end_index=idx,
            paragraph_count=len(chunk),
            character_count=sum(len(SAMPLE_S_PARAGRAPH_TEXTS[i]) for i in range(idx * 3, idx * 3 + 3)),
            token_estimate=100,
            window_hash=sha256_utf8(f"win-{run_id}-{idx}"),
            idempotency_key=sha256_utf8(f"idem-{run_id}-{idx}"),
            status="pending",
        )
        session.add(w)
        windows.append(w)
    session.flush()
    return windows


def ensure_consent(session: Session, book_id: int) -> int:
    provider = ProviderConfiguration(provider_name="fixture", plus_model="fixture-model")
    session.add(provider)
    session.flush()
    est = estimate_whole_book_analysis(session, book_id, "whole_book_native", provider.id)
    est.pricing_status = "unavailable"
    session.flush()
    consent = create_whole_book_consent(
        session,
        book_id=book_id,
        estimate_id=est.id,
        user_budget_limit_cny="1000",
        max_provider_calls=100,
        max_input_tokens=10_000_000,
        max_output_tokens=10_000_000,
        auto_retry_enabled=False,
        max_retries_per_unit=0,
    )
    return consent.id


def prepare_sample_s_run(session: Session) -> tuple[int, int]:
    book, snapshot_id = seed_sample_s_book(session)
    run = create_whole_book_run_v1(
        session,
        book.id,
        snapshot_id,
        "whole_book_native",
        str(uuid.uuid4()),
        "fixture",
    )
    consent_id = ensure_consent(session, book.id)
    run.consent_id = consent_id
    from app.narrative_core.services.whole_book_minimal_helpers_v1 import set_stage_completed

    set_stage_completed(session, run.id, "windowing", progress_total=3)
    seed_three_windows(session, run.id, snapshot_id)
    session.flush()
    return run.id, book.id
