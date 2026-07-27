import {
  PATTERN_DTO_HAS_ORM_TABLE,
  STRUCTURE_MAP_DEFAULT_MAX_EDGES,
  STRUCTURE_MAP_DEFAULT_MAX_NODES,
  type StructureMapViewMode,
} from "./keys";

export interface StructureMapNodeDto {
  node_id: string;
  node_type: string;
  title: string;
  asset_id: number | null;
  asset_version_id: number | null;
  is_canonical: boolean;
  view_modes: StructureMapViewMode[];
  chapter_range: [number | null, number | null];
  parent_id: string | null;
  evidence_count: number;
  collapsed: boolean;
  searchable_text: string;
}

export interface StructureMapEdgeDto {
  edge_id: string;
  source_node_id: string;
  target_node_id: string;
  relation_id: number | null;
  relation_version_id: number | null;
  is_canonical: boolean;
  edge_type: string;
  evidence_count: number;
  label: string;
}

export interface StructureMapFiltersDto {
  view_mode: StructureMapViewMode;
  search_query: string;
  include_candidates: boolean;
  max_nodes: number;
  max_edges: number;
  theme: "system" | "light" | "dark";
}

export interface NarrativeStructureMapProjectionDto {
  schema: string;
  book_id: number;
  book_snapshot_id: number;
  source_run_id: number | null;
  projection_version: string;
  root_nodes: StructureMapNodeDto[];
  edges: StructureMapEdgeDto[];
  filters: StructureMapFiltersDto;
  evidence_index: Record<string, string[]>;
  review_summary: Record<string, unknown>;
  conflict_summary: Record<string, unknown>;
  generated_at: string;
}

export const STRUCTURE_MAP_PROJECTION_SCHEMA =
  "narrative_structure_map_projection";

export {
  PATTERN_DTO_HAS_ORM_TABLE,
  STRUCTURE_MAP_DEFAULT_MAX_EDGES,
  STRUCTURE_MAP_DEFAULT_MAX_NODES,
};
