"""Minimal Free fixture chapter functions synthesis (WB-2.2).

Native-input independent: Snapshot paragraphs + CitationCatalog only.
WB-2.1 structure is optional derived context (never hard dependency).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisConflict,
    BookSnapshotChapter,
    BookSnapshotParagraph,
    NarrativeAsset,
    NarrativeAssetEvidence,
    NarrativeAssetVersion,
    WholeBookCheckpoint,
    WholeBookRunStageRow,
    utc_now,
)
from app.narrative_core.asset_key import build_asset_key
from app.narrative_core.contracts.whole_book_contract_v1 import (
    WholeBookRunStatus,
)
from app.narrative_core.enums import ConflictStatus, ConflictType, OriginType, ReviewStatus
from app.narrative_core.services.chapter_functions_output_contract_v2 import (
    FAILURE_EMPTY_RESULT_AFTER_REPAIR,
    FAILURE_REQUIRED_CHAPTER_MISSING,
    MAX_REPAIR_COUNT,
    _public_shape_validate,
    validate_chapter_functions_provider_output_v2,
)
from app.narrative_core.services.citation_catalog_v2 import build_catalog_from_paragraph_units
from app.narrative_core.services.fixture_chapter_functions_sample_s import (
    FixtureChapterFunctionsMode,
    build_fixture_chapter_functions_v2,
)
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)
from app.narrative_core.services.whole_book_minimal_helpers_v1 import (
    CHAPTER_FUNCTIONS_ENGINE_ID,
    CHAPTER_FUNCTIONS_PROMPT_VERSION,
    MAX_CHAPTERS_PER_BATCH,
    assert_run_not_terminal,
    ensure_fixture_consent,
    set_stage_completed,
    upsert_checkpoint,
)
from app.narrative_core.services.whole_book_provider_orchestrator import (
    CountingFakeWholeBookProvider,
    ProviderCallResult,
    UNIT_SYNTHESIS,
    WholeBookProviderOrchestrator,
    WholeBookProviderTransport,
    stable_request_hash,
)
from app.narrative_core.services.whole_book_run_v1_service import get_run
from app.narrative_core.services.whole_book_snapshot_v1_service import get_snapshot_paragraph_text
from app.narrative_core.services.whole_book_structure_product_v1_service import (
    load_structure_checkpoint_envelope,
)
from app.services.whole_book_source_fingerprint import sha256_utf8

CHAPTER_FUNCTIONS_RESULT_CHECKPOINT_KEY = "chapter_functions_result_v2"
CHAPTER_FUNCTIONS_STAGE_CODE = "synthesize_chapter_functions"
CHAPTER_FUNCTIONS_UNIT_PREFIX = "chapter_functions:v2"


@dataclass
class FixtureChapterFunctionsTransport:
    """Fixture transport for chapter_functions provider units (no network)."""

    mode: FixtureChapterFunctionsMode = "available"
    citation_ids: list[str] = field(default_factory=list)
    chapter_units: list[dict[str, Any]] = field(default_factory=list)
    context_capabilities: dict[str, Any] = field(default_factory=dict)
    structure_context: dict[str, Any] | None = None
    inner: CountingFakeWholeBookProvider = field(default_factory=CountingFakeWholeBookProvider)
    call_count: int = 0
    repair_count: int = 0

    def invoke(self, *, unit_key: str, unit_type: str, request_payload: dict[str, Any]) -> ProviderCallResult:
        self.call_count += 1
        kind = str(request_payload.get("operation_kind") or "chapter_functions_initial")
        if kind == "chapter_functions_contract_repair":
            self.repair_count += 1
        batch_units = list(request_payload.get("chapter_units") or self.chapter_units)
        batch_cids = list(request_payload.get("citation_ids") or self.citation_ids)
        payload = build_fixture_chapter_functions_v2(
            citation_ids=batch_cids,
            chapter_units=batch_units,
            mode=self.mode,
            context_capabilities=self.context_capabilities,
            structure_context=self.structure_context,
        )
        return ProviderCallResult(ok=True, result_payload=payload)


def _load_cf_checkpoint(session: Session, run_id: int) -> dict[str, Any] | None:
    row = session.scalar(
        select(WholeBookCheckpoint).where(
            WholeBookCheckpoint.run_id == run_id,
            WholeBookCheckpoint.stage_code == CHAPTER_FUNCTIONS_STAGE_CODE,
            WholeBookCheckpoint.checkpoint_key == CHAPTER_FUNCTIONS_RESULT_CHECKPOINT_KEY,
        )
    )
    if row is None:
        return None
    try:
        return json.loads(row.checkpoint_payload_json or "{}")
    except json.JSONDecodeError:
        return None


def _build_snapshot_catalog(
    session: Session, snapshot_id: int
) -> tuple[Any, list[str], dict[str, Any], list[dict[str, Any]]]:
    paragraphs = list(
        session.scalars(
            select(BookSnapshotParagraph)
            .where(BookSnapshotParagraph.snapshot_id == snapshot_id)
            .order_by(BookSnapshotParagraph.global_paragraph_index.asc())
        ).all()
    )
    chapters = list(
        session.scalars(
            select(BookSnapshotChapter)
            .where(BookSnapshotChapter.snapshot_id == snapshot_id)
            .order_by(BookSnapshotChapter.chapter_order.asc())
        ).all()
    )
    units: list[dict[str, Any]] = []
    for sp in paragraphs:
        text = get_snapshot_paragraph_text(session, sp.id) or "x"
        units.append(
            {
                "chapter_id": sp.snapshot_chapter_id,
                "paragraph_id": sp.id,
                "stable_paragraph_id": str(getattr(sp, "stable_paragraph_id", None) or sp.id),
                "content_hash": str(sp.content_hash or "missing"),
                "text": text if text.strip() else "x",
            }
        )
    chapter_units: list[dict[str, Any]] = []
    para_by_chapter: dict[int, list[str]] = {}
    caps = {
        "can_identify_chapter_functions": bool(units),
        "selected_chapter_count": 0,
        "selected_paragraph_count": len(units),
        "fixture_test_data": True,
        "max_chapters_per_batch": MAX_CHAPTERS_PER_BATCH,
    }
    if not units:
        return None, [], caps, []

    catalog = build_catalog_from_paragraph_units(
        context_bundle_hash=sha256_utf8(f"fixture-cf-{snapshot_id}"),
        snapshot_id=snapshot_id,
        paragraph_units=units,
    )
    citation_ids = list(catalog.citation_ids)
    # Map chapter → first citation for that chapter when possible.
    entries = list(getattr(catalog, "entries", None) or ())
    for entry in entries:
        ch_id = getattr(entry, "chapter_id", None)
        if ch_id is None and isinstance(entry, dict):
            ch_id = entry.get("chapter_id")
        cid = getattr(entry, "citation_id", None)
        if cid is None and isinstance(entry, dict):
            cid = entry.get("citation_id")
        if ch_id is None or cid is None:
            continue
        para_by_chapter.setdefault(int(ch_id), []).append(str(cid))

    if chapters:
        for ch in chapters:
            order = int(ch.chapter_order)
            cids = para_by_chapter.get(int(ch.id), [])
            if not cids and citation_ids:
                cids = [citation_ids[min(max(order - 1, 0), len(citation_ids) - 1)]]
            chapter_units.append(
                {
                    "chapter_id": ch.id,
                    "chapter_order": order,
                    "citation_ids": cids[:1],
                }
            )
    else:
        # Fallback: distinct chapter ids from paragraphs.
        seen: dict[int, int] = {}
        for sp in paragraphs:
            cid = int(sp.snapshot_chapter_id)
            if cid not in seen:
                seen[cid] = len(seen) + 1
                cids = para_by_chapter.get(cid, [])
                if not cids and citation_ids:
                    cids = [citation_ids[min(seen[cid] - 1, len(citation_ids) - 1)]]
                chapter_units.append(
                    {
                        "chapter_id": cid,
                        "chapter_order": seen[cid],
                        "citation_ids": cids[:1],
                    }
                )

    caps["selected_chapter_count"] = len(chapter_units)
    caps["selected_chapter_orders"] = tuple(u["chapter_order"] for u in chapter_units)
    caps["all_chapter_orders"] = caps["selected_chapter_orders"]
    return catalog, citation_ids, caps, chapter_units


def _batch_chapter_units(chapter_units: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    for i in range(0, len(chapter_units), MAX_CHAPTERS_PER_BATCH):
        batches.append(chapter_units[i : i + MAX_CHAPTERS_PER_BATCH])
    return batches or [[]]


def _citation_to_paragraph(
    session: Session, snapshot_id: int, citation_id: str, catalog: Any
) -> BookSnapshotParagraph | None:
    entry = None
    try:
        entries = getattr(catalog, "entries", None) or ()
        for item in entries:
            cid = str(
                getattr(item, "citation_id", None)
                or (item.get("citation_id") if isinstance(item, dict) else "")
            )
            if cid == citation_id:
                entry = item
                break
    except Exception:  # noqa: BLE001
        entry = None
    para_id = None
    if entry is not None:
        para_id = getattr(entry, "paragraph_id", None)
        if para_id is None and isinstance(entry, dict):
            para_id = entry.get("paragraph_id")
    if para_id is None:
        return None
    return session.get(BookSnapshotParagraph, int(para_id))


def _confirmed_chapter_function_asset(session: Session, asset_id: int) -> NarrativeAssetVersion | None:
    version = session.scalar(
        select(NarrativeAssetVersion).where(
            NarrativeAssetVersion.asset_id == asset_id,
            NarrativeAssetVersion.is_canonical.is_(True),
        )
    )
    if version is None:
        return None
    if version.review_status == ReviewStatus.CONFIRMED.value:
        return version
    attrs = json.loads(version.attributes_json or "{}")
    if attrs.get("state") == "confirmed":
        return version
    return None


def _persist_chapter_function_assets(
    session: Session,
    *,
    run_id: int,
    book_id: int,
    snapshot_id: int,
    result: dict[str, Any],
    catalog: Any,
) -> dict[str, Any]:
    """Persist chapter_function assets; never overwrite confirmed versions."""

    created = 0
    conflicts = 0
    skipped_confirmed = 0
    chapters = list(result.get("chapters") or [])
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        chapter_id = chapter.get("chapter_id")
        if chapter_id is None:
            continue
        order = int(chapter.get("chapter_order") or 0)
        primary = chapter.get("primary_function")
        title = f"ch{order}:{primary or 'null'}"
        summary_obj = chapter.get("observed_summary") if isinstance(chapter.get("observed_summary"), dict) else {}
        summary = str(summary_obj.get("value") or "")
        asset_key = build_asset_key(
            book_id=book_id,
            asset_type="chapter_function",
            stable_label=f"chapter-function:{chapter_id}",
        )
        asset = session.scalar(
            select(NarrativeAsset).where(
                NarrativeAsset.book_id == book_id,
                NarrativeAsset.asset_key == asset_key,
            )
        )
        if asset is None:
            asset = NarrativeAsset(
                book_id=book_id,
                asset_key=asset_key,
                lifecycle_status="active",
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            session.add(asset)
            session.flush()

        secondary = list(chapter.get("secondary_functions") or [])
        labels = [x for x in ((primary,) if primary else ()) + tuple(secondary) if x]
        attrs_base = {
            "whole_book_run_id": run_id,
            "contract_version": "v2",
            "schema_version": "2.0.0",
            "chapter_id": chapter_id,
            "chapter_order": order,
            "primary_function": primary,
            "secondary_functions": secondary,
            "function_labels": labels,
            "chapter_functions_v2": result,
            "chapter": chapter,
            "result_origin": "fixture",
            "fixture_test_data": True,
        }

        confirmed = _confirmed_chapter_function_asset(session, asset.id)
        if confirmed is not None:
            skipped_confirmed += 1
            candidate = NarrativeAssetVersion(
                asset_id=asset.id,
                book_snapshot_id=snapshot_id,
                asset_type="chapter_function",
                title=title,
                summary=summary,
                narrative_function=str(primary or ""),
                attributes_json=json.dumps(
                    {**attrs_base, "conflict_with_confirmed": True},
                    ensure_ascii=False,
                ),
                confidence=float(chapter.get("confidence") or 0.6),
                origin_type=OriginType.MODEL.value,
                review_status=ReviewStatus.CANDIDATE.value,
                is_canonical=False,
                created_at=utc_now(),
            )
            session.add(candidate)
            session.flush()
            session.add(
                AnalysisConflict(
                    book_id=book_id,
                    run_id=None,
                    book_snapshot_id=snapshot_id,
                    conflict_type=ConflictType.LOCKED_ASSET_VS_NEW_RUN.value,
                    left_ref_type="asset_version",
                    left_ref_id=str(confirmed.id),
                    right_ref_type="asset_version",
                    right_ref_id=str(candidate.id),
                    description=f"chapter_function conflict for {chapter_id}"[:500],
                    severity="warning",
                    status=ConflictStatus.OPEN.value,
                    resolution_json=json.dumps(
                        {
                            "target_asset_id": asset.id,
                            "whole_book_run_id": run_id,
                            "chapter_id": chapter_id,
                        },
                        ensure_ascii=False,
                    ),
                    created_at=utc_now(),
                )
            )
            conflicts += 1
            continue

        prior = session.scalar(
            select(NarrativeAssetVersion).where(
                NarrativeAssetVersion.asset_id == asset.id,
                NarrativeAssetVersion.is_canonical.is_(True),
            )
        )
        if prior is not None:
            prior.is_canonical = False
            session.flush()

        version = NarrativeAssetVersion(
            asset_id=asset.id,
            book_snapshot_id=snapshot_id,
            asset_type="chapter_function",
            title=title,
            summary=summary,
            narrative_function=str(primary or ""),
            attributes_json=json.dumps(attrs_base, ensure_ascii=False),
            confidence=float(chapter.get("confidence") or 0.6),
            origin_type=OriginType.MODEL.value,
            review_status=ReviewStatus.CANDIDATE.value,
            is_canonical=True,
            source_fingerprint=stable_request_hash(
                {"run_id": run_id, "chapter_id": chapter_id, "primary": primary}
            ),
            created_at=utc_now(),
        )
        session.add(version)
        session.flush()
        created += 1

        cids = list(summary_obj.get("citation_ids") or chapter.get("supporting_citation_ids") or [])
        if cids and catalog is not None:
            para = _citation_to_paragraph(session, snapshot_id, str(cids[0]), catalog)
            if para is not None:
                text = get_snapshot_paragraph_text(session, para.id) or ""
                session.add(
                    NarrativeAssetEvidence(
                        asset_version_id=version.id,
                        book_snapshot_id=snapshot_id,
                        snapshot_chapter_id=para.snapshot_chapter_id,
                        snapshot_paragraph_id=para.id,
                        paragraph_content_hash=str(para.content_hash or ""),
                        start_offset=0,
                        end_offset=min(len(text), 32),
                        evidence_role="support",
                        evidence_label=str(cids[0]),
                        created_at=utc_now(),
                    )
                )
    session.flush()
    return {
        "assets_created": created,
        "conflicts_created": conflicts,
        "confirmed_skipped": skipped_confirmed,
    }


def _finalize_run(session: Session, run_id: int) -> None:
    from app.narrative_core.services.whole_book_minimal_helpers_v1 import finalize_whole_book_run_v1

    finalize_whole_book_run_v1(session, run_id)


def _fail_chapter_functions_stage(
    session: Session,
    run_id: int,
    *,
    failure_code: str,
    message: str,
    finalize_run: bool = True,
) -> dict[str, Any]:
    run = get_run(session, run_id)
    stage = session.scalar(
        select(WholeBookRunStageRow).where(
            WholeBookRunStageRow.run_id == run_id,
            WholeBookRunStageRow.stage_code == CHAPTER_FUNCTIONS_STAGE_CODE,
        )
    )
    if stage is not None:
        stage.status = "failed"
        stage.last_error_code = failure_code
        stage.last_error_message_safe = message[:500]
        session.flush()
    envelope = {
        "result_status": "failed",
        "failure_code": failure_code,
        "contract_version": "v2",
        "chapter_functions": None,
        "coverage_scope": None,
        "fixture_test_data": True,
        "source_revision": {
            "run_id": run_id,
            "snapshot_id": run.snapshot_id,
            "book_id": run.book_id,
        },
    }
    upsert_checkpoint(
        session,
        run_id=run_id,
        stage_code=CHAPTER_FUNCTIONS_STAGE_CODE,
        checkpoint_key=CHAPTER_FUNCTIONS_RESULT_CHECKPOINT_KEY,
        payload=envelope,
    )
    if finalize_run:
        run.status = WholeBookRunStatus.failed.value
        run.failed_at = utc_now()
        run.failure_code = failure_code
        run.failure_message_safe = message[:500]
    run.current_stage_code = CHAPTER_FUNCTIONS_STAGE_CODE
    session.flush()
    return {
        "run_id": run_id,
        "reused": False,
        "result_status": "failed",
        "failure_code": failure_code,
        "provider_calls": 0,
    }


def _optional_structure_context(session: Session, run_id: int) -> dict[str, Any] | None:
    envelope = load_structure_checkpoint_envelope(session, run_id)
    if envelope is None:
        return None
    structure = envelope.get("structure")
    return structure if isinstance(structure, dict) else None


def _merge_chapter_results(parts: list[dict[str, Any]]) -> dict[str, Any]:
    if not parts:
        return {
            "contract_version": "v2",
            "evidence_contract_version": "v2",
            "coverage_scope": "insufficient",
            "chapters": [],
            "limitations": ["FIXTURE_TEST_DATA"],
        }
    chapters: list[dict[str, Any]] = []
    seen_orders: set[int] = set()
    limitations: list[str] = []
    for part in parts:
        for ch in part.get("chapters") or []:
            if not isinstance(ch, dict):
                continue
            order = int(ch.get("chapter_order") or -1)
            if order in seen_orders:
                continue
            seen_orders.add(order)
            chapters.append(ch)
        for lim in part.get("limitations") or []:
            if lim not in limitations:
                limitations.append(str(lim))
    chapters.sort(key=lambda c: int(c.get("chapter_order") or 0))
    base = dict(parts[-1])
    base["chapters"] = chapters
    base["limitations"] = limitations or ["FIXTURE_TEST_DATA"]
    if chapters and base.get("coverage_scope") == "insufficient":
        base["coverage_scope"] = "full_selected_range"
    return base


def synthesize_minimal_chapter_functions_v1(
    session: Session,
    run_id: int,
    transport: WholeBookProviderTransport | None = None,
    *,
    mode: FixtureChapterFunctionsMode = "available",
    finalize_run: bool = True,
) -> dict[str, Any]:
    run = get_run(session, run_id)
    # Structure may have soft-failed; allow CF when run was failed only by STRUCTURE_*.
    if run.status == WholeBookRunStatus.failed.value and str(run.failure_code or "").startswith(
        "STRUCTURE_"
    ):
        run.status = WholeBookRunStatus.running.value
        run.failed_at = None
        run.failure_code = None
        run.failure_message_safe = None
        session.flush()
    run = assert_run_not_terminal(session, run_id)

    overview_stage = session.scalar(
        select(WholeBookRunStageRow).where(
            WholeBookRunStageRow.run_id == run_id,
            WholeBookRunStageRow.stage_code == "synthesize_overview",
        )
    )
    if overview_stage is None or overview_stage.status != "completed":
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_RUN_INVALID_TRANSITION,
            "synthesize_overview stage not completed",
        )

    # Structure is optional: completed / skipped / failed / absent all OK.
    existing = _load_cf_checkpoint(session, run_id)
    if existing is not None and existing.get("result_status") in {
        "completed",
        "insufficient",
        "conflict",
    }:
        return {
            "run_id": run_id,
            "reused": True,
            "result_status": existing.get("result_status"),
            "provider_calls": 0,
            "coverage_scope": (existing.get("chapter_functions") or {}).get("coverage_scope"),
            "batch_count": existing.get("batch_count") or 0,
        }

    if run.snapshot_id is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_FOUND,
            "run missing snapshot",
        )

    catalog, citation_ids, caps, chapter_units = _build_snapshot_catalog(session, run.snapshot_id)
    structure_ctx = _optional_structure_context(session, run_id)
    effective_mode: FixtureChapterFunctionsMode = mode
    if not citation_ids or not chapter_units or not caps.get("can_identify_chapter_functions"):
        effective_mode = "insufficient"
        caps["can_identify_chapter_functions"] = False

    if transport is None:
        transport = FixtureChapterFunctionsTransport(
            mode=effective_mode,
            citation_ids=citation_ids,
            chapter_units=chapter_units,
            context_capabilities=caps,
            structure_context=structure_ctx,
        )
    elif isinstance(transport, FixtureChapterFunctionsTransport):
        if not transport.citation_ids:
            transport.citation_ids = citation_ids
        if not transport.chapter_units:
            transport.chapter_units = chapter_units
        if not transport.context_capabilities:
            transport.context_capabilities = caps
        if transport.structure_context is None:
            transport.structure_context = structure_ctx
        if transport.mode == "available" and effective_mode == "insufficient":
            transport.mode = "insufficient"

    expected_scope = "insufficient" if effective_mode == "insufficient" else "full_selected_range"
    if effective_mode == "partial":
        expected_scope = "partial_span"
    shape_caps = {
        "expected_coverage_scope": expected_scope,
        "permits_empty_observation": expected_scope == "insufficient",
        "requires_chapter_observation": expected_scope != "insufficient",
        "selected_chapter_orders": caps.get("selected_chapter_orders") or (),
        "selected_paragraph_count": int(caps.get("selected_paragraph_count") or 0),
        "selected_chapter_count": int(caps.get("selected_chapter_count") or 0),
    }

    consent_id = ensure_fixture_consent(session, run)
    orch = WholeBookProviderOrchestrator(
        session, engine_version="1.0.0", prompt_version=CHAPTER_FUNCTIONS_PROMPT_VERSION
    )
    batches = _batch_chapter_units(chapter_units)
    provider_calls = 0
    batch_payloads: list[dict[str, Any]] = []
    reused_all = True

    for batch_index, batch in enumerate(batches):
        unit_key = f"{CHAPTER_FUNCTIONS_UNIT_PREFIX}:batch:{batch_index}"
        batch_cids: list[str] = []
        for u in batch:
            for cid in u.get("citation_ids") or []:
                if cid not in batch_cids:
                    batch_cids.append(str(cid))
        if not batch_cids:
            batch_cids = list(citation_ids)

        request_payload = {
            "module_key": "chapter_functions",
            "contract_version": "v2",
            "operation_kind": "chapter_functions_initial",
            "run_id": run_id,
            "snapshot_id": run.snapshot_id,
            "batch_index": batch_index,
            "batch_count": len(batches),
            "chapter_units": batch,
            "citation_ids": batch_cids,
            "context_capabilities": caps,
            "structure_derived_context": (
                {
                    "present": structure_ctx is not None,
                    "marker": "DERIVED_CONTEXT_NOT_FACT",
                    "coverage_scope": (structure_ctx or {}).get("coverage_scope"),
                }
            ),
            "native_input_usage": {
                "chapter_analysis_asset_count": 0,
                "reader_journey_asset_count": 0,
                "aggregate_insights_asset_count": 0,
            },
            "fixture_test_data": True,
        }

        unit_result = orch.execute_provider_unit(
            run_id=run_id,
            stage_code=CHAPTER_FUNCTIONS_STAGE_CODE,
            unit_type=UNIT_SYNTHESIS,
            unit_key=unit_key,
            request_payload=request_payload,
            consent_id=consent_id,
            transport=transport,
        )
        if unit_result.get("status") == "failed":
            return _fail_chapter_functions_stage(
                session,
                run_id,
                failure_code="CHAPTER_FN_PROVIDER_UNIT_FAILED",
                message="chapter functions provider unit failed",
                finalize_run=finalize_run,
            )
        if not unit_result.get("reused"):
            reused_all = False
            provider_calls += 1

        if isinstance(transport, FixtureChapterFunctionsTransport):
            raw_payload = build_fixture_chapter_functions_v2(
                citation_ids=batch_cids,
                chapter_units=batch,
                mode=transport.mode,
                context_capabilities=transport.context_capabilities or caps,
                structure_context=transport.structure_context,
            )
        else:
            result_payload = unit_result.get("result_payload")
            if not isinstance(result_payload, dict) or not result_payload:
                raw = transport.invoke(
                    unit_key=unit_key,
                    unit_type=UNIT_SYNTHESIS,
                    request_payload=request_payload,
                )
                result_payload = dict(raw.result_payload or {})
            raw_payload = dict(result_payload)

        validation = validate_chapter_functions_provider_output_v2(
            raw_payload,
            allowed_citation_ids=batch_cids or citation_ids,
            catalog=catalog,
            capabilities=shape_caps,
            repair_count=0,
        )
        if not validation.ok:
            # Max one contract repair.
            repair_payload = dict(request_payload)
            repair_payload["operation_kind"] = "chapter_functions_contract_repair"
            repair_payload["failure_code"] = validation.failure_code
            repair_unit_key = f"{unit_key}:repair"
            repair_result = orch.execute_provider_unit(
                run_id=run_id,
                stage_code=CHAPTER_FUNCTIONS_STAGE_CODE,
                unit_type=UNIT_SYNTHESIS,
                unit_key=repair_unit_key,
                request_payload=repair_payload,
                consent_id=consent_id,
                transport=transport,
            )
            if not repair_result.get("reused"):
                reused_all = False
                provider_calls += 1
            if isinstance(transport, FixtureChapterFunctionsTransport):
                # Illegal modes stay illegal after repair; legal modes rebuild.
                if transport.mode in {
                    "failed_empty",
                    "failed_unknown_label",
                    "missing_citation",
                }:
                    repaired_raw = raw_payload
                else:
                    repaired_raw = build_fixture_chapter_functions_v2(
                        citation_ids=batch_cids,
                        chapter_units=batch,
                        mode="repair_success" if transport.mode != "insufficient" else "insufficient",
                        context_capabilities=transport.context_capabilities or caps,
                        structure_context=transport.structure_context,
                    )
            else:
                repaired_payload = repair_result.get("result_payload")
                if not isinstance(repaired_payload, dict) or not repaired_payload:
                    repaired = transport.invoke(
                        unit_key=repair_unit_key,
                        unit_type=UNIT_SYNTHESIS,
                        request_payload=repair_payload,
                    )
                    repaired_payload = dict(repaired.result_payload or {})
                repaired_raw = dict(repaired_payload)
            validation = validate_chapter_functions_provider_output_v2(
                repaired_raw,
                allowed_citation_ids=batch_cids or citation_ids,
                catalog=catalog,
                capabilities=shape_caps,
                repair_count=MAX_REPAIR_COUNT,
            )
            if not validation.ok or validation.typed_payload is None:
                primary = validation.failure_code or FAILURE_EMPTY_RESULT_AFTER_REPAIR
                if expected_scope != "insufficient" and not list(
                    (repaired_raw or {}).get("chapters") or []
                ):
                    primary = FAILURE_EMPTY_RESULT_AFTER_REPAIR
                return _fail_chapter_functions_stage(
                    session,
                    run_id,
                    failure_code=primary,
                    message="chapter functions contract failed after repair",
                    finalize_run=finalize_run,
                )
            batch_payloads.append(validation.typed_payload)
        else:
            assert validation.typed_payload is not None
            batch_payloads.append(validation.typed_payload)

    merged = _merge_chapter_results(batch_payloads)
    # Final whole-result validation (orders unique across batches).
    typed, err = _public_shape_validate(
        merged,
        allowed_citation_ids=citation_ids,
        capabilities=shape_caps,
    )
    if err is not None or typed is None:
        primary = err or FAILURE_REQUIRED_CHAPTER_MISSING
        if expected_scope != "insufficient" and not list(merged.get("chapters") or []):
            primary = FAILURE_EMPTY_RESULT_AFTER_REPAIR
        return _fail_chapter_functions_stage(
            session,
            run_id,
            failure_code=primary,
            message="chapter functions contract failed after merge validation",
            finalize_run=finalize_run,
        )
    result = typed

    persist_meta = _persist_chapter_function_assets(
        session,
        run_id=run_id,
        book_id=run.book_id,
        snapshot_id=run.snapshot_id,
        result=result,
        catalog=catalog,
    )
    result_status: Literal["completed", "insufficient", "conflict"] = "completed"
    if result.get("coverage_scope") == "insufficient":
        result_status = "insufficient"
    if persist_meta.get("conflicts_created", 0) > 0:
        result_status = "conflict"

    envelope = {
        "result_status": "completed" if result_status == "insufficient" else result_status,
        "product_result_status": result_status,
        "failure_code": None,
        "contract_version": "v2",
        "schema_version": "2.0.0",
        "coverage_scope": result.get("coverage_scope"),
        "chapter_functions": result,
        "fixture_test_data": True,
        "engine_id": CHAPTER_FUNCTIONS_ENGINE_ID,
        "prompt_version": CHAPTER_FUNCTIONS_PROMPT_VERSION,
        "persist": persist_meta,
        "batch_count": len(batches),
        "max_chapters_per_batch": MAX_CHAPTERS_PER_BATCH,
        "source_revision": {
            "run_id": run_id,
            "snapshot_id": run.snapshot_id,
            "book_id": run.book_id,
        },
        "evidence_references": [
            cid
            for chapter in result.get("chapters") or []
            if isinstance(chapter, dict)
            for cid in list(chapter.get("supporting_citation_ids") or [])
        ],
        "native_input_usage": {
            "chapter_analysis_asset_count": 0,
            "reader_journey_asset_count": 0,
            "aggregate_insights_asset_count": 0,
        },
    }
    if result_status == "insufficient":
        envelope["result_status"] = "completed"
        envelope["product_result_status"] = "insufficient"

    upsert_checkpoint(
        session,
        run_id=run_id,
        stage_code=CHAPTER_FUNCTIONS_STAGE_CODE,
        checkpoint_key=CHAPTER_FUNCTIONS_RESULT_CHECKPOINT_KEY,
        payload=envelope,
    )
    set_stage_completed(session, run_id, CHAPTER_FUNCTIONS_STAGE_CODE, progress_total=len(batches) or 1)
    run.current_stage_code = CHAPTER_FUNCTIONS_STAGE_CODE
    if finalize_run:
        _finalize_run(session, run_id)
    else:
        session.flush()

    return {
        "run_id": run_id,
        "reused": reused_all,
        "result_status": envelope["result_status"],
        "product_result_status": envelope.get("product_result_status"),
        "coverage_scope": result.get("coverage_scope"),
        "provider_calls": 0 if reused_all else provider_calls,
        "chapter_count": len(result.get("chapters") or []),
        "batch_count": len(batches),
        "persist": persist_meta,
    }
