/**
 * Phase 1D Agent L — Structure Map adapters + SVG prototype.
 *
 * Product name: Narrative Structure Map
 * Feature dir may still say narrativePattern (Agent C draft).
 * No new graph library. Projection DTO only — no Pattern ORM.
 */

import {
  useEffect,
  useMemo,
  useState,
  type KeyboardEvent,
} from "react";
import type {
  NarrativeStructureMapProjectionDto,
  StructureMapNodeDto,
} from "../contracts/structureMap";
import {
  PATTERN_DTO_HAS_ORM_TABLE,
  STRUCTURE_MAP_DEFAULT_MAX_EDGES,
  STRUCTURE_MAP_DEFAULT_MAX_NODES,
} from "../contracts/structureMap";
import type { StructureMapViewMode } from "../contracts/keys";
import type { WholeBookEvidenceRefDto } from "../contracts/evidence";
import { WholeBookEvidenceDrawer } from "../review/EvidenceDrawer";
import "../review/reviewPrototype.css";

/** Convert Structure Map projection nodes into a lightweight tree for SVG. */
export type StructureMapLayoutNode = {
  id: string;
  title: string;
  x: number;
  y: number;
  width: number;
  height: number;
  parentId: string | null;
  isCanonical: boolean;
  evidenceCount: number;
};

export function structureMapBoundaryNotes(): string[] {
  return [
    "Frontend feature dir may remain narrativePattern temporarily.",
    "Product formal name: Narrative Structure Map.",
    "Data source: Narrative Asset/Relation Projection — not Pattern ORM.",
    `PATTERN_DTO_HAS_ORM_TABLE=${String(PATTERN_DTO_HAS_ORM_TABLE)}`,
    "Pattern DTO is display contract only; do not copy Asset/Relation content into Pattern tables.",
    "Users must not change canonical facts on the map; Review Actions go through Review Action Adapter.",
    "Integration may later rename narrativePattern → structureMap; Phase 1D avoids large renames.",
  ];
}

export function filterStructureMapNodes(
  projection: NarrativeStructureMapProjectionDto,
  options?: {
    includeCandidates?: boolean;
    conflictOnly?: boolean;
    staleOnly?: boolean;
    search?: string;
  },
): StructureMapNodeDto[] {
  const includeCandidates =
    options?.includeCandidates ?? projection.filters.include_candidates;
  const meta = (projection.review_summary?.node_meta ?? {}) as Record<
    string,
    { conflict?: boolean; stale?: boolean }
  >;
  const q = (options?.search ?? projection.filters.search_query ?? "").trim().toLowerCase();
  return projection.root_nodes.filter((n) => {
    if (!includeCandidates && !n.is_canonical) return false;
    const m = meta[n.node_id] ?? {};
    if (options?.conflictOnly && !m.conflict) return false;
    if (options?.staleOnly && !m.stale) return false;
    if (q && !n.searchable_text.toLowerCase().includes(q) && !n.title.toLowerCase().includes(q)) {
      return false;
    }
    return true;
  });
}

export function layoutStructureMapNodes(
  nodes: StructureMapNodeDto[],
): StructureMapLayoutNode[] {
  const roots = nodes.filter((n) => !n.parent_id);
  const byParent = new Map<string | null, StructureMapNodeDto[]>();
  for (const n of nodes) {
    const key = n.parent_id;
    const list = byParent.get(key) ?? [];
    list.push(n);
    byParent.set(key, list);
  }
  const laid: StructureMapLayoutNode[] = [];
  let row = 0;
  const walk = (parentId: string | null, depth: number) => {
    const children = byParent.get(parentId) ?? (parentId === null ? roots : []);
    children.forEach((child, index) => {
      laid.push({
        id: child.node_id,
        title: child.title,
        x: 24 + depth * 180,
        y: 24 + row * 72,
        width: 160,
        height: 48,
        parentId: child.parent_id,
        isCanonical: child.is_canonical,
        evidenceCount: child.evidence_count,
      });
      row += 1;
      walk(child.node_id, depth + 1);
      void index;
    });
  };
  walk(null, 0);
  // Flat fallback if no parent links
  if (laid.length === 0) {
    nodes.forEach((n, i) => {
      laid.push({
        id: n.node_id,
        title: n.title,
        x: 24 + (i % 5) * 180,
        y: 24 + Math.floor(i / 5) * 72,
        width: 160,
        height: 48,
        parentId: n.parent_id,
        isCanonical: n.is_canonical,
        evidenceCount: n.evidence_count,
      });
    });
  }
  return laid;
}

