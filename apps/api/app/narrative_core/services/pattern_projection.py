"""Internal Pattern Map projection adapter (Phase 1B Integration).

Reads canonical Asset / Relation data for a book and produces projection input
for a future Pattern Map engine. No API routes, no Pattern tables, no graph libs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    BookSnapshotChapter,
    NarrativeAsset,
    NarrativeAssetEvidence,
    NarrativeAssetVersion,
    NarrativeRelation,
    NarrativeRelationEvidence,
    NarrativeRelationVersion,
)


@dataclass(frozen=True)
class PatternProjectionAsset:
    asset_id: int
    asset_key: str
    version_id: int
    asset_type: str
    title: str
    confidence: float
    review_status: str
    evidence_count: int
    chapter_ids: tuple[int, ...]
    entity_ids: tuple[int, ...]
    storyline_ids: tuple[int, ...]
    book_snapshot_id: int | None
    paragraph_hashes: tuple[str, ...]


@dataclass(frozen=True)
class PatternProjectionRelation:
    relation_id: int
    relation_key: str
    version_id: int
    relation_type: str
    source_asset_id: int
    target_asset_id: int
    confidence: float
    review_status: str
    evidence_count: int
    book_snapshot_id: int | None
    paragraph_hashes: tuple[str, ...]


@dataclass(frozen=True)
class PatternProjectionInput:
    book_id: int
    assets: tuple[PatternProjectionAsset, ...]
    relations: tuple[PatternProjectionRelation, ...]


def _parse_attributes_json(raw: str | None) -> dict:
    if not raw or not str(raw).strip():
        return {}
    try:
        loaded = json.loads(str(raw))
    except (json.JSONDecodeError, TypeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _parse_id_list(attrs: dict, key: str) -> tuple[int, ...]:
    """Safely parse optional int lists from attributes_json."""
    raw = attrs.get(key)
    if raw is None:
        return ()
    if not isinstance(raw, list):
        return ()
    ids: list[int] = []
    for item in raw:
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            ids.append(item)
        elif isinstance(item, str) and item.strip().isdigit():
            ids.append(int(item.strip()))
    return tuple(sorted(set(ids)))


def _chapter_ids_from_evidence(
    session: Session,
    *,
    snapshot_chapter_ids: set[int],
) -> tuple[int, ...]:
    if not snapshot_chapter_ids:
        return ()
    rows = session.scalars(
        select(BookSnapshotChapter).where(
            BookSnapshotChapter.id.in_(snapshot_chapter_ids)
        )
    ).all()
    source_ids: list[int] = []
    for row in rows:
        if row.source_chapter_id is not None:
            source_ids.append(int(row.source_chapter_id))
    return tuple(sorted(set(source_ids)))


def _project_asset(
    session: Session,
    asset: NarrativeAsset,
    version: NarrativeAssetVersion,
    evidence: list[NarrativeAssetEvidence],
) -> PatternProjectionAsset:
    attrs = _parse_attributes_json(version.attributes_json)
    snapshot_chapter_ids = {int(e.snapshot_chapter_id) for e in evidence}
    return PatternProjectionAsset(
        asset_id=int(asset.id),
        asset_key=str(asset.asset_key),
        version_id=int(version.id),
        asset_type=str(version.asset_type),
        title=str(version.title),
        confidence=float(version.confidence or 0.0),
        review_status=str(version.review_status),
        evidence_count=len(evidence),
        chapter_ids=_chapter_ids_from_evidence(
            session, snapshot_chapter_ids=snapshot_chapter_ids
        ),
        entity_ids=_parse_id_list(attrs, "entity_ids"),
        storyline_ids=_parse_id_list(attrs, "storyline_ids"),
        book_snapshot_id=(
            None if version.book_snapshot_id is None else int(version.book_snapshot_id)
        ),
        paragraph_hashes=tuple(
            sorted({str(e.paragraph_content_hash) for e in evidence if e.paragraph_content_hash})
        ),
    )


def _project_relation(
    session: Session,
    relation: NarrativeRelation,
    version: NarrativeRelationVersion,
    evidence: list[NarrativeRelationEvidence],
) -> PatternProjectionRelation:
    return PatternProjectionRelation(
        relation_id=int(relation.id),
        relation_key=str(relation.relation_key),
        version_id=int(version.id),
        relation_type=str(version.relation_type),
        source_asset_id=int(relation.source_asset_id),
        target_asset_id=int(relation.target_asset_id),
        confidence=float(version.confidence or 0.0),
        review_status=str(version.review_status),
        evidence_count=len(evidence),
        book_snapshot_id=(
            None if version.book_snapshot_id is None else int(version.book_snapshot_id)
        ),
        paragraph_hashes=tuple(
            sorted({str(e.paragraph_content_hash) for e in evidence if e.paragraph_content_hash})
        ),
    )


def build_pattern_projection_input(session: Session, book_id: int) -> PatternProjectionInput:
    """Only include canonical versions. Count evidence. Collect chapter ids / hashes from evidence."""
    bid = int(book_id)

    asset_versions = session.scalars(
        select(NarrativeAssetVersion)
        .join(NarrativeAsset, NarrativeAssetVersion.asset_id == NarrativeAsset.id)
        .where(
            NarrativeAsset.book_id == bid,
            NarrativeAssetVersion.is_canonical.is_(True),
        )
        .options(
            selectinload(NarrativeAssetVersion.asset),
            selectinload(NarrativeAssetVersion.evidence),
        )
        .order_by(NarrativeAsset.id.asc())
    ).all()

    relation_versions = session.scalars(
        select(NarrativeRelationVersion)
        .join(NarrativeRelation, NarrativeRelationVersion.relation_id == NarrativeRelation.id)
        .where(
            NarrativeRelation.book_id == bid,
            NarrativeRelationVersion.is_canonical.is_(True),
        )
        .options(
            selectinload(NarrativeRelationVersion.relation),
            selectinload(NarrativeRelationVersion.evidence),
        )
        .order_by(NarrativeRelation.id.asc())
    ).all()

    assets = tuple(
        _project_asset(session, version.asset, version, list(version.evidence))
        for version in asset_versions
    )
    relations = tuple(
        _project_relation(session, version.relation, version, list(version.evidence))
        for version in relation_versions
    )

    return PatternProjectionInput(book_id=bid, assets=assets, relations=relations)


__all__ = [
    "PatternProjectionAsset",
    "PatternProjectionInput",
    "PatternProjectionRelation",
    "build_pattern_projection_input",
]
