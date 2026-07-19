import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import type {
  JourneyCurveMetric,
  JourneySceneNode,
  ReaderJourneyVisualization,
} from "../../types/readerJourneyVisualization";
import { METRIC_LABELS_ZH } from "./journeyUiLabels";
import { PHASE_BAND_COLORS } from "./journeyVisualTokens";
import {
  buildLinePathD,
  clampViewWindow,
  collectDataWarnings,
  computeYScale,
  resolveMetricValue,
  xForSceneOrdinal,
} from "./journeyChartScales";
import {
  CHART_PAD,
  JOURNEY_VISUALIZATION_VERSION,
  PHASE_BAND_OPACITY,
  RISK_BAND_OPACITY,
  SCENE_DENSITY,
  allowsHorizontalPanZoom,
  computeChartContentWidth,
  requiresBrush,
  type YDomainMode,
} from "./journeyVisualizationConfig";

const ROLE_CLASS: Record<string, string> = {
  core: "journey-node-core",
  secondary: "journey-node-secondary",
  beat: "journey-node-beat",
};

const NODE_RADIUS: Record<string, number> = {
  core: 7,
  secondary: 5,
  beat: 3.5,
};

export type CanonicalJourneyChartProps = {
  visualization: ReaderJourneyVisualization;
  metric: JourneyCurveMetric;
  chartHeight: number;
  yDomainMode: YDomainMode;
  viewStart: number;
  viewEnd: number;
  onViewChange: (start: number, end: number) => void;
  selectedSceneOrdinal: number | null;
  selectedPhaseOrdinal: number | null;
  markerMode: "compact" | "full";
  /** When true, always render full scene span at 0–100 (PNG full export). */
  exportFullJourney?: boolean;
  onSelectScene: (node: JourneySceneNode) => void;
  onSelectRisk: (intervalKey: string, startNode?: JourneySceneNode) => void;
  onSelectHook: (node: JourneySceneNode) => void;
  onSelectPayoff: (node: JourneySceneNode) => void;
};

type TooltipState = {
  ordinal: number;
  x: number;
  y: number;
};

function hookTier(
  visualization: ReaderJourneyVisualization,
  ordinal: number,
  sceneCount: number,
): "chapter" | "phase" | "key" {
  if (ordinal === sceneCount) return "chapter";
  const isPhaseTurn = visualization.phases.some(
    (phase) => phase.ordinal > 1 && phase.start_scene_ordinal === ordinal,
  );
  if (isPhaseTurn) return "phase";
  const marker = visualization.hook_markers.find((item) => item.scene_ordinal === ordinal);
  if ((marker?.strength ?? 0) >= 70) return "phase";
  return "key";
}

