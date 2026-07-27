"""Phase 1D Agent L / Integration — Narrative Structure Map Projection.

Projection only via NarrativeProjectionSource (Result Projection inputs).
No Pattern tables. No new facts. Does not write narrative facts to the database.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.narrative_core.product_contract.enums import StructureMapViewMode
from app.narrative_core.product_contract.result_envelope import ReviewSummaryDto
from app.narrative_core.product_contract.structure_map import (
    STRUCTURE_MAP_DEFAULT_MAX_EDGES,
    STRUCTURE_MAP_DEFAULT_MAX_NODES,
    STRUCTURE_MAP_PROJECTION_SCHEMA,
    NarrativeStructureMapProjectionDto,
    StructureMapEdgeDto,
    StructureMapFiltersDto,
    StructureMapNodeDto,
)
from app.narrative_core.services.narrative_projection_source import NarrativeProjectionSource
from app.narrative_core.services.whole_book_result_projection import (
    ConflictSummaryDto,
    ProjectionAssetRow,
    ProjectionRelationRow,
    WholeBookResultIndexService,
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
    return (
        StructureMapViewMode.STRUCTURE_STAGES,
        StructureMapViewMode.STORYLINES,
        StructureMapViewMode.CHARACTER_GROWTH,
    )


def _merge_asset_rows(
    canonical: tuple[ProjectionAssetRow, ...],
    candidates: tuple[ProjectionAssetRow, ...],
) -> tuple[ProjectionAssetRow, ...]:
    by_version: dict[int, ProjectionAssetRow] = {int(a.version_id): a for a in canonical}
    for row in candidates:
        by_version.setdefault(int(row.version_id), row)
    return tuple(by_version.values())


def _merge_relation_rows(
    canonical: tuple[ProjectionRelationRow, ...],
    candidates: tuple[ProjectionRelationRow, ...],
) -> tuple[ProjectionRelationRow, ...]:
    by_version: dict[int, ProjectionRelationRow] = {
        int(r.version_id): r for r in canonical
    }
    for row in candidates:
        by_version.setdefault(int(row.version_id), row)
    return tuple(by_version.values())


def _as_review_dict(summary: ReviewSummaryDto | dict[str, Any]) -> dict[str, Any]:
    if isinstance(summary, dict):
        return dict(summary)
    return {
        "candidate_count": int(getattr(summary, "candidate_count", 0) or 0),
        "confirmed_count": int(getattr(summary, "confirmed_count", 0) or 0),
        "corrected_count": int(getattr(summary, "corrected_count", 0) or 0),
        "rejected_count": int(getattr(summary, "rejected_count", 0) or 0),
        "locked_count": int(getattr(summary, "locked_count", 0) or 0),
        "stale_count": int(getattr(summary, "stale_count", 0) or 0),
    }


def _as_conflict_dict(
    summary: ConflictSummaryDto | dict[str, Any],
) -> dict[str, Any]:
    if isinstance(summary, dict):
        return dict(summary)
    return {
        "total": int(getattr(summary, "total", 0) or 0),
        "open": int(getattr(summary, "open", 0) or 0),
        "open_count": int(getattr(summary, "open", 0) or 0),
        "blocking": int(getattr(summary, "blocking", 0) or 0),
        "warning": int(getattr(summary, "warning", 0) or 0),
        "info": int(getattr(summary, "info", 0) or 0),
        "conflict_ids": list(getattr(summary, "conflict_ids", ()) or ()),
        "blocking_auto_resolve_forbidden": True,
    }


class NarrativeStructureMapProjectionService:
    """Build NarrativeStructureMapProjectionDto via NarrativeProjectionSource."""

    def __init__(
        self,
        session: Session,
        *,
        projection_source: NarrativeProjectionSource | None = None,
    ) -> None:
        self._session = session
        self._source: NarrativeProjectionSource = projection_source or WholeBookResultIndexService(
            session
        )

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
        snap = int(book_snapshot_id or 0)
        if snap <= 0:
            raise ValueError("book_snapshot_id is required for Structure Map projection")

        if include_candidates:
            canonical_assets = self._source.get_canonical_assets_for_projection(
                book_id=bid,
                book_snapshot_id=snap,
                run_id=source_run_id,
                limit=max(max_nodes * 2, max_nodes),
            )
            candidate_assets = self._source.get_candidate_assets_for_projection(
                book_id=bid,
                book_snapshot_id=snap,
                run_id=source_run_id,
                limit=max(max_nodes * 2, max_nodes),
            )
            assets = _merge_asset_rows(canonical_assets, candidate_assets)
            canonical_relations = self._source.get_canonical_relations_for_projection(
                book_id=bid,
                book_snapshot_id=snap,
                run_id=source_run_id,
                limit=max(max_edges * 2, max_edges),
            )
            candidate_relations = self._source.get_candidate_relations_for_projection(
                book_id=bid,
                book_snapshot_id=snap,
                run_id=source_run_id,
                limit=max(max_edges * 2, max_edges),
            )
            relations = _merge_relation_rows(canonical_relations, candidate_relations)
        else:
            assets = self._source.get_canonical_assets_for_projection(
                book_id=bid,
                book_snapshot_id=snap,
                run_id=source_run_id,
                limit=max(max_nodes * 2, max_nodes),
            )
            relations = self._source.get_canonical_relations_for_projection(
                book_id=bid,
                book_snapshot_id=snap,
                run_id=source_run_id,
                limit=max(max_edges * 2, max_edges),
            )

        # Rejected must not appear in default/canonical projection inputs.
        assets = tuple(a for a in assets if str(a.review_status).lower() != "rejected")
        relations = tuple(r for r in relations if str(r.review_status).lower() != "rejected")

        review_summary = _as_review_dict(
            self._source.get_review_summary(
                book_id=bid, book_snapshot_id=snap, run_id=source_run_id
            )
        )
        conflict_summary = _as_conflict_dict(
            self._source.get_conflict_summary(
                book_id=bid, book_snapshot_id=snap, run_id=source_run_id
            )
        )

        nodes: list[StructureMapNodeDto] = []
        evidence_index: dict[str, tuple[str, ...]] = {}
        node_meta: dict[str, dict[str, Any]] = {}
        asset_version_ids: list[int] = []

        for asset in assets:
            views = _views_for_asset_type(str(asset.asset_type))
            if mode not in views:
                continue
            searchable = " ".join(
                [
                    str(asset.title or ""),
                    str(asset.asset_type or ""),
                    str(asset.review_status or ""),
                    "locked" if asset.is_locked else "unlocked",
                    "stale" if asset.stale else "fresh",
                    f"conf:{float(asset.confidence or 0.0):.2f}",
                    " ".join(f"entity:{e}" for e in asset.entity_ids),
                    " ".join(f"storyline:{s}" for s in asset.storyline_ids),
                ]
            ).lower()
            if search_query and search_query.lower() not in searchable:
                continue

            node_id = f"asset:{asset.asset_id}:v:{asset.version_id}"
            nodes.append(
                StructureMapNodeDto(
                    node_id=node_id,
                    node_type=str(asset.asset_type),
                    title=str(asset.title or f"Asset {asset.asset_id}"),
                    asset_id=int(asset.asset_id),
                    asset_version_id=int(asset.version_id),
                    is_canonical=bool(asset.is_canonical),
                    view_modes=views,
                    chapter_range=asset.chapter_range,
                    parent_id=None,
                    evidence_count=int(asset.evidence_count),
                    collapsed=False,
                    searchable_text=searchable,
                )
            )
            node_meta[node_id] = {
                "confidence": float(asset.confidence or 0.0),
                "review_status": str(asset.review_status),
                "lock_status": "locked" if asset.is_locked else "unlocked",
                "stale": bool(asset.stale),
                "conflict": False,
                "entity_ids": list(asset.entity_ids),
                "storyline_ids": list(asset.storyline_ids),
                "chapter_ids": [],
            }
            asset_version_ids.append(int(asset.version_id))

        asset_id_to_node = {
            n.asset_id: n.node_id for n in nodes if n.asset_id is not None
        }
        linked_nodes: list[StructureMapNodeDto] = []
        for n in nodes:
            parent_id = None
            meta = node_meta.get(n.node_id, {})
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
        relation_version_ids: list[int] = []
        for relation in relations:
            src = asset_id_to_node.get(int(relation.source_asset_id))
            tgt = asset_id_to_node.get(int(relation.target_asset_id))
            if src is None or tgt is None:
                continue
            if src not in node_ids or tgt not in node_ids:
                continue
            edge_id = f"relation:{relation.relation_id}:v:{relation.version_id}"
            edges.append(
                StructureMapEdgeDto(
                    edge_id=edge_id,
                    source_node_id=src,
                    target_node_id=tgt,
                    relation_id=int(relation.relation_id),
                    relation_version_id=int(relation.version_id),
                    is_canonical=bool(relation.is_canonical),
                    edge_type=str(relation.relation_type),
                    evidence_count=int(relation.evidence_count),
                    label=str(relation.relation_type or ""),
                )
            )
            relation_version_ids.append(int(relation.version_id))

        # Lazy evidence index: ids/hashes only via Projection Source (no full body).
        evidence_entries = self._source.get_evidence_index(
            book_id=bid,
            book_snapshot_id=snap,
            asset_version_ids=asset_version_ids,
            relation_version_ids=relation_version_ids,
            limit=500,
        )
        by_target: dict[tuple[str, int], list[str]] = {}
        for entry in evidence_entries:
            key = (entry.evidence_type, int(entry.target_version_id))
            by_target.setdefault(key, []).append(
                f"{entry.evidence_type}:{entry.evidence_id}"
            )
        for n in nodes:
            if n.asset_version_id is None:
                continue
            refs = by_target.get(("asset_evidence", int(n.asset_version_id)), [])
            evidence_index[n.node_id] = tuple(refs)
            if not lazy_evidence:
                # Still no body — only ids (lazy load body via EvidenceReadService).
                evidence_index[n.node_id] = tuple(refs)
        for e in edges:
            if e.relation_version_id is None:
                continue
            refs = by_target.get(("relation_evidence", int(e.relation_version_id)), [])
            evidence_index[e.edge_id] = tuple(refs)

        truncated_nodes = False
        truncated_edges = False
        if len(nodes) > max_nodes:
            nodes = nodes[:max_nodes]
            truncated_nodes = True
            kept = {n.node_id for n in nodes}
            edges = [
                e for e in edges if e.source_node_id in kept and e.target_node_id in kept
            ]
            evidence_index = {
                k: v
                for k, v in evidence_index.items()
                if k in kept or k.startswith("relation:")
            }
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
            "projection_source": "NarrativeProjectionSource",
        }
        conflict_summary = {
            **conflict_summary,
            "blocking_auto_resolve_forbidden": True,
        }

        # Mark conflicted nodes from conflict_ids when available (version ids may appear).
        conflict_ids = set(int(x) for x in conflict_summary.get("conflict_ids") or [])
        if conflict_ids:
            for n in nodes:
                meta = node_meta.get(n.node_id)
                if meta is not None and n.asset_version_id in conflict_ids:
                    meta["conflict"] = True

        return NarrativeStructureMapProjectionDto(
            book_id=bid,
            book_snapshot_id=snap,
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


__all__ = [
    "PROJECTION_VERSION",
    "NarrativeStructureMapProjectionService",
]
