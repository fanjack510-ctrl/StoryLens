"""Formal Whole-Book V2 cost/window estimate via Hierarchical planners (CHG-081).

Formal prepare / reanalysis confirmation MUST use the same planners as the
hierarchical pipeline (plan_windows / build_token_plan / build_cost_plan).
Never route formal V2 UI through the legacy Free / minimal estimator.
"""

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
from app.narrative_core.whole_book_v2.pipeline import (
    CHARS_PER_TOKEN,
    ChapterMeta,
    ProviderBudget,
    _group_count,
    build_cost_plan,
    build_token_plan,
    plan_windows,
)
from app.services.cloud_pricing import model_pricing_available, pricing_status
from app.services.provider_pricing import get_model_pricing, is_deepseek_model
from app.services.whole_book_source_fingerprint import compute_book_revision_hash_v1

HIERARCHICAL_ESTIMATE_VERSION = "whole_book_hierarchical_v2_estimate_v1"
CURRENCY = "CNY"
DEFAULT_EXPIRE_HOURS = 24
DEFAULT_TOPIC_COUNT = 7
DEFAULT_FINAL_SYNTHESIS_CALLS = 6


def _resolve_model_name(provider: ProviderConfiguration | None) -> str:
    if provider is None:
        return ""
    return str(provider.plus_model or "").strip()


def _chapter_char_counts(session: Session, book_id: int) -> list[tuple[int, int, int, str]]:
    """Return (chapter_id, chapter_index, char_count, title) ordered by chapter_index."""
    chapters = session.scalars(
        select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.chapter_index.asc())
    ).all()
    out: list[tuple[int, int, int, str]] = []
    for ch in chapters:
        paras = session.scalars(
            select(Paragraph)
            .where(Paragraph.chapter_id == ch.id)
            .order_by(Paragraph.paragraph_index.asc())
        ).all()
        chars = sum(len(p.normalized_text or p.raw_text or "") for p in paras)
        if chars <= 0:
            chars = len(ch.normalized_text or ch.raw_text or "")
        out.append(
            (
                int(ch.id),
                int(ch.chapter_index),
                max(0, int(chars)),
                str(ch.title or f"第{ch.chapter_index}章"),
            )
        )
    return out


def hierarchical_call_breakdown(*, window_count: int) -> dict[str, int]:
    extract = int(window_count)
    consolidation = _group_count(window_count) + DEFAULT_TOPIC_COUNT
    final_synthesis = DEFAULT_FINAL_SYNTHESIS_CALLS
    repair = max(
        1,
        math.ceil((extract + consolidation + final_synthesis) * 0.08),
    )
    total = extract + consolidation + final_synthesis + repair
    return {
        "extraction_calls": extract,
        "window_extraction_calls": extract,  # alias for older UI keys
        "consolidation_calls": consolidation,
        "final_synthesis_calls": final_synthesis,
        "repair_reserve_calls": repair,
        "chapter_function_batch_calls": 0,
        "estimated_total_calls": total,
    }


def build_provider_budget(*, provider_name: str, model_name: str) -> ProviderBudget:
    pricing = get_model_pricing(model_name) if model_name else None
    return ProviderBudget(
        provider=provider_name or "formal",
        model=model_name or "default",
        input_rate_per_mtok=float(pricing.input_cache_miss_per_1m) if pricing else 1.0,
        output_rate_per_mtok=float(pricing.output_per_1m) if pricing else 2.0,
    )


