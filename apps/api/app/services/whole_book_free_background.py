"""Background executor for formal Free whole-book create (HTTP must not block)."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


def execute_free_whole_book_pipeline_background(
    session_factory: sessionmaker[Session],
    run_id: int,
    *,
    provider_config_id: int | None = None,
) -> None:
    """Continue a deferred formal Free whole-book run in a fresh session.

    Create HTTP returns after the WholeBookRun row is committed so the UI can
    leave「创建中…」and show progress. Provider work happens here.
    """

    from app.narrative_core.services.whole_book_foundation_errors import (
        WholeBookFoundationError,
    )
    from app.narrative_core.services.whole_book_minimal_pipeline_v1_service import (
        build_formal_gateway_transports,
        execute_minimal_pipeline_v1,
    )
    from app.narrative_core.services.whole_book_run_v1_service import get_run

    with session_factory() as session:
        try:
            run = get_run(session, int(run_id))
            transports = build_formal_gateway_transports(
                session,
                run=run,
                provider_config_id=provider_config_id,
            )
            execute_minimal_pipeline_v1(session, int(run_id), transports=transports)
            session.commit()
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
        except Exception:  # noqa: BLE001
            session.rollback()
            logger.exception("free_whole_book_background_crashed run_id=%s", run_id)
            try:
                with session_factory() as fail_session:
                    from app.db.models import WholeBookRun
                    from app.narrative_core.contracts.whole_book_contract_v1 import (
                        WholeBookRunStatus,
                    )

                    run = fail_session.get(WholeBookRun, int(run_id))
                    if run is not None and run.status not in {
                        WholeBookRunStatus.completed.value,
                        WholeBookRunStatus.failed.value,
                        WholeBookRunStatus.cancelled.value,
                    }:
                        run.status = WholeBookRunStatus.failed.value
                        run.failure_code = "WHOLE_BOOK_BACKGROUND_FAILED"
                        run.failure_message_safe = "全书分析后台执行失败，可重试或检查 Provider 配置。"
                        fail_session.commit()
            except Exception:  # noqa: BLE001
                logger.exception(
                    "free_whole_book_background_mark_failed_also_crashed run_id=%s",
                    run_id,
                )


__all__ = ["execute_free_whole_book_pipeline_background"]
