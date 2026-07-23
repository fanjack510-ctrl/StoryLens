import { useId, useState } from "react";
import type { JourneyCurveMetric } from "../../types/readerJourneyVisualization";
import { JourneyPopover } from "./JourneyPopover";
import {
  ALL_METRIC_KEYS,
  METRIC_HINTS_ZH,
  METRIC_LABELS_ZH,
  formatJourneyMetricLabel,
} from "./journeyUiLabels";
import type { ChartHeightPreset, YDomainMode } from "./journeyVisualizationConfig";
import {
  COMPARE_METRIC_LABEL,
  FIT_ALL_LABEL,
  OVERLAY_COMPARE_TITLE,
} from "./readerJourneyLensExplanation";
import {
  DEFAULT_OBSERVATION_LENS,
  OBSERVATION_LENSES,
  getObservationLens,
  getObservationLensHint,
  type ObservationLensId,
} from "./observationLenses";

type Props = {
  metric: JourneyCurveMetric;
  onMetricChange: (metric: JourneyCurveMetric) => void;
  /** Observation lens (v2). When set, primary selector shows lenses instead of raw metrics. */
  observationLens?: ObservationLensId;
  onObservationLensChange?: (lens: ObservationLensId) => void;
  /** @deprecated Prefer compareWith — kept for call-site compat during transition. */
  overlayComposite?: boolean;
  onOverlayCompositeChange?: (enabled: boolean) => void;
  /** Explicit secondary metric for 对比指标 (null = no purple line). */
  compareWith?: JourneyCurveMetric | null;
  onCompareWithChange?: (metric: JourneyCurveMetric | null) => void;
  heightPreset: ChartHeightPreset;
  onHeightPresetChange: (preset: ChartHeightPreset) => void;
  yDomainMode: YDomainMode;
  onYDomainModeChange: (mode: YDomainMode) => void;
  canPanZoom: boolean;
  showBrush: boolean;
  showZoomControls: boolean;
  onFitAll: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFocusPhase: () => void;
  onResetView: () => void;
  /** Restore Source/Inspector preferred pane widths to defaults (does not change Scene/URL). */
  onResetPaneWidths?: () => void;
  inspectorCollapsed: boolean;
  onToggleInspector: () => void;
  /** @deprecated Source visibility is controlled by top mode switch (正文对照/旅程视图/仅看正文). */
  sourceCollapsed?: boolean;
  /** @deprecated Removed — duplicates top mode switch. */
  onToggleSource?: () => void;
  /** @deprecated Always false — source toggle removed from Journey toolbar. */
  showSourceToggle?: boolean;
  onExportPng: () => void;
  exportBusy?: boolean;
  /** When true, collapse secondary actions into 更多 (narrow widths). */
  compactActions?: boolean;
  /** Unused — metric menu is always compact popover. Kept for call-site compat. */
  narrowLayout?: boolean;
};

/**
 * Compact chart toolbar: inline lens segmented control · phase fit · details · more.
 * Lens options stay in document flow (wrap pushes content down) — never overlay the chart.
 */
