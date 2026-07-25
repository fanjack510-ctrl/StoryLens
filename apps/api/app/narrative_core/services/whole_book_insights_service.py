"""Pro Chapter Asset Aggregation Insights service — license gate + private engine.

Capability key remains ``pro_whole_book_insights``. Aggregates completed single-chapter
analysis assets; does not perform native whole-book / full-text analysis.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.narrative_core.enums import CapabilityKey, CapabilityReasonCode
from app.narrative_core.services.capability_service import DefaultCapabilityService
from app.narrative_core.services.whole_book_insights_errors import (
    WholeBookInsightsError,
    WholeBookInsightsErrorCode,
)
from app.narrative_core.services.whole_book_insights_input_builder import (
    build_whole_book_insights_input,
)
from app.narrative_core.services.whole_book_insights_private_loader import (
    WholeBookInsightsEngineProtocol,
    try_import_whole_book_insights_engine,
)

CAPABILITY_KEY = CapabilityKey.PRO_WHOLE_BOOK_INSIGHTS


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_pro_license(session: Session) -> None:
    svc = DefaultCapabilityService(session)
    decision = svc.evaluate_capability(CAPABILITY_KEY)
    if decision.allowed:
        return
    if decision.reason_code == CapabilityReasonCode.CAPABILITY_NOT_LICENSED:
        raise WholeBookInsightsError(
            WholeBookInsightsErrorCode.PRO_LICENSE_REQUIRED,
            "StoryLens Pro license required for chapter asset aggregation insights.",
        )
    if decision.reason_code in {
        CapabilityReasonCode.CAPABILITY_NOT_SHIPPED,
        CapabilityReasonCode.CAPABILITY_UNKNOWN,
    }:
        raise WholeBookInsightsError(
            WholeBookInsightsErrorCode.PRO_CAPABILITY_NOT_AVAILABLE,
            "Chapter asset aggregation insights capability is not available in this build.",
        )
    if decision.reason_code in {
        CapabilityReasonCode.CAPABILITY_LICENSE_EXPIRED,
        CapabilityReasonCode.CAPABILITY_LICENSE_INVALID,
    }:
        raise WholeBookInsightsError(
            WholeBookInsightsErrorCode.PRO_LICENSE_REQUIRED,
            decision.display_message or "Pro license is not valid.",
        )
    raise WholeBookInsightsError(
        WholeBookInsightsErrorCode.PRO_CAPABILITY_NOT_AVAILABLE,
        decision.display_message or "Chapter asset aggregation insights is not available.",
    )


def compute_whole_book_insights(
    session: Session,
    book_id: int,
    *,
    engine: WholeBookInsightsEngineProtocol | None = None,
) -> dict[str, Any]:
    """On-demand compute; no cache, no provider HTTP."""
    _require_pro_license(session)

    try:
        input_payload = build_whole_book_insights_input(session, book_id)
    except ValueError as exc:
        if str(exc) == "book_not_found":
            raise WholeBookInsightsError(
                WholeBookInsightsErrorCode.BOOK_NOT_FOUND,
                "书籍不存在",
            ) from exc
        raise WholeBookInsightsError(
            WholeBookInsightsErrorCode.WHOLE_BOOK_INSIGHTS_INPUT_INVALID,
            str(exc),
        ) from exc

    valid = int((input_payload.get("coverage") or {}).get("valid_chapters") or 0)
    if valid <= 0:
        raise WholeBookInsightsError(
            WholeBookInsightsErrorCode.WHOLE_BOOK_INSIGHTS_INSUFFICIENT_COVERAGE,
            "Not enough completed chapter analyses with reader journey scores.",
            details={"coverage": input_payload.get("coverage") or {}},
        )

    resolved_engine = engine if engine is not None else try_import_whole_book_insights_engine()
    if resolved_engine is None:
        raise WholeBookInsightsError(
            WholeBookInsightsErrorCode.PRIVATE_ENGINE_UNAVAILABLE,
            "Private chapter asset aggregation insights engine is not installed.",
        )

    try:
        result = resolved_engine.compute(input_payload)
    except WholeBookInsightsError:
        raise
    except Exception as exc:
        raise WholeBookInsightsError(
            WholeBookInsightsErrorCode.WHOLE_BOOK_INSIGHTS_INPUT_INVALID,
            f"Private engine rejected input: {exc}",
        ) from exc

    if not isinstance(result, dict):
        raise WholeBookInsightsError(
            WholeBookInsightsErrorCode.WHOLE_BOOK_INSIGHTS_INPUT_INVALID,
            "Private engine returned invalid payload.",
        )

    result.setdefault("book_id", book_id)
    result.setdefault("computed_at", _utc_now_iso())
    result.setdefault(
        "data_source",
        {
            "capability_key": CAPABILITY_KEY.value,
            "api_alias": "pro.whole_book_insights",
            "input_schema": input_payload.get("schema"),
            "coverage": input_payload.get("coverage"),
        },
    )
    return result
