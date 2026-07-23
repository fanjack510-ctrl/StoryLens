import type {
  NarrativePatternMapDto,
  PatternMapFilterDto,
  PatternMapNodeDto,
} from "../contracts/patternMap.draft";

export type PatternMapCollapseState = Record<string, boolean>;

/** Build initial collapsed map from node.collapsedByDefault. */
export function initialCollapseState(nodes: PatternMapNodeDto[]): PatternMapCollapseState {
  const state: PatternMapCollapseState = {};
  for (const node of nodes) {
    if (node.childCount > 0) {
      state[node.id] = node.collapsedByDefault;
    }
  }
  return state;
}

export function childrenByParentId(nodes: PatternMapNodeDto[]): Map<string | null, PatternMapNodeDto[]> {
  const map = new Map<string | null, PatternMapNodeDto[]>();
  for (const node of nodes) {
    const key = node.parentId;
    const list = map.get(key) ?? [];
    list.push(node);
    map.set(key, list);
  }
  for (const list of map.values()) {
    list.sort((a, b) => a.orderIndex - b.orderIndex || a.id.localeCompare(b.id));
  }
  return map;
}

/**
 * Visible nodes under current collapse state (depth-first).
 * Does not assume chapter count equals node count.
 */
export function collectVisibleNodes(
  nodes: PatternMapNodeDto[],
  collapsed: PatternMapCollapseState,
): PatternMapNodeDto[] {
  const byParent = childrenByParentId(nodes);
  const visible: PatternMapNodeDto[] = [];

  const walk = (parentId: string | null) => {
    const children = byParent.get(parentId) ?? [];
    for (const child of children) {
      visible.push(child);
      if (child.childCount > 0 && !collapsed[child.id]) {
        walk(child.id);
      }
    }
  };

  walk(null);
  return visible;
}

export function setCollapsed(
  state: PatternMapCollapseState,
  nodeId: string,
  collapsed: boolean,
): PatternMapCollapseState {
  return { ...state, [nodeId]: collapsed };
}

export function expandAll(nodes: PatternMapNodeDto[]): PatternMapCollapseState {
  const next: PatternMapCollapseState = {};
  for (const node of nodes) {
    if (node.childCount > 0) next[node.id] = false;
  }
  return next;
}

export function collapseToDefaults(nodes: PatternMapNodeDto[]): PatternMapCollapseState {
  return initialCollapseState(nodes);
}

export function matchNodeSearch(node: PatternMapNodeDto, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return false;
  return (
    node.title.toLowerCase().includes(q) ||
    node.summary.toLowerCase().includes(q) ||
    node.id.toLowerCase().includes(q) ||
    node.nodeType.toLowerCase().includes(q)
  );
}

export function findMatchingNodeIds(nodes: PatternMapNodeDto[], query: string): string[] {
  if (!query.trim()) return [];
  return nodes.filter((n) => matchNodeSearch(n, query)).map((n) => n.id);
}

/** Ensure ancestors of target are expanded so the node becomes visible. */
export function expandAncestorsForNode(
  nodes: PatternMapNodeDto[],
  collapsed: PatternMapCollapseState,
  targetId: string,
): PatternMapCollapseState {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const next = { ...collapsed };
  let current = byId.get(targetId);
  while (current?.parentId) {
    next[current.parentId] = false;
    current = byId.get(current.parentId);
  }
  return next;
}

export function applyFilterToNodes(
  nodes: PatternMapNodeDto[],
  filter: PatternMapFilterDto,
): PatternMapNodeDto[] {
  return nodes.filter((node) => {
    if (node.confidence < filter.minConfidence) return false;
    if (!filter.includeDisputed && node.userStatus === "disputed") return false;
    if (filter.mode === "storyline" && filter.storylineIds.length) {
      if (node.nodeType === "book_root") return true;
      if (node.nodeType === "storyline") return filter.storylineIds.includes(node.id);
      return node.relatedStorylineIds.some((id) => filter.storylineIds.includes(id));
    }
    if (filter.mode === "character_growth" && filter.characterIds.length) {
      if (node.nodeType === "book_root") return true;
      if (node.nodeType === "character_arc") return filter.characterIds.includes(node.id);
      return node.relatedCharacterIds.some((id) => filter.characterIds.includes(id));
    }
    if (filter.mode === "structure_stage" && filter.stageIds.length) {
      if (node.nodeType === "book_root" || node.nodeType === "structure_stage") {
        return node.nodeType === "book_root" || filter.stageIds.includes(node.id);
      }
      // Keep descendants whose ancestor stage is selected via relatedAssetIds or parent chain later.
      return true;
    }
    if (filter.searchQuery.trim()) {
      return matchNodeSearch(node, filter.searchQuery);
    }
    return true;
  });
}

export function countNodesByDepth(nodes: PatternMapNodeDto[]): Record<number, number> {
  const counts: Record<number, number> = {};
  for (const node of nodes) {
    counts[node.depth] = (counts[node.depth] ?? 0) + 1;
  }
  return counts;
}

export function summarizeMapScale(map: NarrativePatternMapDto): {
  nodeCount: number;
  edgeCount: number;
  maxDepth: number;
  defaultVisibleCount: number;
  fullyExpandedCount: number;
  evidenceRefCount: number;
} {
  const collapsed = initialCollapseState(map.nodes);
  const defaultVisible = collectVisibleNodes(map.nodes, collapsed);
  const expanded = collectVisibleNodes(map.nodes, expandAll(map.nodes));
  const evidenceRefCount = Object.values(map.evidenceByNodeId ?? {}).reduce(
    (sum, refs) => sum + refs.length,
    0,
  );
  return {
    nodeCount: map.nodes.length,
    edgeCount: map.edges.length,
    maxDepth: map.nodes.reduce((max, n) => Math.max(max, n.depth), 0),
    defaultVisibleCount: defaultVisible.length,
    fullyExpandedCount: expanded.length,
    evidenceRefCount,
  };
}
