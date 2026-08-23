"""挑出一本书该用哪份分析文档。

一本书可能有好几份：重跑过、换过读法、或者先拆了整本又拆了一次开篇。「用哪一份」这个问题
只有一个正确答案，所以它只该有一处实现。

**读得最多的那份赢，而不是最新的那份。** 开篇拆解只读前五章，它比整本分析新，但它不该
让整本分析作废——那是一次更窄的阅读，不是一次更正确的阅读。按「最新」挑，一个先拆了
542 章、后来又花两毛钱拆了开篇的用户，会发现自己的整本结果从检索和共性视图里消失了。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import WholeBookCheckpoint, WholeBookRun

__all__ = ["RESULT_STAGE", "all_documents", "best_document", "by_coverage", "by_techniques"]

#: 存全书分析文档的检查点阶段。
RESULT_STAGE = "v2_result"


def _coverage(doc: dict[str, Any]) -> int:
    """这份文档读了多少章。读不出来时按 0 算——那样它只会在没有别的选择时被选中。"""
    meta = doc.get("analysis_metadata") or {}
    cov = meta.get("coverage") or {}
    try:
        return int(cov.get("chapters_analysed") or 0)
    except (TypeError, ValueError):
        return 0


def technique_count(doc: dict[str, Any]) -> int:
    """这份文档里有几条可复用技法。"""
    breakdown = doc.get("story_breakdown") or {}
    return len(breakdown.get("reusable_techniques") or [])


def by_coverage(doc: dict[str, Any]) -> tuple:
    """读得最多的赢。跨书检索用这个——条目越多，能被找到的东西越多。"""
    return (_coverage(doc),)


def by_techniques(doc: dict[str, Any]) -> tuple:
    """有技法的赢，其次才看读得多不多。

    共性视图比的是「怎么写的」，而那只有拆文才产出。《余罪》整本那次跑的是 partial 拆文，
    技法零条；后来只拆了五章的那次有六条。按覆盖挑会选中前者，于是这本书对共性视图
    毫无贡献——用户看着一本明明拆过文的书被标成「没有拆文」。
    """
    return (technique_count(doc) > 0, technique_count(doc), _coverage(doc))


def all_documents(session: Session, book_id: int) -> list[dict[str, Any]]:
    """这本书所有能读出来的分析文档，覆盖多的在前。

    给跨书检索用。检索不需要在几份文档之间二选一——它要的是「这本书里出现过的东西」，
    而那是几份文档的**并集**：整本那次留下了逐章的钩子和证据，只拆开篇那次留下了技法。
    挑其中一份，另一份里的东西就从检索里消失了，而用户并不知道自己搜不到它。
    """
    out: list[tuple[tuple, dict[str, Any]]] = []
    for run_id, raw in _rows(session, book_id):
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict) and parsed.get("book_metadata"):
            out.append(((_coverage(parsed), int(run_id)), parsed))
    out.sort(key=lambda pair: pair[0], reverse=True)
    return [doc for _, doc in out]


def _rows(session: Session, book_id: int):
    return session.execute(
        select(
            WholeBookCheckpoint.run_id,
            WholeBookCheckpoint.checkpoint_payload_json,
        )
        .join(WholeBookRun, WholeBookRun.id == WholeBookCheckpoint.run_id)
        .where(
            WholeBookRun.book_id == int(book_id),
            WholeBookCheckpoint.stage_code == RESULT_STAGE,
            WholeBookCheckpoint.checkpoint_key == "latest",
        )
    ).all()


def best_document(
    session: Session,
    book_id: int,
    *,
    key: Any = None,
) -> dict[str, Any] | None:
    """这本书最值得用的那份分析文档。

    「最值得」取决于问的是什么，所以排序函数由调用方给：跨书检索要条目多（`by_coverage`），
    共性视图要有技法（`by_techniques`）。默认按覆盖。同分时取运行号大的那份。

    一份都读不出来时返回 None——没有文档和有一份读不出来的文档，对调用方是同一件事。
    """
    rank_fn = key or by_coverage
    rows = _rows(session, book_id)

    best: tuple[tuple, dict[str, Any]] | None = None
    for run_id, raw in rows:
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(parsed, dict) or not parsed.get("book_metadata"):
            continue
        rank = (*rank_fn(parsed), int(run_id))
        if best is None or rank > best[0]:
            best = (rank, parsed)
    return best[1] if best else None
