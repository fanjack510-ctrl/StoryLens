import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import type { JourneyCurveMetric } from "../../types/readerJourneyVisualization";
import { JourneyPopover } from "./JourneyPopover";
import {
  ALL_METRIC_KEYS,
  METRIC_HINTS_ZH,
  METRIC_LABELS_ZH,
  formatJourneyMetricLabel,
} from "./journeyUiLabels";
import type {
  ChartHeightPreset,
  YDomainMode,
} from "./journeyVisualizationConfig";
import {
  DEFAULT_OBSERVATION_LENS,
  OBSERVATION_LENSES,
  getObservationLens,
  getObservationLensHint,
  type ObservationLensId,
} from "./observationLenses";
import {
  COMPARE_CANDIDATE_METRICS,
  buildComparisonState,
  type CompareMetricKey,
} from "./comparisonState";
import {
  EXIT_COMPARE_LABEL,
  OVERLAY_COMPARE_TITLE,
  START_COMPARE_LABEL,
} from "./readerJourneyLensExplanation";

type Props = {
  metric: JourneyCurveMetric;
  onMetricChange: (metric: JourneyCurveMetric) => void;
  observationLens?: ObservationLensId;
  onObservationLensChange?: (lens: ObservationLensId) => void;
  /**
   * What the main curve is called for this book, from the backend (INV-P4).
   *
   * Six lenses at one visual tier made the reader pick a viewpoint before knowing what any
   * of them meant, and on 42 real scenes they are largely one signal anyway (好奇×钩子
   * r=+0.91). One named main line answers 「读者还想不想读下去」 and the other five become the
   * decomposition of that answer.
   */
  mainCurveLabel?: string;
  mainCurveWhy?: string;
  /**
   * What the hook lens is called for this book. 「钩子回收」 is the suspense reading of it, the
   * same way 「提出疑问」 was of its first action; on a romance chapter whose scenes are already
   * labelled 起了心结 / 挑明, a button still reading 钩子回收 puts two vocabularies on one screen.
   */
  hookLensLabel?: string;
  /** @deprecated Prefer compareWith — kept for call-site compat. */
  overlayComposite?: boolean;
  onOverlayCompositeChange?: (enabled: boolean) => void;
  compareWith?: CompareMetricKey | string | null;
  onCompareWithChange?: (metric: CompareMetricKey | null) => void;
  heightPreset: ChartHeightPreset;
  onHeightPresetChange: (preset: ChartHeightPreset) => void;
  yDomainMode: YDomainMode;
  onYDomainModeChange: (mode: YDomainMode) => void;
  canPanZoom: boolean;
  showBrush: boolean;
  showZoomControls: boolean;
  onFitAll?: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFocusPhase: () => void;
  onResetView: () => void;
  onResetPaneWidths?: () => void;
  inspectorCollapsed: boolean;
  onToggleInspector: () => void;
  sourceCollapsed?: boolean;
  onToggleSource?: () => void;
  showSourceToggle?: boolean;
  onExportPng: () => void;
  exportBusy?: boolean;
  compactActions?: boolean;
  narrowLayout?: boolean;
  /** @deprecated Analysis info is developer/settings only — not shown in ordinary topbar. */
  analysisInfoContent?: ReactNode;
};

/**
 * Single topbar: six Lenses (left) + 收起详情 / 对比分析 (right), same visual tier.
 */