export function CanonicalJourneyChart({
  visualization,
  metric,
  chartHeight,
  yDomainMode,
  viewStart,
  viewEnd,
  onViewChange,
  selectedSceneOrdinal,
  selectedPhaseOrdinal,
  markerMode,
  exportFullJourney = false,
  onSelectScene,
  onSelectRisk,
  onSelectHook,
  onSelectPayoff,
}: CanonicalJourneyChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const nodes = visualization.scene_nodes;
  const sceneCount = nodes.length;
  const series = visualization.curve_series[metric] ?? [];

  const effectiveView = exportFullJourney
    ? { start: 1, end: Math.max(sceneCount, 1) }
    : { start: viewStart, end: viewEnd };
  const effectiveYMode: YDomainMode = exportFullJourney ? "fixed_0_100" : yDomainMode;

  const [viewportWidth, setViewportWidth] = useState(640);
  const [hover, setHover] = useState<TooltipState | null>(null);
  const dragRef = useRef<{
    pointerId: number;
    originX: number;
    start: number;
    end: number;
  } | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () => setViewportWidth(Math.max(Math.floor(el.clientWidth || 0), 320));
    update();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => update());
    observer.observe(el);
    return () => observer.disconnect();
  }, [sceneCount]);

  const chartWidth = useMemo(() => {
    if (exportFullJourney) {
      return Math.max(
        sceneCount * SCENE_DENSITY.minPxPerScene + CHART_PAD.left + CHART_PAD.right,
        720,
      );
    }
    return computeChartContentWidth(
      sceneCount,
      viewportWidth,
      effectiveView.start,
      effectiveView.end,
    );
  }, [exportFullJourney, sceneCount, viewportWidth, effectiveView.start, effectiveView.end]);

  const yScale = useMemo(
    () => computeYScale(series, chartHeight, effectiveYMode),
    [series, chartHeight, effectiveYMode],
  );

  const warnings = useMemo(() => collectDataWarnings(series), [series]);

  const xFor = useCallback(
    (ordinal: number) => xForSceneOrdinal(ordinal, sceneCount, chartWidth),
    [sceneCount, chartWidth],
  );

  const linePath = useMemo(
    () => buildLinePathD(series, xFor, yScale.yForValue),
    [series, xFor, yScale],
  );

  const hookOrdinals = useMemo(() => {
    if (markerMode === "compact") {
      return new Set(visualization.hook_markers.map((m) => m.scene_ordinal));
    }
    const ordinals = new Set<number>();
    for (const node of nodes) {
      if (node.primary_hook || node.hooks.length) ordinals.add(node.scene_ordinal);
    }
    for (const marker of visualization.suppressed_hooks ?? []) {
      ordinals.add(marker.scene_ordinal);
    }
    for (const marker of visualization.hook_markers) {
      ordinals.add(marker.scene_ordinal);
    }
    return ordinals;
  }, [markerMode, nodes, visualization.hook_markers, visualization.suppressed_hooks]);

  const payoffOrdinals = useMemo(() => {
    if (markerMode === "compact") {
      return new Set(visualization.payoff_markers.map((m) => m.scene_ordinal));
    }
    const ordinals = new Set<number>();
    for (const node of nodes) {
      if (node.primary_payoff || node.payoffs.length) ordinals.add(node.scene_ordinal);
    }
    for (const marker of visualization.payoff_markers) {
      ordinals.add(marker.scene_ordinal);
    }
    return ordinals;
  }, [markerMode, nodes, visualization.payoff_markers]);
  const riskOrdinals = useMemo(() => {
    const set = new Set<number>();
    for (const interval of visualization.risk_intervals) {
      for (let o = interval.start_scene_ordinal; o <= interval.end_scene_ordinal; o += 1) {
        set.add(o);
      }
    }
    return set;
  }, [visualization.risk_intervals]);

  const showBrush = !exportFullJourney && requiresBrush(sceneCount);
  const canPan = !exportFullJourney && allowsHorizontalPanZoom(sceneCount);

  const scrollToView = useCallback(() => {
    const el = containerRef.current;
    if (!el || exportFullJourney) return;
    const x1 = xFor(effectiveView.start);
    const x2 = xFor(effectiveView.end);
    const mid = (x1 + x2) / 2;
    el.scrollLeft = Math.max(0, mid - el.clientWidth / 2);
  }, [effectiveView.start, effectiveView.end, xFor, exportFullJourney]);

  useEffect(() => {
    scrollToView();
  }, [scrollToView, chartWidth]);

  const onPointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!canPan || exportFullJourney) return;
    if ((event.target as Element).closest("[data-node-hit]")) return;
    dragRef.current = {
      pointerId: event.pointerId,
      originX: event.clientX,
      start: effectiveView.start,
      end: effectiveView.end,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const onPointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const plotWidth = chartWidth - CHART_PAD.left - CHART_PAD.right;
    const pxPerScene = plotWidth / Math.max(sceneCount - 1, 1);
    const deltaScenes = Math.round((drag.originX - event.clientX) / Math.max(pxPerScene, 1));
    if (deltaScenes === 0) return;
    const span = drag.end - drag.start;
    const next = clampViewWindow(
      drag.start + deltaScenes,
      drag.start + deltaScenes + span,
      sceneCount,
      2,
    );
    onViewChange(next.start, next.end);
  };

  const onPointerUp = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (dragRef.current?.pointerId === event.pointerId) {
      dragRef.current = null;
      try {
        event.currentTarget.releasePointerCapture(event.pointerId);
      } catch {
        /* ignore */
      }
    }
  };

  const brushHeight = showBrush ? 36 : 0;
  const totalHeight = chartHeight + brushHeight;
  const padTop = CHART_PAD.top;
  const padLeft = CHART_PAD.left;
  const plotHeight = chartHeight - CHART_PAD.top - CHART_PAD.bottom;
  const plotWidth = Math.max(chartWidth - CHART_PAD.left - CHART_PAD.right, 1);
  const clipPathId = exportFullJourney
    ? "journey-plot-clip-full-export"
    : "journey-plot-clip";

  const tooltipNode =
    hover != null ? nodes.find((n) => n.scene_ordinal === hover.ordinal) : undefined;
  const tooltipPoint =
    hover != null ? series.find((p) => p.scene_ordinal === hover.ordinal) : undefined;
  const tooltipScore = resolveMetricValue(tooltipPoint);
  const tooltipPhase =
    tooltipNode?.phase_ordinal != null
      ? visualization.phases.find((p) => p.ordinal === tooltipNode.phase_ordinal)
      : undefined;
  const tooltipHook = visualization.hook_markers.find(
    (m) => m.scene_ordinal === hover?.ordinal,
  );
  const tooltipPayoff = visualization.payoff_markers.find(
    (m) => m.scene_ordinal === hover?.ordinal,
  );
  const tooltipRisk = visualization.risk_intervals.find(
    (r) =>
      hover != null &&
      hover.ordinal >= r.start_scene_ordinal &&
      hover.ordinal <= r.end_scene_ordinal,
  );

  return (
    <div
      className="journey-curve-container canonical-journey-chart"
      ref={containerRef}
      data-testid={
        exportFullJourney ? "journey-curve-container-full-export" : "journey-curve-container"
      }
      data-canonical-chart="true"
      data-visualization-version={JOURNEY_VISUALIZATION_VERSION}
      data-plot-height={plotHeight}
      data-svg-height={totalHeight}
      data-chart-height={chartHeight}
      data-clip-height={plotHeight}
      data-export-full={exportFullJourney ? "true" : "false"}
      style={{
        overflowX: "auto",
        overflowY: "hidden",
      }}
    >
      {warnings.length > 0 && (
        <div
          className="journey-chart-data-warning"
          data-testid="journey-chart-data-warning"
          role="status"
        >
          检测到 {warnings.length} 个超出 0—100 的分数，已按真实值绘制（未静默裁剪）。
        </div>
      )}
      <div
        className="journey-curve-svg-frame"
        data-testid={exportFullJourney ? undefined : "journey-curve-svg-frame"}
        style={{
          height: totalHeight,
          minHeight: totalHeight,
          maxHeight: totalHeight,
          overflowX: "auto",
          overflowY: "hidden",
        }}
      >
      <svg
        data-testid={exportFullJourney ? "journey-curve-svg-full-export" : "journey-curve-svg"}
        className="journey-curve-svg"
        width={chartWidth}
        height={totalHeight}
        viewBox={`0 0 ${chartWidth} ${totalHeight}`}
        preserveAspectRatio="xMidYMid meet"
        style={{
          width: chartWidth,
          height: totalHeight,
          minHeight: totalHeight,
          maxHeight: totalHeight,
          maxWidth: "none",
          overflow: "visible",
          display: "block",
          flexShrink: 0,
          cursor: canPan ? "grab" : "default",
        }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      >
        <defs>
          <clipPath id={clipPathId} data-testid={exportFullJourney ? undefined : "journey-plot-clip"}>
            <rect
              x={padLeft}
              y={padTop}
              width={plotWidth}
              height={plotHeight}
              data-clip-height={plotHeight}
            />
          </clipPath>
        </defs>

        {/* 1. Phase background (clipped to plot) */}
        <g data-layer="phase_background" clipPath={`url(#${clipPathId})`}>
          {visualization.phases.map((phase, index) => {
            const x1 = xFor(phase.start_scene_ordinal) - 8;
            const x2 = xFor(phase.end_scene_ordinal) + 8;
            return (
              <rect
                key={`phase-band-${phase.ordinal}`}
                x={x1}
                y={padTop}
                width={Math.max(x2 - x1, 4)}
                height={plotHeight}
                fill={PHASE_BAND_COLORS[index % PHASE_BAND_COLORS.length]}
                opacity={
                  selectedPhaseOrdinal === phase.ordinal
                    ? PHASE_BAND_OPACITY.active
                    : PHASE_BAND_OPACITY.idle
                }
              />
            );
          })}
        </g>

        {/* 2. Risk background */}
        <g data-layer="risk_background" clipPath={`url(#${clipPathId})`}>
          {visualization.risk_intervals.map((interval) => {
            const x1 = xFor(interval.start_scene_ordinal) - 6;
            const x2 = xFor(interval.end_scene_ordinal) + 6;
            const startNode = nodes.find(
              (node) => node.scene_ordinal === interval.start_scene_ordinal,
            );
            return (
              <rect
                key={`${interval.risk_type}-${interval.start_scene_ordinal}`}
                data-testid={`journey-risk-${interval.risk_type}-${interval.start_scene_ordinal}`}
                x={x1}
                y={padTop}
                width={Math.max(x2 - x1, 4)}
                height={plotHeight}
                fill="#f3ddd8"
                opacity={RISK_BAND_OPACITY}
                style={{ cursor: "pointer" }}
                onClick={(event) => {
                  event.stopPropagation();
                  onSelectRisk(
                    `${interval.risk_type}-${interval.start_scene_ordinal}`,
                    startNode,
                  );
                }}
              />
            );
          })}
        </g>

        {/* 3. Grid + axes */}
        <g data-layer="grid">
          {visualization.phases.map((phase) => (
            <line
              key={`phase-line-${phase.start_scene_ordinal}`}
              x1={xFor(phase.start_scene_ordinal)}
              y1={padTop}
              x2={xFor(phase.start_scene_ordinal)}
              y2={padTop + plotHeight}
              stroke="var(--line)"
              strokeDasharray="3 3"
              strokeOpacity={0.55}
            />
          ))}
          <line
            x1={CHART_PAD.left}
            y1={padTop + plotHeight}
            x2={chartWidth - CHART_PAD.right}
            y2={padTop + plotHeight}
            stroke="var(--line)"
          />
          <line
            x1={CHART_PAD.left}
            y1={padTop}
            x2={CHART_PAD.left}
            y2={padTop + plotHeight}
            stroke="var(--line)"
          />
          {yScale.ticks.map((tick) => {
            const y = yScale.yForValue(tick);
            return (
              <g
                key={`y-tick-${tick}`}
                data-testid={exportFullJourney ? undefined : `journey-y-tick-${tick}`}
              >
                <line
                  x1={CHART_PAD.left}
                  y1={y}
                  x2={chartWidth - CHART_PAD.right}
                  y2={y}
                  stroke="var(--line)"
                  strokeOpacity={0.35}
                />
                <text
                  x={CHART_PAD.left - 6}
                  y={y + 3}
                  textAnchor="end"
                  className="journey-axis-label"
                >
                  {tick}
                </text>
              </g>
            );
          })}
          {nodes.map((node) => {
            const dense = sceneCount > SCENE_DENSITY.fitAllMax && markerMode === "compact";
            if (dense && node.scene_ordinal % 2 === 0 && node.scene_ordinal !== sceneCount) {
              return null;
            }
            return (
              <text
                key={`x-label-${node.scene_ordinal}`}
                x={xFor(node.scene_ordinal)}
                y={chartHeight - 8}
                textAnchor="middle"
                className="journey-axis-label"
                data-testid={
                  exportFullJourney ? undefined : `journey-x-label-${node.scene_ordinal}`
                }
              >
                S{node.scene_ordinal}
              </text>
            );
          })}
        </g>

        {/* 4. Curve (clipped); nodes stay outside clip so radius is never cropped */}
        <g data-layer="curve" clipPath={`url(#${clipPathId})`}>
          {linePath && (
            <path
              d={linePath}
              fill="none"
              stroke="var(--accent)"
              strokeWidth={2.25}
              data-testid="journey-curve-path"
            />
          )}
        </g>

        {/* 5. Nodes — not clipped by plot clipPath */}
        <g data-layer="nodes">
          {nodes.map((node) => {
            const point = series.find((item) => item.scene_ordinal === node.scene_ordinal);
            const value = resolveMetricValue(point);
            const cx = xFor(node.scene_ordinal);
            if (value == null) {
              return (
                <g
                  key={node.scene_ordinal}
                  data-testid={
                    exportFullJourney ? undefined : `journey-curve-node-${node.scene_ordinal}`
                  }
                  data-node-hit="true"
                  data-missing="true"
                  className={`journey-curve-node ${ROLE_CLASS[node.role] ?? ""}`}
                  onClick={() => onSelectScene(node)}
                  style={{ cursor: "pointer" }}
                >
                  <line
                    x1={cx - 5}
                    y1={padTop + plotHeight / 2 - 5}
                    x2={cx + 5}
                    y2={padTop + plotHeight / 2 + 5}
                    stroke="var(--muted)"
                    strokeWidth={1.5}
                  />
                  <line
                    x1={cx + 5}
                    y1={padTop + plotHeight / 2 - 5}
                    x2={cx - 5}
                    y2={padTop + plotHeight / 2 + 5}
                    stroke="var(--muted)"
                    strokeWidth={1.5}
                  />
                </g>
              );
            }
            const cy = yScale.yForValue(value);
            const radius = NODE_RADIUS[node.role] ?? 4;
            const selected = selectedSceneOrdinal === node.scene_ordinal;
            const tier = hookTier(visualization, node.scene_ordinal, sceneCount);
            const hookSize = tier === "chapter" ? 7 : tier === "phase" ? 5.5 : 4;
            return (
              <g
                key={node.scene_ordinal}
                data-testid={
                  exportFullJourney ? undefined : `journey-curve-node-${node.scene_ordinal}`
                }
                data-node-hit="true"
                data-score={String(value)}
                className={`journey-curve-node ${ROLE_CLASS[node.role] ?? ""} ${
                  selected ? "selected journey-node-active" : ""
                }`}
                data-hook-tier={hookOrdinals.has(node.scene_ordinal) ? tier : undefined}
                onMouseEnter={() => setHover({ ordinal: node.scene_ordinal, x: cx, y: cy })}
                onMouseLeave={() => setHover(null)}
                onClick={() => onSelectScene(node)}
                style={{ cursor: "pointer" }}
              >
                <rect x={cx - 14} y={cy - 14} width={28} height={28} fill="transparent" />
                <circle
                  cx={cx}
                  cy={cy}
                  r={radius + (selected ? 3 : 0)}
                  fill="var(--surface)"
                  stroke="var(--accent)"
                  strokeWidth={selected ? 3 : 1.5}
                />
                {payoffOrdinals.has(node.scene_ordinal) && (
                  <circle
                    cx={cx + 5}
                    cy={cy - 5}
                    r={3.2}
                    fill="var(--accent)"
                    data-marker="payoff"
                    onClick={(event) => {
                      event.stopPropagation();
                      onSelectPayoff(node);
                    }}
                  />
                )}
                {hookOrdinals.has(node.scene_ordinal) && (
                  <path
                    d={`M ${cx - hookSize / 2} ${cy + 7} L ${cx} ${cy + 7 - hookSize} L ${cx + hookSize / 2} ${cy + 7} Z`}
                    fill="#8a6d3b"
                    data-marker="hook"
                    data-hook-tier={tier}
                    onClick={(event) => {
                      event.stopPropagation();
                      onSelectHook(node);
                    }}
                  />
                )}
                {riskOrdinals.has(node.scene_ordinal) && (
                  <rect
                    x={cx - 5}
                    y={padTop + plotHeight - 6}
                    width={10}
                    height={5}
                    fill="#a13a31"
                    opacity={0.85}
                    data-marker="risk"
                  />
                )}
              </g>
            );
          })}
        </g>

        {/* 6. Active scene guide (under labels) */}
        <g data-layer="active_scene">
          {selectedSceneOrdinal != null && (
            <g data-testid={exportFullJourney ? undefined : "journey-active-scene-guide"}>
              <line
                x1={xFor(selectedSceneOrdinal)}
                y1={padTop}
                x2={xFor(selectedSceneOrdinal)}
                y2={padTop + plotHeight}
                stroke="var(--accent)"
                strokeWidth={1.5}
                strokeDasharray="4 3"
                opacity={0.85}
              />
            </g>
          )}
        </g>

        {/* 7. Labels / tooltip */}
        <g data-layer="labels_tooltip">
          {hover != null && tooltipNode && (
            <foreignObject
              x={Math.min(Math.max(hover.x - 90, 4), chartWidth - 200)}
              y={Math.max(hover.y - 110, 4)}
              width={196}
              height={108}
              data-testid="journey-node-tooltip"
            >
              <div className="journey-node-tooltip-card" xmlns="http://www.w3.org/1999/xhtml">
                <div>
                  Scene {tooltipNode.scene_ordinal}
                  {tooltipNode.role ? ` · ${tooltipNode.role}` : ""}
                </div>
                <div>Phase {tooltipNode.phase_ordinal ?? "—"}{tooltipPhase ? ` · ${tooltipPhase.title}` : ""}</div>
                <div>
                  {METRIC_LABELS_ZH[metric]}：
                  {tooltipScore == null ? "—" : Math.round(tooltipScore)}
                </div>
                <div>Hook：{tooltipHook?.summary ?? "—"}</div>
                <div>Payoff：{tooltipPayoff?.summary ?? "—"}</div>
                <div>Risk：{tooltipRisk?.summary ?? tooltipRisk?.risk_type ?? "—"}</div>
              </div>
            </foreignObject>
          )}
        </g>

        {showBrush && (
          <g
            data-layer="brush"
            data-testid={exportFullJourney ? undefined : "journey-chart-brush"}
          >
            <rect
              x={CHART_PAD.left}
              y={chartHeight + 6}
              width={chartWidth - CHART_PAD.left - CHART_PAD.right}
              height={22}
              fill="var(--surface2)"
              stroke="var(--line)"
            />
            {(() => {
              const plotW = chartWidth - CHART_PAD.left - CHART_PAD.right;
              const x1 =
                CHART_PAD.left +
                ((effectiveView.start - 1) / Math.max(sceneCount - 1, 1)) * plotW;
              const x2 =
                CHART_PAD.left +
                ((effectiveView.end - 1) / Math.max(sceneCount - 1, 1)) * plotW;
              return (
                <rect
                  data-testid="journey-chart-brush-window"
                  x={x1}
                  y={chartHeight + 6}
                  width={Math.max(x2 - x1, 8)}
                  height={22}
                  fill="var(--accent)"
                  opacity={0.35}
                  style={{ cursor: "ew-resize" }}
                  onPointerDown={(event) => {
                    event.stopPropagation();
                    dragRef.current = {
                      pointerId: event.pointerId,
                      originX: event.clientX,
                      start: effectiveView.start,
                      end: effectiveView.end,
                    };
                    (event.target as Element).setPointerCapture?.(event.pointerId);
                  }}
                />
              );
            })()}
          </g>
        )}
      </svg>
      </div>
    </div>
  );
}

export default CanonicalJourneyChart;