export type StructureMapPrototypeProps = {
  projection: NarrativeStructureMapProjectionDto;
  /** Lazy evidence payloads keyed by evidence_index values */
  evidenceByKey?: Record<string, WholeBookEvidenceRefDto>;
  theme?: "light" | "dark";
  onThemeChange?: (theme: "light" | "dark") => void;
  className?: string;
};

/**
 * Zero-dependency SVG Structure Map prototype.
 * Not registered in product result navigation.
 */
export function StructureMapPrototype({
  projection,
  evidenceByKey = {},
  theme = "light",
  onThemeChange,
  className,
}: StructureMapPrototypeProps) {
  const [viewMode, setViewMode] = useState<StructureMapViewMode>(
    projection.filters.view_mode,
  );
  const [includeCandidates, setIncludeCandidates] = useState(
    projection.filters.include_candidates,
  );
  const [conflictOnly, setConflictOnly] = useState(false);
  const [staleOnly, setStaleOnly] = useState(false);
  const [query, setQuery] = useState("");
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerEvidence, setDrawerEvidence] = useState<WholeBookEvidenceRefDto[]>([]);

  const filtered = useMemo(
    () =>
      filterStructureMapNodes(
        { ...projection, filters: { ...projection.filters, view_mode: viewMode } },
        { includeCandidates, conflictOnly, staleOnly, search: query },
      ).filter((n) => n.view_modes.includes(viewMode) || n.view_modes.length === 0),
    [projection, viewMode, includeCandidates, conflictOnly, staleOnly, query],
  );

  const visible = useMemo(() => {
    return filtered.filter((n) => {
      if (!n.parent_id) return true;
      // Collapse: hide children of collapsed parents
      let pid: string | null | undefined = n.parent_id;
      while (pid) {
        if (collapsed[pid]) return false;
        const parent = filtered.find((x) => x.node_id === pid);
        pid = parent?.parent_id ?? null;
      }
      return true;
    });
  }, [filtered, collapsed]);

  const layout = useMemo(() => layoutStructureMapNodes(visible), [visible]);
  const layoutById = useMemo(() => new Map(layout.map((n) => [n.id, n])), [layout]);
  const selected = filtered.find((n) => n.node_id === selectedId) ?? null;

  const truncated =
    Boolean(projection.review_summary?.truncated) ||
    projection.root_nodes.length >= (projection.filters.max_nodes || STRUCTURE_MAP_DEFAULT_MAX_NODES);

  useEffect(() => {
    // Compatibility: Agent C 36-default / 81-expand fixtures remain separate under narrativePattern.
    void STRUCTURE_MAP_DEFAULT_MAX_EDGES;
  }, []);

  const openEvidenceForNode = (nodeId: string) => {
    const keys = projection.evidence_index[nodeId] ?? [];
    const refs = keys
      .map((k) => evidenceByKey[k])
      .filter((x): x is WholeBookEvidenceRefDto => Boolean(x));
    setDrawerEvidence(refs);
    setDrawerOpen(true);
  };

  const onKey = (e: KeyboardEvent<SVGElement>) => {
    if (e.key === "Escape") {
      setSelectedId(null);
      setDrawerOpen(false);
    }
  };

  return (
    <div
      className={`sl-sm-proto sl-sm-proto--${theme} ${className ?? ""}`.trim()}
      data-testid="structure-map-prototype"
    >
      <header className="sl-sm-toolbar">
        <h3>Narrative Structure Map</h3>
        <label>
          视图
          <select
            value={viewMode}
            onChange={(e) => setViewMode(e.target.value as StructureMapViewMode)}
            aria-label="结构地图视图"
          >
            <option value="structure_stages">结构阶段</option>
            <option value="storylines">故事线</option>
            <option value="character_growth">人物成长</option>
          </select>
        </label>
        <label>
          <input
            type="checkbox"
            checked={includeCandidates}
            onChange={(e) => setIncludeCandidates(e.target.checked)}
            aria-label="include_candidates"
          />
          include_candidates
        </label>
        <label>
          <input
            type="checkbox"
            checked={conflictOnly}
            onChange={(e) => setConflictOnly(e.target.checked)}
          />
          conflict
        </label>
        <label>
          <input
            type="checkbox"
            checked={staleOnly}
            onChange={(e) => setStaleOnly(e.target.checked)}
          />
          stale
        </label>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索节点"
          aria-label="搜索结构地图节点"
        />
        <button
          type="button"
          onClick={() => onThemeChange?.(theme === "light" ? "dark" : "light")}
        >
          主题: {theme}
        </button>
      </header>
      {truncated ? (
        <p className="sl-sm-trunc" role="status">
          节点/边已截断（默认 max_nodes={STRUCTURE_MAP_DEFAULT_MAX_NODES} /
          max_edges={STRUCTURE_MAP_DEFAULT_MAX_EDGES}）
        </p>
      ) : null}
      <svg
        role="img"
        aria-label="Narrative Structure Map SVG"
        tabIndex={0}
        width="100%"
        height="420"
        className="sl-sm-svg"
        onKeyDown={onKey}
        data-testid="structure-map-svg"
      >
        {layout.map((n) => {
          if (!n.parentId || !layoutById.has(n.parentId)) return null;
          const p = layoutById.get(n.parentId)!;
          return (
            <line
              key={`e-${n.id}`}
              x1={p.x + p.width / 2}
              y1={p.y + p.height}
              x2={n.x + n.width / 2}
              y2={n.y}
              className="sl-sm-edge"
            />
          );
        })}
        {layout.map((n) => (
          <g
            key={n.id}
            transform={`translate(${n.x},${n.y})`}
            className={`sl-sm-node ${n.isCanonical ? "is-canonical" : "is-candidate"}`}
            onClick={() => setSelectedId(n.id)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setSelectedId(n.id);
              }
            }}
            tabIndex={0}
            role="button"
            aria-label={n.title}
            data-testid={`structure-map-node-${n.id}`}
          >
            <rect width={n.width} height={n.height} rx={6} />
            <text x={8} y={20} className="sl-sm-node-title">
              {n.title.slice(0, 14)}
            </text>
            <text x={8} y={38} className="sl-sm-node-meta">
              {n.isCanonical ? "canonical" : "candidate"} · ev {n.evidenceCount}
            </text>
          </g>
        ))}
      </svg>
      {selected ? (
        <aside className="sl-sm-detail" data-testid="structure-map-detail">
          <h4>{selected.title}</h4>
          <p>
            {selected.node_type} · asset {selected.asset_id} · version{" "}
            {selected.asset_version_id}
          </p>
          <p>
            chapter_range: {String(selected.chapter_range[0])}–
            {String(selected.chapter_range[1])}
          </p>
          <button
            type="button"
            onClick={() =>
              setCollapsed((c) => ({
                ...c,
                [selected.node_id]: !c[selected.node_id],
              }))
            }
          >
            {collapsed[selected.node_id] ? "展开子节点" : "折叠子节点"}
          </button>
          <button type="button" onClick={() => openEvidenceForNode(selected.node_id)}>
            打开 Evidence Drawer
          </button>
          <p className="sl-sm-note">拖拽位置不会保存为故事事实 · 无自由编辑</p>
        </aside>
      ) : null}
      <WholeBookEvidenceDrawer
        open={drawerOpen}
        evidence={drawerEvidence}
        theme={theme}
        onClose={() => setDrawerOpen(false)}
      />
      <details>
        <summary>Pattern / Structure 边界</summary>
        <ul>
          {structureMapBoundaryNotes().map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      </details>
    </div>
  );
}

