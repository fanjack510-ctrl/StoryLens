"""Whole-book consent service (WB-0.3) — immutable consents, no API keys."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import BookSnapshot, WholeBookConsent, WholeBookCostEstimate
from app.narrative_core.services.whole_book_cost_estimate_service import (
    compute_book_revision_hash,
    is_estimate_valid,
)
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)


def create_whole_book_consent(
    session: Session,
    *,
    book_id: int,
    estimate_id: int,
    user_budget_limit_cny: Decimal | str | float,
    max_provider_calls: int | None = None,
    max_input_tokens: int | None = None,
    max_output_tokens: int | None = None,
    auto_retry_enabled: bool = False,
    max_retries_per_unit: int = 0,
    now: datetime | None = None,
) -> WholeBookConsent:
    estimate = session.get(WholeBookCostEstimate, estimate_id)
    if estimate is None or estimate.book_id != book_id:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_ESTIMATE_EXPIRED,
            "estimate not found for book",
        )
    ok, code = is_estimate_valid(session, estimate, now=now)
    if not ok:
        raise WholeBookFoundationError(code or "WHOLE_BOOK_ESTIMATE_EXPIRED", "estimate invalid")

    # Re-check revision explicitly.
    if compute_book_revision_hash(session, book_id) != estimate.book_revision_hash:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_BOOK_CHANGED,
            "book revision changed",
        )

    budget = Decimal(str(user_budget_limit_cny))
    if budget < 0:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_BUDGET_TOO_LOW,
            "budget must be >= 0",
        )

    accepted_max = estimate.estimated_cost_max_cny
    if estimate.pricing_status == "available":
        if accepted_max is None:
            raise WholeBookFoundationError(
                WholeBookFoundationErrorCode.WHOLE_BOOK_PRICING_UNAVAILABLE,
                "available pricing missing max cost",
            )
        if budget < Decimal(str(accepted_max)):
            raise WholeBookFoundationError(
                WholeBookFoundationErrorCode.BUDGET_TOO_LOW,
                f"费用预算低于预计最高费用：预计最高 ¥{accepted_max}，当前预算 ¥{budget}",
                details={
                    "estimated_cost_max_cny": str(accepted_max),
                    "max_cost_budget_cny": str(budget),
                },
            )
        from app.narrative_core.services.whole_book_start_limits_v1 import (
            assert_limits_cover_estimate,
        )

        assert_limits_cover_estimate(
            estimate,
            max_provider_calls=max_provider_calls,
            max_input_tokens=max_input_tokens,
            max_output_tokens=max_output_tokens,
            user_budget_limit_cny=None,  # already checked above
        )
        calls = max_provider_calls if max_provider_calls is not None else estimate.estimated_provider_call_count
        in_tok = max_input_tokens if max_input_tokens is not None else estimate.estimated_input_tokens
        out_tok = max_output_tokens if max_output_tokens is not None else estimate.estimated_output_tokens
    else:
        if max_provider_calls is None or max_provider_calls <= 0:
            raise WholeBookFoundationError(
                WholeBookFoundationErrorCode.WHOLE_BOOK_CALL_LIMIT_REQUIRED,
                "max_provider_calls required when pricing unavailable",
            )
        if max_input_tokens is None or max_input_tokens <= 0:
            raise WholeBookFoundationError(
                WholeBookFoundationErrorCode.WHOLE_BOOK_TOKEN_LIMIT_REQUIRED,
                "max_input_tokens required when pricing unavailable",
            )
        if max_output_tokens is None or max_output_tokens <= 0:
            raise WholeBookFoundationError(
                WholeBookFoundationErrorCode.WHOLE_BOOK_TOKEN_LIMIT_REQUIRED,
                "max_output_tokens required when pricing unavailable",
            )
        calls = max_provider_calls
        in_tok = max_input_tokens
        out_tok = max_output_tokens

    current = now or datetime.now(timezone.utc)
    consent = WholeBookConsent(
        book_id=book_id,
        estimate_id=estimate.id,
        book_revision_hash=estimate.book_revision_hash,
        mode=estimate.mode,
        provider_config_id=estimate.provider_config_id,
        model_name=estimate.model_name,
        accepted_estimated_cost_max_cny=accepted_max,
        user_budget_limit_cny=budget,
        max_provider_calls=int(calls),
        max_input_tokens=int(in_tok),
        max_output_tokens=int(out_tok),
        auto_retry_enabled=bool(auto_retry_enabled),
        max_retries_per_unit=int(max_retries_per_unit or 0),
        accepted_at=current,
        expires_at=estimate.expires_at,
        revoked_at=None,
    )
    session.add(consent)
    session.flush()
    return consent


def validate_whole_book_consent(
    session: Session,
    consent_id: int,
    *,
    book_id: int,
    estimate_id: int,
    snapshot_id: int,
    now: datetime | None = None,
) -> WholeBookConsent:
    """Validate consent for create / provider paths under one binding contract.

    Required bindings (keyword-only; no positional extras, no **kwargs):
    - book_id
    - estimate_id (prepare / estimate identity)
    - snapshot_id
    - book revision (consent.book_revision_hash vs live book + snapshot content)
    """
    consent = session.get(WholeBookConsent, consent_id)
    if consent is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_CONSENT_REQUIRED,
            "consent not found",
        )
    if int(consent.book_id) != int(book_id):
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_CONSENT_REQUIRED,
            "consent book_id mismatch",
        )
    if int(consent.estimate_id) != int(estimate_id):
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_ESTIMATE_EXPIRED,
            "consent estimate_id mismatch",
        )
    snapshot = session.get(BookSnapshot, snapshot_id)
    if snapshot is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_FOUND,
            f"snapshot not found: {snapshot_id}",
        )
    if int(snapshot.book_id) != int(book_id):
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_BOOK_MISMATCH,
            f"snapshot {snapshot_id} belongs to book {snapshot.book_id}, not {book_id}",
        )
    # Snapshot content_hash is the book revision fingerprint at snapshot time.
    snap_revision = str(snapshot.source_fingerprint or snapshot.content_hash or "")
    if snap_revision and snap_revision != consent.book_revision_hash:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_BOOK_CHANGED,
            "snapshot revision does not match consent",
        )
    if consent.revoked_at is not None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_CONSENT_REVOKED,
            "consent revoked",
        )
    current = now or datetime.now(timezone.utc)
    exp = consent.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if current > exp:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_CONSENT_EXPIRED,
            "consent expired",
        )
    if compute_book_revision_hash(session, consent.book_id) != consent.book_revision_hash:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_BOOK_CHANGED,
            "book revision changed since consent",
        )
    return consent


def validate_whole_book_consent_for_run(
    session: Session,
    consent_id: int,
    *,
    book_id: int,
    snapshot_id: int,
    now: datetime | None = None,
) -> WholeBookConsent:
    """Mid-run budget/retry path: bind consent to the run's book + snapshot.

    estimate_id is taken from the consent row (identity fixed at create time).
    """
    consent = session.get(WholeBookConsent, consent_id)
    if consent is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_CONSENT_REQUIRED,
            "consent not found",
        )
    return validate_whole_book_consent(
        session,
        consent_id,
        book_id=book_id,
        estimate_id=int(consent.estimate_id),
        snapshot_id=snapshot_id,
        now=now,
    )


def revoke_whole_book_consent(
    session: Session,
    consent_id: int,
    *,
    now: datetime | None = None,
) -> WholeBookConsent:
    consent = session.get(WholeBookConsent, consent_id)
    if consent is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_CONSENT_REQUIRED,
            "consent not found",
        )
    if consent.revoked_at is None:
        consent.revoked_at = now or datetime.now(timezone.utc)
        session.flush()
    return consent


def consent_to_dict(row: WholeBookConsent) -> dict[str, Any]:
    def _dec(v: Any) -> str | None:
        return None if v is None else str(v)

    return {
        "id": row.id,
        "book_id": row.book_id,
        "estimate_id": row.estimate_id,
        "book_revision_hash": row.book_revision_hash,
        "mode": row.mode,
        "provider_config_id": row.provider_config_id,
        "model_name": row.model_name,
        "accepted_estimated_cost_max_cny": _dec(row.accepted_estimated_cost_max_cny),
        "user_budget_limit_cny": _dec(row.user_budget_limit_cny),
        "max_provider_calls": row.max_provider_calls,
        "max_input_tokens": row.max_input_tokens,
        "max_output_tokens": row.max_output_tokens,
        "auto_retry_enabled": row.auto_retry_enabled,
        "max_retries_per_unit": row.max_retries_per_unit,
        "accepted_at": row.accepted_at.isoformat() if row.accepted_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
    }
