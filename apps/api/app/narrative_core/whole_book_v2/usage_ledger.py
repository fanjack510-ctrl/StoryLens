"""Whole-Book V2 provider usage ledger (model_invocations + checkpoints)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, ModelInvocation, WholeBookCheckpoint, WholeBookRun
from app.model_gateway.base import ModelResponse

USAGE_STAGE = "provider_usage"
TASK_TYPE = "whole_book_v2"


def projection_client_request_id(whole_book_run_id: int) -> str:
    return f"whole_book_v2:{int(whole_book_run_id)}"


def ensure_task_projection(session: Session, wb_run: WholeBookRun) -> AnalysisRun:
    """Ensure an AnalysisRun row so Task Center + model_invocations share one ledger."""
    key = projection_client_request_id(int(wb_run.id))
    existing = session.scalars(
        select(AnalysisRun).where(AnalysisRun.client_request_id == key)
    ).first()
    status_map = {
        "pending": "queued",
        "running": "running",
        "paused": "paused",
        "recoverable": "failed",
        "completed": "succeeded",
        "failed": "failed",
        "cancelled": "cancelled",
        "canceled": "cancelled",
    }
    mapped = status_map.get(str(wb_run.status), "running")
    progress = _progress_pair(session, int(wb_run.id))
    if existing is not None:
        existing.status = mapped
        existing.provider = str(wb_run.provider_name or existing.provider or "")
        existing.model = str(wb_run.model_name or existing.model or "")
        existing.progress_current = progress[0]
        existing.progress_total = progress[1]
        existing.error_code = wb_run.failure_code
        existing.error_message = wb_run.failure_message_safe
        if mapped == "succeeded" and existing.completed_at is None:
            existing.completed_at = wb_run.completed_at or datetime.now(timezone.utc)
        if mapped == "failed":
            existing.failed_stage = wb_run.current_stage_code
        session.flush()
        return existing
    run = AnalysisRun(
        task_type=TASK_TYPE,
        subject_type="book",
        subject_id=str(int(wb_run.book_id)),
        book_id=int(wb_run.book_id),
        provider=str(wb_run.provider_name or ""),
        model=str(wb_run.model_name or ""),
        prompt_version="whole_book_v2",
        schema_version="whole-book-analysis-v2.0",
        input_hash=hashlib.sha256(key.encode("utf-8")).hexdigest(),
        prompt_hash="",
        status=mapped,
        progress_current=progress[0],
        progress_total=progress[1],
        client_request_id=key,
        analysis_type="whole_book_v2",
        scope_type="whole_book",
        book_snapshot_id=wb_run.snapshot_id,
        execution_mode="cloud",
        cloud_consent=True,
        sends_content_to_cloud=True,
        error_code=wb_run.failure_code,
        error_message=wb_run.failure_message_safe,
    )
    session.add(run)
    session.flush()
    return run


def _progress_pair(session: Session, whole_book_run_id: int) -> tuple[int, int]:
    rows = list(
        session.scalars(
            select(WholeBookCheckpoint).where(
                WholeBookCheckpoint.run_id == int(whole_book_run_id),
                WholeBookCheckpoint.stage_code == USAGE_STAGE,
            )
        )
    )
    done = len(rows)
    return done, max(done, 1)


def record_provider_call(
    session: Session | None,
    *,
    whole_book_run_id: int,
    unit_key: str,
    provider: str,
    model: str,
    response: ModelResponse,
    repair: bool = False,
    window_id: str | None = None,
) -> None:
    """Persist one V2 provider call into checkpoints + model_invocations (no API keys / full novel)."""
    if session is None:
        return
    wb = session.get(WholeBookRun, int(whole_book_run_id))
    if wb is None:
        return
    analysis_run = ensure_task_projection(session, wb)
    seq = int(_progress_pair(session, int(whole_book_run_id))[0]) + 1
    safe_meta = {
        "run_id": int(whole_book_run_id),
        "analysis_run_id": int(analysis_run.id),
        "unit_id": unit_key,
        "window_id": window_id,
        "provider": provider,
        "model": model,
        "status": "succeeded" if response.text else "empty",
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
        "total_tokens": (response.input_tokens or 0) + (response.output_tokens or 0)
        if response.input_tokens is not None or response.output_tokens is not None
        else None,
        "finish_reason": response.finish_reason,
        "request_id": getattr(response, "request_id", None)
        or getattr(response, "provider_request_id", None),
        "repair": repair,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    payload = json.dumps(safe_meta, ensure_ascii=False)
    session.add(
        WholeBookCheckpoint(
            run_id=int(whole_book_run_id),
            stage_code=USAGE_STAGE,
            checkpoint_key=f"call:{seq}:{unit_key}"[:120],
            sequence_no=seq,
            completed_unit_count=seq,
            payload_hash=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            checkpoint_payload_json=payload,
        )
    )
    snap = {
        "unit_key": unit_key,
        "window_id": window_id,
        "whole_book_run_id": int(whole_book_run_id),
        "prompt_chars": None,
        "schema_only": True,
    }
    session.add(
        ModelInvocation(
            run_id=int(analysis_run.id),
            task_type=TASK_TYPE if not repair else f"{TASK_TYPE}_repair",
            provider_name=provider,
            model_name=model,
            prompt_version="whole_book_v2",
            schema_version="whole-book-analysis-v2.0",
            attempt_no=seq,
            invocation_kind="repair" if repair else "initial",
            request_hash=hashlib.sha256(f"{unit_key}:{seq}".encode("utf-8")).hexdigest(),
            input_snapshot_json=json.dumps(snap, ensure_ascii=False),
            raw_response_text=(response.text or "")[:4000],
            parsed_response_json=None,
            status="succeeded",
            latency_ms=0,
            http_request_sent=True,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            total_tokens=safe_meta["total_tokens"],
            request_id=safe_meta["request_id"],
            finish_reason=response.finish_reason,
            is_cloud=True,
            cloud_provider=provider,
            sends_content_to_cloud=True,
            audit_type="provider_invocation",
            sent_at=datetime.now(timezone.utc),
        )
    )
    analysis_run.progress_current = seq
    analysis_run.progress_total = max(seq, int(analysis_run.progress_total or 0), 1)
    analysis_run.status = "running"
    session.flush()


def count_usage_calls(session: Session, whole_book_run_id: int) -> int:
    return len(
        list(
            session.scalars(
                select(WholeBookCheckpoint).where(
                    WholeBookCheckpoint.run_id == int(whole_book_run_id),
                    WholeBookCheckpoint.stage_code == USAGE_STAGE,
                )
            )
        )
    )


__all__ = [
    "TASK_TYPE",
    "USAGE_STAGE",
    "count_usage_calls",
    "ensure_task_projection",
    "projection_client_request_id",
    "record_provider_call",
]
