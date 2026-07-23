import { useEffect, useId, useRef, useState } from "react";
import { JourneyPopover } from "./JourneyPopover";
import {
  COMPARE_CANDIDATE_METRICS,
  buildComparisonState,
  type CompareMetricKey,
  type ComparisonState,
} from "./comparisonState";
import {
  CHANGE_COMPARE_LABEL,
  EXIT_COMPARE_LABEL,
  OVERLAY_COMPARE_TITLE,
  RESET_VIEW_LABEL,
  START_COMPARE_LABEL,
} from "./readerJourneyLensExplanation";
import { getObservationLens, type ObservationLensId } from "./observationLenses";

type Props = {
  observationLens: ObservationLensId;
  compareWith: string | null;
  onCompareWithChange: (metric: CompareMetricKey | null) => void;
  resetViewEnabled: boolean;
  onResetView: () => void;
  liveMessage?: string | null;
};

/**
 * Chart tools outside the main Lens bar: 对比分析 + 重置视图,
 * plus a persistent comparison status strip when active.
 */
export function JourneyComparisonTools({
  observationLens,
  compareWith,
  onCompareWithChange,
  resetViewEnabled,
  onResetView,
  liveMessage = null,
}: Props) {
  const lens = getObservationLens(observationLens);
  const comparison: ComparisonState = buildComparisonState(observationLens, compareWith);
  const compareEnabled = !lens.isPairedHookPayoff;
  const [panelOpen, setPanelOpen] = useState(false);
  const [pending, setPending] = useState<CompareMetricKey | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const panelTitleId = useId();
  const triggerId = useId();

  useEffect(() => {
    if (!panelOpen) setPending(null);
  }, [panelOpen]);

  useEffect(() => {
    if (!compareEnabled && panelOpen) setPanelOpen(false);
  }, [compareEnabled, panelOpen]);

  if (!compareEnabled && !resetViewEnabled && !liveMessage) {
    return null;
  }

  const openPanel = (open: boolean) => {
    setPanelOpen(open);
    if (open) {
      setPending(comparison.mode === "active" ? comparison.compareMetric : null);
    }
  };

  const confirmStart = () => {
    if (!pending || pending === lens.primaryKey) return;
    onCompareWithChange(pending);
    setPanelOpen(false);
    triggerRef.current?.focus();
  };

  const cancelPanel = () => {
    setPanelOpen(false);
    setPending(null);
    triggerRef.current?.focus();
  };

  const exitCompare = () => {
    onCompareWithChange(null);
    setPanelOpen(false);
  };

  const selectorPanel = (
    <div
      className="journey-compare-picker"
      data-testid="journey-compare-selector-list"
      role="dialog"
      aria-labelledby={panelTitleId}
    >
      <h4 id={panelTitleId} className="journey-compare-picker-title">
        选择对比指标
      </h4>
      <p className="journey-compare-picker-primary" data-testid="journey-compare-primary-label">
        当前主指标
        <br />
        <span aria-current="true">● {lens.labelZh}</span>
      </p>
      <p className="journey-compare-picker-secondary-label">选择第二个指标</p>
      <div role="radiogroup" aria-label="选择第二个指标" className="journey-compare-picker-options">
        {COMPARE_CANDIDATE_METRICS.map(({ key, label }) => {
          const disabled = key === lens.primaryKey;
          const selected = pending === key;
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
                if (!disabled) setPending(key);
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
          className="journey-tool-btn"
          data-testid="journey-compare-cancel"
          onClick={cancelPanel}
        >
          取消
        </button>
        <button
          type="button"
          className="journey-tool-btn journey-tool-btn-primary"
          data-testid="journey-compare-confirm"
          disabled={!pending || pending === lens.primaryKey}
          onClick={confirmStart}
        >
          {START_COMPARE_LABEL}
        </button>
      </div>
    </div>
  );

  const compareTrigger = (
    <button
      type="button"
      ref={triggerRef}
      id={triggerId}
      className={`journey-tool-btn${comparison.mode === "active" ? " is-active" : ""}`}
      data-testid={
        comparison.mode === "active" ? "journey-comparison-change" : "journey-overlay-composite"
      }
      data-compare-with={comparison.mode === "active" ? comparison.compareMetric : ""}
      aria-pressed={comparison.mode === "active"}
      aria-expanded={panelOpen}
      aria-label={comparison.mode === "active" ? CHANGE_COMPARE_LABEL : OVERLAY_COMPARE_TITLE}
      title={comparison.mode === "active" ? CHANGE_COMPARE_LABEL : OVERLAY_COMPARE_TITLE}
      onClick={() => openPanel(!panelOpen)}
    >
      {comparison.mode === "active" ? CHANGE_COMPARE_LABEL : OVERLAY_COMPARE_TITLE}
    </button>
  );

  return (
    <div className="journey-comparison-tools" data-testid="journey-comparison-tools">
      {liveMessage ? (
        <p className="journey-compare-live" data-testid="journey-compare-live" aria-live="polite">
          {liveMessage}
        </p>
      ) : null}

      {comparison.mode === "active" ? (
        <div
          className="journey-comparison-toolbar"
          data-testid="journey-comparison-toolbar"
          data-comparison-mode="active"
          data-compare-with={comparison.compareMetric}
          role="status"
          aria-label={`对比模式：${comparison.primaryLabel} 与 ${comparison.compareLabel}`}
        >
          <span
            hidden
            data-testid="journey-overlay-composite"
            data-compare-with={comparison.compareMetric}
          />
          <div className="journey-comparison-active" data-testid="journey-comparison-active">
            <strong>对比模式：</strong>
            {comparison.primaryLabel} × {comparison.compareLabel}
          </div>
          <ul className="journey-comparison-line-legend" data-testid="journey-comparison-line-legend">
            <li data-line="primary">● 绿色实线：{comparison.primaryLabel}</li>
            <li data-line="compare">┄ 紫色虚线：{comparison.compareLabel}</li>
          </ul>
          <div className="journey-comparison-actions">
            <JourneyPopover
              open={panelOpen}
              onOpenChange={openPanel}
              align="end"
              data-testid="journey-compare-select-menu"
              menuLabel="选择对比指标"
              trigger={compareTrigger}
            >
              {selectorPanel}
            </JourneyPopover>
            <button
              type="button"
              className="journey-tool-btn"
              data-testid="journey-comparison-exit"
              aria-label={EXIT_COMPARE_LABEL}
              onClick={exitCompare}
            >
              {EXIT_COMPARE_LABEL}
            </button>
            <button
              type="button"
              className="journey-tool-btn"
              hidden
              data-testid="journey-compare-none"
              onClick={exitCompare}
            >
              {EXIT_COMPARE_LABEL}
            </button>
          </div>
        </div>
      ) : compareEnabled || resetViewEnabled ? (
        <div
          className="journey-chart-analysis-tools"
          data-testid="journey-chart-analysis-tools"
          data-comparison-mode="inactive"
        >
          {compareEnabled ? (
            <JourneyPopover
              open={panelOpen}
              onOpenChange={openPanel}
              align="end"
              data-testid="journey-compare-select-menu"
              menuLabel="选择对比指标"
              trigger={compareTrigger}
            >
              {selectorPanel}
            </JourneyPopover>
          ) : null}
          {resetViewEnabled ? (
            <button
              type="button"
              className="journey-tool-btn"
              data-testid="journey-zoom-fit-all"
              title={RESET_VIEW_LABEL}
              aria-label={RESET_VIEW_LABEL}
              onClick={onResetView}
            >
              {RESET_VIEW_LABEL}
            </button>
          ) : null}
        </div>
      ) : null}

      {comparison.mode === "active" && resetViewEnabled ? (
        <div className="journey-chart-analysis-tools-secondary">
          <button
            type="button"
            className="journey-tool-btn"
            data-testid="journey-zoom-fit-all"
            title={RESET_VIEW_LABEL}
            aria-label={RESET_VIEW_LABEL}
            onClick={onResetView}
          >
            {RESET_VIEW_LABEL}
          </button>
        </div>
      ) : null}
    </div>
  );
}
