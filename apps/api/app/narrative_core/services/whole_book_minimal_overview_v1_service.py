"""Minimal book overview synthesis orchestration (WB-1.6)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    BookSnapshot,
    NarrativeAssetEvidence,
    NarrativeAssetVersion,
    NarrativeEntity,
    NarrativeRelationVersion,
    WholeBookOverviewResult,
    WholeBookRunStageRow,
    utc_now,
)
from app.narrative_core.contracts.whole_book_contract_v1 import (
    BOOK_OVERVIEW_RESULT_VERSION,
    WHOLE_BOOK_CONTRACT_VERSION,
    AnalysisProvenanceV1,
    ArtifactState,
    BookOverviewResultV1,
    EntityAliasV1,
    EvidenceState,
    PersistedEvidenceV1,
    PersistedNarrativeAssetV1,
    PersistedNarrativeEntityV1,
    PersistedNarrativeRelationV1,
    ResultOrigin,
    WholeBookRunStatus,
    WholeBookSynthesisRequestV1,
    WholeBookSynthesisResponseV1,
)
from app.narrative_core.services.fixture_overview_synthesis_sample_s import (
    build_fixture_overview_response_v1,
)
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)
from app.narrative_core.services.whole_book_minimal_helpers_v1 import (
    OVERVIEW_ENGINE_ID,
    OVERVIEW_PROMPT_VERSION,
    assert_run_not_terminal,
    build_run_contract_dict,
    ensure_fixture_consent,
    native_input_usage,
    set_stage_completed,
    snapshot_metadata_dict,
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
from app.narrative_core.services.whole_book_windowing_v1_service import calculate_window_coverage_v1, list_windows


@dataclass
class FixtureOverviewTransport:
    inner: CountingFakeWholeBookProvider = field(default_factory=CountingFakeWholeBookProvider)
    entity_name_to_id: dict[str, int] = field(default_factory=dict)
    asset_title_to_id: dict[str, int] = field(default_factory=dict)
    evidence_ids: list[int] = field(default_factory=list)
    key_event_asset_ids: list[int] = field(default_factory=list)
    important_entity_ids: list[int] = field(default_factory=list)

    def invoke(self, *, unit_key: str, unit_type: str, request_payload: dict[str, Any]) -> ProviderCallResult:
        if unit_type != UNIT_SYNTHESIS:
            return self.inner.invoke(
                unit_key=unit_key, unit_type=unit_type, request_payload=request_payload
            )
        request = WholeBookSynthesisRequestV1.model_validate(request_payload)
        response = build_fixture_overview_response_v1(
            request,
            entity_name_to_id=self.entity_name_to_id,
            asset_title_to_id=self.asset_title_to_id,
            evidence_ids=self.evidence_ids,
            key_event_asset_ids=self.key_event_asset_ids,
            important_entity_ids=self.important_entity_ids,
        )
        return ProviderCallResult(ok=True, result_payload=response.model_dump(mode="json"))


def _load_materialized_projection(session: Session, run_id: int) -> dict[str, Any]:
    run = get_run(session, run_id)
    entities = list(
        session.scalars(select(NarrativeEntity).where(NarrativeEntity.created_by == str(run_id))).all()
    )
    versions = list(
        session.scalars(select(NarrativeAssetVersion)).all()
    )
    versions = [v for v in versions if json.loads(v.attributes_json or "{}").get("whole_book_run_id") == run_id]
    version_ids = [v.id for v in versions]
    evidences = (
        list(
            session.scalars(
                select(NarrativeAssetEvidence).where(
                    NarrativeAssetEvidence.asset_version_id.in_(version_ids)
                )
            ).all()
        )
        if version_ids
        else []
    )
    relations = [
        r
        for r in session.scalars(select(NarrativeRelationVersion)).all()
        if json.loads(r.attributes_json or "{}").get("whole_book_run_id") == run_id
    ]
    entity_name_to_id = {e.canonical_name: e.id for e in entities}
    asset_title_to_id = {v.title: v.asset_id for v in versions}
    key_events = [v.asset_id for v in versions if v.asset_type == "event"]
    return {
        "entities": entities,
        "versions": versions,
        "evidences": evidences,
        "relations": relations,
        "entity_name_to_id": entity_name_to_id,
        "asset_title_to_id": asset_title_to_id,
        "evidence_ids": [e.id for e in evidences],
        "key_event_asset_ids": key_events,
        "important_entity_ids": [e.id for e in entities],
        "snapshot_id": run.snapshot_id,
        "book_id": run.book_id,
    }


def _build_synthesis_request(session: Session, run_id: int) -> WholeBookSynthesisRequestV1:
    run = get_run(session, run_id)
    if run.snapshot_id is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_FOUND,
            "run missing snapshot",
        )
    proj = _load_materialized_projection(session, run_id)
    windows = list_windows(session, run_id)
    coverage = calculate_window_coverage_v1(
        session, snapshot_id=run.snapshot_id, run_id=run_id, windows=windows
    )
    provenance = AnalysisProvenanceV1(
        run_id=run.id,
        snapshot_id=run.snapshot_id,
        window_ids=[w.id for w in windows],
        engine_id=OVERVIEW_ENGINE_ID,
        engine_version="1.0.0",
        prompt_version=OVERVIEW_PROMPT_VERSION,
        result_origin=ResultOrigin.fixture,
        source_mode=run.mode,  # type: ignore[arg-type]
        deterministic=True,
        config_hashes={},
        generated_at=utc_now(),
    )
    entities_dto = [
        PersistedNarrativeEntityV1(
            entity_id=e.id,
            snapshot_id=run.snapshot_id,
            entity_type="character",
            canonical_name=e.canonical_name,
            aliases=[],
            state=ArtifactState.candidate,
            confidence=0.9,
            current_version_no=1,
            created_by_run_id=run_id,
            evidence_ids=[],
            provenance=provenance,
        )
        for e in proj["entities"]
    ]
    assets_dto = [
        PersistedNarrativeAssetV1(
            asset_id=v.asset_id,
            snapshot_id=run.snapshot_id,
            asset_type=v.asset_type,
            title=v.title,
            state=ArtifactState.candidate,
            confidence=float(v.confidence),
            subject_entity_ids=[],
            current_version_id=v.id,
            created_by_run_id=run_id,
            evidence_ids=[],
            provenance=provenance,
        )
        for v in proj["versions"]
    ]
    evidences_dto: list[PersistedEvidenceV1] = []
    return WholeBookSynthesisRequestV1(
        run=build_run_contract_dict(run),  # type: ignore[arg-type]
        snapshot=snapshot_metadata_dict(session, run.snapshot_id),
        coverage=coverage,  # type: ignore[arg-type]
        entities=entities_dto,
        assets=assets_dto,
        relations=[],
        evidences=evidences_dto,
        open_conflicts=[],
    )


def _validate_synthesis_ids(response: WholeBookSynthesisResponseV1, proj: dict[str, Any]) -> None:
    entity_ids = {e.id for e in proj["entities"]}
    asset_ids = {v.asset_id for v in proj["versions"]}
    evidence_ids = {e.id for e in proj["evidences"]}
    result = response.result
    for claim in result.claims:
        if claim.availability.value == "available":
            if not claim.supporting_asset_ids:
                raise ValueError(f"claim {claim.claim_key} missing supporting_asset_ids")
            if not claim.evidence_ids:
                raise ValueError(f"claim {claim.claim_key} missing evidence_ids")
        for aid in claim.supporting_asset_ids:
            if aid not in asset_ids:
                raise ValueError(f"unknown supporting_asset_id {aid}")
        for eid in claim.evidence_ids:
            if eid not in evidence_ids:
                raise ValueError(f"unknown evidence_id {eid}")
    for eid in result.important_entity_ids:
        if eid not in entity_ids:
            raise ValueError(f"unknown important_entity_id {eid}")
    for aid in result.key_event_asset_ids:
        if aid not in asset_ids:
            raise ValueError(f"unknown key_event_asset_id {aid}")


def _persist_overview(session: Session, run_id: int, result: BookOverviewResultV1) -> WholeBookOverviewResult:
    blob = json.dumps(result.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    result_hash = stable_request_hash({"result": result.model_dump(mode="json")})
    existing = session.scalar(select(WholeBookOverviewResult).where(WholeBookOverviewResult.run_id == run_id))
    if existing is None:
        row = WholeBookOverviewResult(
            run_id=run_id,
            book_id=result.book_id,
            snapshot_id=result.snapshot_id,
            result_version=BOOK_OVERVIEW_RESULT_VERSION,
            contract_version=WHOLE_BOOK_CONTRACT_VERSION,
            mode=result.mode.value,
            result_origin=result.result_origin.value,
            status=result.status,
            result_json=blob,
            result_hash=result_hash,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(row)
    else:
        existing.result_json = blob
        existing.result_hash = result_hash
        existing.status = result.status
        existing.updated_at = utc_now()
        row = existing
    session.flush()
    return row


def synthesize_minimal_book_overview_v1(
    session: Session,
    run_id: int,
    transport: WholeBookProviderTransport | None = None,
    *,
    finalize_run: bool = True,
) -> dict[str, Any]:
    run = assert_run_not_terminal(session, run_id)
    stage = session.scalar(
        select(WholeBookRunStageRow).where(
            WholeBookRunStageRow.run_id == run_id,
            WholeBookRunStageRow.stage_code == "materialize_assets",
        )
    )
    if stage is None or stage.status != "completed":
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_RUN_INVALID_TRANSITION,
            "materialize_assets stage not completed",
        )

    existing_overview = session.scalar(
        select(WholeBookOverviewResult).where(WholeBookOverviewResult.run_id == run_id)
    )
    if existing_overview is not None:
        return {"run_id": run_id, "reused": True, "overview_id": existing_overview.id}

    proj = _load_materialized_projection(session, run_id)
    if transport is None:
        transport = FixtureOverviewTransport(
            entity_name_to_id=proj["entity_name_to_id"],
            asset_title_to_id=proj["asset_title_to_id"],
            evidence_ids=proj["evidence_ids"],
            key_event_asset_ids=proj["key_event_asset_ids"],
            important_entity_ids=proj["important_entity_ids"],
        )

    request = _build_synthesis_request(session, run_id)
    from app.narrative_core.contracts.whole_book_contract_v1 import WholeBookRunV1, BookSnapshotMetadataV1

    request = WholeBookSynthesisRequestV1(
        run=WholeBookRunV1.model_validate(build_run_contract_dict(run)),
        snapshot=BookSnapshotMetadataV1.model_validate(snapshot_metadata_dict(session, run.snapshot_id)),  # type: ignore[arg-type]
        coverage=request.coverage,
        entities=request.entities,
        assets=request.assets,
        relations=request.relations,
        evidences=request.evidences,
        open_conflicts=[],
    )

    consent_id = ensure_fixture_consent(session, run)
    orch = WholeBookProviderOrchestrator(
        session, engine_version="1.0.0", prompt_version=OVERVIEW_PROMPT_VERSION
    )
    payload = request.model_dump(mode="json")
    unit_result = orch.execute_provider_unit(
        run_id=run_id,
        stage_code="synthesize_overview",
        unit_type=UNIT_SYNTHESIS,
        unit_key="overview:v1",
        request_payload=payload,
        consent_id=consent_id,
        transport=transport,
    )
    if unit_result.get("status") == "failed":
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_RUN_INVALID_TRANSITION,
            "overview synthesis failed",
        )

    if isinstance(transport, FixtureOverviewTransport):
        response = build_fixture_overview_response_v1(
            request,
            entity_name_to_id=proj["entity_name_to_id"],
            asset_title_to_id=proj["asset_title_to_id"],
            evidence_ids=proj["evidence_ids"],
            key_event_asset_ids=proj["key_event_asset_ids"],
            important_entity_ids=proj["important_entity_ids"],
        )
    else:
        result_payload = unit_result.get("result_payload")
        if not isinstance(result_payload, dict) or not result_payload:
            raw = transport.invoke(
                unit_key="overview:v1", unit_type=UNIT_SYNTHESIS, request_payload=payload
            )
            result_payload = raw.result_payload
        response = WholeBookSynthesisResponseV1.model_validate(result_payload)

    _validate_synthesis_ids(response, proj)
    row = _persist_overview(session, run_id, response.result)

    set_stage_completed(session, run_id, "synthesize_overview", progress_total=1)
    run.current_stage_code = "synthesize_overview"
    if finalize_run:
        # Standalone overview callers (pre-WB-2.1). Free pipeline passes False
        # so synthesize_structure_stages can run before project_result/finalize.
        for stage_code in ("project_result", "finalize"):
            set_stage_completed(session, run_id, stage_code, progress_total=1)
        run.status = WholeBookRunStatus.completed.value
        run.current_stage_code = "finalize"
        run.completed_at = utc_now()
    session.flush()

    return {
        "run_id": run_id,
        "reused": False,
        "overview_id": row.id,
        "provider_calls": 0 if unit_result.get("reused") else 1,
        "claims": len(response.result.claims),
    }
