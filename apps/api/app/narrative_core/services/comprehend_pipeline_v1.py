"""「读懂」的执行入口：把一次全书任务跑成一份专著/工具书报告。

它挂在跟评测、拆文同一套任务机制上——同一个 WholeBookRun、同一张进度、同一本记账、同一个
心跳。这不是图省事：那套东西今天刚被打磨过（重复任务防护、心跳判活、写锁风暴），另起一套等
于把那些坑重新踩一遍。

**但引擎完全不同。** 小说那条线要花 163 次调用去猜结构（起承转合），专著的结构是白给的：章首
自带带页码的小节目录，正文每节又以同样的编号起头。所以这里没有窗口规划、没有连续性链，只有
「哪些节合成一次调用」。

**结果单独存。** 评测和拆文共用 WholeBookAnalysisV2 那个契约，而这份产出的形状完全不同（主张
/ 依据 / 做法 / 术语 / 存疑）。硬塞进那个契约，就得给每个字段找一个不属于它的位置——读的人
会以为那是同一种东西。所以存成自己的检查点，用自己的读取口。
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Book, WholeBookCheckpoint, WholeBookRun
from app.narrative_core.comprehend.contracts import ComprehendResult
from app.narrative_core.comprehend.coordinator import ComprehendCoordinator
from app.narrative_core.comprehend.planner import plan_units
from app.narrative_core.contracts.whole_book_contract_v1 import WholeBookRunStatus
from app.narrative_core.whole_book_v2.contracts import ProgressV2
from app.narrative_core.whole_book_v2.repository import WholeBookV2Repository
from app.services.document_formats import outline_from_bytes

logger = logging.getLogger(__name__)

__all__ = [
    "COMPREHEND_MODE",
    "COMPREHEND_ENGINE_VERSION",
    "COMPREHEND_RESULT_STAGE",
    "build_progress",
    "execute_comprehend_pipeline_v1",
    "load_comprehend_result",
]

COMPREHEND_MODE = "comprehend"
COMPREHEND_ENGINE_VERSION = "comprehend-engine-1.0"
COMPREHEND_RESULT_STAGE = "comprehend_result"


def _as_dict(result: ComprehendResult) -> dict[str, Any]:
    return {
        "schema_version": "comprehend/1.0",
        "book": result.book.__dict__,
        "chapters": [
            {
                "chapter": c.chapter,
                "title": c.title,
                "summary": c.summary,
                "through_line": c.through_line,
                "error": c.error,
                "sections": [s.__dict__ for s in c.sections],
            }
            for c in result.chapters
        ],
        "sections_total": result.sections_total,
        "sections_covered": result.sections_covered,
        "coverage": result.coverage,
        "trustworthy": result.trustworthy,
        "provider_calls": result.provider_calls,
        "failures": result.failures,
        "rules": result.rules,
    }


def load_comprehend_result(session: Session, run_id: int) -> dict[str, Any] | None:
    row = session.scalars(
        select(WholeBookCheckpoint).where(
            WholeBookCheckpoint.run_id == int(run_id),
            WholeBookCheckpoint.stage_code == COMPREHEND_RESULT_STAGE,
            WholeBookCheckpoint.checkpoint_key == "latest",
        )
    ).first()
    if row is None:
        return None
    try:
        return json.loads(row.checkpoint_payload_json)
    except Exception:  # noqa: BLE001
        return None


def _save_result(session: Session, run_id: int, payload: dict[str, Any]) -> None:
    row = session.scalars(
        select(WholeBookCheckpoint).where(
            WholeBookCheckpoint.run_id == int(run_id),
            WholeBookCheckpoint.stage_code == COMPREHEND_RESULT_STAGE,
            WholeBookCheckpoint.checkpoint_key == "latest",
        )
    ).first()
    text = json.dumps(payload, ensure_ascii=False)
    if row is None:
        session.add(
            WholeBookCheckpoint(
                run_id=int(run_id),
                stage_code=COMPREHEND_RESULT_STAGE,
                checkpoint_key="latest",
                sequence_no=1,
                completed_unit_count=int(payload.get("provider_calls") or 0),
                payload_hash="",
                checkpoint_payload_json=text,
            )
        )
    else:
        row.sequence_no += 1
        row.completed_unit_count = int(payload.get("provider_calls") or 0)
        row.checkpoint_payload_json = text
    session.flush()


def build_progress(
    *,
    done: int,
    total: int,
    stage: str,
    action: str,
    elapsed: float,
    provider: str,
    model: str,
) -> ProgressV2:
    """这一条进度长什么样。

    抽成纯函数，是因为它埋在闭包里时只有真跑一次才会炸——而它真的炸了：ProgressV2 的字段
    全是必填，少一个就整条进度写不进去，异常还会被外层标成「模型中间结果格式不符合要求」，
    把人指向模型。
    """
    per = elapsed / max(1, done)
    return ProgressV2(
        overall_percent=round(min(99.0, 100.0 * done / max(1, total)), 2),
        current_stage=stage,
        stage_percent=round(100.0 * done / max(1, total), 2),
        current_window=done,
        total_windows=total,
        current_chapter=done,
        total_chapters=total,
        provider_calls_completed=done,
        provider_calls_estimated=total,
        successful_calls=done,
        failed_calls=0,
        retry_calls=0,
        repair_calls=0,
        elapsed_seconds=int(elapsed),
        estimated_remaining_seconds=int(per * max(0, total - done)),
        estimated_cost=0.0,
        estimated_actual_cost=0.0,
        provider=provider,
        model=model,
        last_completed_action=action,
        current_action=action,
        last_activity_at=datetime.now(timezone.utc).isoformat(),
    )


def execute_comprehend_pipeline_v1(
    session: Session,
    run_id: int,
    *,
    commit_progress: bool = True,
) -> dict[str, Any]:
    run = session.get(WholeBookRun, int(run_id))
    if run is None:
        raise ValueError(f"whole book run {run_id} not found")
    book = session.get(Book, int(run.book_id))
    if book is None:
        raise ValueError(f"book {run.book_id} not found")
    if not book.source_content:
        raise ValueError("这本书没有保存原始文件，无法按专著读法分析")

    run.engine_id = "comprehend_engine"
    run.engine_version = COMPREHEND_ENGINE_VERSION
    run.status = WholeBookRunStatus.running.value
    run.current_stage_code = "parse_structure"
    session.flush()

    outline = outline_from_bytes(book.source_file_name or "book.txt", book.source_content)
    units = plan_units(outline)
    repo = WholeBookV2Repository(session)
    provider = str(run.provider_name or "")
    model = str(run.model_name or "")
    started = time.monotonic()
    lock = threading.Lock()

    def write_progress(done: int, total: int, stage: str, action: str) -> None:
        repo.save_progress(
            int(run_id),
            build_progress(
                done=done,
                total=total,
                stage=stage,
                action=action,
                elapsed=max(0.0, time.monotonic() - started),
                provider=provider,
                model=model,
            ),
        )
        if commit_progress:
            try:
                session.commit()
            except Exception:  # noqa: BLE001 — 报进度失败不该让分析本身失败
                session.rollback()

    write_progress(0, max(1, len(units)), "parse_structure", "正在识别章节结构")

    from app.model_gateway.base import ModelRequest
    from app.narrative_core.services.whole_book_provider_gateway import _run_async
    from app.narrative_core.services.whole_book_v2_formal_pipeline_v1 import (
        _bind_formal_gateway,
    )
    from app.narrative_core.whole_book_v2.usage_ledger import record_provider_call

    gateway = _bind_formal_gateway(session, provider_name=provider)

    def ask(prompt: str) -> str:
        response = _run_async(
            gateway.generate(
                provider,
                ModelRequest(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_output_tokens=1600,
                    enable_thinking=False,
                ),
            )
        )
        # 记账和 Session 都要在锁里：这个函数会被多个线程同时调用，而 SQLAlchemy 的 Session
        # 不是线程安全的。模型调用本身在锁外，那才是慢的那一步。
        with lock:
            record_provider_call(
                session,
                whole_book_run_id=int(run_id),
                unit_key="comprehend",
                provider=provider,
                model=model,
                response=response,
            )
        return str(getattr(response, "text", "") or "")

    run.current_stage_code = "digest_sections"
    session.flush()

    coordinator = ComprehendCoordinator(
        ask=ask,
        concurrency=4,
        on_call=lambda done, total: write_progress(
            done, total, "digest_sections", "正在逐节读取"
        ),
    )
    result = coordinator.run(outline, book_title=str(book.title or ""))

    payload = _as_dict(result)
    _save_result(session, int(run_id), payload)
    run.status = WholeBookRunStatus.completed.value
    run.current_stage_code = "complete"
    session.flush()
    write_progress(len(units), max(1, len(units)), "complete", "已完成")
    logger.info(
        "comprehend_done run_id=%s coverage=%s/%s calls=%s",
        run_id,
        result.sections_covered,
        result.sections_total,
        result.provider_calls,
    )
    return payload