export function JourneyChartToolbar({
  metric,
  onMetricChange,
  observationLens = DEFAULT_OBSERVATION_LENS,
  mainCurveLabel,
  mainCurveWhy,
  hookLensLabel,
  onObservationLensChange,
  overlayComposite = false,
  onOverlayCompositeChange,
  compareWith = null,
  onCompareWithChange,
  heightPreset,
  onHeightPresetChange,
  yDomainMode,
  onYDomainModeChange,
  canPanZoom,
  showBrush,
  showZoomControls,
  onFitAll,
  onZoomIn,
  onZoomOut,
  onFocusPhase,
  onResetView,
  onResetPaneWidths,
  inspectorCollapsed,
  onToggleInspector,
  onExportPng,
  exportBusy = false,
  analysisInfoContent = null,
}: Props) {
  const [metricOpen, setMetricOpen] = useState(false);
  const [comparePanelOpen, setComparePanelOpen] = useState(false);
  const [pendingCompare, setPendingCompare] = useState<CompareMetricKey | null>(
    null,
  );
  const metricTriggerId = useId();
  const compareTriggerId = useId();
  const comparePanelTitleId = useId();
  const compareTriggerRef = useRef<HTMLButtonElement | null>(null);
  const lensListRef = useRef<HTMLDivElement | null>(null);

  void overlayComposite;
  void onOverlayCompositeChange;
  void onFitAll;
  void analysisInfoContent;
  void exportBusy;
  void onExportPng;
  void heightPreset;
  void onHeightPresetChange;
  void yDomainMode;
  void onYDomainModeChange;
  void onResetPaneWidths;
  void showZoomControls;

  const useLenses = typeof onObservationLensChange === "function";
  const lensDef = getObservationLens(observationLens);
  const metricLabel = formatJourneyMetricLabel(metric);
  const inspectorLabel = inspectorCollapsed ? "展开详情" : "收起详情";
  // Falls back to the shipped wording when the backend has nothing to say — which is the
  // honest answer for a book whose profile is not confirmed: without one there is no basis
  // for claiming which decision this reader is making.
  const foldedLenses = OBSERVATION_LENSES.filter(
    (item) => item.tier === "folded" && item.id !== observationLens,
  );
  const mainLabel =
    mainCurveLabel || getObservationLens(DEFAULT_OBSERVATION_LENS).labelZh;
  const mainWhy = mainCurveWhy || "";
  const lensLabelFor = (id: ObservationLensId, fallback: string) =>
    id === "hook_payoff" && hookLensLabel ? hookLensLabel : fallback;
  const comparison = buildComparisonState(observationLens, compareWith);
  const compareEnabled =
    !lensDef.isPairedHookPayoff && typeof onCompareWithChange === "function";
  const compareActive = comparison.mode === "active";

  useEffect(() => {
    if (!comparePanelOpen) setPendingCompare(null);
  }, [comparePanelOpen]);

  useEffect(() => {
    if (!compareEnabled && comparePanelOpen) setComparePanelOpen(false);
  }, [compareEnabled, comparePanelOpen]);

  useEffect(() => {
    const list = lensListRef.current;
    if (!list) return;
    const active = list.querySelector<HTMLElement>(
      `[data-testid="journey-lens-${lensDef.id}"]`,
    );
    active?.scrollIntoView({
      inline: "nearest",
      block: "nearest",
      behavior: "smooth",
    });
  }, [lensDef.id]);

  const handleMetricSelect = (key: JourneyCurveMetric) => {
    onMetricChange(key);
    setMetricOpen(false);
  };

  const handleLensSelect = (id: ObservationLensId) => {
    onObservationLensChange?.(id);
  };

  const openComparePanel = (open: boolean) => {
    setComparePanelOpen(open);
    if (open) {
      setPendingCompare(compareActive ? comparison.compareMetric : null);
    }
  };

  const confirmCompare = () => {
    if (!pendingCompare || pendingCompare === lensDef.primaryKey) return;
    onCompareWithChange?.(pendingCompare);
    setComparePanelOpen(false);
    compareTriggerRef.current?.focus();
  };

  const cancelComparePanel = () => {
    setComparePanelOpen(false);
    setPendingCompare(null);
    compareTriggerRef.current?.focus();
  };

  const exitCompare = () => {
    onCompareWithChange?.(null);
    setComparePanelOpen(false);
  };

  const compareSelectorPanel = (
    <div
      className="journey-compare-picker"
      data-testid="journey-compare-selector-list"
      role="dialog"
      aria-labelledby={comparePanelTitleId}
    >
      <h4 id={comparePanelTitleId} className="journey-compare-picker-title">
        选择对比指标
      </h4>
      <p
        className="journey-compare-picker-primary"
        data-testid="journey-compare-primary-label"
      >
        当前主指标
        <br />
        <span aria-current="true">● {lensDef.labelZh}</span>
      </p>
      <p className="journey-compare-picker-secondary-label">选择第二个指标</p>
      <div
        role="radiogroup"
        aria-label="选择第二个指标"
        className="journey-compare-picker-options"
      >
        {COMPARE_CANDIDATE_METRICS.map(({ key, label }) => {
          const disabled = key === lensDef.primaryKey;
          const selected = pendingCompare === key;
          return (
            <button
              key={key}
              type="button"
              role="radio"
              className={selected ? "active" : ""}
              data-testid={`journey-compare-${key}`}
              aria-checked={selected}
              aria-disabled={disabled}
              disabled={disabled}
              onClick={() => {
                if (!disabled) setPendingCompare(key);
              }}
            >
              {selected ? "● " : "○ "}
              {label}
            </button>
          );
        })}
      </div>
      <div className="journey-compare-picker-actions">
        <button
          type="button"
          className="journey-toolbar-btn"
          data-testid="journey-compare-cancel"
          onClick={cancelComparePanel}
        >
          取消
        </button>
        <button
          type="button"
          className="journey-toolbar-btn journey-lens-segment active"
          data-testid="journey-compare-confirm"
          disabled={!pendingCompare || pendingCompare === lensDef.primaryKey}
          onClick={confirmCompare}
        >
          {START_COMPARE_LABEL}
        </button>
      </div>
    </div>
  );

  const lensSegmented = (
    <div
      className="journey-topbar__lenses journey-lens-select-inline"
      data-testid="journey-lens-select-menu"
      data-lens-layout="inline-segmented"
    >
      <div
        role="radiogroup"
        aria-label="观察镜头"
        className="journey-lens-segmented"
        data-testid="journey-lens-select"
        data-current-lens={lensDef.id}
      >
        <div
          ref={lensListRef}
          role="presentation"
          className="journey-lens-selector-list"
          data-testid="journey-lens-selector-list"
          data-lens-panel="inline"
        >
          {OBSERVATION_LENSES.filter(
            // The folded three stay reachable behind 更多视角 — see ObservationLensDef.tier
            // for the measurement. A folded lens that is currently selected still shows,
            // so a saved URL never lands on a control the reader cannot see.
            (item) => item.tier !== "folded" || lensDef.id === item.id,
          ).map((item) => {
            const selected = lensDef.id === item.id;
            const isMain = item.id === DEFAULT_OBSERVATION_LENS;
            return (
              <button
                key={item.id}
                type="button"
                role="radio"
                data-testid={`journey-lens-${item.id}`}
                className={
                  `journey-toolbar-btn journey-lens-segment ` +
                  `${selected ? "active" : ""} ${isMain ? "journey-lens-main" : "journey-lens-part"}`
                }
                aria-checked={selected}
                aria-current={selected ? "true" : undefined}
                aria-label={
                  isMain ? mainLabel : lensLabelFor(item.id, item.labelZh)
                }
                title={
                  isMain
                    ? [mainLabel, mainWhy, getObservationLensHint(item.id)]
                        .filter(Boolean)
                        .join("\n")
                    : `${lensLabelFor(item.id, item.labelZh)}\n${getObservationLensHint(item.id)}`
                }
                onClick={() => handleLensSelect(item.id)}
              >
                {isMain ? mainLabel : lensLabelFor(item.id, item.labelZh)}
              </button>
            );
          })}
        </div>
      </div>

      {foldedLenses.length ? (
        <details className="journey-lens-more" data-testid="journey-lens-more">
          <summary>更多视角</summary>
          <div className="journey-lens-more-body">
            <p className="journey-lens-more-note">
              这三项与主线或彼此高度重合（实测
              r=0.70–0.91），已并入主线的归因；需要单独看时在这里打开。
            </p>
            {foldedLenses.map((item) => (
              <button
                key={item.id}
                type="button"
                data-testid={`journey-lens-${item.id}`}
                className="journey-toolbar-btn journey-lens-segment journey-lens-part"
                onClick={() => handleLensSelect(item.id)}
              >
                {lensLabelFor(item.id, item.labelZh)}
              </button>
            ))}
          </div>
        </details>
      ) : null}
    </div>
  );

  const metricMenu = (
    <JourneyPopover
      open={metricOpen}
      onOpenChange={setMetricOpen}
      align="start"
      data-testid="journey-metric-select-menu"
      menuLabel="选择指标"
      trigger={
        <button
          type="button"
          id={metricTriggerId}
          className={`journey-toolbar-btn journey-toolbar-btn-select ${metricOpen ? "active" : ""}`}
          data-testid="journey-metric-select"
          data-current-metric={metric}
          title={`指标：${metricLabel}`}
          aria-label={`指标：${metricLabel}`}
          aria-expanded={metricOpen}
          aria-haspopup="listbox"
          onClick={() => setMetricOpen((v) => !v)}
        >
          <span className="journey-toolbar-btn-label">指标</span>
          <span className="journey-toolbar-btn-sep" aria-hidden="true">
            ：
          </span>
          <span className="journey-toolbar-btn-value">{metricLabel}</span>
        </button>
      }
    >
      <div
        role="listbox"
        aria-label="选择指标"
        data-metric-panel="popover"
        data-testid="journey-metric-selector-list"
      >
        {ALL_METRIC_KEYS.map((key) => {
          const selected = metric === key;
          const label = METRIC_LABELS_ZH[key];
          const hint = METRIC_HINTS_ZH[key];
          return (
            <button
              key={key}
              type="button"
              role="option"
              data-testid={`journey-metric-${key}`}
              className={selected ? "active" : ""}
              aria-selected={selected}
              onClick={() => handleMetricSelect(key)}
            >
              <span className="journey-metric-option-label">{label}</span>
              {hint ? (
                <span className="journey-metric-option-hint">{hint}</span>
              ) : null}
            </button>
          );
        })}
      </div>
    </JourneyPopover>
  );

  const compareAction = compareEnabled ? (
    compareActive ? (
      <button
        type="button"
        ref={compareTriggerRef}
        id={compareTriggerId}
        className="journey-toolbar-btn journey-lens-segment active"
        data-testid="journey-comparison-exit"
        data-compare-with={comparison.compareMetric}
        aria-pressed="true"
        aria-label={EXIT_COMPARE_LABEL}
        title={EXIT_COMPARE_LABEL}
        onClick={exitCompare}
      >
        {EXIT_COMPARE_LABEL}
      </button>
    ) : (
      <JourneyPopover
        open={comparePanelOpen}
        onOpenChange={openComparePanel}
        align="end"
        data-testid="journey-compare-select-menu"
        menuLabel="选择对比指标"
        trigger={
          <button
            type="button"
            ref={compareTriggerRef}
            id={compareTriggerId}
            className={`journey-toolbar-btn journey-lens-segment ${comparePanelOpen ? "active" : ""}`}
            data-testid="journey-overlay-composite"
            data-compare-with=""
            aria-pressed="false"
            aria-expanded={comparePanelOpen}
            aria-label={OVERLAY_COMPARE_TITLE}
            title={OVERLAY_COMPARE_TITLE}
            onClick={() => openComparePanel(!comparePanelOpen)}
          >
            {OVERLAY_COMPARE_TITLE}
          </button>
        }
      >
        {compareSelectorPanel}
      </JourneyPopover>
    )
  ) : null;

  return (
    <div
      className={`journey-toolbar-region journey-topbar${useLenses ? " journey-toolbar-region-with-lenses" : ""}`}
      data-testid="journey-toolbar-region"
      data-topbar="unified"
      data-metric-panel-open={metricOpen ? "true" : "false"}
      data-observation-lens={useLenses ? lensDef.id : undefined}
      data-lens-layout={useLenses ? "inline-segmented" : undefined}
      data-compare-enabled={compareEnabled ? "true" : "false"}
      data-compare-active={compareActive ? "true" : "false"}
    >
      <div
        className="journey-curve-toolbar journey-viz-toolbar journey-topbar__row"
        data-testid="journey-curve-toolbar"
        data-visualization-version="4.2"
        role="toolbar"
        aria-label="阅读旅程顶部操作"
      >
        <div
          className="journey-toolbar-left journey-topbar__lenses-wrap"
          data-testid="journey-metric-switcher"
        >
          {useLenses ? lensSegmented : metricMenu}
          {useLenses ? (
            <span hidden aria-hidden="true">
              {metricMenu}
            </span>
          ) : null}
        </div>
        <div
          className="journey-toolbar-right journey-topbar__actions"
          data-testid="journey-toolbar-right"
        >
          <button
            type="button"
            className="journey-toolbar-btn journey-lens-segment"
            data-testid="journey-inspector-toggle"
            aria-pressed={!inspectorCollapsed}
            onClick={onToggleInspector}
          >
            {inspectorLabel}
          </button>
          {compareAction}
          {/* Compatibility: compare entry moved into topbar actions (not a secondary rail). */}
          <span
            hidden
            aria-hidden="true"
            data-testid="journey-chart-tools"
            data-tools-relocated="topbar"
          />
          {compareActive ? (
            <span
              hidden
              aria-hidden="true"
              data-testid="journey-overlay-composite"
              data-compare-with={comparison.compareMetric}
            />
          ) : null}
        </div>
        <div data-testid="journey-zoom-controls" hidden aria-hidden="true" />
        <button
          type="button"
          hidden
          aria-hidden="true"
          data-testid="journey-zoom-focus-phase"
          onClick={onFocusPhase}
        >
          当前阶段
        </button>
        <button
          type="button"
          hidden
          aria-hidden="true"
          data-testid="journey-all-metrics"
        >
          全部指标
        </button>
        <button
          type="button"
          hidden
          aria-hidden="true"
          data-testid="journey-zoom-in"
          onClick={onZoomIn}
          disabled={!canPanZoom && !showBrush}
        >
          放大
        </button>
        <button
          type="button"
          hidden
          aria-hidden="true"
          data-testid="journey-zoom-out"
          onClick={onZoomOut}
          disabled={!canPanZoom && !showBrush}
        >
          缩小
        </button>
        <button
          type="button"
          hidden
          aria-hidden="true"
          data-testid="journey-zoom-reset"
          onClick={onResetView}
        >
          恢复默认
        </button>
      </div>
      <span hidden aria-hidden="true" data-testid="journey-metric-keys-audit">
        {ALL_METRIC_KEYS.join(",")}
      </span>
      <span hidden aria-hidden="true" data-testid="journey-lens-keys-audit">
        {OBSERVATION_LENSES.map((item) => item.id).join(",")}
      </span>
    </div>
  );
}
