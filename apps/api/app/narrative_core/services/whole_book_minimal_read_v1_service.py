"""Read/projection helpers for minimal analysis API (Wave C)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    BookSnapshotChapter,
    BookSnapshotParagraph,
    NarrativeAsset,
    NarrativeAssetEvidence,
    NarrativeAssetVersion,
    NarrativeEntity,
    NarrativeEntityAlias,
    NarrativeRelation,
    NarrativeRelationVersion,
    WholeBookOverviewResult,
    WholeBookProviderAttempt,
    WholeBookProviderUnit,
    WholeBookWindowAnalysisResult,
)
from app.narrative_core.contracts.whole_book_contract_v1.common import sha256_hex
from app.narrative_core.services.whole_book_minimal_materialization_v1_service import (
    _relations_for_wb_run,
    _versions_for_wb_run,
)
from app.narrative_core.services.whole_book_run_v1_service import get_run, list_stages, run_to_dict, stage_to_dict
from app.narrative_core.services.whole_book_snapshot_v1_service import get_snapshot_paragraph_text


def count_provider_calls(session: Session, run_id: int) -> int:
    units = session.scalars(
        select(WholeBookProviderUnit.id).where(WholeBookProviderUnit.run_id == run_id)
    ).all()
    if not units:
        return 0
    return int(
        session.scalar(
            select(func.count())
            .select_from(WholeBookProviderAttempt)
            .where(
                WholeBookProviderAttempt.provider_unit_id.in_(units),
                WholeBookProviderAttempt.status == "succeeded",
            )
        )
        or 0
    )


def get_minimal_analysis_summary(session: Session, run_id: int) -> dict[str, Any]:
    run = get_run(session, run_id)
    stages = list_stages(session, run_id)
    window_rows = session.scalars(
        select(WholeBookWindowAnalysisResult).where(WholeBookWindowAnalysisResult.run_id == run_id)
    ).all()
    valid = sum(1 for row in window_rows if row.validation_status == "valid")
    invalid = sum(1 for row in window_rows if row.validation_status == "invalid")
    entities = session.scalars(
        select(NarrativeEntity).where(
            NarrativeEntity.created_by == str(run_id),
            NarrativeEntity.lifecycle_status == "active",
        )
    ).all()
    versions = _versions_for_wb_run(session, run_id)
    version_ids = [v.id for v in versions]
    evidences = (
        session.scalars(
            select(NarrativeAssetEvidence).where(
                NarrativeAssetEvidence.asset_version_id.in_(version_ids)
            )
        ).all()
        if version_ids
        else []
    )
    relations = _relations_for_wb_run(session, run_id)
    overview = session.scalar(
        select(WholeBookOverviewResult).where(WholeBookOverviewResult.run_id == run_id)
    )
    by_type: dict[str, int] = {}
    for version in versions:
        by_type[version.asset_type] = by_type.get(version.asset_type, 0) + 1
    rel_by_type: dict[str, int] = {}
    for rel in relations:
        rel_by_type[rel.relation_type] = rel_by_type.get(rel.relation_type, 0) + 1
    return {
        "run": run_to_dict(run),
        "stages": [stage_to_dict(s) for s in stages],
        "window_results": {
            "total": len(window_rows),
            "valid": valid,
            "invalid": invalid,
        },
        "entities": {"total": len(entities), "characters": len(entities)},
        "assets": {"total": len(versions), "by_type": by_type},
        "evidences": {"total": len(evidences), "valid": len(evidences)},
        "relations": {"total": len(relations), "by_type": rel_by_type},
        "overview_available": overview is not None,
        "provider_calls": count_provider_calls(session, run_id),
        "result_origin": run.result_origin,
    }


def list_run_entities(session: Session, run_id: int) -> list[dict[str, Any]]:
    entities = session.scalars(
        select(NarrativeEntity).where(
            NarrativeEntity.created_by == str(run_id),
            NarrativeEntity.lifecycle_status == "active",
        )
    ).all()
    out: list[dict[str, Any]] = []
    for entity in entities:
        aliases = session.scalars(
            select(NarrativeEntityAlias).where(NarrativeEntityAlias.entity_id == entity.id)
        ).all()
        out.append(
            {
                "entity_id": entity.id,
                "canonical_name": entity.canonical_name,
                "entity_type": entity.entity_type,
                "state": "candidate",
                "aliases": [a.alias_text for a in aliases],
                "confidence": 0.9,
            }
        )
    return out


def list_run_assets(
    session: Session,
    run_id: int,
    *,
    asset_type: str | None = None,
    entity_id: int | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], int]:
    rows = _versions_for_wb_run(session, run_id)
    if asset_type:
        rows = [row for row in rows if row.asset_type == asset_type]
    if entity_id is not None:
        filtered: list[NarrativeAssetVersion] = []
        for row in rows:
            attrs = json.loads(row.attributes_json or "{}")
            subject_ids = attrs.get("subject_entity_ids") or []
            if entity_id in subject_ids:
                filtered.append(row)
        rows = filtered
    rows = sorted(rows, key=lambda row: row.id)
    total = len(rows)
    page = rows[offset : offset + limit]
    items = [
        {
            "asset_id": row.asset_id,
            "asset_version_id": row.id,
            "asset_type": row.asset_type,
            "title": row.title,
            "summary": row.summary,
            "state": row.review_status,
            "confidence": float(row.confidence),
            "subject_entity_ids": json.loads(row.attributes_json or "{}").get("subject_entity_ids", []),
        }
        for row in page
    ]
    return items, total


def list_run_evidences(session: Session, run_id: int) -> list[dict[str, Any]]:
    versions = [v.id for v in _versions_for_wb_run(session, run_id)]
    if not versions:
        return []
    rows = session.scalars(
        select(NarrativeAssetEvidence).where(NarrativeAssetEvidence.asset_version_id.in_(versions))
    ).all()
    return [
        {
            "evidence_id": row.id,
            "asset_version_id": row.asset_version_id,
            "snapshot_id": row.book_snapshot_id,
            "snapshot_paragraph_id": row.snapshot_paragraph_id,
            "start_offset": row.start_offset,
            "end_offset": row.end_offset,
            "state": "valid",
            "quote_text": row.evidence_label,
        }
        for row in rows
    ]


def list_run_relations(session: Session, run_id: int) -> list[dict[str, Any]]:
    versions = _relations_for_wb_run(session, run_id)
    out: list[dict[str, Any]] = []
    for version in versions:
        rel = session.get(NarrativeRelation, version.relation_id)
        attrs = json.loads(version.attributes_json or "{}")
        endpoints = attrs.get("contract_endpoints") or {}
        out.append(
            {
                "relation_id": version.relation_id,
                "relation_version_id": version.id,
                "relation_type": version.relation_type,
                "source_asset_id": rel.source_asset_id if rel else None,
                "target_asset_id": rel.target_asset_id if rel else None,
                "contract_endpoints": endpoints,
                "confidence": float(version.confidence),
            }
        )
    return out


def get_run_overview(session: Session, run_id: int) -> dict[str, Any] | None:
    row = session.scalar(select(WholeBookOverviewResult).where(WholeBookOverviewResult.run_id == run_id))
    if row is None:
        return None
    return json.loads(row.result_json or "{}")


def get_evidence_source(session: Session, evidence_id: int) -> dict[str, Any]:
    row = session.get(NarrativeAssetEvidence, evidence_id)
    if row is None:
        raise ValueError("evidence not found")
    paragraph = session.get(BookSnapshotParagraph, row.snapshot_paragraph_id)
    chapter = session.get(BookSnapshotChapter, row.snapshot_chapter_id) if row.snapshot_chapter_id else None
    paragraph_text = get_snapshot_paragraph_text(session, row.snapshot_paragraph_id)
    quote_text = paragraph_text[row.start_offset : row.end_offset]
    state = "valid"
    if sha256_hex(paragraph_text) != row.paragraph_content_hash:
        state = "stale"
    elif quote_text != row.evidence_label[: len(quote_text)]:
        # evidence_label stores quote; verify slice
        if row.evidence_label and quote_text != row.evidence_label:
            state = "stale"
    return {
        "evidence_id": row.id,
        "snapshot_id": row.book_snapshot_id,
        "chapter_id": chapter.source_chapter_id if chapter else None,
        "chapter_index": chapter.chapter_order if chapter else 0,
        "chapter_title": chapter.title if chapter else "",
        "paragraph_index": paragraph.paragraph_order if paragraph else 0,
        "global_paragraph_index": paragraph.global_paragraph_index if paragraph else 0,
        "start_offset": row.start_offset,
        "end_offset": row.end_offset,
        "quote_text": quote_text,
        "paragraph_text": paragraph_text,
        "state": state,
    }
