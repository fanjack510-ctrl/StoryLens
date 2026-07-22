import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import { useSearchParams } from "react-router-dom";
import type {
  JourneyCurveMetric,
  JourneySceneNode,
  ReaderJourneyVisualization,
} from "../../types/readerJourneyVisualization";
import type { JourneySelectionSource } from "../../types/journeySelection";
import { CanonicalJourneyChart } from "./CanonicalJourneyChart";
import { exportJourneyPng, JourneyExportError } from "./exportJourneyPng";
import { JourneyChartToolbar } from "./JourneyChartToolbar";
import { JourneyDiagnosisBand } from "./JourneyDiagnosisBand";
import { JourneyDetailErrorBoundary } from "./JourneyDetailErrorBoundary";
import {
  clampViewWindow,
  focusPhaseWindow,
  resolveMetricValue,
  zoomViewWindow,
} from "./journeyChartScales";
import { buildChapterSummaryBullets } from "./journeyChapterSummary";
import {
  buildHookPayoffChapterBullets,
  buildHookPayoffSceneSummary,
  formatHookPayoffSceneCaption,
  isHookPayoffLens,
  phaseHookPayoffAverages,
} from "./hookPayoffLensModel";
import {
  DEFAULT_OBSERVATION_LENS,
  V2_LOCAL_FIXTURE_BANNER,
  V2_NATIVE_REAL_BANNER,
  getObservationLens,
  isLegacyUncalibratedVisualization,
  resolveJourneyTopBanner,
  type ObservationLensId,
} from "./observationLenses";
import {
  formatLensBindingCaption,
  formatLensPhaseScoreLabel,
  phaseAverageForLens,
  resolveLensMetricBinding,
} from "./lensMetricBinding";
import type { SceneDiagnosisLike } from "./diagnosisBandModel";
import {
  applyJourneySelectionIntent,
  logJourneySelectionTransaction,
  nextJourneyTransactionId,
  type JourneySelectionIntent,
} from "./journeySelectionTransaction";
import {
  JourneyMarkerInspectorPanel,
  JourneyPhaseDetailPanel,
  JourneyQuestionInspectorPanel,
  JourneySceneDetailPanel,
} from "./JourneySceneDetailPanel";
import { roleLabelZh, formatJourneyPhaseLabel, resolvePhaseSummaryDisplay, formatJourneySceneLabel } from "./journeyUiLabels";
import {
  CANONICAL_OVERVIEW_MODE,
  OVERVIEW_MODE_PARAM,
  isLegacyOverviewMode,
  normalizeOverviewModeParam,
  parseInspectorType,
  parseOverviewMode,
  type JourneyInspectorType,
} from "./overviewMode";
import {
  CHART_SHELL_MIN_HEIGHT_PX,
  JOURNEY_VISUALIZATION_VERSION,
  LAYOUT_BREAKPOINTS,
  LAYOUT_TOKENS,
  SCENE_DENSITY,
  UI_PREF_KEYS,
  URL_CHART_PARAMS,
  allowsHorizontalPanZoom,
  chartHeightPx,
  defaultViewWindow,
  plotAreaHeightPx,
  readChartHeightPreset,
  readLocalPref,
  readYDomainMode,
  requiresBrush,
  resolveJourneyLayoutMode,
  showsZoomControls,
  writeChartHeightPreset,
  writeLocalPref,
  writeYDomainMode,
  type ChartHeightPreset,
  type JourneyLayoutMode,
  type YDomainMode,
} from "./journeyVisualizationConfig";
import {
  INSPECTOR_DOCK_HEIGHT_RANGE,
  INSPECTOR_PANE_WIDTH_RANGE,
  MAIN_PANE_MIN_WIDTH_PX,
  SOURCE_PANE_WIDTH_RANGE,
  SPLITTER_WIDTH_PX,
  clampPreferredToRange,
  effectiveDockHeight,
  effectivePaneWidth,
  maxSidePaneWidth,
  sanitizePreferredWidth,
} from "./journeyPaneWidth";
import { JourneyPaneSplitter } from "./JourneyPaneSplitter";
import { PHASE_BAND_COLORS } from "./journeyVisualTokens";
import "./readerJourney.css";

const phaseColors = PHASE_BAND_COLORS;

function exportErrorMessage(error: unknown): string {
  if (
    typeof error === "object" &&
    error !== null &&
    "userMessage" in error &&
    typeof (error as { userMessage: unknown }).userMessage === "string"
  ) {
    return (error as { userMessage: string }).userMessage;
  }
  return "导出过程中发生未知错误";
}

const ROLE_CLASS: Record<string, string> = {
  core: "journey-node-core",
  secondary: "journey-node-secondary",
  beat: "journey-node-beat",
};

export type JourneySelectionChangePatch = Partial<{
  activeSceneOrdinal: number | null;
  activePhaseOrdinal: number | null;
  selectedMetric: JourneyCurveMetric;
  selectedQuestionClusterId: string | null;
  evidenceParagraphIds: string[];
  source: JourneySelectionSource;
}>;

type Props = {
  visualization: ReaderJourneyVisualization;
  chapterTitle?: string;
  onLocateEvidence: (paragraphId: string) => void;
  onSelectScene?: (sceneId: number) => void;
  activeSceneOrdinal?: number | null;
  activePhaseOrdinal?: number | null;
  selectedMetric?: JourneyCurveMetric;
  selectedQuestionClusterId?: string | null;
  onSelectionChange?: (patch: JourneySelectionChangePatch) => void;
  compactHead?: boolean;
  /** Optional presentation labels for 分析信息 (no new runs). */
  analysisRunId?: number | null;
  journeyRunId?: number | null;
  /** Optional SourcePane (正文) for three-column workspace grid. */
  sourcePane?: ReactNode;
  sourceCollapsed?: boolean;
  onSourceCollapsedChange?: (collapsed: boolean) => void;
};

function riskIntervalLabel(interval: {
  start_scene_ordinal: number;
  end_scene_ordinal: number;
  span?: number;
}): string {
  return `Scene ${interval.start_scene_ordinal}—${interval.end_scene_ordinal} (span ${interval.span ?? interval.end_scene_ordinal - interval.start_scene_ordinal + 1})`;
}

function weakIntervalDisplay(summary: {
  max_low_payoff_interval?:
    | string
    | {
        start_scene_ordinal?: number;
        end_scene_ordinal?: number;
        span?: number;
      }
    | null;
  weak_interval?: string | null;
}): string {
  const interval = summary.max_low_payoff_interval;
  if (typeof interval === "string" && interval.trim()) {
    return interval;
  }
  if (
    interval &&
    typeof interval === "object" &&
    interval.start_scene_ordinal != null &&
    interval.end_scene_ordinal != null
  ) {
    return riskIntervalLabel({
      start_scene_ordinal: interval.start_scene_ordinal,
      end_scene_ordinal: interval.end_scene_ordinal,
      span: interval.span,
    }).replace(/ \(span.*\)$/, "");
  }
  return summary.weak_interval || "—";
}