def plan_hierarchical_v2_for_book(
    session: Session,
    book_id: int,
    *,
    provider_name: str,
    model_name: str,
) -> dict[str, Any]:
    """Deterministic Hierarchical V2 plan — no Provider calls."""
    rows = _chapter_char_counts(session, book_id)
    chapter_count = len(rows)
    character_count = sum(r[2] for r in rows)
    paragraph_count = 0
    for ch_id, _, _, _ in rows:
        paragraph_count += len(
            session.scalars(select(Paragraph.id).where(Paragraph.chapter_id == ch_id)).all()
        )
    budget = build_provider_budget(provider_name=provider_name, model_name=model_name)
    if chapter_count == 0:
        return {
            "chapter_count": 0,
            "paragraph_count": 0,
            "character_count": 0,
            "window_count": 0,
            "token_plan": None,
            "cost_plan": None,
            "call_breakdown": hierarchical_call_breakdown(window_count=0),
            "context_safe": True,
            "budget": budget,
        }
    metas = [
        ChapterMeta(
            chapter_id=ch_id,
            chapter_index=ch_index if ch_index >= 1 else idx,
            title=title,
            text="",  # estimate uses token_hint — do not materialize full book text
            snapshot_id=0,
            revision_hash="hierarchical-estimate",
            token_hint=max(1, math.ceil(max(chars, 1) / CHARS_PER_TOKEN)),
        )
        for idx, (ch_id, ch_index, chars, title) in enumerate(rows, start=1)
    ]
    windows = plan_windows(metas, book_id=book_id, budget=budget)
    token_plan = build_token_plan(windows, budget=budget)
    token_plan = token_plan.model_copy(update={"chapter_count": chapter_count})
    cost_plan = build_cost_plan(token_plan, budget)
    return {
        "chapter_count": chapter_count,
        "paragraph_count": paragraph_count,
        "character_count": character_count,
        "window_count": len(windows),
        "token_plan": token_plan,
        "cost_plan": cost_plan,
        "call_breakdown": hierarchical_call_breakdown(window_count=len(windows)),
        "context_safe": token_plan.context_safe == "YES",
        "budget": budget,
    }


def estimate_hierarchical_whole_book_analysis_v1(
    session: Session,
    book_id: int,
    mode: WholeBookMode | str,
    provider_config_id: int,
    *,
    provider_name: str | None = None,
    now: datetime | None = None,
) -> tuple[WholeBookCostEstimate, dict[str, Any]]:
    """Persist a WholeBookCostEstimate row filled from Hierarchical V2 planners.

    Returns ``(estimate_row, plan_dict)`` so prepare can reuse context_safe / breakdown
    without a second full plan pass.
    """
    resolved_mode = mode if isinstance(mode, WholeBookMode) else WholeBookMode(str(mode))
    book = session.get(Book, book_id)
    if book is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_BOOK_CHANGED,
            f"book {book_id} not found",
        )
    provider = session.get(ProviderConfiguration, provider_config_id)
    model_name = _resolve_model_name(provider)
    resolved_provider_name = (
        str(provider_name or (provider.provider_name if provider else "") or "formal").strip()
    )

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
        elif is_deepseek_model(model_name) or model_pricing_available(model_name):
            pricing_status_value = "available"
            pricing_reason = None
        else:
            pricing_reason = "model_pricing_missing"

    plan = plan_hierarchical_v2_for_book(
        session,
        book_id,
        provider_name=resolved_provider_name,
        model_name=model_name or "default",
    )
    token_plan = plan["token_plan"]
    cost_plan = plan["cost_plan"]
    created = now or datetime.now(timezone.utc)
    expires = created + timedelta(hours=DEFAULT_EXPIRE_HOURS)
    revision_hash = compute_book_revision_hash_v1(session, book_id)

    cost_min: Decimal | None = None
    cost_max: Decimal | None = None
    if pricing_status_value == "available" and cost_plan is not None:
        cost_min = Decimal(str(cost_plan.estimated_cost_low))
        cost_max = Decimal(str(cost_plan.estimated_cost_high))

    window_count = int(plan["window_count"])
    if token_plan is None:
        input_tokens = 0
        output_tokens = 0
        total_calls = 0
    else:
        input_tokens = int(token_plan.estimated_input_tokens)
        output_tokens = int(token_plan.estimated_output_tokens)
        total_calls = int(token_plan.estimated_total_calls)

    # 同一本书、同一版本、同一读法、同一模型，预估就是同一个数——已经有那一行就别再写一行。
    #
    # 这个函数是「准备全书分析」页调的，而那个页面在有任务跑着时每 3 秒轮询一次。每调一次
    # 插一行，于是一个纯粹用来看的页面成了写入方，跟正在跑的分析抢同一把写锁：日志里那 84 次
    # `database is locked` 全是它；《我不是戏神》1299 章的估算又慢，撞得更狠，最后连它自己
    # 都 500，页面显示「本地分析服务暂时不可用」。
    #
    # 有效性就地判：书的版本哈希要一致（这一支存的是 compute_book_revision_hash_v1，跟
    # 旧路径那个不是同一个函数，不能借用它的校验器），且还没过期。model_name 也要比——
    # 换模型价格就变，复用旧行等于给出另一个模型的报价。计划照旧现算（纯读，不占写锁），
    # 因为 context_safe 不在表里，凭空复用等于猜。
    existing = session.scalars(
        select(WholeBookCostEstimate)
        .where(
            WholeBookCostEstimate.book_id == book_id,
            WholeBookCostEstimate.mode == resolved_mode.value,
            WholeBookCostEstimate.provider_config_id == provider_config_id,
            WholeBookCostEstimate.model_name == model_name,
            WholeBookCostEstimate.estimate_version == HIERARCHICAL_ESTIMATE_VERSION,
        )
        .order_by(WholeBookCostEstimate.id.desc())
        .limit(1)
    ).first()
    if existing is not None and existing.book_revision_hash == revision_hash:
        expires_at = existing.expires_at
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at is not None and created <= expires_at:
            return existing, plan

    row = WholeBookCostEstimate(
        book_id=book_id,
        book_revision_hash=revision_hash,
        mode=resolved_mode.value,
        provider_config_id=provider_config_id,
        model_name=model_name,
        chapter_count=int(plan["chapter_count"]),
        paragraph_count=int(plan["paragraph_count"]),
        character_count=int(plan["character_count"]),
        estimated_window_count=window_count,
        estimated_provider_call_count=total_calls,
        estimated_input_tokens=input_tokens,
        estimated_output_tokens=output_tokens,
        estimated_cost_min_cny=cost_min,
        estimated_cost_max_cny=cost_max,
        currency=CURRENCY,
        pricing_status=pricing_status_value,
        pricing_reason_code=pricing_reason,
        contract_version=WHOLE_BOOK_CONTRACT_VERSION,
        estimate_version=HIERARCHICAL_ESTIMATE_VERSION,
        created_at=created,
        expires_at=expires,
    )
    session.add(row)
    session.flush()
    return row, plan


