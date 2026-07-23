"""Phase 1D Agent L — Narrative Structure Map Projection.

Projection only from Asset / Relation versions. No Pattern tables. No new facts.
Does not write narrative facts to the database.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    NarrativeAsset,
    NarrativeAssetVersion,
    NarrativeRelation,
    NarrativeRelationVersion,
)
from app.narrative_core.enums import AssetLifecycleStatus, ConflictStatus
from app.narrative_core.product_contract.enums import StructureMapViewMode
from app.narrative_core.product_contract.structure_map import (
    STRUCTURE_MAP_DEFAULT_MAX_EDGES,
    STRUCTURE_MAP_DEFAULT_MAX_NODES,
    STRUCTURE_MAP_PROJECTION_SCHEMA,
    NarrativeStructureMapProjectionDto,
    StructureMapEdgeDto,
    StructureMapFiltersDto,
    StructureMapNodeDto,
)
from app.narrative_core.services.conflict_service import AnalysisConflictServiceImpl
from app.narrative_core.services.pattern_projection import (
    _parse_attributes_json,
    _parse_id_list,
    _chapter_ids_from_evidence,
)

PROJECTION_VERSION = "phase1d-structure-map-1"


_VIEW_BY_ASSET_TYPE: dict[str, tuple[StructureMapViewMode, ...]] = {
    "structure_stage": (StructureMapViewMode.STRUCTURE_STAGES,),
    "stage": (StructureMapViewMode.STRUCTURE_STAGES,),
    "storyline": (StructureMapViewMode.STORYLINES,),
    "character": (
        StructureMapViewMode.CHARACTER_GROWTH,
        StructureMapViewMode.STORYLINES,
    ),
    "character_arc": (StructureMapViewMode.CHARACTER_GROWTH,),
    "arc": (StructureMapViewMode.CHARACTER_GROWTH,),
}


def _views_for_asset_type(asset_type: str) -> tuple[StructureMapViewMode, ...]:
    key = str(asset_type or "").lower()
    if key in _VIEW_BY_ASSET_TYPE:
        return _VIEW_BY_ASSET_TYPE[key]
    # Default: appear in all three views so projection is usable without typed assets.
    return (
        StructureMapViewMode.STRUCTURE_STAGES,
        StructureMapViewMode.STORYLINES,
        StructureMapViewMode.CHARACTER_GROWTH,
    )


class NarrativeStructureMapProjectionService:
    """Build NarrativeStructureMapProjectionDto from Asset/Relation data."""

    def __init__(
        self,
        session: Session,
        *,
        conflict_service: AnalysisConflictServiceImpl | None = None,
    ) -> None:
        self._session = session
        self._conflicts = conflict_service or AnalysisConflictServiceImpl(session)

    def project(
        self,
        book_id: int,
        *,
        book_snapshot_id: int | None = None,
        source_run_id: int | None = None,
        view_mode: StructureMapViewMode | str = StructureMapViewMode.STRUCTURE_STAGES,
        include_candidates: bool = False,
        search_query: str = "",
        max_nodes: int = STRUCTURE_MAP_DEFAULT_MAX_NODES,
        max_edges: int = STRUCTURE_MAP_DEFAULT_MAX_EDGES,
        theme: str = "system",
        lazy_evidence: bool = True,
    ) -> NarrativeStructureMapProjectionDto:
        """Project structure map. Default: canonical only. Candidates require explicit flag."""
        assert include_candidates in (True, False)
        mode = StructureMapViewMode(view_mode)
        bid = int(book_id)

        asset_rows = self._load_asset_versions(bid, include_candidates=include_candidates)
        relation_rows = self._load_relation_versions(
            bid, include_candidates=include_candidates
        )

        conflict_version_ids = self._conflicted_version_ids(bid)
        review_summary, conflict_summary = self._summaries(
            bid, asset_rows, relation_rows, conflict_version_ids
        )

        nodes: list[StructureMapNodeDto] = []
        evidence_index: dict[str, tuple[str, ...]] = {}
        node_meta: dict[str, dict[str, Any]] = {}

        resolved_snapshot = book_snapshot_id
        for asset, version, evidence in asset_rows:
            if resolved_snapshot is None and version.book_snapshot_id is not None:
                resolved_snapshot = int(version.book_snapshot_id)
            chapter_ids = _chapter_ids_from_evidence(
                self._session,
                snapshot_chapter_ids={int(e.snapshot_chapter_id) for e in evidence},
            )
            attrs = _parse_attributes_json(version.attributes_json)
            entity_ids = _parse_id_list(attrs, "entity_ids")
            storyline_ids = _parse_id_list(attrs, "storyline_ids")
            views = _views_for_asset_type(str(version.asset_type))
            if mode not in views and mode not in (
                StructureMapViewMode.STRUCTURE_STAGES,
                StructureMapViewMode.STORYLINES,
                StructureMapViewMode.CHARACTER_GROWTH,
            ):
                continue
            # Filter by view: keep if asset declares the view OR has no specific restriction
            # (all three default). Already handled by _views_for_asset_type.
            if mode not in views:
                continue

            node_id = f"asset:{asset.id}:v:{version.id}"
            stale = asset.lifecycle_status == AssetLifecycleStatus.STALE.value or (
                asset.stale_at is not None
            )
            in_conflict = int(version.id) in conflict_version_ids
            searchable = " ".join(
                [
                    str(version.title or ""),
                    str(version.asset_type or ""),
                    str(version.review_status or ""),
                    "locked" if asset.is_locked else "unlocked",
                    "stale" if stale else "fresh",
                    "conflict" if in_conflict else "",
                    f"conf:{float(version.confidence or 0.0):.2f}",
                    " ".join(f"entity:{e}" for e in entity_ids),
                    " ".join(f"storyline:{s}" for s in storyline_ids),
                ]
            ).lower()
            if search_query and search_query.lower() not in searchable:
                continue

            chapter_range: tuple[int | None, int | None] = (None, None)
            if chapter_ids:
                chapter_range = (min(chapter_ids), max(chapter_ids))

            nodes.append(
                StructureMapNodeDto(
                    node_id=node_id,
                    node_type=str(version.asset_type),
                    title=str(version.title or f"Asset {asset.id}"),
                    asset_id=int(asset.id),
                    asset_version_id=int(version.id),
                    is_canonical=bool(version.is_canonical),
                    view_modes=views,
                    chapter_range=chapter_range,
                    parent_id=None,
                    evidence_count=len(evidence),
                    collapsed=False,
                    searchable_text=searchable,
                )
            )
            node_meta[node_id] = {
                "confidence": float(version.confidence or 0.0),
                "review_status": str(version.review_status),
                "lock_status": "locked" if asset.is_locked else "unlocked",
                "stale": stale,
                "conflict": in_conflict,
                "entity_ids": list(entity_ids),
                "storyline_ids": list(storyline_ids),
                "chapter_ids": list(chapter_ids),
            }
            if not lazy_evidence:
                evidence_index[node_id] = tuple(
                    f"asset_evidence:{e.id}" for e in evidence
                )
            else:
                # Lazy: only keys, load body via EvidenceReadService on demand.
                evidence_index[node_id] = tuple(
                    f"asset_evidence:{e.id}" for e in evidence
                )

        # Parent linking for storyline/character views via attributes parent_asset_id
        asset_id_to_node = {
            n.asset_id: n.node_id for n in nodes if n.asset_id is not None
        }
        linked_nodes: list[StructureMapNodeDto] = []
        for n in nodes:
            parent_id = None
            meta = node_meta.get(n.node_id, {})
            # Heuristic: first storyline_id matching another asset node
            for sid in meta.get("storyline_ids") or []:
                cand = asset_id_to_node.get(int(sid))
                if cand and cand != n.node_id:
                    parent_id = cand
                    break
            linked_nodes.append(
                StructureMapNodeDto(
                    node_id=n.node_id,
                    node_type=n.node_type,
                    title=n.title,
                    asset_id=n.asset_id,
                    asset_version_id=n.asset_version_id,
                    is_canonical=n.is_canonical,
                    view_modes=n.view_modes,
                    chapter_range=n.chapter_range,
                    parent_id=parent_id,
                    evidence_count=n.evidence_count,
                    collapsed=n.collapsed,
                    searchable_text=n.searchable_text,
                )
            )
        nodes = linked_nodes

        node_ids = {n.node_id for n in nodes}
        edges: list[StructureMapEdgeDto] = []
        for relation, version, evidence in relation_rows:
            src = asset_id_to_node.get(int(relation.source_asset_id))
            tgt = asset_id_to_node.get(int(relation.target_asset_id))
            if src is None or tgt is None:
                continue
            if src not in node_ids or tgt not in node_ids:
                continue
            edge_id = f"relation:{relation.id}:v:{version.id}"
            edges.append(
                StructureMapEdgeDto(
                    edge_id=edge_id,
                    source_node_id=src,
                    target_node_id=tgt,
                    relation_id=int(relation.id),
                    relation_version_id=int(version.id),
                    is_canonical=bool(version.is_canonical),
                    edge_type=str(version.relation_type),
                    evidence_count=len(evidence),
                    label=str(version.summary or version.relation_type or ""),
                )
            )
            evidence_index[edge_id] = tuple(
                f"relation_evidence:{e.id}" for e in evidence
            )

        truncated_nodes = False
        truncated_edges = False
        if len(nodes) > max_nodes:
            nodes = nodes[:max_nodes]
            truncated_nodes = True
            kept = {n.node_id for n in nodes}
            edges = [e for e in edges if e.source_node_id in kept and e.target_node_id in kept]
            evidence_index = {k: v for k, v in evidence_index.items() if k in kept or k.startswith("relation:")}
        if len(edges) > max_edges:
            edges = edges[:max_edges]
            truncated_edges = True

        filters = StructureMapFiltersDto(
            view_mode=mode,
            search_query=search_query,
            include_candidates=include_candidates,
            max_nodes=max_nodes,
            max_edges=max_edges,
            theme=theme,
        )
        review_summary = {
            **review_summary,
            "node_meta": node_meta,
            "truncated": truncated_nodes or truncated_edges,
            "truncated_nodes": truncated_nodes,
            "truncated_edges": truncated_edges,
            "visible_node_count": len(nodes),
            "visible_edge_count": len(edges),
            "lazy_evidence": lazy_evidence,
            "writes_database_facts": False,
            "pattern_orm_table": False,
        }
        conflict_summary = {
            **conflict_summary,
            "blocking_auto_resolve_forbidden": True,
        }

        return NarrativeStructureMapProjectionDto(
            book_id=bid,
            book_snapshot_id=int(resolved_snapshot or 0),
            source_run_id=source_run_id,
            projection_version=PROJECTION_VERSION,
            root_nodes=tuple(nodes),
            edges=tuple(edges),
            filters=filters,
            evidence_index=evidence_index,
            review_summary=review_summary,
            conflict_summary=conflict_summary,
            generated_at=datetime.now(timezone.utc).isoformat(),
            schema=STRUCTURE_MAP_PROJECTION_SCHEMA,
        )

    # ------------------------------------------------------------------

    def _load_asset_versions(
        self, book_id: int, *, include_candidates: bool
    ) -> list[tuple[NarrativeAsset, NarrativeAssetVersion, list]]:
        stmt = (
            select(NarrativeAssetVersion)
            .join(NarrativeAsset, NarrativeAssetVersion.asset_id == NarrativeAsset.id)
            .where(NarrativeAsset.book_id == book_id)
            .options(
                selectinload(NarrativeAssetVersion.asset),
                selectinload(NarrativeAssetVersion.evidence),
            )
            .order_by(NarrativeAsset.id.asc(), NarrativeAssetVersion.id.asc())
        )
        if not include_candidates:
            stmt = stmt.where(NarrativeAssetVersion.is_canonical.is_(True))
        versions = list(self._session.scalars(stmt).all())
        out: list[tuple[NarrativeAsset, NarrativeAssetVersion, list]] = []
        seen_assets: set[int] = set()
        for version in versions:
            asset = version.asset
            if include_candidates:
                # Prefer canonical per asset; also include non-canonical if flagged.
                key = int(asset.id)
                if version.is_canonical:
                    seen_assets.add(key)
                elif key in seen_assets and not include_candidates:
                    continue
            out.append((asset, version, list(version.evidence)))
        return out

    def _load_relation_versions(
        self, book_id: int, *, include_candidates: bool
    ) -> list[tuple[NarrativeRelation, NarrativeRelationVersion, list]]:
        stmt = (
            select(NarrativeRelationVersion)
            .join(
                NarrativeRelation,
                NarrativeRelationVersion.relation_id == NarrativeRelation.id,
            )
            .where(NarrativeRelation.book_id == book_id)
            .options(
                selectinload(NarrativeRelationVersion.relation),
                selectinload(NarrativeRelationVersion.evidence),
            )
            .order_by(NarrativeRelation.id.asc(), NarrativeRelationVersion.id.asc())
        )
        if not include_candidates:
            stmt = stmt.where(NarrativeRelationVersion.is_canonical.is_(True))
        versions = list(self._session.scalars(stmt).all())
        return [
            (version.relation, version, list(version.evidence)) for version in versions
        ]

    def _conflicted_version_ids(self, book_id: int) -> set[int]:
        ids: set[int] = set()
        for row in self._conflicts.list_analysis_conflicts(
            book_id, status=ConflictStatus.OPEN.value
        ):
            for ref_type, ref_id in (
                (row.left_ref_type, row.left_ref_id),
                (row.right_ref_type, row.right_ref_id),
            ):
                if str(ref_type) in {
                    "asset_version",
                    "narrative_asset_version",
                    "relation_version",
                    "narrative_relation_version",
                }:
                    try:
                        ids.add(int(ref_id))
                    except (TypeError, ValueError):
                        continue
        return ids

    def _summaries(
        self,
        book_id: int,
        asset_rows: list,
        relation_rows: list,
        conflict_version_ids: set[int],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        review_counts = {
            "candidate_count": 0,
            "confirmed_count": 0,
            "corrected_count": 0,
            "rejected_count": 0,
            "locked_count": 0,
            "stale_count": 0,
        }
        for asset, version, _ev in asset_rows:
            status = str(version.review_status)
            key = f"{status}_count"
            if key in review_counts:
                review_counts[key] += 1
            if asset.is_locked:
                review_counts["locked_count"] += 1
            if asset.stale_at is not None or asset.lifecycle_status == AssetLifecycleStatus.STALE.value:
                review_counts["stale_count"] += 1
        open_conflicts = self._conflicts.list_analysis_conflicts(
            book_id, status=ConflictStatus.OPEN.value
        )
        conflict_summary = {
            "open_count": len(open_conflicts),
            "conflicted_version_count": len(conflict_version_ids),
            "relation_count": len(relation_rows),
        }
        return review_counts, conflict_summary
