import { useId, useState } from "react";
import type { JourneyCurveMetric } from "../../types/readerJourneyVisualization";
import { JourneyPopover } from "./JourneyPopover";
import { MetricSelectorPanel } from "./MetricSelectorPanel";
import { ALL_METRIC_KEYS, PRIMARY_JOURNEY_METRICS, PRIMARY_METRIC_LABELS_ZH, PRIMARY_METRIC_HINTS_ZH, formatJourneyMetricLabel } from "./journeyUiLabels";
import type { ChartHeightPreset, YDomainMode } from "./journeyVisualizationConfig";

type Props = {
  metric: JourneyCurveMetric;
  onMetricChange: (metric: JourneyCurveMetric) => void;
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
  sourceCollapsed?: boolean;
  onToggleSource?: () => void;
  showSourceToggle?: boolean;
  onExportPng: () => void;
  exportBusy?: boolean;
  /** When true, collapse secondary actions into 更多 (narrow widths). */
  compactActions?: boolean;
  /** <1100: full-width accordion-style metric panel. */
  narrowLayout?: boolean;
};

/**
 * Professional single-row chart toolbar (v4.2).
 * Metric opens an in-flow MetricSelectorPanel below the toolbar (never overlays Phase/Chart).
 * Secondary menus use Shared JourneyPopover via overlay-root.
 */