def hierarchical_estimate_to_dict(row: WholeBookCostEstimate) -> dict[str, Any]:
    """Serialize estimate with Hierarchical call breakdown (not legacy CF batches)."""

    def _dec(v: Any) -> str | None:
        return None if v is None else str(v)

    breakdown = hierarchical_call_breakdown(window_count=int(row.estimated_window_count or 0))
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
        "call_breakdown": breakdown,
        "estimated_chapter_function_batches": 0,
        "estimated_chapter_function_repair_reserve": breakdown["repair_reserve_calls"],
        "chapter_function_repair_strategy": "hierarchical_repair_reserve",
        "estimated_input_tokens": row.estimated_input_tokens,
        "estimated_output_tokens": row.estimated_output_tokens,
        "estimated_cost_min_cny": _dec(row.estimated_cost_min_cny),
        "estimated_cost_max_cny": _dec(row.estimated_cost_max_cny),
        "currency": row.currency,
        "pricing_status": row.pricing_status,
        "pricing_reason_code": row.pricing_reason_code,
        "contract_version": row.contract_version,
        "estimate_version": row.estimate_version,
        "planner": "hierarchical_v2",
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
    }


def is_hierarchical_estimate(row: WholeBookCostEstimate | dict[str, Any] | None) -> bool:
    if row is None:
        return False
    if isinstance(row, dict):
        ver = str(row.get("estimate_version") or "")
        return ver == HIERARCHICAL_ESTIMATE_VERSION or row.get("planner") == "hierarchical_v2"
    return str(row.estimate_version or "") == HIERARCHICAL_ESTIMATE_VERSION


__all__ = [
    "HIERARCHICAL_ESTIMATE_VERSION",
    "build_provider_budget",
    "estimate_hierarchical_whole_book_analysis_v1",
    "hierarchical_call_breakdown",
    "hierarchical_estimate_to_dict",
    "is_hierarchical_estimate",
    "plan_hierarchical_v2_for_book",
]
