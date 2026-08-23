"""共性视图的用量记账。

用户自己付模型费。一次花掉钱的调用如果账本上看不见，「这个月我在 StoryLens 上花了多少」
这个问题就没有答案，而那正是用量页面存在的理由。

第一版直接调网关、不记账——三次真实调用花掉的钱，`model_invocations` 里一行都没有。
这个文件补上那一行。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, ModelInvocation
from app.services.cloud_pricing import estimate_cost

__all__ = ["record_synthesis_call"]

PROMPT_VERSION = "common-patterns-1.0"
SCHEMA_VERSION = "common-patterns-1.0"


def record_synthesis_call(
    session: Session,
    *,
    collection_id: int,
    book_ids: list[int],
    provider_name: str,
    model: str,
    prompt: str,
    response: Any,
    latency_ms: int,
    status: str = "succeeded",
    #: 账本上这是哪一件事。共性视图和跨书检索都走这里，混成一个名字之后
    #: 「这个月共性视图花了多少」就没法回答了。
    task_type: str = "common_patterns",
) -> None:
    """一次归纳＝一条运行 + 一条调用记录。

    记账失败不该让归纳失败——用户已经付过这次调用的钱，结果该给他。所以整个函数
    包在一个 except 里：账没记上是我们的问题，不是他的。
    """
    try:
        now = datetime.now(timezone.utc)
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        run = AnalysisRun(
            task_type=task_type,
            subject_type="collection" if collection_id else "library",
            subject_id=str(int(collection_id)),
            provider=provider_name,
            model=model,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            input_hash=prompt_hash,
            prompt_hash=prompt_hash,
            status=status,
            started_at=now,
            execution_mode="cloud",
            analysis_mode=task_type,
            cloud_consent=True,
            cloud_consent_at=now,
            sends_content_to_cloud=True,
            content_hash=prompt_hash,
        )
        session.add(run)
        session.flush()

        # token 直接挂在 ModelResponse 上，不在 `.usage` 下面。第一版照着别处的写法找
        # `response.usage`，`getattr` 默认值把它变成 0——于是账本上多了一行「这次调用
        # 花了 0 token、0 元」。一条说自己免费的付费记录，比没有记录更糟：日费用闸门
        # 是按这些数字拦人的。
        text = getattr(response, "text", None) or getattr(response, "content", None) or ""
        input_tokens = int(getattr(response, "input_tokens", 0) or 0)
        output_tokens = int(getattr(response, "output_tokens", 0) or 0)
        total_tokens = int(getattr(response, "total_tokens", 0) or 0) or (
            input_tokens + output_tokens
        )
        # 定价表里没有这个模型时返回 None，那就写 NULL——宁可空着，也不要编一个价钱。
        cost, currency, pricing_version = estimate_cost(model, input_tokens, output_tokens)
        session.add(
            ModelInvocation(
                run_id=int(run.id),
                task_type=task_type,
                provider_name=provider_name,
                model_name=model,
                prompt_version=PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
                attempt_no=1,
                invocation_kind="initial",
                request_hash=prompt_hash,
                # 不存提示词原文：里面是用户书里的技法描述。存的是这次比了哪几本、多大。
                input_snapshot_json=json.dumps(
                    {
                        "collection_id": int(collection_id),
                        "book_ids": [int(b) for b in book_ids],
                        "prompt_chars": len(prompt),
                    },
                    sort_keys=True,
                    ensure_ascii=False,
                ),
                raw_response_text="",
                status=status,
                latency_ms=int(latency_ms),
                is_cloud=True,
                sends_content_to_cloud=True,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                estimated_cost=cost,
                currency=currency or "CNY",
                pricing_version=pricing_version,
                http_status_code=getattr(response, "http_status_code", None),
                response_model_name=getattr(response, "model", None) or model,
                request_id=getattr(response, "request_id", None),
                finish_reason=getattr(response, "finish_reason", None),
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest() if text else "",
                created_at=now,
            )
        )
        session.flush()
    except Exception:  # noqa: BLE001 — 记账失败不该吞掉用户已经付费拿到的结果
        import logging

        logging.getLogger(__name__).exception(
            "common_patterns_usage_not_recorded collection_id=%s", collection_id
        )