export function JourneyChartToolbar({
  metric,
  onMetricChange,
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
  sourceCollapsed = false,
  onToggleSource,
  showSourceToggle = false,
  onExportPng,
  exportBusy = false,
  compactActions = false,
  narrowLayout = false,
}: Props) {
  const [metricOpen, setMetricOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const metricTriggerId = useId();
  const moreTriggerId = useId();
  const metricPanelDomId = useId();

  const metricLabel = formatJourneyMetricLabel(metric);

  const handleMetricSelect = (key: JourneyCurveMetric) => {
    onMetricChange(key);
    setMetricOpen(false);
  };

  const primaryLeft = (
    <div className="journey-toolbar-left" data-testid="journey-metric-switcher">
      <div
        className="journey-metric-segmented"
        data-testid="journey-metric-segmented"
        role="tablist"
        aria-label="旅程指标"
      >
        {PRIMARY_JOURNEY_METRICS.map((key) => {
          const selected = metric === key;
          const label = PRIMARY_METRIC_LABELS_ZH[key];
          const hint = PRIMARY_METRIC_HINTS_ZH[key];
          return (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={selected}
              className={`journey-metric-segment${selected ? " is-selected" : ""}`}
              data-testid={`journey-metric-segment-${key}`}
              data-metric={key}
              title={hint}
              onClick={() => onMetricChange(key)}
            >
              {label}
            </button>
          );
        })}
      </div>
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
        aria-controls={metricOpen ? metricPanelDomId : undefined}
        onClick={() => {
          setMetricOpen((v) => !v);
          setMoreOpen(false);
        }}
      >
        <span className="journey-toolbar-btn-label">更多指标</span>
        <span className="journey-toolbar-btn-sep" aria-hidden="true">
          ·
        </span>
        <span className="journey-toolbar-btn-value">{metricLabel}</span>
      </button>
      <button
        type="button"
        className="journey-toolbar-btn"
        data-testid="journey-zoom-fit-all"
        onClick={onFitAll}
      >
        适应全部
      </button>
      <button
        type="button"
        className="journey-toolbar-btn"
        data-testid="journey-zoom-focus-phase"
        onClick={onFocusPhase}
      >
        当前阶段
      </button>
    </div>
  );

  const inspectorLabel = inspectorCollapsed ? "展开详情" : "收起详情";
  const sourceLabel = sourceCollapsed ? "展开正文" : "收起正文";

  const moreItems = (
    <>
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
        <div className="journey-anchored-menu-group-label">Y轴</div>
        <button
          type="button"
          role="menuitem"
          className={yDomainMode === "fixed_0_100" ? "active" : ""}
          data-testid="journey-y-domain-fixed"
          aria-pressed={yDomainMode === "fixed_0_100"}
          onClick={() => onYDomainModeChange("fixed_0_100")}
        >
          固定0—100
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
      {compactActions ? (
        <div className="journey-anchored-menu-group" data-testid="journey-more-secondary-actions">
          {showSourceToggle && onToggleSource ? (
            <button
              type="button"
              role="menuitem"
              data-testid="journey-source-toggle-menu"
              onClick={() => {
                onToggleSource();
                setMoreOpen(false);
              }}
            >
              {sourceLabel}
            </button>
          ) : null}
          <button
            type="button"
            role="menuitem"
            data-testid="journey-inspector-toggle-menu"
            onClick={() => {
              onToggleInspector();
              setMoreOpen(false);
            }}
          >
            {inspectorLabel}
          </button>
          <button
            type="button"
            role="menuitem"
            data-testid="journey-export-png-menu"
            disabled={exportBusy}
            onClick={() => {
              onExportPng();
              setMoreOpen(false);
            }}
          >
            {exportBusy ? "导出中" : "导出PNG"}
          </button>
        </div>
      ) : null}
    </>
  );

  const moreMenu = (
    <JourneyPopover
      open={moreOpen}
      onOpenChange={setMoreOpen}
      align="end"
      data-testid="journey-more-menu"
      menuLabel="更多设置"
      trigger={
        <button
          type="button"
          id={moreTriggerId}
          className={`journey-toolbar-btn ${moreOpen ? "active" : ""}`}
          data-testid="journey-more-chart-settings"
          aria-expanded={moreOpen}
          aria-haspopup="menu"
          aria-label="更多设置"
          onClick={() => {
            setMoreOpen((v) => !v);
            setMetricOpen(false);
          }}
        >
          更多设置
        </button>
      }
    >
      <div role="none">{moreItems}</div>
    </JourneyPopover>
  );

  return (
    <div
      className={`journey-toolbar-region${narrowLayout ? " is-narrow" : ""}`}
      data-testid="journey-toolbar-region"
      data-metric-panel-open={metricOpen ? "true" : "false"}
    >
      <div
        className={`journey-curve-toolbar journey-viz-toolbar ${compactActions ? "is-compact" : ""}`}
        data-testid="journey-curve-toolbar"
        data-visualization-version="4.2"
        role="toolbar"
        aria-label="图表工具栏"
      >
        {primaryLeft}
        <div className="journey-toolbar-right" data-testid="journey-toolbar-right">
          {!compactActions && showSourceToggle && onToggleSource ? (
            <button
              type="button"
              className="journey-toolbar-btn"
              data-testid="journey-source-toggle"
              aria-pressed={!sourceCollapsed}
              onClick={onToggleSource}
            >
              {sourceLabel}
            </button>
          ) : null}
          {!compactActions ? (
            <button
              type="button"
              className="journey-toolbar-btn journey-toolbar-btn-primary"
              data-testid="journey-inspector-toggle"
              aria-pressed={!inspectorCollapsed}
              onClick={onToggleInspector}
            >
              {inspectorLabel}
            </button>
          ) : null}
          {!compactActions ? (
            <button
              type="button"
              className="journey-toolbar-btn"
              data-testid="journey-export-png"
              disabled={exportBusy}
              aria-busy={exportBusy}
              onClick={onExportPng}
            >
              {exportBusy ? "导出中" : "导出PNG"}
            </button>
          ) : null}
          {moreMenu}
        </div>
        {/* Legacy selector compatibility */}
        <div data-testid="journey-zoom-controls" hidden aria-hidden="true" />
      </div>
      <MetricSelectorPanel
        open={metricOpen}
        metric={metric}
        onSelect={handleMetricSelect}
        onClose={() => setMetricOpen(false)}
        triggerId={metricTriggerId}
        listboxId={metricPanelDomId}
        narrow={narrowLayout}
      />
      {/* Keep metric key list reachable for static audits */}
      <span hidden aria-hidden="true" data-testid="journey-metric-keys-audit">
        {ALL_METRIC_KEYS.join(",")}
      </span>
    </div>
  );
}
