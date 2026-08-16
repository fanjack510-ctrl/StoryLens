"""Formal Free create → hierarchical Whole-Book V2 runtime (CHG-078)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Book, WholeBookRun
from app.model_gateway.base import ModelResponse
from app.narrative_core.contracts.whole_book_contract_v1 import WholeBookRunStatus
from app.narrative_core.services.whole_book_gateway_transport_v1 import _run_async
from app.narrative_core.services.whole_book_run_v1_service import get_run, start_whole_book_run_v1
from app.narrative_core.services.whole_book_snapshot_v1_service import get_snapshot, list_chapters
from app.narrative_core.whole_book_v2.contracts import (
    AssessmentSynthesisUnit,
    CharactersSynthesisUnit,
    OverviewTypeSynthesisUnit,
    ChapterFunctionBatchUnit,
    PacingCoreSynthesisUnit,
    StorySynthesisUnit,
    SuspenseSynthesisUnit,
)
from app.narrative_core.whole_book_v2.engine import (
    DeterministicPrimitiveExtractor,
    SourceChapter,
    WholeBookV2Engine,
)
from app.narrative_core.whole_book_v2.pipeline import ProviderBudget
from app.narrative_core.whole_book_v2.provider_engine import (
    CHAPTER_FUNCTION_BATCH_SIZE,
    GatewayWholeBookV2Analyzer,
)
from app.narrative_core.whole_book_v2.repository import WholeBookV2Repository, pinned_provider
from app.narrative_core.whole_book_v2.runtime import ProviderUnitLedger

logger = logging.getLogger(__name__)

ENGINE_ID = "whole_book_v2_hierarchical"
ENGINE_VERSION = "2.1.0"


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").lower() in {"1", "true", "yes", "on"}


class _DeterministicV2Gateway:
    """Opt-in packaged/local evidence gateway — zero real Provider HTTP calls."""

    def __init__(self, payloads: list[dict[str, Any]]):
        self._payloads = list(payloads)
        self.disallow_local_merge = True
        # Opt-in evidence gateway may still use local window extract; formal path does not.
        self.deterministic_extraction = True

    async def generate(self, provider: str, request: Any) -> ModelResponse:
        if not self._payloads:
            raise RuntimeError("deterministic gateway exhausted")
        item = self._payloads.pop(0)
        return ModelResponse(
            text=json.dumps(item, ensure_ascii=False),
            model="deterministic-v2",
            finish_reason="stop",
            input_tokens=10,
            output_tokens=20,
        )


def _deterministic_payloads(chapters: list[SourceChapter]) -> list[dict[str, Any]]:
    result = WholeBookV2Engine(
        DeterministicPrimitiveExtractor(), window_size=3, overlap=0
    ).run(run_id=1, book_id=1, title="deterministic", chapters=chapters)
    return [
        OverviewTypeSynthesisUnit(type_profile=result.type_profile, overview=result.overview).model_dump(
            mode="json"
        ),
        StorySynthesisUnit(story=result.story).model_dump(mode="json"),
        CharactersSynthesisUnit(characters=result.characters).model_dump(mode="json"),
        SuspenseSynthesisUnit(suspense=result.suspense).model_dump(mode="json"),
        PacingCoreSynthesisUnit(pacing=result.pacing).model_dump(mode="json"),
        AssessmentSynthesisUnit(assessment=result.assessment).model_dump(mode="json"),
        # Chapter functions are requested last, in bounded batches (CHG-086).
        *[
            ChapterFunctionBatchUnit(
                functions=result.chapters.functions[i : i + CHAPTER_FUNCTION_BATCH_SIZE]
            ).model_dump(mode="json")
            for i in range(
                0, max(1, len(result.chapters.functions)), CHAPTER_FUNCTION_BATCH_SIZE
            )
        ],
    ]


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
    # CHG-084: formal hierarchical requires real Provider window extraction.
    # Never persist local scaffold merge as a formal "completed" real result.
    gateway.deterministic_extraction = False  # type: ignore[attr-defined]
    gateway.disallow_local_merge = True  # type: ignore[attr-defined]
    return gateway


def _copy_safe_intermediates(
    repo: WholeBookV2Repository,
    *,
    source_run_id: int,
    target_run_id: int,
) -> int:
    """Copy successful intermediate/unit checkpoints when reanalysis allows reuse."""
    return repo.copy_intermediates(source_run_id=source_run_id, target_run_id=target_run_id)


def execute_hierarchical_v2_pipeline_v1(
    session: Session,
    run_id: int,
    *,
    use_fake_gateway: Any | None = None,
    force_full_reanalysis: bool = False,
    previous_run_id: int | None = None,
    commit_progress: bool = False,
) -> dict[str, Any]:
    """Run hierarchical V2 analyze for an existing WholeBookRun and persist V2 result.

    ``use_fake_gateway`` is test-only. Production must pass None (real ModelGateway).
    When ``force_full_reanalysis`` is False and ``previous_run_id`` is set, successful
    intermediate checkpoints may be copied into the new run (same pipeline contract).
    When ``commit_progress`` is True, intermediate checkpoint writes are committed so
    other Sessions (health / progress poll) are not blocked by a multi-hour write txn.
    """
    run = get_run(session, int(run_id))
    book = session.get(Book, int(run.book_id))
    if book is None:
        raise ValueError(f"book not found: {run.book_id}")

    # A book whose five profile axes have been confirmed goes through the long-novel engine.
    # The dispatch lives here rather than at the two call sites so that both the API path and
    # the background worker take the same decision, and so that the rule is written once.
    from app.narrative_core.services.long_novel_pipeline_v1 import (
        book_uses_long_novel_engine,
        execute_long_novel_pipeline_v1,
    )

    if book_uses_long_novel_engine(session, int(run.book_id)):
        logger.info("whole_book_v2_dispatch run_id=%s engine=long_novel", run_id)
        return execute_long_novel_pipeline_v1(
            session,
            int(run_id),
            use_fake_gateway=use_fake_gateway,
            commit_progress=commit_progress,
        )

    provider_name, model_name = pinned_provider(session, int(run_id))
    chapters = _source_chapters(session, run)

    # CHG-081 packaged/local evidence probes — opt-in only; never used by normal installs.
    if _env_flag("STORYLENS_WHOLE_BOOK_V2_FORCE_BACKGROUND_FAIL"):
        raise RuntimeError("STORYLENS_WHOLE_BOOK_V2_FORCE_BACKGROUND_FAIL")

    def _persist_commit() -> None:
        if commit_progress:
            session.commit()

    repo = WholeBookV2Repository(session, on_persist=_persist_commit if commit_progress else None)
    reused = 0
    if (
        not force_full_reanalysis
        and previous_run_id is not None
        and int(previous_run_id) != int(run_id)
    ):
        reused = _copy_safe_intermediates(
            repo, source_run_id=int(previous_run_id), target_run_id=int(run_id)
        )
        _persist_commit()
    if use_fake_gateway is not None:
        gateway = use_fake_gateway
    elif _env_flag("STORYLENS_WHOLE_BOOK_V2_DETERMINISTIC_GATEWAY"):
        gateway = _DeterministicV2Gateway(_deterministic_payloads(chapters))
        logger.warning(
            "whole_book_v2_deterministic_gateway_enabled run_id=%s (no real Provider calls)",
            run_id,
        )
    else:
        gateway = _bind_formal_gateway(session, provider_name=provider_name)
    # Tests may inject a fake gateway; still forbid silent local merge unless the
    # fake explicitly allows it (force_local_merge / missing disallow).
    if use_fake_gateway is not None and not hasattr(gateway, "disallow_local_merge"):
        gateway.disallow_local_merge = False  # type: ignore[attr-defined]
    from app.narrative_core.whole_book_v2.usage_ledger import ensure_task_projection

    ensure_task_projection(session, run)
    analyzer = GatewayWholeBookV2Analyzer(
        gateway,
        provider_name=provider_name,
        model_name=model_name,
        ledger=ProviderUnitLedger(),
        repository=repo,
        budget=ProviderBudget(provider=provider_name, model=model_name),
        db_session=session,
        # CHG-085: force_full only blocks cross-run copy above. Analyzer always
        # reuses THIS run's successful checkpoints on retry/resume.
        force_full_reanalysis=False,
    )
    if run.status == WholeBookRunStatus.pending.value:
        start_whole_book_run_v1(session, int(run_id))
        session.refresh(run)
        _persist_commit()

    run.engine_id = ENGINE_ID
    run.engine_version = ENGINE_VERSION
    session.flush()
    _persist_commit()

    result, responses = _run_async(
        analyzer.analyze(
            run_id=int(run_id),
            book_id=int(run.book_id),
            title=str(book.title or ""),
            chapters=chapters,
        )
    )
    # Formal product must never mark scaffold merge as real_provider.
    if result.analysis_metadata.result_origin == "deterministic_local_merge":
        run.status = WholeBookRunStatus.failed.value
        run.failure_code = "WHOLE_BOOK_V2_LOCAL_MERGE_FORBIDDEN"
        run.failure_message_safe = (
            "全书 V2 合成未能完成真实模型结果，未写入正式完成态。请重新分析。"
        )
        session.flush()
        _persist_commit()
        raise ValueError("formal V2 local merge result rejected")
    version_id = repo.save_result(result)
    run.status = WholeBookRunStatus.completed.value
    run.current_stage_code = "complete"
    session.flush()
    from app.narrative_core.whole_book_v2.usage_ledger import ensure_task_projection

    ensure_task_projection(session, run)
    _persist_commit()
    return {
        "run_id": int(run_id),
        "engine_id": ENGINE_ID,
        "engine_version": ENGINE_VERSION,
        "schema_version": result.schema_version,
        "asset_version_id": version_id,
        "provider_calls": len(responses),
        "pipeline": "hierarchical_v2",
        "intermediates_reused": reused,
        "result_origin": result.analysis_metadata.result_origin,
    }


__all__ = [
    "ENGINE_ID",
    "ENGINE_VERSION",
    "execute_hierarchical_v2_pipeline_v1",
]
