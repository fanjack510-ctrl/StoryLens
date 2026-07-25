"""Whole-Book Insights public-side errors (Pro capability)."""

from __future__ import annotations

from enum import StrEnum


class WholeBookInsightsErrorCode(StrEnum):
    PRO_LICENSE_REQUIRED = "PRO_LICENSE_REQUIRED"
    PRO_CAPABILITY_NOT_AVAILABLE = "PRO_CAPABILITY_NOT_AVAILABLE"
    PRIVATE_ENGINE_UNAVAILABLE = "PRIVATE_ENGINE_UNAVAILABLE"
    WHOLE_BOOK_INSIGHTS_INSUFFICIENT_COVERAGE = "WHOLE_BOOK_INSIGHTS_INSUFFICIENT_COVERAGE"
    WHOLE_BOOK_INSIGHTS_INPUT_INVALID = "WHOLE_BOOK_INSIGHTS_INPUT_INVALID"
    BOOK_NOT_FOUND = "BOOK_NOT_FOUND"


_STATUS_BY_CODE: dict[WholeBookInsightsErrorCode, int] = {
    WholeBookInsightsErrorCode.PRO_LICENSE_REQUIRED: 403,
    WholeBookInsightsErrorCode.PRO_CAPABILITY_NOT_AVAILABLE: 503,
    WholeBookInsightsErrorCode.PRIVATE_ENGINE_UNAVAILABLE: 503,
    WholeBookInsightsErrorCode.WHOLE_BOOK_INSIGHTS_INSUFFICIENT_COVERAGE: 422,
    WholeBookInsightsErrorCode.WHOLE_BOOK_INSIGHTS_INPUT_INVALID: 422,
    WholeBookInsightsErrorCode.BOOK_NOT_FOUND: 404,
}


class WholeBookInsightsError(Exception):
    def __init__(
        self,
        code: WholeBookInsightsErrorCode,
        message: str = "",
        *,
        details: dict | None = None,
    ) -> None:
        self.code = code
        self.message = message or code.value
        self.details = details or {}
        super().__init__(self.message)

    @property
    def status_code(self) -> int:
        return _STATUS_BY_CODE.get(self.code, 500)
