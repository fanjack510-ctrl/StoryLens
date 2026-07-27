import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
  type WheelEvent,
} from "react";
import type {
  NarrativePatternMapDto,
  PatternMapEvidenceRefDto,
  PatternMapNodeDto,
} from "../contracts/patternMap.draft";
import { layoutPatternTree } from "../lib/patternMapLayout";
import {
  collectVisibleNodes,
  expandAll,
  expandAncestorsForNode,
  findMatchingNodeIds,
  initialCollapseState,
  setCollapsed,
  type PatternMapCollapseState,
} from "../lib/patternMapTree";
import { evidenceDeepLinkHref } from "../lib/evidenceDeepLink";
import "./PatternMapPrototype.css";

export type PatternMapPrototypeProps = {
  map: NarrativePatternMapDto;
  /** Isolated theme override for spike tests — does not touch global uiStore. */
  theme?: "light" | "dark";
  onThemeChange?: (theme: "light" | "dark") => void;
  className?: string;
};

const MIN_SCALE = 0.4;
const MAX_SCALE = 2.2;

/**
 * Isolated spike only — MUST NOT be registered in product routes.
 * Validates tree layout, collapse, pan/zoom, selection, detail, theme, search, a11y.
 */
export function PatternMapPrototype({
  map,
  theme = "light",
  onThemeChange,
  className,
}: PatternMapPrototypeProps) {
  const [collapsed, setCollapsedState] = useState<PatternMapCollapseState>(() =>
    initialCollapseState(map.nodes),
  );
  const [selectedId, setSelectedId] = useState<string | null>(
    map.defaultViewport.selectedNodeId,
  );
  const [scale, setScale] = useState(map.defaultViewport.scale || 1);
  const [translate, setTranslate] = useState({
    x: map.defaultViewport.translateX,
    y: map.defaultViewport.translateY,
  });
  const [query, setQuery] = useState("");
  const [matchIndex, setMatchIndex] = useState(0);
  const dragRef = useRef<{
    pointerId: number;
    originX: number;
    originY: number;
    startX: number;
    startY: number;
  } | null>(null);

  const visible = useMemo(
    () => collectVisibleNodes(map.nodes, collapsed),
    [map.nodes, collapsed],
  );
  const layout = useMemo(() => layoutPatternTree(visible), [visible]);
  const layoutById = useMemo(
    () => new Map(layout.nodes.map((n) => [n.id, n])),
    [layout.nodes],
  );
  const selected = map.nodes.find((n) => n.id === selectedId) ?? null;
  const evidence: PatternMapEvidenceRefDto[] =
    (selectedId && map.evidenceByNodeId?.[selectedId]) || [];
  const matches = useMemo(
    () => findMatchingNodeIds(map.nodes, query),
    [map.nodes, query],
  );

  useEffect(() => {
    setMatchIndex(0);
  }, [query]);

  const parentChildEdges = useMemo(() => {
    return visible
      .filter((n) => n.parentId && layoutById.has(n.id) && layoutById.has(n.parentId))
      .map((n) => {
        const child = layoutById.get(n.id)!;
        const parent = layoutById.get(n.parentId!)!;
        return {
          id: `layout-${parent.id}-${child.id}`,
          x1: parent.x + parent.width / 2,
          y1: parent.y + parent.height,
          x2: child.x + child.width / 2,
          y2: child.y,
        };
      });
  }, [visible, layoutById]);

  const toggleNode = (node: PatternMapNodeDto) => {
    if (node.childCount <= 0) return;
    setCollapsedState((prev) => setCollapsed(prev, node.id, !prev[node.id]));
  };

  const selectNode = (nodeId: string) => {
    setSelectedId(nodeId);
    setCollapsedState((prev) => expandAncestorsForNode(map.nodes, prev, nodeId));
  };

  const focusSearchMatch = (direction: 1 | -1) => {
    if (!matches.length) return;
    const next = (matchIndex + direction + matches.length) % matches.length;
    setMatchIndex(next);
    selectNode(matches[next]!);
  };

  const onPointerDown = (event: PointerEvent<SVGSVGElement>) => {
    if ((event.target as Element).closest("[data-pattern-node]")) return;
    dragRef.current = {
      pointerId: event.pointerId,
      originX: event.clientX,
      originY: event.clientY,
      startX: translate.x,
      startY: translate.y,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const onPointerMove = (event: PointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    setTranslate({
      x: drag.startX + (event.clientX - drag.originX),
      y: drag.startY + (event.clientY - drag.originY),
    });
  };

  const onPointerUp = (event: PointerEvent<SVGSVGElement>) => {
    if (dragRef.current?.pointerId === event.pointerId) {
      dragRef.current = null;
      try {
        event.currentTarget.releasePointerCapture(event.pointerId);
      } catch {
        /* ignore */
      }
    }
  };

  const onWheel = (event: WheelEvent<HTMLDivElement>) => {
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    const delta = event.deltaY > 0 ? -0.08 : 0.08;
    setScale((s) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, Number((s + delta).toFixed(2)))));
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "+" || event.key === "=") {
      event.preventDefault();
      setScale((s) => Math.min(MAX_SCALE, Number((s + 0.1).toFixed(2))));
    } else if (event.key === "-" || event.key === "_") {
      event.preventDefault();
      setScale((s) => Math.max(MIN_SCALE, Number((s - 0.1).toFixed(2))));
    } else if (event.key === "Enter" && selected && selected.childCount > 0) {
      event.preventDefault();
      toggleNode(selected);
    } else if (event.key === "ArrowDown" && matches.length) {
      event.preventDefault();
      focusSearchMatch(1);
    } else if (event.key === "ArrowUp" && matches.length) {
      event.preventDefault();
      focusSearchMatch(-1);
    }
  };

  return (
    <div
      className={`pattern-map-prototype ${className ?? ""}`}
      data-testid="pattern-map-prototype"
      data-theme={theme}
      data-visible-count={visible.length}
      tabIndex={0}
      onKeyDown={onKeyDown}
      onWheel={onWheel}
    >
      <header className="pattern-map-toolbar" data-testid="pattern-map-toolbar">
        <div className="pattern-map-toolbar-title">{map.title}</div>
        <div className="pattern-map-toolbar-actions">
          <label className="pattern-map-search">
            <span className="pattern-map-sr-only">搜索节点</span>
            <input
              data-testid="pattern-map-search"
              type="search"
              value={query}
              placeholder="搜索节点"
              aria-label="搜索节点"
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <button
            type="button"
            data-testid="pattern-map-search-next"
            onClick={() => focusSearchMatch(1)}
            disabled={!matches.length}
          >
            定位 ({matches.length})
          </button>
          <button
            type="button"
            data-testid="pattern-map-expand-all"
            onClick={() => setCollapsedState(expandAll(map.nodes))}
          >
            全部展开
          </button>
          <button
            type="button"
            data-testid="pattern-map-collapse-default"
            onClick={() => setCollapsedState(initialCollapseState(map.nodes))}
          >
            默认折叠
          </button>
          <button
            type="button"
            data-testid="pattern-map-zoom-in"
            onClick={() => setScale((s) => Math.min(MAX_SCALE, Number((s + 0.1).toFixed(2))))}
          >
            放大
          </button>
          <button
            type="button"
            data-testid="pattern-map-zoom-out"
            onClick={() => setScale((s) => Math.max(MIN_SCALE, Number((s - 0.1).toFixed(2))))}
          >
            缩小
          </button>
          <button
            type="button"
            data-testid="pattern-map-theme-toggle"
            aria-pressed={theme === "dark"}
            onClick={() => onThemeChange?.(theme === "dark" ? "light" : "dark")}
          >
            {theme === "dark" ? "浅色" : "深色"}
          </button>
        </div>
      </header>

      <div className="pattern-map-body">
        <div className="pattern-map-canvas-wrap" data-testid="pattern-map-canvas-wrap">
          <svg
            className="pattern-map-canvas"
            data-testid="pattern-map-canvas"
            role="img"
            aria-label="叙事结构地图原型"
            width="100%"
            height="100%"
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
          >
            <g transform={`translate(${translate.x} ${translate.y}) scale(${scale})`}>
              {parentChildEdges.map((edge) => (
                <line
                  key={edge.id}
                  className="pattern-map-edge"
                  x1={edge.x1}
                  y1={edge.y1}
                  x2={edge.x2}
                  y2={edge.y2}
                />
              ))}
              {visible.map((node) => {
                const box = layoutById.get(node.id);
                if (!box) return null;
                const isSelected = node.id === selectedId;
                const isMatch = matches.includes(node.id);
                const isCollapsed = Boolean(collapsed[node.id]);
                return (
                  <g
                    key={node.id}
                    data-pattern-node={node.id}
                    data-testid={`pattern-map-node-${node.id}`}
                    data-node-type={node.nodeType}
                    data-collapsed={isCollapsed ? "true" : "false"}
                    data-selected={isSelected ? "true" : "false"}
                    transform={`translate(${box.x} ${box.y})`}
                    role="button"
                    tabIndex={0}
                    aria-label={`${node.title}，${node.nodeType}`}
                    aria-expanded={node.childCount > 0 ? !isCollapsed : undefined}
                    onClick={() => selectNode(node.id)}
                    onDoubleClick={() => toggleNode(node)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        selectNode(node.id);
                      }
                    }}
                  >
                    <rect
                      className={`pattern-map-node-rect${isSelected ? " is-selected" : ""}${
                        isMatch ? " is-match" : ""
                      }`}
                      width={box.width}
                      height={box.height}
                      rx={8}
                    />
                    <text className="pattern-map-node-title" x={12} y={22}>
                      {node.childCount > 0 ? (isCollapsed ? "▸ " : "▾ ") : ""}
                      {node.title}
                    </text>
                    <text className="pattern-map-node-meta" x={12} y={40}>
                      {node.nodeType} · conf {node.confidence.toFixed(2)}
                    </text>
                    {node.childCount > 0 ? (
                      <text
                        className="pattern-map-node-toggle"
                        x={box.width - 14}
                        y={28}
                        textAnchor="end"
                        data-testid={`pattern-map-toggle-${node.id}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleNode(node);
                        }}
                      >
                        {node.childCount}
                      </text>
                    ) : null}
                  </g>
                );
              })}
            </g>
          </svg>
          <div className="pattern-map-hud" data-testid="pattern-map-hud">
            可见 {visible.length} / 全量 {map.nodes.length} · 缩放 {scale.toFixed(2)}
          </div>
        </div>

        <aside
          className="pattern-map-detail"
          data-testid="pattern-map-detail"
          aria-live="polite"
        >
          {selected ? (
            <>
              <h2 data-testid="pattern-map-detail-title">{selected.title}</h2>
              <p className="pattern-map-detail-summary">{selected.summary}</p>
              <dl className="pattern-map-detail-grid">
                <div>
                  <dt>类型</dt>
                  <dd>{selected.nodeType}</dd>
                </div>
                <div>
                  <dt>置信度</dt>
                  <dd>{selected.confidence.toFixed(2)}</dd>
                </div>
                <div>
                  <dt>用户状态</dt>
                  <dd>{selected.userStatus}</dd>
                </div>
                <div>
                  <dt>章节跨度</dt>
                  <dd>
                    {selected.startChapterId ?? "—"} – {selected.endChapterId ?? "—"}
                  </dd>
                </div>
                <div>
                  <dt>Evidence</dt>
                  <dd>{selected.evidenceCount}</dd>
                </div>
                <div>
                  <dt>子节点</dt>
                  <dd>{selected.childCount}</dd>
                </div>
              </dl>
              <h3>Evidence 引用</h3>
              {evidence.length === 0 ? (
                <p data-testid="pattern-map-evidence-empty">详情区按需加载（本节点无内联样本）</p>
              ) : (
                <ul data-testid="pattern-map-evidence-list">
                  {evidence.map((ref) => (
                    <li key={`${ref.paragraphId}-${ref.label}`}>
                      <a
                        href={evidenceDeepLinkHref(map.bookId, ref)}
                        data-testid={`pattern-map-evidence-link-${ref.paragraphId}`}
                      >
                        {ref.label}
                      </a>
                      <div className="pattern-map-evidence-meta">
                        ch {ref.chapterId}
                        {ref.sceneId != null ? ` · scene ${ref.sceneId}` : ""} · {ref.paragraphId}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <p data-testid="pattern-map-detail-empty">选择节点查看详情与 Evidence</p>
          )}
        </aside>
      </div>
    </div>
  );
}
