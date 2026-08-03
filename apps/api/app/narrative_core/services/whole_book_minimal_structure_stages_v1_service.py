"""Minimal Free fixture structure stages synthesis (WB-2.1).

Native-input independent: Snapshot paragraphs + CitationCatalog only.
Does not read overview / chapter analysis / reader journey / aggregate insights.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisConflict,
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
from app.narrative_core.services.citation_catalog_v2 import build_catalog_from_paragraph_units
from app.narrative_core.services.fixture_structure_stages_sample_s import (
    FixtureStructureMode,
    build_fixture_structure_stages_v2,
)
from app.narrative_core.services.structure_stages_output_contract_v2 import (
    FAILURE_EMPTY_RESULT_AFTER_REPAIR,
    FAILURE_REQUIRED_STAGE_MISSING,
    _public_shape_validate,
)
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)
from app.narrative_core.services.whole_book_minimal_helpers_v1 import (
    STRUCTURE_ENGINE_ID,
    STRUCTURE_PROMPT_VERSION,
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
from app.services.whole_book_source_fingerprint import sha256_utf8

STRUCTURE_RESULT_CHECKPOINT_KEY = "structure_stages_result_v2"
STRUCTURE_UNIT_KEY = "structure_stages:v2"
STRUCTURE_STAGE_CODE = "synthesize_structure_stages"


@dataclass
class FixtureStructureTransport:
    """Fixture transport for structure_stages provider unit (no network)."""

    mode: FixtureStructureMode = "multi_stage"
    citation_ids: list[str] = field(default_factory=list)
    context_capabilities: dict[str, Any] = field(default_factory=dict)
    inner: CountingFakeWholeBookProvider = field(default_factory=CountingFakeWholeBookProvider)
    call_count: int = 0

    def invoke(self, *, unit_key: str, unit_type: str, request_payload: dict[str, Any]) -> ProviderCallResult:
        self.call_count += 1
        payload = build_fixture_structure_stages_v2(
            citation_ids=self.citation_ids,
            mode=self.mode,
            context_capabilities=self.context_capabilities,
        )
        return ProviderCallResult(ok=True, result_payload=payload)


def _load_structure_checkpoint(session: Session, run_id: int) -> dict[str, Any] | None:
    row = session.scalar(
        select(WholeBookCheckpoint).where(
            WholeBookCheckpoint.run_id == run_id,
            WholeBookCheckpoint.stage_code == STRUCTURE_STAGE_CODE,
            WholeBookCheckpoint.checkpoint_key == STRUCTURE_RESULT_CHECKPOINT_KEY,
        )
    )
    if row is None:
        return None
    try:
        return json.loads(row.checkpoint_payload_json or "{}")
    except json.JSONDecodeError:
        return None


def _build_snapshot_catalog(session: Session, snapshot_id: int) -> tuple[Any, list[str], dict[str, Any]]:
    paragraphs = list(
        session.scalars(
            select(BookSnapshotParagraph)
            .where(BookSnapshotParagraph.snapshot_id == snapshot_id)
            .order_by(BookSnapshotParagraph.global_paragraph_index.asc())
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
    caps = {
        "can_identify_local_stages": bool(units),
        "selected_chapter_count": len({u["chapter_id"] for u in units}),
        "selected_paragraph_count": len(units),
        "fixture_test_data": True,
    }
    if not units:
        return None, [], caps
    catalog = build_catalog_from_paragraph_units(
        context_bundle_hash=sha256_utf8(f"fixture-ss-{snapshot_id}"),
        snapshot_id=snapshot_id,
        paragraph_units=units,
    )
    return catalog, list(catalog.citation_ids), caps


def _citation_to_paragraph(
    session: Session, snapshot_id: int, citation_id: str, catalog: Any
) -> BookSnapshotParagraph | None:
    entry = None
    try:
        entries = getattr(catalog, "entries", None) or ()
        for item in entries:
            cid = str(getattr(item, "citation_id", None) or item.get("citation_id") if isinstance(item, dict) else "")
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


def _confirmed_structure_asset(session: Session, asset_id: int) -> NarrativeAssetVersion | None:
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


def _persist_structure_assets(
    session: Session,
    *,
    run_id: int,
    book_id: int,
    snapshot_id: int,
    structure: dict[str, Any],
    catalog: Any,
) -> dict[str, Any]:
    """Persist structure_stage assets; never overwrite confirmed versions."""

    created = 0
    conflicts = 0
    skipped_confirmed = 0
    stages = list(structure.get("stages") or [])
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        ref = str(stage.get("local_stage_ref") or stage.get("stage_key") or "").strip()
        if not ref:
            continue
        title = str(stage.get("title") or ref)
        summary_obj = stage.get("summary") if isinstance(stage.get("summary"), dict) else {}
        summary = str(summary_obj.get("value") or "")
        asset_key = build_asset_key(
            book_id=book_id,
            asset_type="structure_stage",
            stable_label=f"structure-stage:{ref}",
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

        confirmed = _confirmed_structure_asset(session, asset.id)
        if confirmed is not None:
            skipped_confirmed += 1
            # Conflict: new candidate version without touching confirmed canonical.
            candidate = NarrativeAssetVersion(
                asset_id=asset.id,
                book_snapshot_id=snapshot_id,
                asset_type="structure_stage",
                title=title,
                summary=summary,
                narrative_function=str(stage.get("narrative_function") or ""),
                attributes_json=json.dumps(
                    {
                        "whole_book_run_id": run_id,
                        "contract_version": "v2",
                        "schema_version": "2.0.0",
                        "local_stage_ref": ref,
                        "structure_stages_v2": structure,
                        "stage": stage,
                        "result_origin": "fixture",
                        "fixture_test_data": True,
                        "conflict_with_confirmed": True,
                    },
                    ensure_ascii=False,
                ),
                confidence=float(stage.get("confidence") or 0.6),
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
                    description=f"structure_stage conflict for {ref}"[:500],
                    severity="warning",
                    status=ConflictStatus.OPEN.value,
                    resolution_json=json.dumps(
                        {
                            "target_asset_id": asset.id,
                            "whole_book_run_id": run_id,
                            "local_stage_ref": ref,
                        },
                        ensure_ascii=False,
                    ),
                    created_at=utc_now(),
                )
            )
            conflicts += 1
            continue

        # Demote prior canonical if present and not confirmed.
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
            asset_type="structure_stage",
            title=title,
            summary=summary,
            narrative_function=str(stage.get("narrative_function") or ""),
            attributes_json=json.dumps(
                {
                    "whole_book_run_id": run_id,
                    "contract_version": "v2",
                    "schema_version": "2.0.0",
                    "local_stage_ref": ref,
                    "structure_stages_v2": structure,
                    "stage": stage,
                    "result_origin": "fixture",
                    "fixture_test_data": True,
                },
                ensure_ascii=False,
            ),
            confidence=float(stage.get("confidence") or 0.6),
            origin_type=OriginType.MODEL.value,
            review_status=ReviewStatus.CANDIDATE.value,
            is_canonical=True,
            source_fingerprint=stable_request_hash({"run_id": run_id, "ref": ref, "title": title}),
            created_at=utc_now(),
        )
        session.add(version)
        session.flush()
        created += 1

        # Bind first summary citation as evidence when resolvable.
        cids = list(summary_obj.get("citation_ids") or [])
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
    run = get_run(session, run_id)
    for stage_code in ("project_result", "finalize"):
        set_stage_completed(session, run_id, stage_code, progress_total=1)
    run.status = WholeBookRunStatus.completed.value
    run.current_stage_code = "finalize"
    run.completed_at = utc_now()
    session.flush()


def _fail_structure_stage(
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
            WholeBookRunStageRow.stage_code == STRUCTURE_STAGE_CODE,
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
        "structure": None,
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
        stage_code=STRUCTURE_STAGE_CODE,
        checkpoint_key=STRUCTURE_RESULT_CHECKPOINT_KEY,
        payload=envelope,
    )
    run.current_stage_code = STRUCTURE_STAGE_CODE
    # When a later stage (chapter_functions) follows, soft-fail the structure stage only.
    if finalize_run:
        run.status = WholeBookRunStatus.failed.value
        run.failed_at = utc_now()
        run.failure_code = failure_code
        run.failure_message_safe = message[:500]
    else:
        run.failure_code = failure_code
        run.failure_message_safe = message[:500]
    session.flush()
    return {
        "run_id": run_id,
        "reused": False,
        "result_status": "failed",
        "failure_code": failure_code,
        "provider_calls": 0,
    }


def synthesize_minimal_structure_stages_v1(
    session: Session,
    run_id: int,
    transport: WholeBookProviderTransport | None = None,
    *,
    mode: FixtureStructureMode = "multi_stage",
    finalize_run: bool = True,
) -> dict[str, Any]:
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

    existing = _load_structure_checkpoint(session, run_id)
    if existing is not None and existing.get("result_status") in {"completed", "insufficient", "conflict"}:
        return {
            "run_id": run_id,
            "reused": True,
            "result_status": existing.get("result_status"),
            "provider_calls": 0,
            "coverage_scope": (existing.get("structure") or {}).get("coverage_scope"),
        }

    if run.snapshot_id is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_FOUND,
            "run missing snapshot",
        )

    catalog, citation_ids, caps = _build_snapshot_catalog(session, run.snapshot_id)
    effective_mode: FixtureStructureMode = mode
    if not citation_ids or not caps.get("can_identify_local_stages"):
        effective_mode = "insufficient"
        caps["can_identify_local_stages"] = False

    if transport is None:
        transport = FixtureStructureTransport(
            mode=effective_mode,
            citation_ids=citation_ids,
            context_capabilities=caps,
        )
    elif isinstance(transport, FixtureStructureTransport):
        if not transport.citation_ids:
            transport.citation_ids = citation_ids
        if not transport.context_capabilities:
            transport.context_capabilities = caps
        if transport.mode == "multi_stage" and effective_mode == "insufficient":
            transport.mode = "insufficient"

    request_payload = {
        "module_key": "structure_stages",
        "contract_version": "v2",
        "run_id": run_id,
        "snapshot_id": run.snapshot_id,
        "citation_ids": citation_ids,
        "context_capabilities": caps,
        "native_input_usage": {
            "chapter_analysis_asset_count": 0,
            "reader_journey_asset_count": 0,
            "aggregate_insights_asset_count": 0,
        },
        "fixture_test_data": True,
    }

    consent_id = ensure_fixture_consent(session, run)
    orch = WholeBookProviderOrchestrator(
        session, engine_version="1.0.0", prompt_version=STRUCTURE_PROMPT_VERSION
    )
    unit_result = orch.execute_provider_unit(
        run_id=run_id,
        stage_code=STRUCTURE_STAGE_CODE,
        unit_type=UNIT_SYNTHESIS,
        unit_key=STRUCTURE_UNIT_KEY,
        request_payload=request_payload,
        consent_id=consent_id,
        transport=transport,
    )
    if unit_result.get("status") == "failed":
        return _fail_structure_stage(
            session,
            run_id,
            failure_code="STRUCTURE_PROVIDER_UNIT_FAILED",
            message="structure stages provider unit failed",
            finalize_run=finalize_run,
        )

    if isinstance(transport, FixtureStructureTransport):
        structure = build_fixture_structure_stages_v2(
            citation_ids=transport.citation_ids or citation_ids,
            mode=transport.mode,
            context_capabilities=transport.context_capabilities or caps,
        )
    else:
        raw = transport.invoke(
            unit_key=STRUCTURE_UNIT_KEY,
            unit_type=UNIT_SYNTHESIS,
            request_payload=request_payload,
        )
        structure = dict(raw.result_payload or {})

    # Server-frozen expected scope for empty-policy.
    expected_scope = "insufficient" if effective_mode == "insufficient" else "full_selected_range"
    shape_caps = dict(caps)
    if expected_scope == "insufficient":
        shape_caps = {
            "selected_chapter_orders": (),
            "all_chapter_orders": (),
            "selected_paragraph_count": 0,
            "batch_count": 0,
            "can_identify_local_stages": False,
        }
    else:
        # Capability geometry that freezes expected_coverage_scope=full_selected_range.
        orders = tuple(range(1, max(1, int(caps.get("selected_chapter_count") or 1)) + 1))
        shape_caps = {
            "selected_chapter_orders": orders,
            "all_chapter_orders": orders,
            "selected_paragraph_count": int(caps.get("selected_paragraph_count") or len(citation_ids)),
            "batch_count": 1,
            "can_identify_local_stages": True,
        }
    typed, err = _public_shape_validate(
        structure,
        allowed_citation_ids=citation_ids,
        capabilities=shape_caps,
    )
    if err is not None or typed is None:
        primary = err or FAILURE_REQUIRED_STAGE_MISSING
        if expected_scope != "insufficient" and not list(structure.get("stages") or []):
            primary = FAILURE_EMPTY_RESULT_AFTER_REPAIR
        return _fail_structure_stage(
            session,
            run_id,
            failure_code=primary,
            message="structure stages contract failed after fixture validation",
            finalize_run=finalize_run,
        )
    structure = typed

    persist_meta = _persist_structure_assets(
        session,
        run_id=run_id,
        book_id=run.book_id,
        snapshot_id=run.snapshot_id,
        structure=structure,
        catalog=catalog,
    )
    result_status: Literal["completed", "insufficient", "conflict"] = "completed"
    if structure.get("coverage_scope") == "insufficient":
        result_status = "insufficient"
    if persist_meta.get("conflicts_created", 0) > 0:
        result_status = "conflict"

    envelope = {
        "result_status": "completed" if result_status == "insufficient" else result_status,
        "product_result_status": result_status,
        "failure_code": None,
        "contract_version": "v2",
        "schema_version": "2.0.0",
        "coverage_scope": structure.get("coverage_scope"),
        "structure": structure,
        "fixture_test_data": True,
        "engine_id": STRUCTURE_ENGINE_ID,
        "prompt_version": STRUCTURE_PROMPT_VERSION,
        "persist": persist_meta,
        "source_revision": {
            "run_id": run_id,
            "snapshot_id": run.snapshot_id,
            "book_id": run.book_id,
        },
        "evidence_references": [
            cid
            for stage in structure.get("stages") or []
            if isinstance(stage, dict)
            for cid in list((stage.get("summary") or {}).get("citation_ids") or [])
        ],
    }
    # Product API: legal insufficient is completed.
    if result_status == "insufficient":
        envelope["result_status"] = "completed"
        envelope["product_result_status"] = "insufficient"

    upsert_checkpoint(
        session,
        run_id=run_id,
        stage_code=STRUCTURE_STAGE_CODE,
        checkpoint_key=STRUCTURE_RESULT_CHECKPOINT_KEY,
        payload=envelope,
    )
    set_stage_completed(session, run_id, STRUCTURE_STAGE_CODE, progress_total=1)
    run.current_stage_code = STRUCTURE_STAGE_CODE
    if finalize_run:
        _finalize_run(session, run_id)
    else:
        session.flush()

    return {
        "run_id": run_id,
        "reused": bool(unit_result.get("reused")),
        "result_status": envelope["result_status"],
        "product_result_status": envelope.get("product_result_status"),
        "coverage_scope": structure.get("coverage_scope"),
        "provider_calls": 0 if unit_result.get("reused") else 1,
        "stage_count": len(structure.get("stages") or []),
        "persist": persist_meta,
    }
