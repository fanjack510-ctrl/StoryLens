import type { PatternMapNodeDto } from "../contracts/patternMap.draft";

export type PatternMapLayoutNode = {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  depth: number;
};

export type PatternMapLayoutResult = {
  nodes: PatternMapLayoutNode[];
  width: number;
  height: number;
};

const NODE_WIDTH = 180;
const NODE_HEIGHT = 52;
const GAP_X = 28;
const GAP_Y = 64;

/**
 * Simple top-down tree layout for prototype validation.
 * Intentionally dependency-free; replaceable by dagre/elk later if Integration approves.
 */
export function layoutPatternTree(visible: PatternMapNodeDto[]): PatternMapLayoutResult {
  if (!visible.length) {
    return { nodes: [], width: 0, height: 0 };
  }

  const byParent = new Map<string | null, PatternMapNodeDto[]>();
  for (const node of visible) {
    const key = node.parentId;
    // Only link parent if parent is also visible; otherwise treat as forest root.
    const parentVisible = key != null && visible.some((n) => n.id === key);
    const effectiveParent = parentVisible ? key : null;
    const list = byParent.get(effectiveParent) ?? [];
    list.push(node);
    byParent.set(effectiveParent, list);
  }

  const subtreeWidth = new Map<string, number>();

  const measure = (node: PatternMapNodeDto): number => {
    const children = byParent.get(node.id) ?? [];
    if (!children.length) {
      subtreeWidth.set(node.id, NODE_WIDTH);
      return NODE_WIDTH;
    }
    const width =
      children.reduce((sum, child) => sum + measure(child), 0) + GAP_X * (children.length - 1);
    const w = Math.max(NODE_WIDTH, width);
    subtreeWidth.set(node.id, w);
    return w;
  };

  const roots = byParent.get(null) ?? [];
  for (const root of roots) measure(root);

  const placed: PatternMapLayoutNode[] = [];

  const place = (node: PatternMapNodeDto, left: number, depth: number) => {
    const width = subtreeWidth.get(node.id) ?? NODE_WIDTH;
    const x = left + width / 2 - NODE_WIDTH / 2;
    const y = depth * (NODE_HEIGHT + GAP_Y);
    placed.push({
      id: node.id,
      x,
      y,
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
      depth,
    });
    const children = byParent.get(node.id) ?? [];
    let cursor = left;
    for (const child of children) {
      const childWidth = subtreeWidth.get(child.id) ?? NODE_WIDTH;
      place(child, cursor, depth + 1);
      cursor += childWidth + GAP_X;
    }
  };

  let cursor = 0;
  for (const root of roots) {
    const width = subtreeWidth.get(root.id) ?? NODE_WIDTH;
    place(root, cursor, 0);
    cursor += width + GAP_X * 2;
  }

  // Guard against accidental duplicate placement (defensive for forest projections).
  const deduped: PatternMapLayoutNode[] = [];
  const seen = new Set<string>();
  for (const node of placed) {
    if (seen.has(node.id)) continue;
    seen.add(node.id);
    deduped.push(node);
  }

  const maxX = deduped.reduce((m, n) => Math.max(m, n.x + n.width), 0);
  const maxY = deduped.reduce((m, n) => Math.max(m, n.y + n.height), 0);
  return {
    nodes: deduped,
    width: maxX + 40,
    height: maxY + 40,
  };
}

export const PATTERN_MAP_LAYOUT_CONSTANTS = {
  NODE_WIDTH,
  NODE_HEIGHT,
  GAP_X,
  GAP_Y,
} as const;
