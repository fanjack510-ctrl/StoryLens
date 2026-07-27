"""Narrative Structure Map projection DTO (Phase 1D-P).

Projection only — nodes/edges from Asset/Relation versions. No Pattern tables.
Not an ORM model and must not be treated as one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.narrative_core.product_contract.enums import StructureMapViewMode

STRUCTURE_MAP_PROJECTION_SCHEMA = "narrative_structure_map_projection"
STRUCTURE_MAP_DEFAULT_MAX_NODES = 100
STRUCTURE_MAP_DEFAULT_MAX_EDGES = 250

# Explicit: this DTO is NOT backed by a database table.
PATTERN_DTO_HAS_ORM_TABLE = False


@dataclass(frozen=True, slots=True)
class StructureMapNodeDto:
    node_id: str
    node_type: str
    title: str
    asset_id: int | None
    asset_version_id: int | None
    is_canonical: bool
    view_modes: tuple[StructureMapViewMode, ...]
    chapter_range: tuple[int | None, int | None] = (None, None)
    parent_id: str | None = None
    evidence_count: int = 0
    collapsed: bool = False
    searchable_text: str = ""


@dataclass(frozen=True, slots=True)
class StructureMapEdgeDto:
    edge_id: str
    source_node_id: str
    target_node_id: str
    relation_id: int | None
    relation_version_id: int | None
    is_canonical: bool
    edge_type: str
    evidence_count: int = 0
    label: str = ""


@dataclass(frozen=True, slots=True)
class StructureMapFiltersDto:
    view_mode: StructureMapViewMode
    search_query: str = ""
    include_candidates: bool = False
    max_nodes: int = STRUCTURE_MAP_DEFAULT_MAX_NODES
    max_edges: int = STRUCTURE_MAP_DEFAULT_MAX_EDGES
    theme: str = "system"  # system | light | dark


@dataclass(frozen=True, slots=True)
class NarrativeStructureMapProjectionDto:
    book_id: int
    book_snapshot_id: int
    source_run_id: int | None
    projection_version: str
    root_nodes: tuple[StructureMapNodeDto, ...]
    edges: tuple[StructureMapEdgeDto, ...]
    filters: StructureMapFiltersDto
    evidence_index: dict[str, tuple[str, ...]] = field(default_factory=dict)
    review_summary: dict[str, Any] = field(default_factory=dict)
    conflict_summary: dict[str, Any] = field(default_factory=dict)
    generated_at: str = ""
    schema: str = STRUCTURE_MAP_PROJECTION_SCHEMA

    def __post_init__(self) -> None:
        if len(self.root_nodes) > self.filters.max_nodes:
            raise ValueError("root_nodes exceeds max_nodes filter")
        if len(self.edges) > self.filters.max_edges:
            raise ValueError("edges exceeds max_edges filter")
