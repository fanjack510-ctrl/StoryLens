"""Background executor for formal Free whole-book create (HTTP must not block)."""

from __future__ import annotations

import logging
import threading
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


def _mark_run_failed(session_factory: sessionmaker[Session], run_id: int, exc: BaseException) -> None:
    from app.db.models import WholeBookRun
    from app.narrative_core.contracts.whole_book_contract_v1 import WholeBookRunStatus
    from app.narrative_core.whole_book_v2.failure_taxonomy import classify_pipeline_exception

    classified = classify_pipeline_exception(exc)
    with session_factory() as fail_session:
        run = fail_session.get(WholeBookRun, int(run_id))
        if run is None:
            return
        if run.status in {
            WholeBookRunStatus.completed.value,
            WholeBookRunStatus.cancelled.value,
        }:
            return
        run.status = WholeBookRunStatus.failed.value
        run.failure_code = classified.failure_code
        run.failure_message_safe = classified.message_safe
        run.current_stage_code = classified.failure_stage
        fail_session.commit()
        logger.warning(
            "free_whole_book_background_marked_failed run_id=%s stage=%s code=%s category=%s",
            run_id,
            classified.failure_stage,
            classified.failure_code,
            classified.category,
        )


def execute_free_whole_book_pipeline_background(
    session_factory: sessionmaker[Session],
    run_id: int,
    *,
    provider_config_id: int | None = None,
    force_full_reanalysis: bool = False,
    previous_run_id: int | None = None,
) -> None:
    """Continue a deferred formal Free whole-book run in a fresh session.

    Create HTTP returns after the WholeBookRun row is committed so the UI can
    leave「创建中…」and show progress. Provider work happens here.

    CHG-078/080: formal product runs Hierarchical V2 — not minimal_pipeline_v1.
    CHG-081: own DB session + intermediate commits; exceptions must not kill sidecar.
    CHG-085: failure stage/message classified from real exception; resume reuses
    same-run checkpoints (force_full does not reburn THIS run's windows).
    """

    del provider_config_id  # pinned on WholeBookRun at create; hierarchical uses run pin

    from app.narrative_core.services.whole_book_foundation_errors import (
        WholeBookFoundationError,
    )
    from app.narrative_core.services.whole_book_v2_formal_pipeline_v1 import (
        execute_hierarchical_v2_pipeline_v1,
    )

    # Never reuse the request-scoped Session. Always open a new one here.
    with session_factory() as session:
        request_session_id = id(session)
        try:
            execute_hierarchical_v2_pipeline_v1(
                session,
                int(run_id),
                force_full_reanalysis=bool(force_full_reanalysis),
                previous_run_id=int(previous_run_id) if previous_run_id else None,
                commit_progress=True,
            )
            session.commit()
            logger.info(
                "free_whole_book_background_ok run_id=%s session_id=%s",
                run_id,
                request_session_id,
            )
        except WholeBookFoundationError as exc:
            try:
                session.commit()
            except Exception:  # noqa: BLE001
                session.rollback()
            logger.warning(
                "free_whole_book_background_failed run_id=%s code=%s",
                run_id,
                getattr(exc, "code", type(exc).__name__),
            )
            try:
                _mark_run_failed(session_factory, int(run_id), exc)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "free_whole_book_background_mark_failed_also_crashed run_id=%s",
                    run_id,
                )
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            logger.exception("free_whole_book_background_crashed run_id=%s", run_id)
            try:
                _mark_run_failed(session_factory, int(run_id), exc)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "free_whole_book_background_mark_failed_also_crashed run_id=%s",
                    run_id,
                )


def schedule_free_whole_book_pipeline_background(
    session_factory: sessionmaker[Session],
    run_id: int,
    *,
    provider_config_id: int | None = None,
    force_full_reanalysis: bool = False,
    previous_run_id: int | None = None,
) -> threading.Thread:
    """Detach V2 execution from the HTTP request / FastAPI BackgroundTasks lifecycle.

    Packaged sidecar (PyInstaller + uvicorn) must keep accepting /health while a
    long Hierarchical run executes. A dedicated daemon thread owns the work;
    exceptions are swallowed inside the worker so they cannot tear down the API
    process.
    """

    def _runner() -> None:
        try:
            execute_free_whole_book_pipeline_background(
                session_factory,
                int(run_id),
                provider_config_id=provider_config_id,
                force_full_reanalysis=bool(force_full_reanalysis),
                previous_run_id=previous_run_id,
            )
        except Exception:  # noqa: BLE001 — last-resort process boundary
            logger.exception(
                "free_whole_book_background_thread_unhandled run_id=%s",
                run_id,
            )

    thread = threading.Thread(
        target=_runner,
        name=f"wb-v2-bg-{int(run_id)}",
        daemon=True,
    )
    thread.start()
    return thread


__all__ = [
    "execute_free_whole_book_pipeline_background",
    "schedule_free_whole_book_pipeline_background",
]
