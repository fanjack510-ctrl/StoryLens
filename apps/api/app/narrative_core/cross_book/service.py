"""跨书检索的服务层。

两个入口，两种价钱，和共性视图同一条线：
  · `search` 关键词——确定、即时、可核对，覆盖全部条目。免费。搜索框不该收费。
  · `find_by_meaning` 按意思——一次模型调用，只覆盖写法层。Pro。
"""

from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy.orm import Session

from app.narrative_core.cross_book.index import CRAFT_KINDS, KIND_LABELS, build_index
from app.narrative_core.cross_book.search import DEFAULT_LIMIT, keyword_search
from app.narrative_core.cross_book.semantic import (
    MAX_CANDIDATES,
    build_prompt,
    parse_and_verify,
)

__all__ = ["CrossBookError", "find_by_meaning", "search", "search_scope"]


class CrossBookError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def search_scope(session: Session, book_ids: list[int] | None = None) -> dict[str, Any]:
    """检索能覆盖到什么。

    用户按下搜索之前该知道自己在搜多大范围——「没找到」在「搜了三本书」和「搜了八十本」
    之下是完全不同的两个结论。
    """
    items = build_index(session, book_ids)
    by_kind: dict[str, int] = {}
    books: dict[int, str] = {}
    for item in items:
        by_kind[item.kind] = by_kind.get(item.kind, 0) + 1
        books[item.book_id] = item.book_title
    craft = sum(by_kind.get(k, 0) for k in CRAFT_KINDS)
    return {
        "book_count": len(books),
        "books": [{"book_id": b, "title": t} for b, t in sorted(books.items())],
        "item_count": len(items),
        "craft_count": craft,
        "kinds": [
            {"kind": k, "label": KIND_LABELS.get(k, k), "count": n}
            for k, n in sorted(by_kind.items(), key=lambda kv: -kv[1])
        ],
    }


def search(
    session: Session,
    query: str,
    *,
    book_ids: list[int] | None = None,
    kinds: list[str] | None = None,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """关键词检索。免费。"""
    items = build_index(session, book_ids)
    return keyword_search(items, query, kinds=kinds, limit=limit)


def find_by_meaning(
    session: Session,
    query: str,
    *,
    book_ids: list[int] | None = None,
) -> dict[str, Any]:
    """按意思找。Pro。一次模型调用，结果逐条核对编号。"""
    text = (query or "").strip()
    if not text:
        raise CrossBookError("QUERY_REQUIRED", "说说你在找什么。")

    items = build_index(session, book_ids)
    candidates = [i for i in items if i.is_craft]
    if not candidates:
        raise CrossBookError(
            "NOTHING_TO_SEARCH",
            "还没有可以按意思检索的内容——它来自拆文的产出，先跑一次拆解。",
        )

    truncated = len(candidates) > MAX_CANDIDATES
    used = candidates[:MAX_CANDIDATES]

    from app.model_gateway.base import ModelRequest
    from app.narrative_core.services.whole_book_active_provider_v1 import (
        active_provider_availability,
    )
    from app.narrative_core.services.whole_book_cost_estimate_service import _resolve_model_name
    from app.narrative_core.services.whole_book_provider_gateway import _run_async
    from app.narrative_core.services.whole_book_v2_formal_pipeline_v1 import _bind_formal_gateway

    row, provider_name, blockers = active_provider_availability(session)
    if row is None or blockers:
        raise CrossBookError(
            "PROVIDER_UNAVAILABLE",
            blockers[0] if blockers else "AI 服务尚未连接，请先在设置里完成配置。",
        )
    model = _resolve_model_name(row)
    if not model:
        raise CrossBookError(
            "PROVIDER_UNAVAILABLE", "当前服务商没有配置可用模型，请先在设置里选一个。"
        )

    prompt = build_prompt(text, used)
    started = time.monotonic()
    response = _run_async(
        gateway_generate(
            _bind_formal_gateway(session, provider_name=provider_name),
            provider_name,
            ModelRequest(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                # 检索要稳定：同一个问题问两次，结果该基本一致。
                temperature=0.1,
                max_output_tokens=1500,
                enable_thinking=False,
            ),
        )
    )
    from app.narrative_core.common_patterns.ledger import record_synthesis_call

    record_synthesis_call(
        session,
        collection_id=0,
        book_ids=sorted({i.book_id for i in used}),
        provider_name=provider_name,
        model=model,
        prompt=prompt,
        response=response,
        latency_ms=int((time.monotonic() - started) * 1000),
        task_type="cross_book_search",
    )

    raw = getattr(response, "text", None) or getattr(response, "content", None) or ""
    verified = parse_and_verify(_extract_json(raw), used)
    if verified.get("parse_failed"):
        raise CrossBookError("SEARCH_UNREADABLE", "这次检索没有返回可读的结果，请重试。")

    return {
        "query": text,
        "matches": verified["matches"],
        "dropped": verified["dropped"],
        # 覆盖范围要说出来。用户以为搜了全部、其实只搜了写法层，
        # 「没找到」就会被读成「这些书里没有」——那是一个错的结论。
        "searched_craft_items": len(used),
        "total_craft_items": len(candidates),
        "truncated": truncated,
        "scope_note": (
            "按意思检索只覆盖「写法」层——技法、高光片段、配角功能、主要人物。"
            "章末钩子、逐章功能和原文证据不在其中，那些用上面的关键词检索。"
        ),
        "provider_name": provider_name,
        "model_name": model,
    }


def gateway_generate(gateway, provider_name, request):
    return gateway.generate(provider_name, request)


def _extract_json(text: str) -> Any:
    raw = (text or "").strip()
    if "```" in raw:
        for part in raw.split("```"):
            candidate = part.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            if candidate.startswith("{"):
                raw = candidate
                break
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start : end + 1]
    try:
        return json.loads(raw)
    except ValueError:
        return raw
