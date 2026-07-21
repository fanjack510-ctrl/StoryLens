"""Delete a book and all StoryLens-local analysis data (transactional)."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, Book, Chapter, ReaderJourneyRun

# Statuses that still write / hold the book — block delete until stopped.
BOOK_ACTIVE_ANALYSIS_STATUSES = (
    "queued",
    "running",
    "boundary_candidates_running",
    "boundary_candidates_partial",
    "awaiting_boundary_review",
    "boundary_confirmed",
    "boundary_confirmed_budget_blocked",
    "scene_analysis_running",
    "scene_analysis_partial",
    "awaiting_provider_recovery",
)

BOOK_ACTIVE_JOURNEY_STATUSES = (
    "queued",
    "scene_profiles_running",
    "scene_profiles_partial",
    "chapter_synthesis_running",
)


class BookNotFoundError(LookupError):
    pass


class BookHasActiveTasksError(RuntimeError):
    def __init__(self, message: str = "", *, active_count: int = 0) -> None:
        super().__init__(message or "这本书还有正在运行的分析任务，请先停止任务后再删除。")
        self.active_count = active_count


class BookDeleteFailedError(RuntimeError):
    pass


def _chapter_ids(session: Session, book_id: int) -> list[int]:
    return list(session.scalars(select(Chapter.id).where(Chapter.book_id == book_id)))


def count_active_tasks(session: Session, book_id: int) -> int:
    chapter_ids = _chapter_ids(session, book_id)
    subject_ids = [str(cid) for cid in chapter_ids]
    analysis_count = 0
    if subject_ids:
        analysis_count = len(
            list(
                session.scalars(
                    select(AnalysisRun.id).where(
                        AnalysisRun.subject_type == "chapter",
                        AnalysisRun.subject_id.in_(subject_ids),
                        AnalysisRun.status.in_(BOOK_ACTIVE_ANALYSIS_STATUSES),
                    )
                )
            )
        )
    journey_count = len(
        list(
            session.scalars(
                select(ReaderJourneyRun.id).where(
                    ReaderJourneyRun.book_id == book_id,
                    ReaderJourneyRun.status.in_(BOOK_ACTIVE_JOURNEY_STATUSES),
                )
            )
        )
    )
    return analysis_count + journey_count


def _delete_analysis_runs_for_book(session: Session, book_id: int) -> int:
    """AnalysisRun has no book_id FK — must delete explicitly before chapters cascade."""
    chapter_ids = _chapter_ids(session, book_id)
    if not chapter_ids:
        return 0
    subject_ids = [str(cid) for cid in chapter_ids]
    result = session.execute(
        delete(AnalysisRun).where(
            AnalysisRun.subject_type == "chapter",
            AnalysisRun.subject_id.in_(subject_ids),
        )
    )
    return int(result.rowcount or 0)


def _delete_book_subtree(session: Session, book_id: int) -> None:
    book = session.get(Book, book_id)
    if book is None:
        raise BookNotFoundError("BOOK_NOT_FOUND")

    child_ids = list(
        session.scalars(select(Book.id).where(Book.revision_of_book_id == book_id))
    )
    for child_id in child_ids:
        _delete_book_subtree(session, child_id)

    active = count_active_tasks(session, book_id)
    if active > 0:
        raise BookHasActiveTasksError(active_count=active)

    _delete_analysis_runs_for_book(session, book_id)
    # book_id CASCADE covers chapters, paragraphs, scenes, journeys, etc.
    # source_content BLOB is on the Book row — deleted with it. No OS original files.
    session.delete(book)
    session.flush()


def delete_book(session: Session, book_id: int) -> None:
    """Delete book + StoryLens-local descendants in one transaction.

    Does not delete user TXT/DOCX/EPUB files on disk (imports are stored as DB BLOBs only).
    """
    try:
        _delete_book_subtree(session, book_id)
        session.commit()
    except BookNotFoundError:
        session.rollback()
        raise
    except BookHasActiveTasksError:
        session.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        raise BookDeleteFailedError("BOOK_DELETE_FAILED") from exc
