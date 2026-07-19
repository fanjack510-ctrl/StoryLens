import {
  useCallback,
  useEffect,
  useId,
  useRef,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import type { JourneyCurveMetric } from "../../types/readerJourneyVisualization";
import { ALL_METRIC_KEYS, METRIC_HINTS_ZH, METRIC_LABELS_ZH } from "./journeyUiLabels";

type Props = {
  open: boolean;
  metric: JourneyCurveMetric;
  onSelect: (metric: JourneyCurveMetric) => void;
  onClose: () => void;
  /** Id of the trigger button (aria-controls / focus return). */
  triggerId: string;
  /** Stable id for the listbox (aria-controls target). */
  listboxId?: string;
  /** Narrow layout uses single-column accordion style. */
  narrow?: boolean;
};

/**
 * In-document-flow metric selector panel (v4.2).
 * Opens below JourneyToolbar and pushes Phase/Chart down — never overlays.
 * No position:absolute/fixed, no elevated z-index.
 */
export function MetricSelectorPanel({
  open,
  metric,
  onSelect,
  onClose,
  triggerId,
  listboxId: listboxIdProp,
  narrow = false,
}: Props) {
  const generatedId = useId();
  const listboxId = listboxIdProp ?? generatedId;
  const listRef = useRef<HTMLDivElement>(null);
  const optionRefs = useRef<Map<JourneyCurveMetric, HTMLButtonElement>>(new Map());

  const focusOption = useCallback((key: JourneyCurveMetric) => {
    optionRefs.current.get(key)?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    focusOption(metric);
  }, [open, metric, focusOption]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (event: MouseEvent) => {
      const t = event.target as Node;
      const trigger = document.getElementById(triggerId);
      if (trigger?.contains(t)) return;
      if (listRef.current?.contains(t)) return;
      onClose();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onClose();
        document.getElementById(triggerId)?.focus();
      }
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, onClose, triggerId]);

  if (!open) return null;

  const moveFocus = (from: JourneyCurveMetric, delta: number) => {
    const idx = ALL_METRIC_KEYS.indexOf(from);
    if (idx < 0) return;
    const next = ALL_METRIC_KEYS[(idx + delta + ALL_METRIC_KEYS.length) % ALL_METRIC_KEYS.length];
    if (next) focusOption(next);
  };

  const onOptionKeyDown = (
    event: ReactKeyboardEvent<HTMLButtonElement>,
    key: JourneyCurveMetric,
  ) => {
    switch (event.key) {
      case "ArrowRight":
      case "ArrowDown":
        event.preventDefault();
        moveFocus(key, 1);
        break;
      case "ArrowLeft":
      case "ArrowUp":
        event.preventDefault();
        moveFocus(key, -1);
        break;
      case "Home":
        event.preventDefault();
        focusOption(ALL_METRIC_KEYS[0]!);
        break;
      case "End":
        event.preventDefault();
        focusOption(ALL_METRIC_KEYS[ALL_METRIC_KEYS.length - 1]!);
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        onSelect(key);
        break;
      case "Escape":
        event.preventDefault();
        onClose();
        document.getElementById(triggerId)?.focus();
        break;
      case "Tab":
        onClose();
        break;
      default:
        break;
    }
  };

  return (
    <div
      ref={listRef}
      id={listboxId}
      className={`journey-metric-selector-panel${narrow ? " is-narrow" : ""}`}
      data-testid="journey-metric-select-menu"
      data-metric-panel="in-flow"
      role="listbox"
      aria-label="选择当前指标"
      aria-labelledby={triggerId}
    >
      <div className="journey-metric-selector-grid" data-testid="journey-metric-selector-grid">
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
              className={`journey-metric-selector-option${selected ? " is-selected" : ""}`}
              aria-selected={selected}
              tabIndex={selected ? 0 : -1}
              ref={(el) => {
                if (el) optionRefs.current.set(key, el);
                else optionRefs.current.delete(key);
              }}
              onClick={() => onSelect(key)}
              onKeyDown={(event) => onOptionKeyDown(event, key)}
            >
              <span className="journey-metric-selector-option-label">{label}</span>
              {hint ? (
                <span className="journey-metric-selector-option-hint">{hint}</span>
              ) : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}
