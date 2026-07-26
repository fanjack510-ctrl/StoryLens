"""Background executor for Native Overview runs (HTTP must not block)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


def execute_native_overview_run_background(
    session_factory: sessionmaker[Session],
    run_id: int,
    *,
    provider_id: str | None = None,
    model_id: str | None = None,
) -> None:
    """Open a fresh session and continue a deferred Native Overview run."""

    from app.narrative_core.services.native_overview_http_factory import (
        build_native_overview_service,
    )
    from app.narrative_core.services.native_overview_service import NativeOverviewError

    with session_factory() as session:
        try:
            service = build_native_overview_service(
                session,
                provider_id=provider_id,
                model_id=model_id,
            )
            service.execute_run(int(run_id))
            session.commit()
        except NativeOverviewError as exc:
            session.commit()
            logger.warning(
                "native_overview_background_failed run_id=%s code=%s",
                run_id,
                getattr(exc, "code", type(exc).__name__),
            )
        except Exception:  # noqa: BLE001
            session.rollback()
            logger.exception("native_overview_background_crashed run_id=%s", run_id)
            try:
                with session_factory() as fail_session:
                    from app.db.models import AnalysisRun
                    from app.narrative_core.enums import RunStatus

                    run = fail_session.get(AnalysisRun, int(run_id))
                    if run is not None and run.status not in {
                        RunStatus.COMPLETED.value,
                        RunStatus.FAILED.value,
                        RunStatus.CANCELLED.value,
                    }:
                        run.status = RunStatus.FAILED.value
                        run.error_code = "NATIVE_OVERVIEW_BACKGROUND_FAILED"
                        run.error_message = "原生全书概览后台执行失败。"
                        run.retryable = True
                        fail_session.commit()
            except Exception:  # noqa: BLE001
                logger.exception(
                    "native_overview_background_mark_failed_also_crashed run_id=%s",
                    run_id,
                )


__all__ = ["execute_native_overview_run_background"]
