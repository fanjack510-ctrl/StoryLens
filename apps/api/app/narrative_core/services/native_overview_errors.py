"""Native Overview error envelope (shared by service / orchestrator / materializer)."""

from __future__ import annotations

from typing import Any

from app.narrative_core.contracts.whole_book_overview_errors import (
    WHOLE_BOOK_OVERVIEW_ERROR_META,
    WholeBookOverviewErrorCode,
    overview_error_payload,
)

NATIVE_OVERVIEW_UNAVAILABLE_CODE = "PRO_NATIVE_OVERVIEW_UNAVAILABLE"


class NativeOverviewError(Exception):
    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        http_status: int | None = None,
        details: dict[str, Any] | None = None,
        run_id: str | None = None,
        stage_key: str | None = None,
        window_index: int | None = None,
    ) -> None:
        self.code = code
        self.details = details or {}
        self.run_id = run_id
        self.stage_key = stage_key
        self.window_index = window_index
        try:
            meta = WHOLE_BOOK_OVERVIEW_ERROR_META[WholeBookOverviewErrorCode(code)]
            self.http_status = http_status if http_status is not None else meta["http_status"]
            self.message = message or meta["user_message"]
            self.retryable = meta["retryable"]
        except ValueError:
            self.http_status = http_status if http_status is not None else 503
            self.message = message or "原生全书概览不可用。"
            self.retryable = False
        super().__init__(self.message)

    def as_envelope(self) -> dict[str, Any]:
        try:
            return overview_error_payload(
                self.code,
                message=self.message,
                details=self.details,
                run_id=self.run_id,
                stage_key=self.stage_key,
                window_index=self.window_index,
            )
        except ValueError:
            return {
                "error": {
                    "code": self.code,
                    "message": self.message,
                    "retryable": self.retryable,
                    "details": self.details,
                    "run_id": self.run_id,
                    "stage_key": self.stage_key,
                    "window_index": self.window_index,
                }
            }


__all__ = [
    "NATIVE_OVERVIEW_UNAVAILABLE_CODE",
    "NativeOverviewError",
]