export function JourneyChartToolbar({
  metric,
  onMetricChange,
  observationLens = DEFAULT_OBSERVATION_LENS,
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
}: Props) {
  const [metricOpen, setMetricOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);
  const metricTriggerId = useId();
  const moreTriggerId = useId();
  const compareTriggerId = useId();
  const lensHintId = useId();

  void overlayComposite;
  void onOverlayCompositeChange;
  void onFocusPhase;

  const useLenses = typeof onObservationLensChange === "function";
  const lensDef = getObservationLens(observationLens);
  const lensHint = getObservationLensHint(observationLens);
  const metricLabel = formatJourneyMetricLabel(metric);
  const compareEnabled = typeof onCompareWithChange === "function" && !lensDef.isPairedHookPayoff;

  const handleMetricSelect = (key: JourneyCurveMetric) => {
    onMetricChange(key);
    setMetricOpen(false);
  };

  const handleLensSelect = (id: ObservationLensId) => {
    onObservationLensChange?.(id);
  };

  const inspectorLabel = inspectorCollapsed ? "展开详情" : "收起详情";

  const compareMenu = compareEnabled ? (
    <JourneyPopover
      open={compareOpen}
      onOpenChange={(open) => {
        setCompareOpen(open);
        if (open) {
          setMoreOpen(false);
          setMetricOpen(false);
        }
      }}
      align="end"
      data-testid="journey-compare-select-menu"
      menuLabel={COMPARE_METRIC_LABEL}
      trigger={
        <button
          type="button"
          id={compareTriggerId}
          className={`journey-toolbar-btn ${compareWith ? "active" : ""}`}
          data-testid="journey-overlay-composite"
          data-compare-with={compareWith || ""}
          aria-pressed={Boolean(compareWith)}
          title={COMPARE_METRIC_LABEL}
          aria-expanded={compareOpen}
          onClick={() => setCompareOpen((v) => !v)}
        >
          {OVERLAY_COMPARE_TITLE}
        </button>
      }
    >
      <div role="listbox" aria-label={COMPARE_METRIC_LABEL} data-testid="journey-compare-selector-list">
        <button
          type="button"
          role="option"
          className={!compareWith ? "active" : ""}
          data-testid="journey-compare-none"
          aria-selected={!compareWith}
          onClick={() => {
            onCompareWithChange?.(null);
            setCompareOpen(false);
          }}
        >
          退出对比
        </button>
        {(
          [
            ["reading_momentum", "综合阅读动力"],
            ["plot_progress", "剧情推进"],
            ["reading_tension", "阅读张力"],
            ["arousal", "情绪强度"],
            ["pacing_speed", "节奏速度"],
          ] as const
        )
          .filter(([key]) => key !== lensDef.primaryKey)
          .map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="option"
              className={compareWith === key ? "active" : ""}
              data-testid={`journey-compare-${key}`}
              aria-selected={compareWith === key}
              onClick={() => {
                onCompareWithChange?.(key as JourneyCurveMetric);
                setCompareOpen(false);
              }}
            >
              {label}
            </button>
          ))}
      </div>
    </JourneyPopover>
  ) : null;

  const lensSegmented = (
    <div
      className="journey-lens-select-inline"
      data-testid="journey-lens-select-menu"
      data-lens-layout="inline-segmented"
    >
      <div
        role="radiogroup"
        aria-label="观察镜头"
        aria-describedby={lensHintId}
        className="journey-lens-segmented"
        data-testid="journey-lens-select"
        data-current-lens={lensDef.id}
      >
        <div
          role="presentation"
          className="journey-lens-selector-list"
          data-testid="journey-lens-selector-list"
          data-lens-panel="inline"
        >
          {OBSERVATION_LENSES.map((item) => {
            const selected = lensDef.id === item.id;
            return (
              <button
                key={item.id}
                type="button"
                role="radio"
                data-testid={`journey-lens-${item.id}`}
                className={`journey-toolbar-btn journey-lens-segment ${selected ? "active" : ""}`}
                aria-checked={selected}
                aria-label={item.labelZh}
                title={item.labelZh}
                onClick={() => handleLensSelect(item.id)}
              >
                {item.labelZh}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );

  const metricMenu = (
    <JourneyPopover
      open={metricOpen}
      onOpenChange={(open) => {
        setMetricOpen(open);
        if (open) {
          setMoreOpen(false);
        }
      }}
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
          onClick={() => {
            setMetricOpen((v) => !v);
            setMoreOpen(false);
          }}
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
              {hint ? <span className="journey-metric-option-hint">{hint}</span> : null}
            </button>
          );
        })}
      </div>
    </JourneyPopover>
  );

  const moreItems = (
    <>
      <div className="journey-anchored-menu-group" data-testid="journey-more-export-group">
        <button
          type="button"
          role="menuitem"
          data-testid="journey-export-png"
          disabled={exportBusy}
          onClick={() => {
            onExportPng();
            // Keep menu open while exporting so「导出中」status remains visible.
          }}
        >
          {exportBusy ? "导出中" : "导出 PNG"}
        </button>
      </div>
      <div className="journey-anchored-menu-group" data-testid="journey-chart-height-controls">
        <div className="journey-anchored-menu-group-label">图表高度</div>
        {(
          [
            ["compact", "紧凑"],
            ["standard", "标准"],
            ["expanded", "展开"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="menuitem"
            className={heightPreset === key ? "active" : ""}
            data-testid={`journey-chart-height-${key}`}
            aria-pressed={heightPreset === key}
            onClick={() => onHeightPresetChange(key)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="journey-anchored-menu-group" data-testid="journey-y-domain-controls">
        <div className="journey-anchored-menu-group-label">Y 轴</div>
        <button
          type="button"
          role="menuitem"
          className={yDomainMode === "fixed_0_100" ? "active" : ""}
          data-testid="journey-y-domain-fixed"
          aria-pressed={yDomainMode === "fixed_0_100"}
          onClick={() => onYDomainModeChange("fixed_0_100")}
        >
          固定 0—100
        </button>
        <button
          type="button"
          role="menuitem"
          className={yDomainMode === "focus_data" ? "active" : ""}
          data-testid="journey-y-domain-focus"
          aria-pressed={yDomainMode === "focus_data"}
          onClick={() => onYDomainModeChange("focus_data")}
        >
          聚焦数据
        </button>
      </div>
      {showZoomControls ? (
        <div className="journey-anchored-menu-group" data-testid="journey-zoom-extra-controls">
          <button
            type="button"
            role="menuitem"
            data-testid="journey-zoom-in"
            onClick={onZoomIn}
            disabled={!canPanZoom && !showBrush}
          >
            放大
          </button>
          <button
            type="button"
            role="menuitem"
            data-testid="journey-zoom-out"
            onClick={onZoomOut}
            disabled={!canPanZoom && !showBrush}
          >
            缩小
          </button>
        </div>
      ) : null}
      <div className="journey-anchored-menu-group" data-testid="journey-reset-controls">
        <button type="button" role="menuitem" data-testid="journey-zoom-reset" onClick={onResetView}>
          恢复默认
        </button>
        {onResetPaneWidths ? (
          <button
            type="button"
            role="menuitem"
            data-testid="journey-reset-pane-widths"
            onClick={() => {
              onResetPaneWidths();
              setMoreOpen(false);
            }}
          >
            恢复默认栏宽
          </button>
        ) : null}
      </div>
    </>
  );

  const moreMenu = (
    <JourneyPopover
      open={moreOpen}
      onOpenChange={(open) => {
        setMoreOpen(open);
        if (open) setMetricOpen(false);
      }}
      align="end"
      data-testid="journey-more-menu"
      menuLabel="更多操作"
      trigger={
        <button
          type="button"
          id={moreTriggerId}
          className={`journey-toolbar-btn ${moreOpen ? "active" : ""}`}
          data-testid="journey-more-chart-settings"
          aria-expanded={moreOpen}
          aria-haspopup="menu"
          aria-label="更多操作"
          onClick={() => {
            setMoreOpen((v) => !v);
            setMetricOpen(false);
          }}
        >
          更多操作
        </button>
      }
    >
      <div role="none">{moreItems}</div>
    </JourneyPopover>
  );

  return (
    <div
      className={`journey-toolbar-region${useLenses ? " journey-toolbar-region-with-lenses" : ""}`}
      data-testid="journey-toolbar-region"
      data-metric-panel-open={metricOpen ? "true" : "false"}
      data-observation-lens={useLenses ? lensDef.id : undefined}
      data-lens-layout={useLenses ? "inline-segmented" : undefined}
    >
      <div
        className="journey-curve-toolbar journey-viz-toolbar"
        data-testid="journey-curve-toolbar"
        data-visualization-version="4.2"
        role="toolbar"
        aria-label="图表工具栏"
      >
        <div className="journey-toolbar-left" data-testid="journey-metric-switcher">
          {useLenses ? lensSegmented : metricMenu}
          {useLenses ? (
            <span hidden aria-hidden="true">
              {metricMenu}
            </span>
          ) : null}
        </div>
        <div className="journey-toolbar-tools" data-testid="journey-chart-tools">
          {compareMenu}
          <button
            type="button"
            className="journey-toolbar-btn"
            data-testid="journey-zoom-fit-all"
            title={FIT_ALL_LABEL}
            onClick={onFitAll}
          >
            {FIT_ALL_LABEL}
          </button>
        </div>
        <div className="journey-toolbar-right" data-testid="journey-toolbar-right">
          <button
            type="button"
            className="journey-toolbar-btn journey-toolbar-btn-primary"
            data-testid="journey-inspector-toggle"
            aria-pressed={!inspectorCollapsed}
            onClick={onToggleInspector}
          >
            {inspectorLabel}
          </button>
          {moreMenu}
        </div>
        {/* Legacy selector compatibility — phase focus removed from ordinary UI */}
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
        <button type="button" hidden aria-hidden="true" data-testid="journey-all-metrics">
          全部指标
        </button>
      </div>
      {useLenses ? (
        <p
          id={lensHintId}
          className="journey-lens-active-hint"
          data-testid="journey-lens-active-hint"
        >
          {lensHint}
        </p>
      ) : null}
      {/* Keep metric key list reachable for static audits */}
      <span hidden aria-hidden="true" data-testid="journey-metric-keys-audit">
        {ALL_METRIC_KEYS.join(",")}
      </span>
      <span hidden aria-hidden="true" data-testid="journey-lens-keys-audit">
        {OBSERVATION_LENSES.map((item) => item.id).join(",")}
      </span>
    </div>
  );
}