/** Adapter: reuse Agent C Pattern Map fixture shape optionally for visual spike. */
export function adaptPatternFixtureToStructureProjection(input: {
  bookId: number;
  bookSnapshotId: number;
  nodes: Array<{
    id: string;
    title: string;
    parentId?: string | null;
    nodeType?: string;
  }>;
}): NarrativeStructureMapProjectionDto {
  const root_nodes = input.nodes.map((n) => ({
    node_id: n.id,
    node_type: n.nodeType ?? "structure_stage",
    title: n.title,
    asset_id: null,
    asset_version_id: null,
    is_canonical: true,
    view_modes: ["structure_stages", "storylines", "character_growth"] as StructureMapViewMode[],
    chapter_range: [null, null] as [number | null, number | null],
    parent_id: n.parentId ?? null,
    evidence_count: 0,
    collapsed: false,
    searchable_text: n.title.toLowerCase(),
  }));
  return {
    schema: "narrative_structure_map_projection",
    book_id: input.bookId,
    book_snapshot_id: input.bookSnapshotId,
    source_run_id: null,
    projection_version: "fixture-adapter-1",
    root_nodes,
    edges: [],
    filters: {
      view_mode: "structure_stages",
      search_query: "",
      include_candidates: false,
      max_nodes: STRUCTURE_MAP_DEFAULT_MAX_NODES,
      max_edges: STRUCTURE_MAP_DEFAULT_MAX_EDGES,
      theme: "system",
    },
    evidence_index: {},
    review_summary: { writes_database_facts: false, pattern_orm_table: false },
    conflict_summary: {},
    generated_at: new Date().toISOString(),
  };
}
