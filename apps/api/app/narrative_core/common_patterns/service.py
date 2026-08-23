"""共性视图：把一组书摆在一起，看它们共同做对了什么。

扫榜的最后一步是「横着比」——十几本新书各自的开篇拆完之后，真正要回答的是「它们共同做了
什么」。一本一本读完再自己归纳，是这件事最耗人的一段，也是唯一非做不可的一段。

两层：
  · 能数的先数清楚（`aggregate`）——类型分布、钩子密度、覆盖范围。免费，可核对，不调模型。
  · 归纳交给模型（`synthesize`）——一次调用，结果逐条验证引用。这一层是 Pro。

分成两层不只是省钱。数出来的东西任何时候都成立，而归纳出来的东西需要被检验——把两者
放在同一个结果里但标明来源，读的人才知道哪一半可以直接信。
"""

from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy.orm import Session

from app.narrative_core.common_patterns.aggregate import BookFacts, collect_facts, count_genres
from app.narrative_core.common_patterns.ledger import record_synthesis_call
from app.narrative_core.common_patterns.synthesize import (
    MIN_BOOKS,
    build_prompt,
    parse_and_verify,
)

__all__ = ["CommonPatternsError", "build_overview", "synthesize_patterns"]


class CommonPatternsError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _book_row(f: BookFacts) -> dict[str, Any]:
    return {
        "book_id": f.book_id,
        "title": f.title,
        "usable": f.usable,
        "excluded_reason": f.excluded_reason,
        "primary_genre": f.primary_genre,
        "chapters_analysed": f.chapters_analysed,
        "chapters_total": f.chapters_total,
        "scope_kind": f.scope_kind,
        # 「只拆了开篇」这件事要跟着这本书走到最后：五章的观察不能冒充整本的规律。
        "scope_label": (
            f"开篇 {f.chapters_analysed} 章 / 全书 {f.chapters_total} 章"
            if f.scope_kind == "opening"
            else f"全书 {f.chapters_total} 章"
        ),
        "technique_count": len(f.techniques),
        "hook_count": f.hook_count,
        "hooks_per_chapter": f.hooks_per_chapter,
        "standout_moment_count": f.standout_moment_count,
    }


def build_overview(session: Session, book_ids: list[int]) -> dict[str, Any]:
    """能数出来的那一半。不调模型，因此免费——数出来的东西不该收费。"""
    facts = collect_facts(session, [int(b) for b in book_ids])
    usable = [f for f in facts if f.usable]
    openings = [f for f in usable if f.scope_kind == "opening"]
    return {
        "books": [_book_row(f) for f in facts],
        "usable_count": len(usable),
        "total_count": len(facts),
        "genres": [{"genre": g, "count": n} for g, n in count_genres(facts)],
        "technique_total": sum(len(f.techniques) for f in usable),
        # 有多少本只拆了开篇。混着比不是错，但读结论的人得知道自己在比什么。
        "opening_only_count": len(openings),
        "mixed_scope": bool(openings) and len(openings) != len(usable),
        "can_synthesize": len(usable) >= MIN_BOOKS,
        "min_books": MIN_BOOKS,
        "blocked_reason": (
            ""
            if len(usable) >= MIN_BOOKS
            else f"至少要有 {MIN_BOOKS} 本拆过文的书才谈得上共性——现在只有 {len(usable)} 本。"
        ),
    }


def synthesize_patterns(
    session: Session, book_ids: list[int], *, collection_id: int = 0
) -> dict[str, Any]:
    """归纳那一半。一次模型调用，结果逐条验证引用。"""
    facts = collect_facts(session, [int(b) for b in book_ids])
    usable = [f for f in facts if f.usable]
    if len(usable) < MIN_BOOKS:
        raise CommonPatternsError(
            "NOT_ENOUGH_BOOKS",
            f"至少要有 {MIN_BOOKS} 本拆过文的书才谈得上共性——现在只有 {len(usable)} 本。",
        )

    from app.model_gateway.base import ModelRequest
    from app.narrative_core.services.whole_book_active_provider_v1 import (
        active_provider_availability,
    )
    from app.narrative_core.services.whole_book_provider_gateway import _run_async
    from app.narrative_core.services.whole_book_v2_formal_pipeline_v1 import _bind_formal_gateway

    row, provider_name, blockers = active_provider_availability(session)
    if row is None or blockers:
        raise CommonPatternsError(
            "PROVIDER_UNAVAILABLE",
            blockers[0] if blockers else "AI 服务尚未连接，请先在设置里完成配置。",
        )
    # ProviderConfiguration 上没有 `model_name`——它有 plus / max / flash 三档。
    # 之前照着别处抄了一个不存在的字段名，`getattr` 默认值把它变成空字符串，
    # 于是模型名一路空着送进网关：不报错，只是发出去的请求没说要用哪个模型。
    from app.narrative_core.services.whole_book_cost_estimate_service import _resolve_model_name

    model = _resolve_model_name(row)
    if not model:
        raise CommonPatternsError(
            "PROVIDER_UNAVAILABLE", "当前服务商没有配置可用模型，请先在设置里选一个。"
        )
    gateway = _bind_formal_gateway(session, provider_name=provider_name)

    prompt = build_prompt(facts)
    started = time.monotonic()
    response = _run_async(
        gateway.generate(
            provider_name,
            ModelRequest(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                # 归纳要稳定：同一组书、同一批技法，两次跑出来的共性该基本一致，
                # 否则用户会以为自己看到的是随机的意见。
                temperature=0.1,
                max_output_tokens=3000,
                enable_thinking=False,
            ),
        )
    )
    # 钱花掉了就要记上，不管后面解析成不成功——用量页面回答的是「我花了多少」，
    # 而一次解析失败的调用照样是付过费的。
    record_synthesis_call(
        session,
        collection_id=int(collection_id),
        book_ids=[f.book_id for f in usable],
        provider_name=provider_name,
        model=model,
        prompt=prompt,
        response=response,
        latency_ms=int((time.monotonic() - started) * 1000),
    )
    text = getattr(response, "text", None) or getattr(response, "content", None) or str(response)
    verified = parse_and_verify(_extract_json(text), facts)
    if verified.get("parse_failed"):
        raise CommonPatternsError("SYNTHESIS_UNREADABLE", "这次归纳没有返回可读的结果，请重试。")

    return {
        **build_overview(session, book_ids),
        "patterns": verified["patterns"],
        "not_shared": verified["not_shared"],
        # 被丢掉的条目留在结果里。不显示给普通用户，但它是「这份结果被核对过」的证据——
        # 一个从不丢东西的验证器和没有验证器是一回事。
        "dropped": verified["dropped"],
        "provider_name": provider_name,
        "model_name": model,
    }


def _extract_json(text: str) -> Any:
    """模型经常把 JSON 包在 ```json 里，或者前面带一句「好的，以下是」。"""
    raw = (text or "").strip()
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            candidate = part.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            if candidate.startswith("{"):
                raw = candidate
                break
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start : end + 1]
    try:
        return json.loads(raw)
    except ValueError:
        return raw
