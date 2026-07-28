"""Conservative cross-window materialization (WB-1.5)."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    BookSnapshot,
    NarrativeAsset,
    NarrativeAssetEvidence,
    NarrativeAssetVersion,
    NarrativeEntity,
    NarrativeEntityAlias,
    NarrativeRelation,
    NarrativeRelationVersion,
    WholeBookCheckpoint,
    WholeBookWindowAnalysisResult,
    utc_now,
)
from app.narrative_core.asset_key import build_asset_key, build_relation_key
from app.narrative_core.contracts.whole_book_contract_v1 import (
    CandidateAssetV1,
    CandidateEntityV1,
    CandidateRelationV1,
    WholeBookWindowAnalysisResponseV1,
)
from app.narrative_core.contracts.whole_book_contract_v1.common import sha256_hex
from app.narrative_core.enums import OriginType, ReviewStatus
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)
from app.narrative_core.services.whole_book_minimal_helpers_v1 import (
    MINIMAL_ASSET_TYPES,
    MINIMAL_RELATION_TYPES,
    set_stage_completed,
    upsert_checkpoint,
)
from app.narrative_core.services.whole_book_run_v1_service import get_run
from app.services.whole_book_source_fingerprint import canonical_json_bytes, sha256_utf8

_QUOTE_WRAPPERS = "\"\"''《》「」『』"


def normalize_entity_name_v1(name: str) -> str:
    text = unicodedata.normalize("NFKC", name or "")
    text = "".join(" " if ch.isspace() else ch for ch in text)
    text = re.sub(r" +", " ", text.strip())
    while text and text[0] in _QUOTE_WRAPPERS:
        text = text[1:].lstrip()
    while text and text[-1] in _QUOTE_WRAPPERS:
        text = text[:-1].rstrip()
    return text.casefold()


@dataclass
class _EntityState:
    entity_id: int
    canonical_name: str
    normalized_name: str
    aliases: set[str] = field(default_factory=set)
    confidence: float = 0.0


@dataclass
class _MaterializationContext:
    run_id: int
    book_id: int
    snapshot_id: int
    candidate_to_entity: dict[str, int] = field(default_factory=dict)
    candidate_to_asset: dict[str, int] = field(default_factory=dict)
    entity_states: dict[int, _EntityState] = field(default_factory=dict)
    asset_signatures: dict[str, int] = field(default_factory=dict)
    evidence_keys: dict[tuple[int, int, int, int, str, str], int] = field(default_factory=dict)
    relation_keys: dict[str, int] = field(default_factory=dict)
    entity_endpoint_assets: dict[int, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    ambiguous_entity_merge_count: int = 0
    rejected_candidate_count: int = 0


def compute_event_signature_v1(
    candidate_asset: CandidateAssetV1,
    mapped_entity_ids: list[int],
    core_locator: dict[str, Any],
) -> str:
    payload = {
        "asset_type": candidate_asset.asset_type,
        "title": normalize_entity_name_v1(candidate_asset.title),
        "participants": sorted(mapped_entity_ids),
        "core_evidence": core_locator,
    }
    return sha256_hex(canonical_json_bytes(payload).decode("utf-8"))


def compute_asset_signature_v1(
    candidate_asset: CandidateAssetV1,
    mapped_entity_ids: list[int],
    core_locator: dict[str, Any],
) -> str:
    if candidate_asset.asset_type == "event":
        return compute_event_signature_v1(candidate_asset, mapped_entity_ids, core_locator)
    payload: dict[str, Any] = {
        "asset_type": candidate_asset.asset_type,
        "title": normalize_entity_name_v1(candidate_asset.title),
        "core_evidence": core_locator,
    }
    if candidate_asset.asset_type == "character_profile" and mapped_entity_ids:
        payload["subject_entity_id"] = mapped_entity_ids[0]
    elif candidate_asset.asset_type == "goal":
        payload["goal_text"] = normalize_entity_name_v1(
            str(candidate_asset.payload.get("goal_text", candidate_asset.summary))
        )
        if mapped_entity_ids:
            payload["holder_entity_id"] = mapped_entity_ids[0]
    elif candidate_asset.asset_type == "conflict":
        payload["conflict_text"] = normalize_entity_name_v1(
            str(candidate_asset.payload.get("conflict_text", candidate_asset.summary))
        )
        payload["side_ids"] = sorted(mapped_entity_ids)
    elif candidate_asset.asset_type == "question":
        payload["question_text"] = normalize_entity_name_v1(
            str(candidate_asset.payload.get("question_text", candidate_asset.summary))
        )
    elif candidate_asset.asset_type == "setting_fact":
        payload["fact_text"] = normalize_entity_name_v1(
            str(candidate_asset.payload.get("fact_text", candidate_asset.summary))
        )
    return sha256_hex(canonical_json_bytes(payload).decode("utf-8"))


def _load_valid_window_responses(session: Session, run_id: int) -> list[tuple[int, WholeBookWindowAnalysisResponseV1]]:
    rows = session.scalars(
        select(WholeBookWindowAnalysisResult)
        .where(
            WholeBookWindowAnalysisResult.run_id == run_id,
            WholeBookWindowAnalysisResult.validation_status == "valid",
        )
        .order_by(WholeBookWindowAnalysisResult.window_id.asc())
    ).all()
    return [
        (row.window_id, WholeBookWindowAnalysisResponseV1.model_validate(json.loads(row.response_json)))
        for row in rows
    ]


def _entity_merge_matches(ctx: _MaterializationContext, candidate: CandidateEntityV1) -> list[int]:
    norm = normalize_entity_name_v1(candidate.canonical_name)
    matches: set[int] = set()
    for state in ctx.entity_states.values():
        if state.normalized_name == norm or norm in state.aliases:
            matches.add(state.entity_id)
        for alias in candidate.aliases:
            alias_norm = normalize_entity_name_v1(alias.name)
            if alias_norm == state.normalized_name or alias_norm in state.aliases:
                matches.add(state.entity_id)
    return sorted(matches)


def _create_entity(session: Session, ctx: _MaterializationContext, candidate: CandidateEntityV1) -> int:
    norm = normalize_entity_name_v1(candidate.canonical_name)
    entity = NarrativeEntity(
        book_id=ctx.book_id,
        entity_type="character",
        canonical_name=candidate.canonical_name,
        normalized_name=norm,
        lifecycle_status="active",
        created_by=str(ctx.run_id),
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session.add(entity)
    session.flush()
    ctx.entity_states[entity.id] = _EntityState(
        entity_id=entity.id,
        canonical_name=candidate.canonical_name,
        normalized_name=norm,
        confidence=float(candidate.confidence),
    )
    return entity.id


def _register_alias(session: Session, ctx: _MaterializationContext, entity_id: int, alias_text: str) -> None:
    norm = normalize_entity_name_v1(alias_text)
    state = ctx.entity_states[entity_id]
    if norm == state.normalized_name or norm in state.aliases:
        return
    existing = session.scalar(
        select(NarrativeEntityAlias).where(
            NarrativeEntityAlias.entity_id == entity_id,
            NarrativeEntityAlias.normalized_alias == norm,
        )
    )
    if existing is None:
        session.add(
            NarrativeEntityAlias(
                entity_id=entity_id,
                alias_text=alias_text,
                normalized_alias=norm,
                source_run_id=None,
                source_snapshot_id=ctx.snapshot_id,
                review_status="candidate",
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )
    state.aliases.add(norm)
    session.flush()


def _resolve_entity(session: Session, ctx: _MaterializationContext, candidate: CandidateEntityV1) -> int:
    if candidate.candidate_key in ctx.candidate_to_entity:
        return ctx.candidate_to_entity[candidate.candidate_key]
    matches = _entity_merge_matches(ctx, candidate)
    if len(matches) > 1:
        ctx.ambiguous_entity_merge_count += 1
        ctx.warnings.append("entity_merge_ambiguous")
        entity_id = _create_entity(session, ctx, candidate)
    elif len(matches) == 1:
        entity_id = matches[0]
        state = ctx.entity_states[entity_id]
        state.confidence = max(state.confidence, float(candidate.confidence))
    else:
        entity_id = _create_entity(session, ctx, candidate)
    for alias in candidate.aliases:
        _register_alias(session, ctx, entity_id, alias.name)
    cand_norm = normalize_entity_name_v1(candidate.canonical_name)
    state = ctx.entity_states[entity_id]
    if cand_norm != state.normalized_name:
        _register_alias(session, ctx, entity_id, candidate.canonical_name)
    ctx.candidate_to_entity[candidate.candidate_key] = entity_id
    return entity_id


def _persist_evidence_for_version(
    session: Session,
    ctx: _MaterializationContext,
    response: WholeBookWindowAnalysisResponseV1,
    evidence_key: str,
    asset_version_id: int,
) -> int | None:
    evidence = next((e for e in response.evidences if e.evidence_key == evidence_key), None)
    if evidence is None:
        return None
    locator = evidence.locator
    key = (
        ctx.snapshot_id,
        locator.snapshot_paragraph_id,
        locator.start_offset,
        locator.end_offset,
        locator.quote_hash,
        locator.paragraph_text_hash,
    )
    if key in ctx.evidence_keys:
        return ctx.evidence_keys[key]
    existing = session.scalar(
        select(NarrativeAssetEvidence).where(
            NarrativeAssetEvidence.book_snapshot_id == ctx.snapshot_id,
            NarrativeAssetEvidence.snapshot_paragraph_id == locator.snapshot_paragraph_id,
            NarrativeAssetEvidence.start_offset == locator.start_offset,
            NarrativeAssetEvidence.end_offset == locator.end_offset,
            NarrativeAssetEvidence.paragraph_content_hash == locator.paragraph_text_hash,
            NarrativeAssetEvidence.asset_version_id == asset_version_id,
        )
    )
    if existing is not None:
        ctx.evidence_keys[key] = existing.id
        return existing.id
    row = NarrativeAssetEvidence(
        asset_version_id=asset_version_id,
        book_snapshot_id=ctx.snapshot_id,
        snapshot_chapter_id=locator.snapshot_chapter_id,
        snapshot_paragraph_id=locator.snapshot_paragraph_id,
        paragraph_content_hash=locator.paragraph_text_hash,
        start_offset=locator.start_offset,
        end_offset=locator.end_offset,
        evidence_role="support",
        evidence_label=locator.quote_text[:500],
        created_at=utc_now(),
    )
    session.add(row)
    session.flush()
    ctx.evidence_keys[key] = row.id
    return row.id


def _ensure_entity_endpoint_asset(session: Session, ctx: _MaterializationContext, entity_id: int) -> int:
    if entity_id in ctx.entity_endpoint_assets:
        return ctx.entity_endpoint_assets[entity_id]
    state = ctx.entity_states[entity_id]
    asset_key = build_asset_key(
        book_id=ctx.book_id,
        asset_type="character_profile",
        stable_label=f"endpoint:{entity_id}",
    )
    asset = session.scalar(
        select(NarrativeAsset).where(NarrativeAsset.book_id == ctx.book_id, NarrativeAsset.asset_key == asset_key)
    )
    if asset is None:
        asset = NarrativeAsset(
            book_id=ctx.book_id,
            asset_key=asset_key,
            lifecycle_status="active",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(asset)
        session.flush()
        session.add(
            NarrativeAssetVersion(
                asset_id=asset.id,
                run_id=None,
                book_snapshot_id=ctx.snapshot_id,
                asset_type="character_profile",
                title=f"{state.canonical_name} endpoint",
                summary="Structural relation endpoint",
                attributes_json=json.dumps({"structural_endpoint": True, "entity_id": entity_id, "whole_book_run_id": ctx.run_id}),
                confidence=1.0,
                origin_type=OriginType.MODEL.value,
                review_status="candidate",
                is_canonical=True,
                created_at=utc_now(),
            )
        )
        session.flush()
    ctx.entity_endpoint_assets[entity_id] = asset.id
    return asset.id


def _versions_for_wb_run(session: Session, run_id: int) -> list[NarrativeAssetVersion]:
    out: list[NarrativeAssetVersion] = []
    for row in session.scalars(select(NarrativeAssetVersion)).all():
        attrs = json.loads(row.attributes_json or "{}")
        if attrs.get("whole_book_run_id") == run_id:
            out.append(row)
    return out


def _relations_for_wb_run(session: Session, run_id: int) -> list[NarrativeRelationVersion]:
    out: list[NarrativeRelationVersion] = []
    for row in session.scalars(select(NarrativeRelationVersion)).all():
        attrs = json.loads(row.attributes_json or "{}")
        if attrs.get("whole_book_run_id") == run_id:
            out.append(row)
    return out


def _counts_for_run(session: Session, run_id: int, book_id: int) -> dict[str, int]:
    entities = list(
        session.scalars(select(NarrativeEntity).where(NarrativeEntity.created_by == str(run_id))).all()
    )
    versions = _versions_for_wb_run(session, run_id)
    version_ids = [v.id for v in versions]
    evidences = (
        list(
            session.scalars(
                select(NarrativeAssetEvidence).where(NarrativeAssetEvidence.asset_version_id.in_(version_ids))
            ).all()
        )
        if version_ids
        else []
    )
    relations = _relations_for_wb_run(session, run_id)
    return {
        "entity_count": len(entities),
        "asset_count": len(versions),
        "evidence_count": len(evidences),
        "relation_count": len(relations),
    }


def materialize_minimal_narrative_assets_v1(session: Session, run_id: int) -> dict[str, Any]:
    run = get_run(session, run_id)
    if run.snapshot_id is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_FOUND,
            f"run {run_id} has no snapshot",
        )
    snapshot = session.get(BookSnapshot, run.snapshot_id)
    if snapshot is None:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_FOUND,
            "snapshot missing",
        )

    before = _counts_for_run(session, run_id, run.book_id)
    existing_cp = session.scalar(
        select(WholeBookCheckpoint).where(
            WholeBookCheckpoint.run_id == run_id,
            WholeBookCheckpoint.stage_code == "materialize_assets",
            WholeBookCheckpoint.checkpoint_key == "minimal_asset_materialization_v1",
        )
    )
    if existing_cp is not None and before["entity_count"] > 0:
        payload = json.loads(existing_cp.checkpoint_payload_json or "{}")
        return {"run_id": run_id, "reused": True, "warnings": [], "checkpoint": payload, **before}

    window_responses = _load_valid_window_responses(session, run_id)
    if not window_responses:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_FOUND,
            "no valid window analysis results",
        )

    ctx = _MaterializationContext(run_id=run_id, book_id=run.book_id, snapshot_id=snapshot.id)

    for _window_id, response in window_responses:
        for candidate in response.entities:
            _resolve_entity(session, ctx, candidate)

    for _window_id, response in window_responses:
        for relation in response.relations:
            if relation.relation_type != "alias_of":
                continue
            sub_key = relation.subject.candidate_key
            obj_key = relation.object.candidate_key
            if sub_key in ctx.candidate_to_entity and obj_key in ctx.candidate_to_entity:
                sub_id = ctx.candidate_to_entity[sub_key]
                obj_id = ctx.candidate_to_entity[obj_key]
                if sub_id != obj_id:
                    sub_state = ctx.entity_states[sub_id]
                    obj_state = ctx.entity_states[obj_id]
                    _register_alias(session, ctx, obj_id, sub_state.canonical_name)
                    for alias in sub_state.aliases:
                        _register_alias(session, ctx, obj_id, alias)
                    ctx.candidate_to_entity[sub_key] = obj_id

    for window_id, response in window_responses:
        locators = {e.evidence_key: e.locator for e in response.evidences}
        for asset in response.assets:
            if asset.asset_type not in MINIMAL_ASSET_TYPES:
                ctx.rejected_candidate_count += 1
                continue
            core_key = asset.evidence_keys[0]
            if core_key not in locators:
                ctx.rejected_candidate_count += 1
                continue
            locator = locators[core_key]
            core_locator = {
                "snapshot_paragraph_id": locator.snapshot_paragraph_id,
                "start_offset": locator.start_offset,
                "end_offset": locator.end_offset,
            }
            mapped_entities = [
                ctx.candidate_to_entity[k] for k in asset.subject_entity_keys if k in ctx.candidate_to_entity
            ]
            signature = compute_asset_signature_v1(asset, mapped_entities, core_locator)
            if signature in ctx.asset_signatures:
                ctx.candidate_to_asset[asset.candidate_key] = ctx.asset_signatures[signature]
                continue
            asset_key = build_asset_key(
                book_id=ctx.book_id, asset_type=asset.asset_type, stable_label=signature[:32]
            )
            row = session.scalar(
                select(NarrativeAsset).where(
                    NarrativeAsset.book_id == ctx.book_id, NarrativeAsset.asset_key == asset_key
                )
            )
            if row is None:
                row = NarrativeAsset(
                    book_id=ctx.book_id,
                    asset_key=asset_key,
                    lifecycle_status="active",
                    created_at=utc_now(),
                    updated_at=utc_now(),
                )
                session.add(row)
                session.flush()
            payload_hash = sha256_hex(
                canonical_json_bytes(asset.payload or {"summary": asset.summary}).decode("utf-8")
            )
            attrs = dict(asset.payload or {})
            attrs["signature"] = signature
            attrs["subject_entity_ids"] = mapped_entities
            attrs["source_window_ids"] = [window_id]
            attrs["whole_book_run_id"] = run_id
            version = NarrativeAssetVersion(
                asset_id=row.id,
                run_id=None,
                book_snapshot_id=ctx.snapshot_id,
                asset_type=asset.asset_type,
                title=asset.title,
                summary=asset.summary,
                attributes_json=json.dumps(attrs, ensure_ascii=False),
                confidence=float(asset.confidence),
                origin_type=OriginType.MODEL.value,
                review_status="candidate",
                is_canonical=True,
                source_fingerprint=payload_hash,
                created_at=utc_now(),
            )
            session.add(version)
            session.flush()
            for ev_key in asset.evidence_keys:
                _persist_evidence_for_version(session, ctx, response, ev_key, version.id)
            ctx.asset_signatures[signature] = row.id
            ctx.candidate_to_asset[asset.candidate_key] = row.id

    for window_id, response in window_responses:
        for relation in response.relations:
            if relation.relation_type not in MINIMAL_RELATION_TYPES or relation.relation_type == "alias_of":
                continue
            sub_asset = _map_endpoint(session, ctx, relation.subject.candidate_key, relation.subject.kind.value)
            obj_asset = _map_endpoint(session, ctx, relation.object.candidate_key, relation.object.kind.value)
            if sub_asset is None or obj_asset is None:
                ctx.rejected_candidate_count += 1
                continue
            rel_key = build_relation_key(
                book_id=ctx.book_id,
                source_asset_id=sub_asset,
                target_asset_id=obj_asset,
                identity_fingerprint=f"{relation.relation_type}|{relation.candidate_key}",
            )
            if rel_key in ctx.relation_keys:
                continue
            rel_row = session.scalar(
                select(NarrativeRelation).where(
                    NarrativeRelation.book_id == ctx.book_id, NarrativeRelation.relation_key == rel_key
                )
            )
            if rel_row is None:
                rel_row = NarrativeRelation(
                    book_id=ctx.book_id,
                    source_asset_id=sub_asset,
                    target_asset_id=obj_asset,
                    relation_key=rel_key,
                    lifecycle_status="active",
                    created_at=utc_now(),
                    updated_at=utc_now(),
                )
                session.add(rel_row)
                session.flush()
            contract_endpoints = {
                "subject": relation.subject.model_dump(mode="json"),
                "object": relation.object.model_dump(mode="json"),
            }
            session.add(
                NarrativeRelationVersion(
                    relation_id=rel_row.id,
                    run_id=None,
                    book_snapshot_id=ctx.snapshot_id,
                    relation_type=relation.relation_type,
                    summary=f"{relation.relation_type} relation",
                    attributes_json=json.dumps(
                        {"contract_endpoints": contract_endpoints, "whole_book_run_id": run_id}
                    ),
                    confidence=float(relation.confidence),
                    origin_type=OriginType.MODEL.value,
                    review_status="candidate",
                    is_canonical=True,
                    created_at=utc_now(),
                )
            )
            ctx.relation_keys[rel_key] = rel_row.id
            session.flush()

    after = _counts_for_run(session, run_id, run.book_id)
    reused = before["entity_count"] > 0 and before == after

    payload = {
        "window_result_count": len(window_responses),
        **after,
        "ambiguous_entity_merge_count": ctx.ambiguous_entity_merge_count,
        "rejected_candidate_count": ctx.rejected_candidate_count,
        "materialization_hash": sha256_utf8(json.dumps(after, sort_keys=True)),
    }
    upsert_checkpoint(
        session,
        run_id=run_id,
        stage_code="materialize_assets",
        checkpoint_key="minimal_asset_materialization_v1",
        payload=payload,
    )
    set_stage_completed(session, run_id, "materialize_assets", progress_total=1)
    run.current_stage_code = "synthesize_overview"
    session.flush()
    return {"run_id": run_id, "reused": reused, "warnings": ctx.warnings, "checkpoint": payload, **after}


def _map_endpoint(session: Session, ctx: _MaterializationContext, candidate_key: str, kind: str) -> int | None:
    if kind == "entity":
        entity_id = ctx.candidate_to_entity.get(candidate_key)
        if entity_id is None:
            return None
        return _ensure_entity_endpoint_asset(session, ctx, entity_id)
    return ctx.candidate_to_asset.get(candidate_key)
