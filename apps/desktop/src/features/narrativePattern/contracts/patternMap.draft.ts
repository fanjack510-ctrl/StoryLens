/**
 * Narrative Structure Map — frontend Contract draft (Phase 0B / Phase 1D input).
 *
 * NOT a database schema. NOT wired to product routes.
 * Downstream DB Contract should consume these shapes as input, not copy verbatim.
 */

/** Structural role of a map node (orthogonal to storyline / character filters). */
export type PatternMapNodeType =
  | "book_root"
  | "structure_stage"
  | "storyline"
  | "character_arc"
  | "beat"
  | "turning_point"
  | "payoff_cluster"
  | "supporting";

/** Author / editor confirmation of a pattern node. */
export type PatternMapUserStatus =
  | "unreviewed"
  | "confirmed"
  | "disputed"
  | "ignored";

/** Filter facet for switching map projections (v1 UI may expose a subset). */
export type PatternMapFilterMode =
  | "structure_stage"
  | "storyline"
  | "character_growth"
  | "all";

/** Evidence pointer — must resolve to snapshot-bound text, never free-form quotes alone. */
export type PatternMapEvidenceRefDto = {
  bookSnapshotId: string;
  chapterId: number;
  sceneId: number | null;
  paragraphId: string;
  paragraphContentHash: string;
  label: string;
};

/**
 * Graph node. Hierarchy is expressed via parentId (tree overlay on a DAG of edges).
 * Chapter span is a range — one chapter is NEVER assumed to equal one node.
 */
export type PatternMapNodeDto = {
  id: string;
  parentId: string | null;
  title: string;
  summary: string;
  nodeType: PatternMapNodeType;
  depth: number;
  orderIndex: number;
  importance: number;
  confidence: number;
  startChapterId: number | null;
  endChapterId: number | null;
  relatedCharacterIds: string[];
  relatedStorylineIds: string[];
  relatedAssetIds: string[];
  evidenceCount: number;
  childCount: number;
  collapsedByDefault: boolean;
  userStatus: PatternMapUserStatus;
};

/** Directed relation between pattern nodes (structural / causal / payoff). */
export type PatternMapEdgeDto = {
  id: string;
  sourceNodeId: string;
  targetNodeId: string;
  relationType:
    | "parent_child"
    | "setup_payoff"
    | "parallel"
    | "foreshadow"
    | "character_growth"
    | "storyline_cross";
  confidence: number;
  relatedAssetIds: string[];
  evidenceCount: number;
  label: string | null;
};

export type PatternMapFilterDto = {
  mode: PatternMapFilterMode;
  storylineIds: string[];
  characterIds: string[];
  stageIds: string[];
  minConfidence: number;
  includeDisputed: boolean;
  searchQuery: string;
};

export type PatternMapViewportDto = {
  scale: number;
  translateX: number;
  translateY: number;
  focusedNodeId: string | null;
  selectedNodeId: string | null;
};

/**
 * Full map payload for one book snapshot analysis result.
 * Evidence payloads are intentionally omitted — load by node/edge id in the detail pane.
 */
export type NarrativePatternMapDto = {
  schemaVersion: "pattern-map-draft-1";
  bookId: number;
  bookSnapshotId: string;
  title: string;
  generatedAt: string;
  defaultFilter: PatternMapFilterDto;
  defaultViewport: PatternMapViewportDto;
  nodes: PatternMapNodeDto[];
  edges: PatternMapEdgeDto[];
  /** Optional evidence index for mock / prototype only; production loads on demand. */
  evidenceByNodeId?: Record<string, PatternMapEvidenceRefDto[]>;
};

export const PATTERN_MAP_SCHEMA_VERSION = "pattern-map-draft-1" as const;

export const PATTERN_MAP_NODE_TYPES: readonly PatternMapNodeType[] = [
  "book_root",
  "structure_stage",
  "storyline",
  "character_arc",
  "beat",
  "turning_point",
  "payoff_cluster",
  "supporting",
] as const;

export const PATTERN_MAP_USER_STATUSES: readonly PatternMapUserStatus[] = [
  "unreviewed",
  "confirmed",
  "disputed",
  "ignored",
] as const;
