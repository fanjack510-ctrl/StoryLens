"""Publish a LongNovelAnalysisEngine result where the existing UI already looks.

The engine writes its own ``long_novel_*`` tables — that is where the facts, evidence and
identity live, and where resume reads from. But the desktop app reads a
``WholeBookAnalysisV2`` document from a whole-book checkpoint row, so a result that is not
also written there is invisible to the user no matter how good it is.

This module is the bridge, and it is deliberately thin: it creates or reuses a
``whole_book_runs`` row, marks it with the engine that produced the result, and hands the
document to the existing repository. No UI change, no new endpoint, no new table.

**It writes to the database the product reads.** Every function here takes an explicit
session and an explicit run, so a caller cannot publish by accident.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Book, WholeBookRun
from app.narrative_core.whole_book_v2.contracts import WholeBookAnalysisV2
from app.narrative_core.whole_book_v2.repository import WholeBookV2Repository

__all__ = ["PublishResult", "ensure_run", "publish_document"]

#: Marks a run as produced by this engine, so a reader can tell it apart from a legacy one
#: without inspecting the payload.
ENGINE_IDEMPOTENCY_PREFIX = "long-novel-engine"


@dataclass(frozen=True)
class PublishResult:
    whole_book_run_id: int
    checkpoint_id: int
    chapter_count: int
    real_provider_calls: int


def ensure_run(
    session: Session,
    *,
    book_id: int,
    snapshot_id: int,
    provider_name: str,
    model_name: str,
    label: str,
) -> WholeBookRun:
    """Create or reuse the ``whole_book_runs`` row this result belongs to.

    The idempotency key carries the engine name and the label, so re-publishing the same
    labelled run updates it instead of accumulating duplicates in the task list — the user
    should see one entry per analysis, not one per attempt.
    """
    key = f"{ENGINE_IDEMPOTENCY_PREFIX}:{book_id}:{snapshot_id}:{label}"
    existing = session.scalars(
        select(WholeBookRun).where(WholeBookRun.idempotency_key == key)
    ).first()
    if existing is not None:
        return existing

    run = WholeBookRun(
        book_id=book_id,
        idempotency_key=key,
        snapshot_id=snapshot_id,
        provider_name=provider_name,
        model_name=model_name,
        status="completed",
    )
    session.add(run)
    session.flush()
    return run


def publish_document(
    session: Session,
    *,
    document: dict[str, Any],
    book_id: int,
    snapshot_id: int,
    provider_name: str,
    model_name: str,
    label: str = "default",
) -> PublishResult:
    """Validate the document against the product contract, then persist it.

    Validation happens **before** the write, and against the same model the desktop app
    parses with. A document that would render as a broken screen is rejected here rather
    than stored and discovered by the user.
    """
    run = ensure_run(
        session,
        book_id=book_id,
        snapshot_id=snapshot_id,
        provider_name=provider_name,
        model_name=model_name,
        label=label,
    )

    payload = dict(document)
    metadata = dict(payload.get("analysis_metadata", {}))
    metadata["run_id"] = run.id
    payload["analysis_metadata"] = metadata

    # Raises on any contract violation. This is the last gate before the UI.
    result = WholeBookAnalysisV2.model_validate(payload)

    repository = WholeBookV2Repository(session)
    checkpoint_id = repository.save_result(result)

    book = session.get(Book, book_id)
    if book is not None and hasattr(run, "updated_at"):
        run.updated_at = datetime.now(timezone.utc)

    return PublishResult(
        whole_book_run_id=run.id,
        checkpoint_id=int(checkpoint_id),
        chapter_count=result.book_metadata.chapter_count,
        real_provider_calls=result.analysis_metadata.real_provider_calls,
    )
