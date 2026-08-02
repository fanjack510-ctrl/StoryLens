"""Shared helpers for Wave C minimal whole-book pipeline."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    BookSnapshotChapter,
    BookSnapshotParagraph,
    ProviderConfiguration,
    WholeBookCheckpoint,
    WholeBookRun,
    WholeBookRunStageRow,
    utc_now,
)
from app.narrative_core.contracts.whole_book_contract_v1 import (
    WHOLE_BOOK_CONTRACT_VERSION,
    WholeBookInputUsageV1,
    WholeBookMode,
    WholeBookRunStatus,
    WholeBookStageStatus,
)
from app.narrative_core.services.whole_book_consent_service import create_whole_book_consent
from app.narrative_core.services.whole_book_cost_estimate_service import estimate_whole_book_analysis
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)
from app.narrative_core.services.whole_book_run_v1_service import get_run
from app.narrative_core.services.whole_book_snapshot_v1_service import (
    get_snapshot_paragraph_text,
    to_metadata_dict,
)
from app.services.whole_book_source_fingerprint import sha256_utf8

FIXTURE_ENGINE_ID = "whole_book_window_entity_event_v1"
FIXTURE_ENGINE_VERSION = "1.0.0"
FIXTURE_PROMPT_VERSION = "whole_book_window_entity_event_prompt_v1"
OVERVIEW_ENGINE_ID = "whole_book_overview_synthesis_v1"
OVERVIEW_PROMPT_VERSION = "whole_book_overview_prompt_v1"
STRUCTURE_ENGINE_ID = "whole_book_structure_stages_v1"
STRUCTURE_PROMPT_VERSION = "whole_book_structure_stages_prompt_v2"
CHAPTER_FUNCTIONS_ENGINE_ID = "whole_book_chapter_functions_v1"
CHAPTER_FUNCTIONS_PROMPT_VERSION = "whole_book_chapter_functions_prompt_v2"
MAX_CHAPTERS_PER_BATCH = 8

MINIMAL_ASSET_TYPES = frozenset(
    {
        "character_profile",
        "event",
        "goal",
        "conflict",
        "question",
        "setting_fact",
    }
)
MINIMAL_RELATION_TYPES = frozenset(
    {
        "alias_of",
        "participates_in",
        "causes",
        "precedes",
        "supports",
        "opposes",
    }
)


def real_provider_enabled() -> bool:
    return os.environ.get("STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def native_input_usage() -> WholeBookInputUsageV1:
    return WholeBookInputUsageV1(
        full_text_snapshot_used=True,
        chapter_analysis_asset_count=0,
        reader_journey_asset_count=0,
        confirmed_whole_book_asset_count=0,
    )


def ensure_fixture_consent(session: Session, run: WholeBookRun) -> int:
    if run.consent_id is not None:
        return int(run.consent_id)
    provider = session.scalar(select(ProviderConfiguration).limit(1))
    if provider is None:
        provider = ProviderConfiguration(provider_name="fixture", plus_model="fixture-model")
        session.add(provider)
        session.flush()
    estimate = estimate_whole_book_analysis(
        session, run.book_id, WholeBookMode.whole_book_native.value, provider.id
    )
    estimate.pricing_status = "unavailable"
    session.flush()
    consent = create_whole_book_consent(
        session,
        book_id=run.book_id,
        estimate_id=estimate.id,
        user_budget_limit_cny="1000",
        max_provider_calls=1000,
        max_input_tokens=10_000_000,
        max_output_tokens=10_000_000,
        auto_retry_enabled=False,
        max_retries_per_unit=0,
    )
    run.consent_id = consent.id
    session.flush()
    return int(consent.id)


def get_stage(session: Session, run_id: int, stage_code: str) -> WholeBookRunStageRow | None:
    return session.scalar(
        select(WholeBookRunStageRow).where(
            WholeBookRunStageRow.run_id == run_id,
            WholeBookRunStageRow.stage_code == stage_code,
        )
    )


def set_stage_running(session: Session, run_id: int, stage_code: str) -> None:
    stage = get_stage(session, run_id, stage_code)
    if stage is None:
        return
    now = utc_now()
    if stage.status != WholeBookStageStatus.completed.value:
        stage.status = WholeBookStageStatus.running.value
        stage.started_at = stage.started_at or now
    session.flush()


def set_stage_completed(
    session: Session,
    run_id: int,
    stage_code: str,
    *,
    progress_total: int | None = None,
) -> None:
    stage = get_stage(session, run_id, stage_code)
    if stage is None:
        return
    now = utc_now()
    total = progress_total if progress_total is not None else max(stage.progress_total, 1)
    stage.status = WholeBookStageStatus.completed.value
    stage.progress_total = total
    stage.progress_current = total
    stage.completed_at = now
    session.flush()


def paragraph_contract_dict(
    session: Session,
    paragraph: BookSnapshotParagraph,
    *,
    snapshot_id: int,
) -> dict[str, Any]:
    chapter = session.get(BookSnapshotChapter, paragraph.snapshot_chapter_id)
    text = get_snapshot_paragraph_text(session, paragraph.id)
    return {
        "snapshot_paragraph_id": paragraph.id,
        "snapshot_id": snapshot_id,
        "snapshot_chapter_id": paragraph.snapshot_chapter_id,
        "chapter_id": chapter.source_chapter_id if chapter else 0,
        "chapter_index": chapter.chapter_order if chapter else 0,
        "paragraph_index": paragraph.paragraph_order,
        "global_paragraph_index": int(paragraph.global_paragraph_index or 0),
        "text": text,
        "text_hash": paragraph.content_hash,
        "character_count": len(text),
    }


def load_window_paragraph_dicts(
    session: Session,
    *,
    snapshot_id: int,
    first_global: int,
    last_global: int,
) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(BookSnapshotParagraph)
        .where(
            BookSnapshotParagraph.snapshot_id == snapshot_id,
            BookSnapshotParagraph.global_paragraph_index >= first_global,
            BookSnapshotParagraph.global_paragraph_index <= last_global,
        )
        .order_by(BookSnapshotParagraph.global_paragraph_index.asc())
    ).all()
    return [paragraph_contract_dict(session, row, snapshot_id=snapshot_id) for row in rows]


def _iso_utc(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def build_run_contract_dict(run: WholeBookRun) -> dict[str, Any]:
    if run.snapshot_id is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_FOUND,
            f"run {run.id} has no snapshot",
        )
    return {
        "run_id": run.id,
        "book_id": run.book_id,
        "snapshot_id": run.snapshot_id,
        "mode": run.mode,
        "status": run.status,
        "current_stage_code": run.current_stage_code,
        "idempotency_key": run.idempotency_key,
        "engine_id": run.engine_id,
        "engine_version": run.engine_version,
        "contract_version": run.contract_version or WHOLE_BOOK_CONTRACT_VERSION,
        "prompt_version": run.prompt_version,
        "result_origin": run.result_origin,
        "input_usage": native_input_usage().model_dump(mode="json"),
        "consent_id": run.consent_id,
        "cost_policy_id": run.cost_policy_id,
        "created_at": _iso_utc(run.created_at) or datetime.now(timezone.utc).isoformat(),
        "started_at": _iso_utc(run.started_at),
        "paused_at": _iso_utc(run.paused_at),
        "completed_at": _iso_utc(run.completed_at),
        "failed_at": _iso_utc(run.failed_at),
        "cancelled_at": _iso_utc(run.cancelled_at),
        "failure_code": run.failure_code,
        "failure_message_safe": run.failure_message_safe,
    }


def build_window_contract_dict(window: Any, run: WholeBookRun) -> dict[str, Any]:
    return {
        "window_id": window.id,
        "run_id": run.id,
        "snapshot_id": run.snapshot_id,
        "window_index": window.window_index,
        "first_global_paragraph_index": window.first_global_paragraph_index,
        "last_global_paragraph_index": window.last_global_paragraph_index,
        "chapter_start_index": window.chapter_start_index,
        "chapter_end_index": window.chapter_end_index,
        "paragraph_count": window.paragraph_count,
        "character_count": window.character_count,
        "token_estimate": window.token_estimate,
        "overlap_before_paragraphs": window.overlap_before_paragraphs,
        "overlap_after_paragraphs": window.overlap_after_paragraphs,
        "window_hash": window.window_hash,
        "idempotency_key": window.idempotency_key,
        "status": window.status,
    }


def upsert_checkpoint(
    session: Session,
    *,
    run_id: int,
    stage_code: str,
    checkpoint_key: str,
    payload: dict[str, Any],
) -> None:
    existing = session.scalar(
        select(WholeBookCheckpoint).where(
            WholeBookCheckpoint.run_id == run_id,
            WholeBookCheckpoint.stage_code == stage_code,
            WholeBookCheckpoint.checkpoint_key == checkpoint_key,
        )
    )
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    payload_hash = sha256_utf8(blob)
    if existing is None:
        session.add(
            WholeBookCheckpoint(
                run_id=run_id,
                stage_code=stage_code,
                checkpoint_key=checkpoint_key,
                sequence_no=0,
                payload_hash=payload_hash,
                checkpoint_payload_json=blob,
            )
        )
    else:
        existing.payload_hash = payload_hash
        existing.checkpoint_payload_json = blob
    session.flush()


def assert_run_not_terminal(session: Session, run_id: int) -> WholeBookRun:
    run = get_run(session, run_id)
    if run.status in {
        WholeBookRunStatus.completed.value,
        WholeBookRunStatus.failed.value,
        WholeBookRunStatus.cancelled.value,
    }:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_RUN_TERMINAL,
            f"run {run_id} is terminal ({run.status})",
        )
    return run


def snapshot_metadata_dict(session: Session, snapshot_id: int) -> dict[str, Any]:
    from app.narrative_core.services.whole_book_snapshot_v1_service import get_snapshot

    data = dict(to_metadata_dict(get_snapshot(session, snapshot_id)))
    for key in ("created_at", "completed_at"):
        if data.get(key):
            from datetime import datetime

            raw = data[key]
            if isinstance(raw, str):
                parsed = datetime.fromisoformat(raw)
                data[key] = _iso_utc(parsed)
            else:
                data[key] = _iso_utc(raw)
    return data
