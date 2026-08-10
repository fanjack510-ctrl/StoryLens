"""Formal Free create → hierarchical Whole-Book V2 runtime (CHG-078)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Book, WholeBookRun
from app.narrative_core.contracts.whole_book_contract_v1 import WholeBookRunStatus
from app.narrative_core.services.whole_book_gateway_transport_v1 import _run_async
from app.narrative_core.services.whole_book_run_v1_service import get_run, start_whole_book_run_v1
from app.narrative_core.services.whole_book_snapshot_v1_service import get_snapshot, list_chapters
from app.narrative_core.whole_book_v2.engine import SourceChapter
from app.narrative_core.whole_book_v2.pipeline import ProviderBudget
from app.narrative_core.whole_book_v2.provider_engine import GatewayWholeBookV2Analyzer
from app.narrative_core.whole_book_v2.repository import WholeBookV2Repository, pinned_provider
from app.narrative_core.whole_book_v2.runtime import ProviderUnitLedger

logger = logging.getLogger(__name__)

ENGINE_ID = "whole_book_v2_hierarchical"
ENGINE_VERSION = "2.1.0"


def _source_chapters(session: Session, run: WholeBookRun) -> list[SourceChapter]:
    if run.snapshot_id is None:
        raise ValueError("whole-book run missing snapshot_id")
    snap = get_snapshot(session, int(run.snapshot_id))
    revision = str(snap.source_fingerprint or snap.content_hash or "")
    chapters: list[SourceChapter] = []
    for ch in list_chapters(session, int(snap.id)):
        text = str(ch.content_text or "")
        if not text.strip():
            continue
        # Snapshot chapter_order may be 0-based; V2 SourceChapter requires >= 1.
        order = int(ch.chapter_order)
        chapter_index = order if order >= 1 else order + 1
        chapters.append(
            SourceChapter(
                chapter_id=int(ch.id),
                chapter_index=chapter_index,
                title=str(ch.title or f"第{chapter_index}章"),
                text=text,
                snapshot_id=int(snap.id),
                revision_hash=revision,
            )
        )
    if not chapters:
        raise ValueError("snapshot has no chapter text for V2 analysis")
    return chapters


def _bind_formal_gateway(session: Session, *, provider_name: str) -> Any:
    """Build ModelGateway with keyring credentials — no Fake / fixture fallback."""
    from app.model_gateway.registry import get_model_gateway
    from app.narrative_core.services.whole_book_gateway_transport_v1 import (
        resolve_formal_provider_row,
    )
    from app.services.credentials.keyring_store import KeyringCredentialStore
    from app.services.provider_runtime import apply_provider_runtime, bind_gateway_runtime

    row = resolve_formal_provider_row(session, provider_name=provider_name)
    store = KeyringCredentialStore()
    if not store.available():
        raise ValueError("credential backend unavailable")
    secret = store.get(str(row.provider_name))
    if not secret:
        raise ValueError(f"API key missing for provider {row.provider_name}")
    gateway = get_model_gateway()
    bind_gateway_runtime(gateway, session, store)
    provider = gateway.get(str(row.provider_name))
    apply_provider_runtime(provider, session, store)
    provider.api_key = secret
    provider.enabled = True
    # Formal hierarchical default: local deterministic window extract; synthesis via provider.
    gateway.deterministic_extraction = True  # type: ignore[attr-defined]
    return gateway


def execute_hierarchical_v2_pipeline_v1(
    session: Session,
    run_id: int,
    *,
    use_fake_gateway: Any | None = None,
) -> dict[str, Any]:
    """Run hierarchical V2 analyze for an existing WholeBookRun and persist V2 result.

    ``use_fake_gateway`` is test-only. Production must pass None (real ModelGateway).
    """
    run = get_run(session, int(run_id))
    book = session.get(Book, int(run.book_id))
    if book is None:
        raise ValueError(f"book not found: {run.book_id}")
    provider_name, model_name = pinned_provider(session, int(run_id))
    chapters = _source_chapters(session, run)
    repo = WholeBookV2Repository(session)
    gateway = (
        use_fake_gateway
        if use_fake_gateway is not None
        else _bind_formal_gateway(session, provider_name=provider_name)
    )
    analyzer = GatewayWholeBookV2Analyzer(
        gateway,
        provider_name=provider_name,
        model_name=model_name,
        ledger=ProviderUnitLedger(),
        repository=repo,
        budget=ProviderBudget(provider=provider_name, model=model_name),
    )
    if run.status == WholeBookRunStatus.pending.value:
        start_whole_book_run_v1(session, int(run_id))
        session.refresh(run)

    run.engine_id = ENGINE_ID
    run.engine_version = ENGINE_VERSION
    session.flush()

    result, responses = _run_async(
        analyzer.analyze(
            run_id=int(run_id),
            book_id=int(run.book_id),
            title=str(book.title or ""),
            chapters=chapters,
        )
    )
    version_id = repo.save_result(result)
    run.status = WholeBookRunStatus.completed.value
    run.current_stage_code = "complete"
    session.flush()
    return {
        "run_id": int(run_id),
        "engine_id": ENGINE_ID,
        "engine_version": ENGINE_VERSION,
        "schema_version": result.schema_version,
        "asset_version_id": version_id,
        "provider_calls": len(responses),
        "pipeline": "hierarchical_v2",
    }


__all__ = [
    "ENGINE_ID",
    "ENGINE_VERSION",
    "execute_hierarchical_v2_pipeline_v1",
]
