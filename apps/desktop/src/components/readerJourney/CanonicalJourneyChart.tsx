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
import { formatJourneyMetricLabel, formatJourneySceneLabel, formatJourneyScore, roleLabelZh } from "./journeyUiLabels";
import { PHASE_BAND_COLORS } from "./journeyVisualTokens";
import {
  buildLinePathD,
  clampViewWindow,
  collectDataWarnings,
  computeYScale,
  resolveMetricValue,
  valenceYScaleOptions,
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
import {
  buildLensChartLines,
  getObservationLens,
  mainCurveSeries,
  pacingFitLabel,
  pacingSegmentLabel,
  valenceDirection,
  type ObservationLensId,
} from "./observationLenses";
import { resolveNodeVisualStyle } from "./journeyNodeDiagnosisStyle";
import { buildSegmentMarkers } from "./journeySegmentMarkers";
import { getScenePayoffClaim } from "./narrativeLoopView";
import { buildSceneRoleTags } from "./sceneCardRoleTags";
import { getLensExplanation } from "./readerJourneyLensExplanation";
import {
  HOOK_STRENGTH_LABEL,
  PAYOFF_NOT_CUMULATIVE_HINT,
  PAYOFF_STRENGTH_LABEL,
  getQuestionLifecycle,
  questionsForScene,
  resolveHookPayoffDataStatus,
  sceneRoleInLifecycle,
} from "./hookPayoffLensModel";

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
  /** When set, chart renders observation-lens series instead of raw metric alone. */
  observationLens?: ObservationLensId;
  overlayComposite?: boolean;
  /** Explicit secondary metric id for named compare line. */
  compareWith?: string | null;
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
  observationLens,
  overlayComposite = false,
  compareWith = null,
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
  const lensId = observationLens;
  const lensLines = useMemo(() => {
    if (!lensId) return null;
    return buildLensChartLines(visualization, lensId, {
      overlayComposite,
      compareWith,
    });
  }, [visualization, lensId, overlayComposite, compareWith]);
  const series = useMemo(
    () => lensLines?.[0]?.series ?? visualization.curve_series[metric] ?? [],
    [lensLines, visualization.curve_series, metric],
  );
  const secondarySeries = lensLines && lensLines.length > 1 ? lensLines[1].series : null;
  const lensDef = lensId ? getObservationLens(lensId) : null;

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

  const yScaleOptions = useMemo(() => {
    if (lensDef?.yDomain === "valence_signed" || metric === "valence") {
      return valenceYScaleOptions();
    }
    return undefined;
  }, [lensDef, metric]);

  const yScale = useMemo(
    () => computeYScale(series, chartHeight, effectiveYMode, yScaleOptions),
    [series, chartHeight, effectiveYMode, yScaleOptions],
  );

  const warnings = useMemo(() => {
    const warningDomain = yScaleOptions?.domainOverride
      ? { min: yScaleOptions.domainOverride.min, max: yScaleOptions.domainOverride.max }
      : { min: 0, max: 100 };
    return collectDataWarnings(series, warningDomain);
  }, [series, yScaleOptions]);

  const xFor = useCallback(
    (ordinal: number) => xForSceneOrdinal(ordinal, sceneCount, chartWidth),
    [sceneCount, chartWidth],
  );

  const mainSeries = useMemo(() => mainCurveSeries(series), [series]);
  const mainSecondary = useMemo(
    () => (secondarySeries ? mainCurveSeries(secondarySeries) : []),
    [secondarySeries],
  );

  const linePath = useMemo(
    () => buildLinePathD(mainSeries, xFor, yScale.yForValue),
    [mainSeries, xFor, yScale],
  );
  const secondaryLinePath = useMemo(
    () =>
      mainSecondary.length
        ? buildLinePathD(mainSecondary, xFor, yScale.yForValue)
        : "",
    [mainSecondary, xFor, yScale],
  );

  const segmentMarkers = useMemo(() => {
    if (!lensId) return [];
    const verifiedFullPayoffScenes = new Set<number>();
    for (const node of nodes) {
      const claim = getScenePayoffClaim(visualization, node.scene_ordinal);
      if (claim?.deterministic && claim.claim === "full") {
        verifiedFullPayoffScenes.add(node.scene_ordinal);
      }
    }
    return buildSegmentMarkers(
      nodes.map((node) => ({
        scene_ordinal: node.scene_ordinal,
        reading_momentum:
          node.scores.reading_momentum ?? node.engagement.engagement_score,
        plot_progress: node.scores.plot_progress,
        reading_tension: node.scores.reading_tension,
        hook: node.scores.hook,
        payoff: node.scores.payoff,
        pacing_speed: node.scores.pacing_speed,
        clarity: node.scores.clarity,
        information_gain: node.scores.information_gain,
        arousal:
          ((node.scores.arousal_start ?? 0) + (node.scores.arousal_end ?? 0)) / 2,
      })),
      { lensId, verifiedFullPayoffScenes },
    );
  }, [lensId, nodes, visualization]);

  const pacingSegments = useMemo(() => {
    if (lensId !== "pacing") return [];
    const ordered = [...nodes].sort((a, b) => a.scene_ordinal - b.scene_ordinal);
    const out: Array<{
      fromOrdinal: number;
      toOrdinal: number;
      label: ReturnType<typeof pacingSegmentLabel>;
    }> = [];
    for (let i = 1; i < ordered.length; i += 1) {
      const prev = ordered[i - 1];
      const curr = ordered[i];
      out.push({
        fromOrdinal: prev.scene_ordinal,
        toOrdinal: curr.scene_ordinal,
        label: pacingSegmentLabel(prev.scores.pacing_speed, curr.scores.pacing_speed),
      });
    }
    return out;
  }, [lensId, nodes]);

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
      {lensId === "hook_payoff" ? (
        <div className="journey-hook-payoff-legend" data-testid="journey-hook-payoff-legend">
          <div className="journey-hook-payoff-legend-rows">
            <span className="journey-hook-payoff-legend-item" data-testid="journey-legend-hook">
              <span className="journey-legend-swatch journey-legend-swatch-hook" aria-hidden="true" />
              绿色实线：{HOOK_STRENGTH_LABEL}
            </span>
            <span className="journey-hook-payoff-legend-item" data-testid="journey-legend-payoff">
              <span
                className="journey-legend-swatch journey-legend-swatch-payoff"
                aria-hidden="true"
              />
              紫色虚线：{PAYOFF_STRENGTH_LABEL}
            </span>
          </div>
          <p className="journey-hook-payoff-legend-hint" data-testid="journey-hook-payoff-legend-hint">
            {PAYOFF_NOT_CUMULATIVE_HINT}
          </p>
        </div>
      ) : null}
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
            const semantic =
              lensId === "composite"
                ? tick >= 75
                  ? "强"
                  : tick <= 25
                    ? "弱"
                    : tick === 50
                      ? "中"
                      : null
                : null;
            const label =
              lensId === "composite" && semantic
                ? semantic
                : String(tick);
            return (
              <g
                key={`y-tick-${tick}`}
                data-testid={exportFullJourney ? undefined : `journey-y-tick-${tick}`}
                data-y-semantic={semantic || undefined}
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
                  {label}
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
              data-line-id={lensLines?.[0]?.id ?? metric}
            />
          )}
          {secondaryLinePath ? (
            <path
              d={secondaryLinePath}
              fill="none"
              stroke="var(--journey-secondary-line, #ae3ec9)"
              strokeWidth={2}
              strokeDasharray="6 4"
              data-testid="journey-curve-path-secondary"
              data-line-id={lensLines?.[1]?.id ?? "secondary"}
              data-line-label={lensLines?.[1]?.labelZh ?? ""}
            />
          ) : null}
          {lensLines && lensLines.length > 1 ? (
            <g data-testid="journey-compare-legend" aria-label="对比图例">
              <text x={padLeft} y={padTop - 8} className="journey-compare-legend-text" fontSize={11} fill="var(--muted)">
                {`实线：${lensLines[0]?.labelZh || "当前指标"}  虚线：${lensLines[1]?.labelZh || "对比指标"}`}
              </text>
            </g>
          ) : null}
          {segmentMarkers.map((marker) => {
            const x1 = xFor(marker.fromOrdinal);
            const x2 = xFor(marker.toOrdinal);
            const midX = (x1 + x2) / 2;
            return (
              <text
                key={`seg-${marker.fromOrdinal}-${marker.toOrdinal}-${marker.label}`}
                x={midX}
                y={padTop + 12}
                textAnchor="middle"
                className="journey-segment-marker"
                data-testid={`journey-segment-marker-${marker.toOrdinal}`}
                data-direction={marker.direction}
                fontSize={10}
                fill="var(--muted)"
              >
                {marker.label}
              </text>
            );
          })}
          {pacingSegments.map((seg) => {
            const x1 = xFor(seg.fromOrdinal);
            const x2 = xFor(seg.toOrdinal);
            const midX = (x1 + x2) / 2;
            return (
              <text
                key={`pace-seg-${seg.fromOrdinal}-${seg.toOrdinal}`}
                x={midX}
                y={padTop + plotHeight - 4}
                textAnchor="middle"
                className="journey-pacing-segment-label"
                data-testid={`journey-pacing-segment-${seg.toOrdinal}`}
                data-pacing-segment={seg.label}
                fontSize={9}
                fill="var(--muted)"
              >
                {seg.label}
              </text>
            );
          })}
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
            const isBeat =
              node.role === "beat" ||
              node.node_type === "beat" ||
              node.include_in_main_curve === false;
            const visual = resolveNodeVisualStyle({
              primaryDiagnosis: node.primary_diagnosis,
              secondaryDiagnoses: node.secondary_diagnoses,
              isBeat,
              confidence: node.confidence,
              dataQualityIssue: node.data_quality_issue,
            });
            const radius = isBeat ? 2.5 : NODE_RADIUS[node.role] ?? 4;
            const selected = selectedSceneOrdinal === node.scene_ordinal;
            const tier = hookTier(visualization, node.scene_ordinal, sceneCount);
            const hookSize = tier === "chapter" ? 7 : tier === "phase" ? 5.5 : 4;
            const valenceDir =
              lensId === "emotion" ? valenceDirection(node) : null;
            const pacingLabel =
              lensId === "pacing"
                ? pacingFitLabel(
                    node.scores.pacing_speed ?? value,
                    node.scene_role,
                    node.scores.pacing_fit,
                  )
                : null;
            const stroke = visual.colorToken;
            const fill =
              visual.shape === "hollow_circle" || visual.shape === "triangle" || visual.shape === "diamond"
                ? "var(--surface)"
                : visual.colorToken;
            return (
              <g
                key={node.scene_ordinal}
                data-testid={
                  exportFullJourney ? undefined : `journey-curve-node-${node.scene_ordinal}`
                }
                data-node-hit="true"
                data-score={String(value)}
                data-node-type={isBeat ? "beat" : "scene"}
                data-include-in-main-curve={isBeat ? "false" : "true"}
                data-node-shape={visual.shape}
                className={`journey-curve-node ${ROLE_CLASS[node.role] ?? ""} ${
                  visual.cssClass
                } ${selected ? "selected journey-node-active" : ""}`}
                data-hook-tier={hookOrdinals.has(node.scene_ordinal) ? tier : undefined}
                onMouseEnter={() => setHover({ ordinal: node.scene_ordinal, x: cx, y: cy })}
                onMouseLeave={() => setHover(null)}
                onClick={() => onSelectScene(node)}
                style={{ cursor: "pointer" }}
              >
                <rect x={cx - 14} y={cy - 14} width={28} height={28} fill="transparent" />
                {visual.shape === "square_dot" ? (
                  <rect
                    x={cx - radius}
                    y={cy - radius}
                    width={radius * 2}
                    height={radius * 2}
                    fill={fill}
                    stroke={stroke}
                    strokeWidth={1}
                    data-testid={
                      exportFullJourney
                        ? undefined
                        : `journey-beat-aux-node-${node.scene_ordinal}`
                    }
                  />
                ) : visual.shape === "triangle" ? (
                  <polygon
                    points={`${cx},${cy - radius - 1} ${cx - radius - 1},${cy + radius} ${cx + radius + 1},${cy + radius}`}
                    fill={fill}
                    stroke={stroke}
                    strokeWidth={selected ? 2.5 : 1.5}
                  />
                ) : visual.shape === "diamond" ? (
                  <polygon
                    points={`${cx},${cy - radius - 2} ${cx + radius + 1},${cy} ${cx},${cy + radius + 2} ${cx - radius - 1},${cy}`}
                    fill={fill}
                    stroke={stroke}
                    strokeWidth={selected ? 2.5 : 1.5}
                  />
                ) : (
                  <circle
                    cx={cx}
                    cy={cy}
                    r={radius + (selected ? 3 : 0)}
                    fill={fill}
                    stroke={stroke}
                    strokeWidth={selected ? 3 : 1.5}
                  />
                )}
                {valenceDir && valenceDir !== "flat" ? (
                  <text
                    x={cx}
                    y={cy - radius - 6}
                    textAnchor="middle"
                    fontSize={9}
                    fill="var(--muted)"
                    data-testid={`journey-valence-dir-${node.scene_ordinal}`}
                  >
                    {valenceDir === "up" ? "↑" : "↓"}
                  </text>
                ) : null}
                {pacingLabel ? (
                  <text
                    x={cx}
                    y={cy + radius + 11}
                    textAnchor="middle"
                    fontSize={9}
                    fill="var(--muted)"
                    data-testid={`journey-pacing-fit-${node.scene_ordinal}`}
                  >
                    {pacingLabel}
                  </text>
                ) : null}
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
              x={Math.min(Math.max(hover.x - 90, 4), chartWidth - 220)}
              y={Math.max(hover.y - (lensId === "hook_payoff" ? 160 : 110), 4)}
              width={lensId === "hook_payoff" ? 220 : 196}
              height={lensId === "hook_payoff" ? 168 : 128}
              data-testid="journey-node-tooltip"
            >
              <div
                className="journey-node-tooltip-card"
                {...({ xmlns: "http://www.w3.org/1999/xhtml" } as Record<string, string>)}
              >
                {lensId === "hook_payoff" ? (
                  (() => {
                    const hookVal = tooltipNode.scores.hook;
                    const payoffVal = tooltipNode.scores.payoff;
                    const life = questionsForScene(
                      getQuestionLifecycle(visualization),
                      tooltipNode.scene_ordinal,
                    );
                    const primaryQ = life[0];
                    const dataStatus = resolveHookPayoffDataStatus(visualization, tooltipNode);
                    return (
                      <>
                        <div>
                          {formatJourneySceneLabel(tooltipNode.scene_ordinal)}
                          {tooltipNode.scene_value_summary
                            ? ` · ${tooltipNode.scene_value_summary.slice(0, 24)}`
                            : ""}
                        </div>
                        <div>
                          {HOOK_STRENGTH_LABEL}：
                          {hookVal == null ? "数据不足" : formatJourneyScore(hookVal)}
                        </div>
                        <div>
                          {PAYOFF_STRENGTH_LABEL}：
                          {payoffVal == null ? "数据不足" : formatJourneyScore(payoffVal)}
                        </div>
                        <div>
                          生命周期：
                          {primaryQ
                            ? `${primaryQ.status} · ${sceneRoleInLifecycle(primaryQ, tooltipNode.scene_ordinal)}`
                            : "未关联"}
                        </div>
                        <div>关联问题：{life.length}</div>
                        {primaryQ ? (
                          <div>主要问题：{primaryQ.question_text.slice(0, 36)}</div>
                        ) : null}
                        <div>
                          confidence：
                          {tooltipNode.confidence != null
                            ? tooltipNode.confidence.toFixed(2)
                            : "—"}
                        </div>
                        <div>数据状态：{dataStatus}</div>
                      </>
                    );
                  })()
                ) : (
                  (() => {
                    const lensExpl = getLensExplanation(lensId);
                    const scoreNoun =
                      lensId === "composite"
                        ? lensExpl.chart_title || "综合阅读动力"
                        : lensExpl.title || formatJourneyMetricLabel(metric);
                    const roles = buildSceneRoleTags(visualization, tooltipNode.scene_ordinal);
                    const roleText = roles.map((r) => r.label).join(" · ") || "无特定叙事作用标签";
                    const reason =
                      roles[0]?.title ||
                      tooltipNode.scene_value_summary ||
                      lensExpl.caution;
                    return (
                      <>
                        <div>
                          {formatJourneySceneLabel(tooltipNode.scene_ordinal)}
                          {tooltipNode.role ? ` · ${roleLabelZh(tooltipNode.role)}` : ""}
                        </div>
                        <div>
                          {scoreNoun}：{formatJourneyScore(tooltipScore)}
                        </div>
                        <div>
                          节点类型：
                          {tooltipNode.node_type === "beat" || tooltipNode.role === "beat"
                            ? "节拍"
                            : "场景"}
                        </div>
                        <div>叙事作用：{roleText}</div>
                        <div>主要原因：{String(reason).slice(0, 48)}</div>
                      </>
                    );
                  })()
                )}
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