export function ReaderJourneyWorkspace({
  visualization,
  chapterTitle,
  onLocateEvidence,
  onSelectScene,
  activeSceneOrdinal: controlledSceneOrdinal,
  activePhaseOrdinal: controlledPhaseOrdinal,
  selectedMetric: controlledMetric,
  selectedQuestionClusterId: controlledClusterId,
  onSelectionChange,
  compactHead = false,
  analysisRunId: analysisRunIdProp,
  journeyRunId: journeyRunIdProp,
  sourcePane,
  sourceCollapsed: sourceCollapsedProp,
}: Props) {
  const workspaceRef = useRef<HTMLDivElement>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const overviewMode = parseOverviewMode(searchParams.get("overview"));
  const [markerMode, setMarkerMode] = useState<"compact" | "full">("compact");
  const [selectedPhaseInternal, setSelectedPhaseInternal] = useState<number | null>(null);
  const [selectedSceneOrdinalInternal, setSelectedSceneOrdinalInternal] = useState<number | null>(
    null,
  );
  const [metricInternal, setMetricInternal] = useState<JourneyCurveMetric>("engagement");
  const [observationLens, setObservationLens] =
    useState<ObservationLensId>(DEFAULT_OBSERVATION_LENS);
  const [overlayComposite, setOverlayComposite] = useState(false);
  const [analysisInfoOpen, setAnalysisInfoOpen] = useState(false);
  const [exportStatus, setExportStatus] = useState<"idle" | "exporting" | "succeeded" | "failed">(
    "idle",
  );
  const [exportMessage, setExportMessage] = useState<string | null>(null);
  const [selectedRiskKey, setSelectedRiskKey] = useState<string | null>(null);
  const exportRootRef = useRef<HTMLDivElement>(null);
  const exportFullRootRef = useRef<HTMLDivElement>(null);
  const [heightPreset, setHeightPreset] = useState<ChartHeightPreset>(() => readChartHeightPreset());
  const [yDomainMode, setYDomainMode] = useState<YDomainMode>(() => readYDomainMode());
  /** Inspector dock collapsed by default so the curve is the page hero. */
  const [inspectorCollapsed, setInspectorCollapsed] = useState(() =>
    readLocalPref<boolean>(UI_PREF_KEYS.inspectorCollapsed, true),
  );
  const [sourceCollapsedInternal] = useState(() =>
    readLocalPref<boolean>(UI_PREF_KEYS.sourceCollapsed, false),
  );
  const [insightExpanded, setInsightExpanded] = useState(() =>
    readLocalPref<boolean>(UI_PREF_KEYS.insightStripExpanded, false),
  );
  const [preferredSourceWidth, setPreferredSourceWidth] = useState(() =>
    sanitizePreferredWidth(
      readLocalPref<number>(UI_PREF_KEYS.sourcePaneWidth, SOURCE_PANE_WIDTH_RANGE.default),
      SOURCE_PANE_WIDTH_RANGE,
    ),
  );
  const [preferredInspectorWidth, setPreferredInspectorWidth] = useState(() =>
    sanitizePreferredWidth(
      readLocalPref<number>(UI_PREF_KEYS.inspectorPaneWidth, INSPECTOR_PANE_WIDTH_RANGE.default),
      INSPECTOR_PANE_WIDTH_RANGE,
    ),
  );
  const [preferredDockHeight, setPreferredDockHeight] = useState(() =>
    sanitizePreferredWidth(
      readLocalPref<number>(
        UI_PREF_KEYS.inspectorDockHeight,
        INSPECTOR_DOCK_HEIGHT_RANGE.default,
      ),
      INSPECTOR_DOCK_HEIGHT_RANGE,
    ),
  );
  const [workspaceWidth, setWorkspaceWidth] = useState(
    typeof window !== "undefined" ? window.innerWidth : LAYOUT_BREAKPOINTS.desktopMin,
  );
  const [workspaceHeight, setWorkspaceHeight] = useState(
    typeof window !== "undefined" ? window.innerHeight : 900,
  );
  const [paneResizing, setPaneResizing] = useState(false);
  const [layoutMode, setLayoutMode] = useState<JourneyLayoutMode>("desktop");
  const [narrowPane, setNarrowPane] = useState<"source" | "main" | "inspector">("main");
  const didAutoExpandInspector = useRef(false);
  const sourceCollapsed = sourceCollapsedProp ?? sourceCollapsedInternal;
  const hasSourcePane = sourcePane != null;

  /** Legacy overview=questions|diagnosis → curve (replace; keep other params). */
  useEffect(() => {
    const raw = searchParams.get(OVERVIEW_MODE_PARAM);
    if (!isLegacyOverviewMode(raw)) return;
    setSearchParams((prev) => normalizeOverviewModeParam(prev), { replace: true });
  }, [searchParams, setSearchParams]);

  /** Authoritative final URL write for one user action (wins over stale syncUrl snapshots). */
  const commitSelectionIntent = (intent: JourneySelectionIntent) => {
    const transactionId = nextJourneyTransactionId();
    setSearchParams(
      (prev) => {
        const previousSearch = prev.toString();
        const next = applyJourneySelectionIntent(prev, intent);
        logJourneySelectionTransaction({
          transactionId,
          source: intent.source,
          previousSearch,
          nextSearch: next.toString(),
        });
        return next;
      },
      { replace: true },
    );
  };

  const clearInspectorParam = () => {
    commitSelectionIntent({ source: "clear-inspector", inspector: null });
  };

  const inspectorFromUrl = parseInspectorType(searchParams.get("inspector"));
  void overviewMode;

  /** Deep-link / controlled selection: open Inspector once so detail is reachable. */
  useEffect(() => {
    if (didAutoExpandInspector.current) return;
    if (
      inspectorFromUrl ||
      searchParams.get("scene") ||
      controlledSceneOrdinal != null
    ) {
      didAutoExpandInspector.current = true;
      setInspectorCollapsed(false);
    }
  }, [inspectorFromUrl, searchParams, controlledSceneOrdinal]);

  useEffect(() => {
    const node = workspaceRef.current;
    if (!node || typeof ResizeObserver === "undefined") {
      const fallback =
        typeof window !== "undefined" ? window.innerWidth : LAYOUT_BREAKPOINTS.desktopMin;
      setWorkspaceWidth(fallback);
      setLayoutMode(resolveJourneyLayoutMode(fallback));
      return;
    }
    const update = () => {
      const rect = node.getBoundingClientRect();
      const measured = rect.width;
      const isJsdom =
        typeof navigator !== "undefined" && /jsdom/i.test(navigator.userAgent || "");
      // Pane widths use host width; layout mode uses viewport so 1440px gets right Inspector.
      const hostWidth =
        measured >= 200
          ? measured
          : isJsdom
            ? LAYOUT_BREAKPOINTS.desktopMin
            : typeof window !== "undefined"
              ? window.innerWidth
              : LAYOUT_BREAKPOINTS.desktopMin;
      const layoutWidth =
        typeof window !== "undefined" && !isJsdom
          ? window.innerWidth
          : hostWidth;
      setWorkspaceWidth(hostWidth);
      setWorkspaceHeight(
        rect.height > 0
          ? rect.height
          : typeof window !== "undefined"
            ? window.innerHeight
            : 900,
      );
      setLayoutMode(resolveJourneyLayoutMode(layoutWidth));
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(node);
    const onResize = () => update();
    window.addEventListener("resize", onResize);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", onResize);
    };
  }, []);

  useEffect(() => {
    if (layoutMode === "narrow" && !inspectorCollapsed) {
      setNarrowPane("inspector");
    }
  }, [layoutMode, inspectorCollapsed]);

  const persistSourceWidth = useCallback((next: number) => {
    const clamped = clampPreferredToRange(next, SOURCE_PANE_WIDTH_RANGE);
    setPreferredSourceWidth(clamped);
    writeLocalPref(UI_PREF_KEYS.sourcePaneWidth, clamped);
  }, []);

  const persistInspectorWidth = useCallback((next: number) => {
    const clamped = clampPreferredToRange(next, INSPECTOR_PANE_WIDTH_RANGE);
    setPreferredInspectorWidth(clamped);
    writeLocalPref(UI_PREF_KEYS.inspectorPaneWidth, clamped);
  }, []);

  const persistDockHeight = useCallback((next: number) => {
    const clamped = clampPreferredToRange(next, INSPECTOR_DOCK_HEIGHT_RANGE);
    setPreferredDockHeight(clamped);
    writeLocalPref(UI_PREF_KEYS.inspectorDockHeight, clamped);
  }, []);

  const resetPaneWidths = useCallback(() => {
    persistSourceWidth(SOURCE_PANE_WIDTH_RANGE.default);
    persistInspectorWidth(INSPECTOR_PANE_WIDTH_RANGE.default);
    persistDockHeight(INSPECTOR_DOCK_HEIGHT_RANGE.default);
  }, [persistDockHeight, persistInspectorWidth, persistSourceWidth]);
  const isControlled = controlledSceneOrdinal !== undefined;
  const selectedSceneOrdinal = isControlled
    ? (controlledSceneOrdinal ?? null)
    : selectedSceneOrdinalInternal;
  const selectedPhase =
    controlledPhaseOrdinal !== undefined ? controlledPhaseOrdinal : selectedPhaseInternal;
  const metric = controlledMetric ?? metricInternal;
  const lensDef = getObservationLens(observationLens);
  const topBanner = resolveJourneyTopBanner(visualization);
  const isV2LocalFixtureBanner = topBanner === V2_LOCAL_FIXTURE_BANNER;
  const isV2NativeRealBanner = topBanner === V2_NATIVE_REAL_BANNER;
  const sceneDiagnoses: SceneDiagnosisLike[] = useMemo(
    () =>
      visualization.scene_nodes.map((node) => ({
        scene_ordinal: node.scene_ordinal,
        primary_diagnosis: node.primary_diagnosis,
        secondary_diagnoses: node.secondary_diagnoses,
        positive_mechanism: node.positive_mechanism,
        data_quality_issue: node.data_quality_issue,
        reading_momentum:
          node.scores?.reading_momentum ?? node.engagement?.engagement_score,
        plot_progress: node.scores?.plot_progress,
        role: node.role,
        node_type: node.node_type,
        include_in_main_curve: node.include_in_main_curve,
        legacyUncalibrated: isLegacyUncalibratedVisualization(visualization),
        insufficientData:
          node.confidence != null && node.confidence < 0.45
            ? true
            : !node.primary_diagnosis &&
              node.scores?.reading_momentum == null &&
              node.engagement?.engagement_score == null,
      })),
    [visualization],
  );
  const chapterSummaryBullets = useMemo(() => {
    if (isHookPayoffLens(observationLens)) {
      return buildHookPayoffChapterBullets(visualization);
    }
    return buildChapterSummaryBullets(visualization, sceneDiagnoses);
  }, [visualization, sceneDiagnoses, observationLens]);

  const expandedClusterId = controlledClusterId ?? null;

  const summary = visualization.chapter_summary;
  const nodes = visualization.scene_nodes;
  const sceneCount = nodes.length;
  const selectedNode: JourneySceneNode | undefined = useMemo(
    () => nodes.find((node) => node.scene_ordinal === selectedSceneOrdinal),
    [nodes, selectedSceneOrdinal],
  );

  const phaseStripRef = useRef<HTMLDivElement>(null);
  const chartHeight = chartHeightPx(heightPreset);
  const series = useMemo(
    () => visualization.curve_series[metric] ?? [],
    [visualization.curve_series, metric],
  );

  const initialView = defaultViewWindow(sceneCount);
  const urlXStart = Number(searchParams.get(URL_CHART_PARAMS.xStart));
  const urlXEnd = Number(searchParams.get(URL_CHART_PARAMS.xEnd));
  const [viewWindow, setViewWindow] = useState(() => {
    if (Number.isFinite(urlXStart) && Number.isFinite(urlXEnd)) {
      return clampViewWindow(
        urlXStart,
        urlXEnd,
        sceneCount,
        requiresBrush(sceneCount) ? SCENE_DENSITY.brushMinVisibleScenes : 2,
      );
    }
    return initialView;
  });

  useEffect(() => {
    setViewWindow(defaultViewWindow(sceneCount));
  }, [sceneCount]);

  const syncViewToUrl = useCallback(
    (start: number, end: number) => {
      const next = clampViewWindow(
        start,
        end,
        sceneCount,
        requiresBrush(sceneCount) ? SCENE_DENSITY.brushMinVisibleScenes : 2,
      );
      setViewWindow(next);
      setSearchParams(
        (prev) => {
          const params = new URLSearchParams(prev);
          if (next.start === 1 && next.end === sceneCount) {
            params.delete(URL_CHART_PARAMS.xStart);
            params.delete(URL_CHART_PARAMS.xEnd);
          } else {
            params.set(URL_CHART_PARAMS.xStart, String(next.start));
            params.set(URL_CHART_PARAMS.xEnd, String(next.end));
          }
          return params;
        },
        { replace: true },
      );
    },
    [sceneCount, setSearchParams],
  );

  const handleHeightPresetChange = (preset: ChartHeightPreset) => {
    setHeightPreset(preset);
    writeChartHeightPreset(preset);
  };

  const handleYDomainModeChange = (mode: YDomainMode) => {
    setYDomainMode(mode);
    writeYDomainMode(mode);
  };

  const setInspectorCollapsedPref = (collapsed: boolean) => {
    setInspectorCollapsed(collapsed);
    writeLocalPref(UI_PREF_KEYS.inspectorCollapsed, collapsed);
    if (!collapsed && layoutMode === "narrow") {
      setNarrowPane("inspector");
    }
  };

  const handleToggleInspector = () => {
    if (!inspectorCollapsed && layoutMode === "narrow") {
      setInspectorCollapsed(true);
      writeLocalPref(UI_PREF_KEYS.inspectorCollapsed, true);
      setNarrowPane("main");
      return;
    }
    setInspectorCollapsedPref(!inspectorCollapsed);
  };

  const expandInspector = () => setInspectorCollapsedPref(false);

  /** Narrow drawer is open only when the inspector tab is active and not collapsed. */
  const narrowDrawerOpen =
    layoutMode === "narrow" && !inspectorCollapsed && narrowPane === "inspector";
  /** Detail panel is actually on-screen (desktop right / mid dock / narrow drawer). */
  const detailVisible =
    (layoutMode === "desktop" && !inspectorCollapsed) ||
    (layoutMode === "mid" && !inspectorCollapsed) ||
    narrowDrawerOpen;

  const handleSelectScene = (node: JourneySceneNode, source: JourneySelectionSource = "journey_scene") => {
    if (!isControlled) {
      setSelectedSceneOrdinalInternal(node.scene_ordinal);
    }
    if (controlledPhaseOrdinal === undefined && node.phase_ordinal != null) {
      setSelectedPhaseInternal(node.phase_ordinal);
    }
    onSelectionChange?.({
      activeSceneOrdinal: node.scene_ordinal,
      activePhaseOrdinal: node.phase_ordinal ?? undefined,
      source,
    });
    // Parent SyncWorkspace already applies selection via onSelectionChange; skip onSelectScene
    // to avoid a second syncUrl with a possibly mismatched visualization scene_id.
    if (!onSelectionChange) {
      onSelectScene?.(node.scene_id);
    }
    commitSelectionIntent({
      source: source === "journey_rhythm" ? "rhythm" : "curve",
      inspector: "scene",
      sceneOrdinal: node.scene_ordinal,
      phaseId: node.phase_ordinal,
      paragraphId: node.paragraph_range?.start_paragraph_id ?? null,
      clearCluster: true,
    });
    expandInspector();
  };

  const handleSelectPhase = (phaseOrdinal: number) => {
    const phase = visualization.phases.find((item) => item.ordinal === phaseOrdinal);
    if (!phase) return;
    if (controlledPhaseOrdinal === undefined) {
      setSelectedPhaseInternal(phaseOrdinal);
    }
    // Update activePhase only — do not replace the current Scene selection.
    onSelectionChange?.({
      activePhaseOrdinal: phaseOrdinal,
      source: "journey_phase",
    });
    commitSelectionIntent({
      source: "phase-strip",
      inspector: "phase",
      phaseId: phaseOrdinal,
      preserveScene: true,
    });
    expandInspector();
  };

  /** Mid-width: keep the active phase card scrolled into the strip viewport (strip-only). */
  useEffect(() => {
    if (selectedPhase == null) return;
    const strip = phaseStripRef.current;
    if (!strip) return;
    const card = strip.querySelector<HTMLElement>(`[data-testid="journey-phase-${selectedPhase}"]`);
    if (!card) return;
    const cardLeft = card.offsetLeft;
    const cardRight = cardLeft + card.offsetWidth;
    const viewLeft = strip.scrollLeft;
    const viewRight = viewLeft + strip.clientWidth;
    if (cardLeft < viewLeft) {
      strip.scrollTo({ left: cardLeft, behavior: "smooth" });
    } else if (cardRight > viewRight) {
      strip.scrollTo({ left: Math.max(0, cardRight - strip.clientWidth), behavior: "smooth" });
    }
  }, [selectedPhase]);

  const primaryCluster = useMemo(() => {
    const clusters =
      (visualization.visible_question_clusters?.length
        ? visualization.visible_question_clusters
        : visualization.question_clusters) ?? [];
    return clusters[0] ?? null;
  }, [visualization.question_clusters, visualization.visible_question_clusters]);

  const peakOrdinal = summary.peaks.engagement_peak.scene_ordinal;
  const valleyOrdinal = summary.peaks.engagement_valley.scene_ordinal;
  const strongestHook = summary.strongest_hook;
  const tractionClickable = Boolean(primaryCluster?.cluster_id);
  const hookClickable = Boolean(strongestHook && strongestHook.scene_ordinal != null);

  const handleInsightTraction = () => {
    if (!primaryCluster?.cluster_id) return;
    onSelectionChange?.({
      selectedQuestionClusterId: primaryCluster.cluster_id,
      source: "journey_cluster",
    });
    commitSelectionIntent({
      source: "question-cluster",
      inspector: "question",
      clusterId: primaryCluster.cluster_id,
    });
    expandInspector();
  };

  const handleInsightPeak = () => {
    const node = nodes.find((item) => item.scene_ordinal === peakOrdinal);
    if (node) handleSelectScene(node, "journey_scene");
  };

  const handleInsightValley = () => {
    const node = nodes.find((item) => item.scene_ordinal === valleyOrdinal);
    if (node) handleSelectScene(node, "journey_scene");
  };

  const handleInsightHook = () => {
    if (!strongestHook?.scene_ordinal) return;
    const node = nodes.find((item) => item.scene_ordinal === strongestHook.scene_ordinal);
    if (!node) return;
    if (!isControlled) {
      setSelectedSceneOrdinalInternal(node.scene_ordinal);
    }
    onSelectionChange?.({
      activeSceneOrdinal: node.scene_ordinal,
      activePhaseOrdinal: node.phase_ordinal ?? undefined,
      source: "journey_scene",
    });
    const evidenceId = strongestHook.evidence_paragraph_ids?.[0];
    commitSelectionIntent({
      source: "hook",
      inspector: "hook",
      sceneOrdinal: node.scene_ordinal,
      phaseId: node.phase_ordinal,
      paragraphId: evidenceId ?? undefined,
    });
    expandInspector();
  };

  const handleMetricChange = (key: JourneyCurveMetric) => {
    if (controlledMetric === undefined) {
      setMetricInternal(key);
    }
    onSelectionChange?.({ selectedMetric: key, source: "journey_rhythm" });
  };

  const handleObservationLensChange = (lens: ObservationLensId) => {
    setObservationLens(lens);
    if (lens === "hook_payoff") setOverlayComposite(false);
  };

  const handleLocateEvidence = (paragraphId: string, node?: JourneySceneNode) => {
    onLocateEvidence(paragraphId);
    const sceneOrdinal = node?.scene_ordinal ?? selectedSceneOrdinal;
    onSelectionChange?.({
      evidenceParagraphIds: [paragraphId],
      activeSceneOrdinal: sceneOrdinal,
      source: "journey_evidence",
    });
    if (sceneOrdinal != null) {
      commitSelectionIntent({
        source: "journey_evidence",
        preserveInspector: true,
        sceneOrdinal,
        paragraphId,
      });
    }
  };

  useEffect(() => {
    if (exportStatus !== "succeeded" && exportStatus !== "failed") return;
    const timer = window.setTimeout(() => {
      setExportStatus("idle");
      setExportMessage(null);
    }, 2500);
    return () => window.clearTimeout(timer);
  }, [exportStatus]);

  const waitForJourneyRender = async () => {
    await new Promise<void>((resolve) => {
      requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
    });
    const deadline = performance.now() + 2000;
    while (performance.now() < deadline) {
      const root = exportRootRef.current;
      const svg = root?.querySelector('[data-testid="journey-curve-svg"]');
      if (root?.isConnected && svg instanceof SVGElement) {
        const box = svg.getBoundingClientRect();
        // Real browsers: wait until chart has a box. jsdom often reports 0×0 — SVG presence is enough.
        if (box.width > 0 && box.height > 0) return;
        if (box.width === 0 && box.height === 0 && svg.isConnected) return;
      }
      await new Promise<void>((resolve) => {
        window.setTimeout(resolve, 16);
      });
    }
  };

  const handleExport = async () => {
    if (exportStatus === "exporting") return;
    setExportStatus("exporting");
    setExportMessage(null);

    try {
      if (!workspaceRef.current) {
        throw new JourneyExportError("root_missing");
      }

      await waitForJourneyRender();

      const exportRoot = exportRootRef.current;
      if (!exportRoot || !exportRoot.isConnected) {
        throw new JourneyExportError("root_missing");
      }
      if (!exportRoot.querySelector('[data-testid="journey-curve-svg"]')) {
        throw new JourneyExportError("not_rendered");
      }
      const rootBox = exportRoot.getBoundingClientRect();
      if (rootBox.width < 0 || rootBox.height < 0) {
        throw new JourneyExportError("not_rendered");
      }

      workspaceRef.current.classList.add("journey-exporting");
      try {
        // Prefer offscreen full-journey root so PNG is independent of viewport zoom/Inspector.
        const fullRoot = exportFullRootRef.current;
        const result = await exportJourneyPng(
          fullRoot &&
            fullRoot.querySelector('[data-testid="journey-curve-svg-full-export"]')
            ? fullRoot
            : exportRoot,
          chapterTitle ?? summary.chapter_title,
          { mode: "full_journey" },
        );
        const filename =
          result &&
          typeof result === "object" &&
          "filename" in result &&
          typeof (result as { filename: unknown }).filename === "string"
            ? (result as { filename: string }).filename
            : `StoryLens_${chapterTitle ?? summary.chapter_title}_完整旅程_v4.0.png`;
        setExportStatus("succeeded");
        setExportMessage(`已导出完整旅程：${filename}`);
      } finally {
        workspaceRef.current.classList.remove("journey-exporting");
      }
    } catch (error) {
      if (import.meta.env.DEV) {
        console.error("[ReaderJourney] PNG export failed", error);
      }
      setExportStatus("failed");
      setExportMessage(exportErrorMessage(error));
    }
  };

  const selectedPhaseData = useMemo(
    () => visualization.phases.find((item) => item.ordinal === selectedPhase) ?? null,
    [visualization.phases, selectedPhase],
  );

  const phaseMetricAverages = useMemo(() => {
    const averages = new Map<number, number>();
    for (const phase of visualization.phases) {
      const lensAvg = phaseAverageForLens(visualization, observationLens, phase);
      if (lensAvg != null && Number.isFinite(lensAvg)) {
        averages.set(phase.ordinal, lensAvg);
        continue;
      }
      if (metric === "engagement" && Number.isFinite(phase.average_engagement)) {
        averages.set(phase.ordinal, phase.average_engagement);
        continue;
      }
      const values: number[] = [];
      for (
        let ordinal = phase.start_scene_ordinal;
        ordinal <= phase.end_scene_ordinal;
        ordinal += 1
      ) {
        const point = series.find((item) => item.scene_ordinal === ordinal);
        const resolved = resolveMetricValue(point);
        if (resolved != null && Number.isFinite(resolved)) values.push(resolved);
      }
      if (values.length > 0) {
        averages.set(phase.ordinal, values.reduce((sum, item) => sum + item, 0) / values.length);
      } else if (Number.isFinite(phase.average_engagement)) {
        averages.set(phase.ordinal, phase.average_engagement);
      }
    }
    return averages;
  }, [visualization, series, metric, observationLens]);

  const selectedLensBinding = useMemo(() => {
    if (!selectedNode) return null;
    return resolveLensMetricBinding(visualization, observationLens, selectedNode);
  }, [visualization, observationLens, selectedNode]);

  const selectedCluster = useMemo(() => {
    if (!expandedClusterId) return null;
    const clusters =
      (visualization.visible_question_clusters?.length
        ? visualization.visible_question_clusters
        : visualization.question_clusters) ?? [];
    return clusters.find((item) => item.cluster_id === expandedClusterId) ?? null;
  }, [expandedClusterId, visualization.question_clusters, visualization.visible_question_clusters]);

  const selectedRiskInterval = useMemo(() => {
    if (!selectedRiskKey) return null;
    return (
      visualization.risk_intervals.find(
        (item) => `${item.risk_type}-${item.start_scene_ordinal}` === selectedRiskKey,
      ) ?? null
    );
  }, [selectedRiskKey, visualization.risk_intervals]);

  /** Context Inspector: URL inspector wins; otherwise infer from selection. */
  const effectiveInspector: JourneyInspectorType | null =
    inspectorFromUrl ??
    (selectedSceneOrdinal != null
      ? "scene"
      : selectedPhase != null
        ? "phase"
        : expandedClusterId
          ? "question"
          : null);

  const analysisRunLabel = useMemo(() => {
    if (analysisRunIdProp != null) return String(analysisRunIdProp);
    const fromQuery = searchParams.get("analysisRun");
    if (fromQuery) return fromQuery;
    if (typeof window !== "undefined") {
      const match = window.location.pathname.match(/\/analysis-runs\/(\d+)/);
      if (match?.[1]) return match[1];
    }
    return null;
  }, [analysisRunIdProp, searchParams]);

  const journeyRunLabel =
    journeyRunIdProp != null ? String(journeyRunIdProp) : null;

  const clearInspectorSelection = () => {
    clearInspectorParam();
    setSelectedRiskKey(null);
  };

  const chapterHeading = chapterTitle ?? summary.chapter_title;
  const analysisInfoMeta = (
    <>
      <span>visualization v{visualization.visualization_version}</span>
      <span>engagement v{visualization.formula_versions.engagement_formula_version}</span>
      <span>importance v{visualization.formula_versions.importance_formula_version}</span>
      <span>
        semantic: {visualization.calibration_status.semantic_source ?? "—"}
        {visualization.calibration_status.scene_contract_version
          ? ` · contract ${visualization.calibration_status.scene_contract_version}`
          : ""}
      </span>
      {analysisRunLabel ? <span>分析任务 #{analysisRunLabel}</span> : null}
      {journeyRunLabel ? <span>旅程任务 #{journeyRunLabel}</span> : null}
    </>
  );

  const showDesktopInspector = layoutMode === "desktop" && !inspectorCollapsed;
  const showMidDock = layoutMode === "mid" && !inspectorCollapsed;
  const showNarrowTabs = layoutMode === "narrow";
  const showLeftSplitter =
    hasSourcePane && !sourceCollapsed && (layoutMode === "desktop" || layoutMode === "mid");
  const showRightSplitter = showDesktopInspector;
  const showDockSplitter = showMidDock;

  const leftSplitterPx = showLeftSplitter ? SPLITTER_WIDTH_PX : 0;
  const rightSplitterPx = showRightSplitter ? SPLITTER_WIDTH_PX : 0;
  const dockSplitterPx = showDockSplitter ? SPLITTER_WIDTH_PX : 0;
  const splitterCountForClamp =
    (leftSplitterPx > 0 ? 1 : 0) + (rightSplitterPx > 0 ? 1 : 0);
  /** When a splitter column is hidden, CSS still reserves `--splitter-width` unless zeroed via style. */
  const gridSourceCol = 1;
  const gridLeftSplitCol = 2;
  const gridMainCol = showNarrowTabs ? 1 : 3;
  const gridRightSplitCol = 4;
  const gridInspectorCol = 5;

  // Resolve mutual side widths: first compute inspector assuming preferred source (or 0),
  // then recompute source with effective inspector.
  const sourceCollapsedForWidth = !hasSourcePane || sourceCollapsed || showNarrowTabs;
  const inspectorCollapsedForWidth = inspectorCollapsed || layoutMode !== "desktop";

  const tentativeSource = effectivePaneWidth(
    preferredSourceWidth,
    SOURCE_PANE_WIDTH_RANGE,
    maxSidePaneWidth(
      workspaceWidth,
      inspectorCollapsedForWidth ? 0 : INSPECTOR_PANE_WIDTH_RANGE.min,
      splitterCountForClamp,
    ),
    sourceCollapsedForWidth,
  );

  const inspectorMax = maxSidePaneWidth(
    workspaceWidth,
    tentativeSource,
    splitterCountForClamp,
  );
  const effectiveInspectorWidth = effectivePaneWidth(
    preferredInspectorWidth,
    INSPECTOR_PANE_WIDTH_RANGE,
    inspectorMax,
    inspectorCollapsedForWidth,
  );

  const sourceMax = maxSidePaneWidth(
    workspaceWidth,
    effectiveInspectorWidth,
    splitterCountForClamp,
  );
  const effectiveSourceWidth = effectivePaneWidth(
    preferredSourceWidth,
    SOURCE_PANE_WIDTH_RANGE,
    sourceMax,
    sourceCollapsedForWidth,
  );

  const dockMax = Math.max(
    INSPECTOR_DOCK_HEIGHT_RANGE.min,
    Math.floor(workspaceHeight * 0.55),
  );
  const effectiveDockHeightPx = effectiveDockHeight(
    preferredDockHeight,
    INSPECTOR_DOCK_HEIGHT_RANGE,
    dockMax,
    !showMidDock,
  );

  const sourceDragMax = Math.max(
    SOURCE_PANE_WIDTH_RANGE.min,
    Math.min(SOURCE_PANE_WIDTH_RANGE.max, sourceMax),
  );
  const inspectorDragMax = Math.max(
    INSPECTOR_PANE_WIDTH_RANGE.min,
    Math.min(INSPECTOR_PANE_WIDTH_RANGE.max, inspectorMax),
  );
  const dockDragMax = Math.max(
    INSPECTOR_DOCK_HEIGHT_RANGE.min,
    Math.min(INSPECTOR_DOCK_HEIGHT_RANGE.max, dockMax),
  );

  const compactToolbar = layoutMode === "narrow";
  const layoutStyle = {
    "--source-pane-width": `${effectiveSourceWidth}px`,
    "--inspector-pane-width": `${effectiveInspectorWidth}px`,
    "--inspector-dock-height": `${showMidDock ? effectiveDockHeightPx : 0}px`,
    "--splitter-left-width": `${leftSplitterPx}px`,
    "--splitter-right-width": `${rightSplitterPx}px`,
    "--splitter-dock-width": `${dockSplitterPx}px`,
    "--splitter-width": `${SPLITTER_WIDTH_PX}px`,
    "--journey-toolbar-height": `${LAYOUT_TOKENS.toolbarHeight}px`,
    "--journey-button-height": `${LAYOUT_TOKENS.buttonHeight}px`,
    "--journey-section-gap": `${LAYOUT_TOKENS.sectionGap}px`,
    "--journey-panel-padding": `${LAYOUT_TOKENS.panelPadding}px`,
    "--journey-card-radius": `${LAYOUT_TOKENS.cardRadius}px`,
    "--journey-inspector-anim-ms": paneResizing ? "0ms" : `${LAYOUT_TOKENS.inspectorAnimMs}ms`,
  };

  const inspectorBody = (
    <div
      className="journey-detail-pane journey-context-inspector"
      data-testid="journey-detail-pane"
      data-inspector={effectiveInspector ?? "empty"}
    >
      {effectiveInspector === "phase" && selectedPhaseData ? (
        <JourneyDetailErrorBoundary
          onReset={clearInspectorSelection}
          onBackToOverview={clearInspectorSelection}
        >
          <JourneyPhaseDetailPanel
            phase={selectedPhaseData}
            visualization={visualization}
            onSelectScene={(node) => handleSelectScene(node, "journey_scene")}
          />
        </JourneyDetailErrorBoundary>
      ) : effectiveInspector === "question" && selectedCluster ? (
        <JourneyQuestionInspectorPanel
          cluster={selectedCluster}
          nodes={nodes}
          onSelectScene={(node) => handleSelectScene(node, "journey_cluster")}
        />
      ) : effectiveInspector === "hook" ? (
        <JourneyMarkerInspectorPanel
          kind="hook"
          node={selectedNode ?? null}
          onLocateEvidence={(id) => handleLocateEvidence(id, selectedNode)}
        />
      ) : effectiveInspector === "payoff" ? (
        <JourneyMarkerInspectorPanel
          kind="payoff"
          node={selectedNode ?? null}
        />
      ) : effectiveInspector === "risk" ? (
        <JourneyMarkerInspectorPanel
          kind="risk"
          node={selectedNode ?? null}
          riskInterval={selectedRiskInterval}
        />
      ) : effectiveInspector === "scene" && selectedNode ? (
        <JourneyDetailErrorBoundary
          onReset={() => {
            if (!isControlled) setSelectedSceneOrdinalInternal(null);
            onSelectionChange?.({ activeSceneOrdinal: null, source: "journey_scene" });
            clearInspectorParam();
          }}
          onBackToOverview={() => {
            if (!isControlled) setSelectedSceneOrdinalInternal(null);
            onSelectionChange?.({ activeSceneOrdinal: null, source: "journey_scene" });
            clearInspectorParam();
          }}
        >
          <JourneySceneDetailPanel
            node={selectedNode}
            visualization={visualization}
            observationLensLabel={lensDef.labelZh}
            observationLens={observationLens}
            onLocateEvidence={(id) => handleLocateEvidence(id, selectedNode)}
            onOpenInSceneList={
              onSelectScene ? () => onSelectScene(selectedNode.scene_id) : undefined
            }
          />
        </JourneyDetailErrorBoundary>
      ) : (
        <div className="journey-detail-empty" data-testid="journey-detail-empty">
          <p className="journey-detail-empty-title">
            选择一个阶段、场景或曲线节点，查看详细分析。
          </p>
          <ul className="journey-detail-empty-hints">
            <li>点击阶段卡查看阶段作用</li>
            <li>点击曲线节点查看场景变化</li>
            <li>点击章节结论查看问题、钩子与薄弱点</li>
          </ul>
        </div>
      )}
    </div>
  );

  return (
    <div
      className={`journey-workspace journey-workspace-v4 ${compactHead ? "compact-head" : ""}`}
      data-testid="journey-workspace"
      data-layout={layoutMode}
      data-inspector-collapsed={inspectorCollapsed ? "true" : "false"}
      data-source-collapsed={sourceCollapsed || !hasSourcePane ? "true" : "false"}
      data-visualization-version={JOURNEY_VISUALIZATION_VERSION}
      ref={workspaceRef}
      style={layoutStyle as CSSProperties}
    >
      {!compactHead && (
        <header className="journey-workspace-head">
          <p className="journey-helper">
            以下为模型预测的阅读体验轨迹，不代表真实用户行为数据。
          </p>
        </header>
      )}

      {showNarrowTabs ? (
        <div className="journey-workspace-tabs" data-testid="journey-workspace-tabs">
          {hasSourcePane ? (
            <button
              type="button"
              data-testid="journey-tab-source"
              className={narrowPane === "source" ? "active" : ""}
              onClick={() => {
                setNarrowPane("source");
                if (!inspectorCollapsed) setInspectorCollapsedPref(true);
              }}
            >
              正文
            </button>
          ) : null}
          <button
            type="button"
            data-testid="journey-tab-main"
            className={narrowPane === "main" ? "active" : ""}
            onClick={() => {
              setNarrowPane("main");
              if (!inspectorCollapsed) setInspectorCollapsedPref(true);
            }}
          >
            旅程
          </button>
          <button
            type="button"
            data-testid="journey-tab-inspector"
            className={narrowPane === "inspector" && !inspectorCollapsed ? "active" : ""}
            onClick={() => {
              setNarrowPane("inspector");
              expandInspector();
            }}
          >
            详情
          </button>
        </div>
      ) : null}

      <div
        className={`journey-workspace-grid${paneResizing ? " is-resizing" : ""}`}
        data-testid="journey-workspace-grid"
        data-layout={layoutMode}
        data-source-width={effectiveSourceWidth}
        data-inspector-width={effectiveInspectorWidth}
        data-main-min={MAIN_PANE_MIN_WIDTH_PX}
      >
        {hasSourcePane ? (
          <aside
            className="journey-source-pane"
            data-testid="journey-source-pane"
            style={{ gridColumn: gridSourceCol, gridRow: 1 }}
            hidden={
              (sourceCollapsed && !showNarrowTabs) ||
              (showNarrowTabs && narrowPane !== "source")
            }
            aria-hidden={
              (sourceCollapsed && !showNarrowTabs) ||
              (showNarrowTabs && narrowPane !== "source")
                ? true
                : undefined
            }
          >
            {sourcePane}
          </aside>
        ) : (
          <div
            className="journey-source-pane-spacer"
            data-testid="journey-source-pane-spacer"
            style={{ gridColumn: gridSourceCol, gridRow: 1 }}
            aria-hidden="true"
          />
        )}

        {showLeftSplitter ? (
          <JourneyPaneSplitter
            orientation="vertical"
            value={effectiveSourceWidth || preferredSourceWidth}
            min={SOURCE_PANE_WIDTH_RANGE.min}
            max={sourceDragMax}
            onChange={persistSourceWidth}
            onReset={() => persistSourceWidth(SOURCE_PANE_WIDTH_RANGE.default)}
            label="调整正文区域宽度"
            testId="journey-splitter-source"
            growDirection="positive"
            style={{ gridColumn: gridLeftSplitCol, gridRow: 1 }}
            onDraggingChange={setPaneResizing}
          />
        ) : !showNarrowTabs ? (
          <div
            className="journey-pane-splitter-spacer"
            data-testid="journey-splitter-source-spacer"
            style={{ gridColumn: gridLeftSplitCol, gridRow: 1 }}
            aria-hidden="true"
          />
        ) : null}

        <div
          className="journey-main-pane"
          data-testid="journey-main-pane"
          style={{
            gridColumn: gridMainCol,
            gridRow: 1,
            minWidth: showNarrowTabs ? undefined : MAIN_PANE_MIN_WIDTH_PX,
          }}
          hidden={showNarrowTabs && narrowPane !== "main"}
          aria-hidden={showNarrowTabs && narrowPane !== "main" ? true : undefined}
        >
      <header className="journey-analysis-header" data-testid="journey-analysis-header">
        {topBanner ? (
          <p
            className="journey-legacy-banner"
            data-testid={
              isV2NativeRealBanner
                ? "journey-v2-native-real-banner"
                : isV2LocalFixtureBanner
                  ? "journey-v2-local-fixture-banner"
                  : "journey-legacy-uncalibrated-banner"
            }
            role="status"
          >
            {topBanner}
          </p>
        ) : null}
        {chapterSummaryBullets.length > 0 ? (
          <ul
            className="journey-chapter-summary-bullets"
            data-testid="journey-chapter-summary-bullets"
          >
            {chapterSummaryBullets.map((bullet) => (
              <li key={bullet.kind} data-kind={bullet.kind}>
                {bullet.text}
              </li>
            ))}
          </ul>
        ) : null}
        <div className="journey-analysis-titles">
          <h2 className="journey-analysis-title" data-testid="journey-analysis-title">
            阅读旅程
          </h2>
          <p className="journey-analysis-subtitle" data-testid="journey-analysis-subtitle" title={chapterHeading}>
            {chapterHeading}
          </p>
          <p className="journey-analysis-meta" data-testid="journey-analysis-meta">
            {sceneCount > 0 ? `${sceneCount} 个场景` : "— 个场景"}
            {" · "}
            {visualization.phases.length > 0
              ? `${visualization.phases.length} 个阶段`
              : "— 个阶段"}
            {" · "}
            观察读者在本章中的情绪、节奏、牵引力与钩子变化
          </p>
        </div>
        <div className="journey-analysis-tools" data-testid="journey-analysis-tools">
          <div className="journey-marker-toggle" data-testid="journey-marker-toggle">
            <button
              type="button"
              className={markerMode === "compact" ? "active" : ""}
              data-testid="journey-marker-compact"
              title="精简标记：突出主要阅读结构，仅显示关键场景、钩子、回报和问题簇。"
              onClick={() => setMarkerMode("compact")}
            >
              精简标记
            </button>
            <button
              type="button"
              className={markerMode === "full" ? "active" : ""}
              data-testid="journey-marker-full"
              title="完整标记：显示全部分析节点及派生依据。"
              onClick={() => setMarkerMode("full")}
            >
              完整标记
            </button>
          </div>
          <div className="journey-analysis-info-wrap">
            <button
              type="button"
              data-testid="journey-analysis-info"
              className={analysisInfoOpen ? "active" : ""}
              aria-expanded={analysisInfoOpen}
              onClick={() => setAnalysisInfoOpen((value) => !value)}
            >
              分析信息
            </button>
            {analysisInfoOpen && (
              <div
                className="journey-analysis-info-popover"
                data-testid="journey-analysis-info-popover"
                role="dialog"
              >
                <div className="journey-export-meta" data-testid="journey-export-meta">
                  {analysisInfoMeta}
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      <div
        ref={exportRootRef}
        data-testid="journey-export-root"
        data-reader-journey-export-root="true"
        className="journey-export-root journey-overview-curve-root"
        data-overview-mode={CANONICAL_OVERVIEW_MODE}
      >
        <h3
          className="journey-export-title journey-export-only-title"
          data-testid="journey-export-title"
        >
          阅读旅程
        </h3>
        <p
          className="journey-export-chapter journey-export-only-title"
          data-testid="journey-export-chapter"
        >
          {chapterHeading} · {sceneCount} 个场景
        </p>
        <div className="journey-export-meta journey-export-meta-inline" data-testid="journey-export-meta-inline">
          {analysisInfoMeta}
        </div>

          <div className="journey-overview-pane" data-testid="journey-overview-pane">
          <div className="journey-overview-curve" data-testid="journey-overview-curve">
        <JourneyChartToolbar
          metric={metric}
          onMetricChange={handleMetricChange}
          observationLens={observationLens}
          onObservationLensChange={handleObservationLensChange}
          overlayComposite={overlayComposite}
          onOverlayCompositeChange={setOverlayComposite}
          heightPreset={heightPreset}
          onHeightPresetChange={handleHeightPresetChange}
          yDomainMode={yDomainMode}
          onYDomainModeChange={handleYDomainModeChange}
          canPanZoom={allowsHorizontalPanZoom(sceneCount)}
          showBrush={requiresBrush(sceneCount)}
          showZoomControls={showsZoomControls(sceneCount)}
          onFitAll={() => syncViewToUrl(1, sceneCount)}
          onZoomIn={() => {
            const next = zoomViewWindow(
              viewWindow.start,
              viewWindow.end,
              sceneCount,
              1.35,
              selectedSceneOrdinal,
            );
            syncViewToUrl(next.start, next.end);
          }}
          onZoomOut={() => {
            const next = zoomViewWindow(
              viewWindow.start,
              viewWindow.end,
              sceneCount,
              1 / 1.35,
              selectedSceneOrdinal,
            );
            syncViewToUrl(next.start, next.end);
          }}
          onFocusPhase={() => {
            const phase =
              visualization.phases.find((item) => item.ordinal === selectedPhase) ??
              visualization.phases[0];
            if (!phase) return;
            const next = focusPhaseWindow(
              phase.start_scene_ordinal,
              phase.end_scene_ordinal,
              sceneCount,
            );
            syncViewToUrl(next.start, next.end);
          }}
          onResetView={() => {
            handleHeightPresetChange("standard");
            handleYDomainModeChange("fixed_0_100");
            syncViewToUrl(1, sceneCount);
          }}
          onResetPaneWidths={resetPaneWidths}
          inspectorCollapsed={!detailVisible}
          onToggleInspector={handleToggleInspector}
          compactActions={compactToolbar}
          narrowLayout={layoutMode === "narrow"}
          onExportPng={() => void handleExport()}
          exportBusy={exportStatus === "exporting"}
        />
        {/* Phase navigation — after toolbar (+ optional MetricSelectorPanel), before chart shell */}
        <section className="journey-phase-strip-wrap" data-testid="journey-phase-strip-wrap">
          <label
            className="journey-phase-mobile-select-wrap"
            data-testid="journey-phase-mobile-select-wrap"
          >
            <span className="journey-phase-mobile-select-label">当前阶段</span>
            <select
              className="journey-phase-mobile-select"
              data-testid="journey-phase-mobile-select"
              aria-label="选择旅程阶段"
              value={selectedPhase ?? ""}
              onChange={(event) => {
                const next = Number(event.target.value);
                if (!Number.isFinite(next) || next <= 0) return;
                handleSelectPhase(next);
              }}
            >
              <option value="" disabled>
                选择阶段
              </option>
              {visualization.phases.map((phase) => {
                const phaseMetric =
                  phaseMetricAverages.get(phase.ordinal) ?? phase.average_engagement;
                return (
                <option key={phase.ordinal} value={phase.ordinal}>
                  {`${formatJourneyPhaseLabel(phase.title)} · 场景 ${phase.start_scene_ordinal}—${phase.end_scene_ordinal} · ${formatLensPhaseScoreLabel(visualization, observationLens, phaseMetric)}`}
                </option>
                );
              })}
            </select>
          </label>
          <div
            ref={phaseStripRef}
            className="journey-phase-strip journey-phase-band journey-phase-nav"
            data-testid="journey-phase-strip"
          >
            {visualization.phases.map((phase, index) => {
              const isSelected = selectedPhase === phase.ordinal;
              const phaseLabel = formatJourneyPhaseLabel(phase.title);
              const phaseSummary = resolvePhaseSummaryDisplay(phase.summary, phase.title);
              const phaseMetric =
                phaseMetricAverages.get(phase.ordinal) ?? phase.average_engagement;
              const hookPayoffAvg = isHookPayoffLens(observationLens)
                ? phaseHookPayoffAverages(visualization, phase)
                : null;
              const avgText = hookPayoffAvg
                ? [
                    hookPayoffAvg.avgHook == null
                      ? "平均钩子 —"
                      : `平均钩子 ${Math.round(hookPayoffAvg.avgHook)}`,
                    hookPayoffAvg.avgPayoff == null
                      ? "平均回报 —"
                      : `平均回报 ${Math.round(hookPayoffAvg.avgPayoff)}`,
                  ].join(" · ")
                : formatLensPhaseScoreLabel(visualization, observationLens, phaseMetric);
              const phaseDesc = hookPayoffAvg
                ? `状态：${hookPayoffAvg.statusLabel}`
                : phaseSummary;
              return (
                <button
                  key={phase.ordinal}
                  type="button"
                  className={`journey-phase-card journey-phase-compact journey-phase-nav-card ${isSelected ? "selected active-phase" : ""}`}
                  data-testid={`journey-phase-${phase.ordinal}`}
                  title={`${phaseLabel} · ${phaseDesc}`}
                  aria-pressed={isSelected}
                  aria-selected={isSelected}
                  style={{
                    ["--phase-band-color" as string]: phaseColors[index % phaseColors.length],
                  }}
                  onClick={() => handleSelectPhase(phase.ordinal)}
                >
                  <div className="journey-phase-card-head">
                    <strong className="journey-phase-title">{phaseLabel}</strong>
                    <span className="journey-phase-avg" data-testid={`journey-phase-avg-${phase.ordinal}`}>
                      {avgText}
                    </span>
                  </div>
                  <p className="journey-phase-card-desc">{phaseDesc}</p>
                </button>
              );
            })}
          </div>
        </section>

          {selectedSceneOrdinal != null && selectedLensBinding != null && (
            <p className="journey-active-scene-caption" data-testid="journey-active-scene-caption">
              {isHookPayoffLens(observationLens) && selectedNode
                ? (() => {
                    const summaryHp = buildHookPayoffSceneSummary(visualization, selectedNode);
                    return summaryHp
                      ? formatHookPayoffSceneCaption(summaryHp)
                      : `${formatJourneySceneLabel(selectedSceneOrdinal)} · ${formatLensBindingCaption(selectedLensBinding)}`;
                  })()
                : `${formatJourneySceneLabel(selectedSceneOrdinal)} · ${formatLensBindingCaption(selectedLensBinding)}`}
            </p>
          )}

          {/* Chart shell: viewport only (toolbar is above phase strip) */}
          <div
            className="journey-chart-shell"
            data-testid="journey-chart-shell"
            data-visualization-version={JOURNEY_VISUALIZATION_VERSION}
            style={{ minHeight: CHART_SHELL_MIN_HEIGHT_PX }}
          >
            <div
              className="journey-chart-viewport"
              data-testid="journey-chart-viewport"
              style={{ minHeight: chartHeight }}
            >
              <section
                className="journey-curve-section"
                data-testid="journey-curve-section"
                data-plot-area-height={plotAreaHeightPx(heightPreset)}
                style={{ minHeight: chartHeight, height: chartHeight, flex: "0 0 auto" }}
              >
                <CanonicalJourneyChart
                  visualization={visualization}
                  metric={metric}
                  observationLens={observationLens}
                  overlayComposite={overlayComposite}
                  chartHeight={chartHeight}
                  yDomainMode={yDomainMode}
                  viewStart={viewWindow.start}
                  viewEnd={viewWindow.end}
                  onViewChange={syncViewToUrl}
                  selectedSceneOrdinal={selectedSceneOrdinal}
                  selectedPhaseOrdinal={selectedPhase}
                  markerMode={markerMode}
                  onSelectScene={(node) => handleSelectScene(node, "journey_scene")}
                  onSelectRisk={(intervalKey, startNode) => {
                    setSelectedRiskKey(intervalKey);
                    expandInspector();
                    if (startNode) {
                      if (!isControlled) {
                        setSelectedSceneOrdinalInternal(startNode.scene_ordinal);
                      }
                      onSelectionChange?.({
                        activeSceneOrdinal: startNode.scene_ordinal,
                        activePhaseOrdinal: startNode.phase_ordinal ?? undefined,
                        source: "journey_risk",
                      });
                      commitSelectionIntent({
                        source: "risk",
                        inspector: "risk",
                        sceneOrdinal: startNode.scene_ordinal,
                        phaseId: startNode.phase_ordinal,
                        paragraphId: startNode.paragraph_range?.start_paragraph_id,
                      });
                    } else {
                      commitSelectionIntent({ source: "risk", inspector: "risk" });
                    }
                  }}
                  onSelectHook={(node) => {
                    expandInspector();
                    if (!isControlled) {
                      setSelectedSceneOrdinalInternal(node.scene_ordinal);
                    }
                    onSelectionChange?.({
                      activeSceneOrdinal: node.scene_ordinal,
                      activePhaseOrdinal: node.phase_ordinal ?? undefined,
                      source: "journey_scene",
                    });
                    commitSelectionIntent({
                      source: "hook",
                      inspector: "hook",
                      sceneOrdinal: node.scene_ordinal,
                      phaseId: node.phase_ordinal,
                      paragraphId: node.paragraph_range?.start_paragraph_id,
                    });
                  }}
                  onSelectPayoff={(node) => {
                    expandInspector();
                    if (!isControlled) {
                      setSelectedSceneOrdinalInternal(node.scene_ordinal);
                    }
                    onSelectionChange?.({
                      activeSceneOrdinal: node.scene_ordinal,
                      activePhaseOrdinal: node.phase_ordinal ?? undefined,
                      source: "journey_scene",
                    });
                    commitSelectionIntent({
                      source: "payoff",
                      inspector: "payoff",
                      sceneOrdinal: node.scene_ordinal,
                      phaseId: node.phase_ordinal,
                      paragraphId: node.paragraph_range?.start_paragraph_id,
                    });
                  }}
                />
              </section>

              <JourneyDiagnosisBand
                diagnoses={sceneDiagnoses}
                selectedSceneOrdinal={selectedSceneOrdinal}
                observationLens={observationLens}
                onSelectScene={(ordinal: number) => {
                  const node = visualization.scene_nodes.find(
                    (item) => item.scene_ordinal === ordinal,
                  );
                  if (node) handleSelectScene(node, "journey_rhythm");
                }}
              />

              {/* Scene navigation must sit below SVG — never overlay or steal plot height */}
              <section
                className="journey-rhythm-strip journey-rhythm-strip-thin"
                data-testid="journey-rhythm-strip"
              >
                {nodes.map((node) => (
                  <button
                    key={node.scene_ordinal}
                    type="button"
                    className={`journey-rhythm-dot ${ROLE_CLASS[node.role] ?? ""} ${
                      selectedSceneOrdinal === node.scene_ordinal ? "selected" : ""
                    }`}
                    data-testid={`journey-rhythm-dot-${node.scene_ordinal}`}
                    data-role={node.role}
                    title={`Scene ${node.scene_ordinal} · ${roleLabelZh(node.role)}`}
                    aria-label={`Scene ${node.scene_ordinal}`}
                    onClick={() => handleSelectScene(node, "journey_rhythm")}
                  />
                ))}
              </section>

              <div className="journey-curve-legend" data-testid="journey-curve-legend">
                <span data-legend="active-scene">当前场景</span>
                <span data-legend="hook-key">钩子</span>
                <span data-legend="payoff">回报</span>
                <span data-legend="risk">流失风险</span>
                {markerMode === "full" && (
                  <>
                    <span data-legend="answered">已回答问题</span>
                    <span data-legend="transformed">问题升级</span>
                    <span data-legend="secondary">次级节点</span>
                    <span data-legend="beat">节拍节点</span>
                    <span data-legend="derived">派生标记</span>
                  </>
                )}
              </div>
            </div>
          </div>

        {!detailVisible ? (
          <div className="journey-inspector-summary-bar" data-testid="journey-inspector-summary-bar">
            <div className="journey-inspector-summary-inner" data-testid="journey-inspector-summary-inner">
              <span className="journey-inspector-summary-text" data-testid="journey-inspector-summary-text">
                {selectedNode
                  ? `${formatJourneySceneLabel(selectedNode.scene_ordinal)} · ${roleLabelZh(selectedNode.role)} · ${
                      formatJourneyPhaseLabel(
                        visualization.phases.find((p) => p.ordinal === selectedNode.phase_ordinal)?.title,
                      )
                    }`
                  : selectedPhase != null
                    ? `${formatJourneyPhaseLabel(
                        visualization.phases.find((p) => p.ordinal === selectedPhase)?.title,
                      )} · 点击展开查看阶段详情`
                    : "选择一个阶段、场景或曲线节点查看详细分析"}
              </span>
              <button
                type="button"
                className="journey-toolbar-btn"
                data-testid="journey-inspector-summary-expand"
                aria-label="展开旅程详情"
                onClick={expandInspector}
              >
                展开详情
              </button>
            </div>
          </div>
        ) : null}

        {/* Compact one-line insight strip (below curve to free hero space) */}
        <section className="journey-diagnosis journey-diagnosis-inline" data-testid="journey-diagnosis-summary">
          <div
            className={`journey-insight-strip journey-summary-cards journey-summary-strip journey-summary-oneline ${insightExpanded ? "expanded" : ""}`}
            data-testid="journey-summary-cards"
            data-insight-strip="true"
            data-expanded={insightExpanded ? "true" : "false"}
          >
            <button
              type="button"
              className="journey-insight-oneline-toggle"
              data-testid="journey-insight-oneline-toggle"
              aria-expanded={insightExpanded}
              onClick={() => {
                setInsightExpanded((prev) => {
                  const next = !prev;
                  writeLocalPref(UI_PREF_KEYS.insightStripExpanded, next);
                  return next;
                });
              }}
            >
              {insightExpanded ? "收起摘要" : "章节摘要"}
            </button>
            <div className="journey-insight-oneline-body">
              {tractionClickable ? (
                <button
                  type="button"
                  className="journey-insight-item journey-insight-clickable journey-summary-card journey-summary-card-primary"
                  data-testid="summary-card-traction"
                  title={summary.primary_cluster_title ?? summary.primary_traction}
                  onClick={handleInsightTraction}
                >
                  <span>核心牵引</span>
                  <b>{summary.primary_cluster_title ?? summary.primary_traction}</b>
                </button>
              ) : (
                <div
                  className="journey-insight-item journey-insight-static journey-summary-card journey-summary-card-primary"
                  data-testid="summary-card-traction"
                  title={summary.primary_cluster_title ?? summary.primary_traction}
                >
                  <span>核心牵引</span>
                  <b>{summary.primary_cluster_title ?? summary.primary_traction}</b>
                </div>
              )}
              <span className="journey-insight-sep" aria-hidden="true">
                |
              </span>
              <button
                type="button"
                className="journey-insight-item journey-insight-clickable journey-summary-card"
                data-testid="summary-card-peak"
                title={`Scene ${peakOrdinal} · ${summary.peaks.engagement_peak.value}`}
                onClick={handleInsightPeak}
              >
                <span>峰值场景</span>
                <b>
                  场景 {peakOrdinal} · {summary.peaks.engagement_peak.value}
                </b>
              </button>
              <span className="journey-insight-sep" aria-hidden="true">
                |
              </span>
              <button
                type="button"
                className="journey-insight-item journey-insight-clickable journey-summary-card"
                data-testid="summary-card-weak"
                title={`${weakIntervalDisplay(summary)} · 最低点 Scene ${valleyOrdinal}`}
                onClick={handleInsightValley}
              >
                <span>薄弱区间</span>
                <b>{weakIntervalDisplay(summary)}</b>
              </button>
              <span className="journey-insight-sep" aria-hidden="true">
                |
              </span>
              {hookClickable ? (
                <button
                  type="button"
                  className="journey-insight-item journey-insight-clickable journey-summary-card journey-summary-card-primary"
                  data-testid="summary-card-hook"
                  title={
                    strongestHook?.summary ||
                    (strongestHook ? `Scene ${strongestHook.scene_ordinal}` : undefined)
                  }
                  onClick={handleInsightHook}
                >
                  <span>章尾钩子</span>
                  <b>
                    {strongestHook?.summary ||
                      (strongestHook ? `Scene ${strongestHook.scene_ordinal}` : "—")}
                  </b>
                </button>
              ) : (
                <div
                  className="journey-insight-item journey-insight-static journey-summary-card journey-summary-card-primary"
                  data-testid="summary-card-hook"
                >
                  <span>章尾钩子</span>
                  <b>—</b>
                </div>
              )}
            </div>
          </div>
        </section>
          </div>
          </div>

      </div>
      </div>

        {showDockSplitter ? (
          <JourneyPaneSplitter
            orientation="horizontal"
            value={effectiveDockHeightPx || preferredDockHeight}
            min={INSPECTOR_DOCK_HEIGHT_RANGE.min}
            max={dockDragMax}
            onChange={persistDockHeight}
            onReset={() => persistDockHeight(INSPECTOR_DOCK_HEIGHT_RANGE.default)}
            label="调整详情区域高度"
            testId="journey-splitter-dock"
            growDirection="positive"
            style={{ gridColumn: "1 / -1", gridRow: 2 }}
            onDraggingChange={setPaneResizing}
          />
        ) : null}

        {showMidDock ? (
          <div
            className="journey-inspector-dock"
            data-testid="journey-inspector-dock"
            data-dock="bottom"
            data-detail-state="expanded"
            style={{ gridColumn: "1 / -1", gridRow: showDockSplitter ? 3 : 2 }}
          >
            <div className="journey-inspector-drawer-header" data-testid="journey-inspector-drawer-header">
              <button
                type="button"
                className="journey-collapse-inspector-btn"
                data-testid="journey-collapse-inspector"
                aria-label="收起旅程详情"
                onClick={handleToggleInspector}
              >
                收起详情
              </button>
            </div>
            {inspectorBody}
          </div>
        ) : null}

        {showRightSplitter ? (
          <JourneyPaneSplitter
            orientation="vertical"
            value={effectiveInspectorWidth || preferredInspectorWidth}
            min={INSPECTOR_PANE_WIDTH_RANGE.min}
            max={inspectorDragMax}
            onChange={persistInspectorWidth}
            onReset={() => persistInspectorWidth(INSPECTOR_PANE_WIDTH_RANGE.default)}
            label="调整详情区域宽度"
            testId="journey-splitter-inspector"
            growDirection="negative"
            style={{ gridColumn: gridRightSplitCol, gridRow: 1 }}
            onDraggingChange={setPaneResizing}
          />
        ) : layoutMode === "desktop" ? (
          <div
            className="journey-pane-splitter-spacer"
            data-testid="journey-splitter-inspector-spacer"
            style={{ gridColumn: gridRightSplitCol, gridRow: 1 }}
            aria-hidden="true"
          />
        ) : null}

        {showDesktopInspector ? (
          <aside
            className="journey-inspector-pane"
            data-testid="journey-inspector-pane"
            data-dock="right"
            data-detail-state="expanded"
            style={{ gridColumn: gridInspectorCol, gridRow: 1 }}
          >
            <div className="journey-inspector-drawer-header" data-testid="journey-inspector-drawer-header">
              <button
                type="button"
                className="journey-collapse-inspector-btn"
                data-testid="journey-collapse-inspector"
                aria-label="收起旅程详情"
                onClick={handleToggleInspector}
              >
                收起详情
              </button>
            </div>
            {inspectorBody}
          </aside>
        ) : layoutMode === "desktop" ? (
          <div
            className="journey-inspector-pane-spacer"
            data-testid="journey-inspector-pane-spacer"
            style={{ gridColumn: gridInspectorCol, gridRow: 1 }}
            aria-hidden="true"
          />
        ) : null}

        {narrowDrawerOpen ? (
          <aside
            className="journey-inspector-pane"
            data-testid="journey-inspector-pane"
            data-dock="tab"
            data-detail-state="drawer-open"
            style={{ gridColumn: 1, gridRow: 1 }}
          >
            <div className="journey-inspector-drawer-header" data-testid="journey-inspector-drawer-header">
              <button
                type="button"
                className="journey-collapse-inspector-btn"
                data-testid="journey-collapse-inspector"
                aria-label="收起旅程详情"
                onClick={handleToggleInspector}
              >
                收起详情
              </button>
            </div>
            {inspectorBody}
          </aside>
        ) : null}

        <div
          data-testid="journey-resizable-split"
          data-inspector-collapsed={detailVisible ? "false" : "true"}
          data-detail-visible={detailVisible ? "true" : "false"}
          className="journey-layout-compat-split"
          aria-hidden="true"
        />
      </div>

      {exportMessage && (
        <div
          className="journey-export-feedback"
          data-testid="journey-export-feedback"
          data-status={exportStatus === "failed" ? "failed" : "succeeded"}
          role="status"
        >
          {exportMessage}
        </div>
      )}

      {/* Offscreen full-journey chart for PNG export (independent of viewport zoom). */}
      <div
        ref={exportFullRootRef}
        className="journey-export-full-root"
        data-testid="journey-export-full-root"
        data-reader-journey-export-root="true"
        aria-hidden="true"
      >
        <h2 data-testid="journey-export-full-title">阅读旅程 · 完整旅程</h2>
        <p data-testid="journey-export-full-meta">
          {chapterHeading} · {sceneCount} 个场景 · Y轴 0—100 · viz 4.2
        </p>
        <CanonicalJourneyChart
          visualization={visualization}
          metric={metric}
          observationLens={observationLens}
          overlayComposite={overlayComposite}
          chartHeight={chartHeightPx("standard")}
          yDomainMode="fixed_0_100"
          viewStart={1}
          viewEnd={Math.max(sceneCount, 1)}
          onViewChange={() => undefined}
          selectedSceneOrdinal={null}
          selectedPhaseOrdinal={null}
          markerMode={markerMode}
          exportFullJourney
          onSelectScene={() => undefined}
          onSelectRisk={() => undefined}
          onSelectHook={() => undefined}
          onSelectPayoff={() => undefined}
        />
      </div>
    </div>
  );
}
