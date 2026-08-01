"""Whole-book cost estimation (WB-0.3) — no Snapshot creation, no Provider calls."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Book, Chapter, Paragraph, ProviderConfiguration, WholeBookCostEstimate
from app.narrative_core.contracts.whole_book_contract_v1 import (
    WHOLE_BOOK_CONTRACT_VERSION,
    WholeBookMode,
)
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)
from app.services.cloud_pricing import estimate_cost, model_pricing_available, pricing_status
from app.services.transition_batch_planner import conservative_token_estimate
from app.services.whole_book_source_fingerprint import compute_book_revision_hash_v1

ESTIMATE_VERSION = "whole_book_cost_estimate_v1"
TARGET_INPUT_TOKENS_PER_WINDOW = 18000
RESERVED_OUTPUT_TOKENS_PER_WINDOW = 3000
WINDOW_OVERLAP_RATIO = 0.08
SYNTHESIS_OUTPUT_TOKENS = 6000
SYNTHESIS_INPUT_TOKENS_BASE = 4000
DEFAULT_EXPIRE_HOURS = 24
CURRENCY = "CNY"


def compute_book_revision_hash(session: Session, book_id: int) -> str:
    """Back-compat alias — delegates to unified v1 fingerprint."""
    return compute_book_revision_hash_v1(session, book_id)


def _book_counts(session: Session, book_id: int) -> tuple[int, int, int]:
    chapters = session.scalars(
        select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.chapter_index.asc())
    ).all()
    chapter_count = len(chapters)
    paragraph_count = 0
    character_count = 0
    for ch in chapters:
        paras = session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == ch.id)
            .order_by(Paragraph.paragraph_index.asc())
        ).all()
        paragraph_count += len(paras)
        for p in paras:
            character_count += len(p.normalized_text or p.raw_text or "")
    return chapter_count, paragraph_count, character_count


def _estimate_window_count(total_input_tokens: int) -> int:
    if total_input_tokens <= 0:
        return 0
    effective = TARGET_INPUT_TOKENS_PER_WINDOW * (1.0 - WINDOW_OVERLAP_RATIO)
    if effective <= 0:
        effective = float(TARGET_INPUT_TOKENS_PER_WINDOW)
    return max(1, int(math.ceil(total_input_tokens / effective)))


def _resolve_model_name(provider: ProviderConfiguration | None) -> str:
    if provider is None:
        return ""
    return str(provider.plus_model or provider.max_model or provider.flash_model or "").strip()


def estimate_whole_book_analysis(
    session: Session,
    book_id: int,
    mode: WholeBookMode | str,
    provider_config_id: int,
    *,
    now: datetime | None = None,
) -> WholeBookCostEstimate:
    resolved_mode = mode if isinstance(mode, WholeBookMode) else WholeBookMode(str(mode))
    book = session.get(Book, book_id)
    if book is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_BOOK_CHANGED,
            f"book {book_id} not found",
        )

    provider = session.get(ProviderConfiguration, provider_config_id)
    model_name = _resolve_model_name(provider)
    pricing_status_value = "unavailable"
    pricing_reason: str | None = "provider_config_missing"
    if provider is None:
        pricing_reason = "provider_config_missing"
    elif not model_name:
        pricing_reason = "unsupported_model"
    else:
        status = pricing_status()
        if not status.get("enabled"):
            pricing_reason = "model_pricing_missing"
        elif not model_pricing_available(model_name):
            pricing_reason = "model_pricing_missing"
        else:
            pricing_status_value = "available"
            pricing_reason = None

    chapter_count, paragraph_count, character_count = _book_counts(session, book_id)
    revision_hash = compute_book_revision_hash(session, book_id)
    created = now or datetime.now(timezone.utc)
    expires = created + timedelta(hours=DEFAULT_EXPIRE_HOURS)

    if chapter_count == 0 and paragraph_count == 0 and character_count == 0:
        row = WholeBookCostEstimate(
            book_id=book_id,
            book_revision_hash=revision_hash,
            mode=resolved_mode.value,
            provider_config_id=provider_config_id,
            model_name=model_name,
            chapter_count=0,
            paragraph_count=0,
            character_count=0,
            estimated_window_count=0,
            estimated_provider_call_count=0,
            estimated_input_tokens=0,
            estimated_output_tokens=0,
            estimated_cost_min_cny=None,
            estimated_cost_max_cny=None,
            currency=CURRENCY,
            pricing_status="unavailable",
            pricing_reason_code="book_empty",
            contract_version=WHOLE_BOOK_CONTRACT_VERSION,
            estimate_version=ESTIMATE_VERSION,
            created_at=created,
            expires_at=expires,
        )
        session.add(row)
        session.flush()
        return row

    # Generic project estimator — no novel-specific rules.
    proxy_text = ("汉" if character_count > 0 else "a") * min(max(character_count, 1), 50_000)
    sample_tokens = conservative_token_estimate(proxy_text)
    if character_count > len(proxy_text):
        total_input_tokens = int(math.ceil(sample_tokens * (character_count / len(proxy_text))))
    else:
        total_input_tokens = sample_tokens

    window_count = _estimate_window_count(total_input_tokens)
    window_input_tokens = window_count * TARGET_INPUT_TOKENS_PER_WINDOW
    synthesis_input = SYNTHESIS_INPUT_TOKENS_BASE + min(8000, window_count * 200)
    estimated_input = window_input_tokens + synthesis_input
    estimated_output = window_count * RESERVED_OUTPUT_TOKENS_PER_WINDOW + SYNTHESIS_OUTPUT_TOKENS
    # Window units + overview synthesis + structure_stages unit (WB-2.1).
    provider_calls = 0 if window_count == 0 else window_count + 2

    cost_min: Decimal | None = None
    cost_max: Decimal | None = None
    if pricing_status_value == "available" and model_name:
        base, currency, _ver = estimate_cost(model_name, estimated_input, estimated_output)
        if base is None:
            pricing_status_value = "unavailable"
            pricing_reason = "model_pricing_missing"
        elif currency and str(currency).upper() != CURRENCY:
            pricing_status_value = "unavailable"
            pricing_reason = "model_pricing_missing"
        else:
            cost_min = Decimal(str(round(base * 0.85, 6)))
            cost_max = Decimal(str(round(base * 1.25, 6)))

    row = WholeBookCostEstimate(
        book_id=book_id,
        book_revision_hash=revision_hash,
        mode=resolved_mode.value,
        provider_config_id=provider_config_id,
        model_name=model_name,
        chapter_count=chapter_count,
        paragraph_count=paragraph_count,
        character_count=character_count,
        estimated_window_count=window_count,
        estimated_provider_call_count=provider_calls,
        estimated_input_tokens=estimated_input,
        estimated_output_tokens=estimated_output,
        estimated_cost_min_cny=cost_min,
        estimated_cost_max_cny=cost_max,
        currency=CURRENCY,
        pricing_status=pricing_status_value,
        pricing_reason_code=pricing_reason,
        contract_version=WHOLE_BOOK_CONTRACT_VERSION,
        estimate_version=ESTIMATE_VERSION,
        created_at=created,
        expires_at=expires,
    )
    session.add(row)
    session.flush()
    return row


def is_estimate_valid(
    session: Session,
    estimate: WholeBookCostEstimate,
    *,
    now: datetime | None = None,
    provider_config_id: int | None = None,
    model_name: str | None = None,
) -> tuple[bool, str | None]:
    current = now or datetime.now(timezone.utc)
    exp = estimate.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if current > exp:
        return False, WholeBookFoundationErrorCode.WHOLE_BOOK_ESTIMATE_EXPIRED.value
    if compute_book_revision_hash(session, estimate.book_id) != estimate.book_revision_hash:
        return False, WholeBookFoundationErrorCode.WHOLE_BOOK_BOOK_CHANGED.value
    if provider_config_id is not None and provider_config_id != estimate.provider_config_id:
        return False, WholeBookFoundationErrorCode.WHOLE_BOOK_ESTIMATE_EXPIRED.value
    if model_name is not None and model_name != estimate.model_name:
        return False, WholeBookFoundationErrorCode.WHOLE_BOOK_ESTIMATE_EXPIRED.value
    return True, None


def estimate_to_dict(row: WholeBookCostEstimate) -> dict[str, Any]:
    def _dec(v: Any) -> str | None:
        return None if v is None else str(v)

    return {
        "id": row.id,
        "book_id": row.book_id,
        "book_revision_hash": row.book_revision_hash,
        "mode": row.mode,
        "provider_config_id": row.provider_config_id,
        "model_name": row.model_name,
        "chapter_count": row.chapter_count,
        "paragraph_count": row.paragraph_count,
        "character_count": row.character_count,
        "estimated_window_count": row.estimated_window_count,
        "estimated_provider_call_count": row.estimated_provider_call_count,
        "estimated_input_tokens": row.estimated_input_tokens,
        "estimated_output_tokens": row.estimated_output_tokens,
        "estimated_cost_min_cny": _dec(row.estimated_cost_min_cny),
        "estimated_cost_max_cny": _dec(row.estimated_cost_max_cny),
        "currency": row.currency,
        "pricing_status": row.pricing_status,
        "pricing_reason_code": row.pricing_reason_code,
        "contract_version": row.contract_version,
        "estimate_version": row.estimate_version,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
    }
