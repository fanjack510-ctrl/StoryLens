"""Wire 短篇精读 to a real provider and a book.

Thin on purpose. `pipeline.run_short_form` is pure — it takes paragraphs and a provider and
returns a report — so everything that knows about the database, the gateway and the ledger
lives here and can be replaced without touching the reading logic.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.narrative_core.short_form.contracts import ShortFormResult
from app.narrative_core.short_form.dispatch import book_is_short_form
from app.narrative_core.short_form.pipeline import ShortFormReport, run_short_form

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "你是小说文本的分析器。只输出严格 JSON，不要代码块围栏，不要任何解释文字。"
    "只写正文里写明或可直接指认的内容，不要编造原文里没有的情节、人物或台词。"
)


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("short-form pipeline must not be called from a running event loop")


class _GatewayProvider:
    """The gateway, shaped the way `run_short_form` expects: payload in, raw text out."""

    def __init__(self, gateway: Any, *, provider_name: str, model_name: str) -> None:
        self._gateway = gateway
        self._provider_name = provider_name
        self._model_name = model_name
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def complete(self, *, payload: dict[str, Any], max_output_tokens: int) -> str:
        from app.model_gateway.base import ModelRequest

        parts = [str(payload.get("instruction") or "")]
        if payload.get("lens"):
            parts.append(str(payload["lens"]))
        if payload.get("text"):
            parts.append("正文如下：\n" + str(payload["text"]))
        if payload.get("segments"):
            import json

            parts.append("分段如下：\n" + json.dumps(payload["segments"], ensure_ascii=False))
        response = _run_async(
            self._gateway.generate(
                self._provider_name,
                ModelRequest(
                    model=self._model_name,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": "\n\n".join(p for p in parts if p)},
                    ],
                    temperature=0.0,
                    max_output_tokens=max_output_tokens,
                    response_format_mode="json_object",
                    enable_thinking=False,
                ),
            )
        )
        self.calls += 1
        self.input_tokens += int(getattr(response, "input_tokens", 0) or 0)
        self.output_tokens += int(getattr(response, "output_tokens", 0) or 0)
        return str(getattr(response, "text", "") or "")


def load_paragraphs(session: Session, book_id: int) -> tuple[str, list[str]]:
    """The whole piece as paragraphs, in reading order.

    Chapters are flattened deliberately: a short piece is read in one sitting, and whether its
    author marked chapter breaks is not something the analysis should depend on. This is the
    same property that lets the pipeline handle a piece with no chapter markers at all.
    """
    title = session.execute(
        text("SELECT title FROM books WHERE id = :book_id"), {"book_id": int(book_id)}
    ).scalar() or ""
    rows = session.execute(
        text(
            "SELECT p.raw_text FROM paragraphs p JOIN chapters c ON c.id = p.chapter_id "
            "WHERE p.book_id = :book_id ORDER BY c.chapter_index, p.paragraph_index"
        ),
        {"book_id": int(book_id)},
    ).scalars()
    return str(title), [str(r) for r in rows if str(r or "").strip()]


def analyse_short_form(
    session: Session,
    book_id: int,
    *,
    genre: str = "",
    provider_name: str = "",
    model_name: str = "",
    use_fake_provider: Any | None = None,
) -> ShortFormReport:
    if not book_is_short_form(session, int(book_id)):
        raise ValueError("book is not short-form; use the whole-book pipeline")

    title, paragraphs = load_paragraphs(session, int(book_id))
    if use_fake_provider is not None:
        provider: Any = use_fake_provider
    else:
        from app.narrative_core.services.whole_book_v2_formal_pipeline_v1 import (
            _bind_formal_gateway,
        )

        gateway = _bind_formal_gateway(session, provider_name=provider_name)
        provider = _GatewayProvider(
            gateway, provider_name=provider_name, model_name=model_name
        )

    report = run_short_form(
        provider=provider, paragraphs=paragraphs, title=title, genre=genre
    )
    logger.info(
        "short_form_run book_id=%s segments=%s calls=%s in=%s out=%s",
        book_id,
        report.segments_planned,
        report.provider_calls,
        getattr(provider, "input_tokens", 0),
        getattr(provider, "output_tokens", 0),
    )
    return report


def result_or_empty(report: ShortFormReport) -> ShortFormResult:
    return report.result or ShortFormResult()
