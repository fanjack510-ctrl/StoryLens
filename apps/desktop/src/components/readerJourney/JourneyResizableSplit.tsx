import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import { UI_PREF_KEYS } from "./journeyVisualizationConfig";

export const OVERVIEW_HEIGHT_STORAGE_KEY = UI_PREF_KEYS.overviewHeight;
/** Overview defaults high so the curve stays the page hero. */
export const DEFAULT_OVERVIEW_RATIO = 0.72;
/** Overview content is auto-sized; floor keeps resize clamp sane when Inspector expands. */
export const MIN_OVERVIEW_PX = 440;
export const MIN_DETAIL_PX = 200;
export const COLLAPSED_SUMMARY_PX = 44;

type StoredPreference = {
  ratio: number;
  viewportHeight: number;
  updatedAt: string;
};

type Props = {
  overview: ReactNode;
  detail: ReactNode;
  /** Compact summary shown when Inspector is collapsed (real height, not empty reserve). */
  collapsedSummary?: ReactNode;
  footer?: ReactNode;
  /** Content-area height hint; falls back to container measurement. */
  contentHeight?: number;
  inspectorCollapsed?: boolean;
  onInspectorCollapsedChange?: (collapsed: boolean) => void;
};

function readPreference(): StoredPreference | null {
  try {
    const raw = localStorage.getItem(OVERVIEW_HEIGHT_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredPreference;
    if (!Number.isFinite(parsed.ratio) || parsed.ratio <= 0 || parsed.ratio >= 1) return null;
    return parsed;
  } catch {
    return null;
  }
}

function writePreference(ratio: number, viewportHeight: number) {
  const payload: StoredPreference = {
    ratio,
    viewportHeight,
    updatedAt: new Date().toISOString(),
  };
  try {
    localStorage.setItem(OVERVIEW_HEIGHT_STORAGE_KEY, JSON.stringify(payload));
  } catch {
    /* ignore */
  }
}

export function defaultOverviewRatioForHeight(contentHeight: number): number {
  if (contentHeight >= 900) return 0.72;
  if (contentHeight >= 700) return 0.7;
  return 0.68;
}

export function clampOverviewRatio(ratio: number, containerHeight: number): number {
  if (containerHeight <= 0) return ratio;
  const minRatio = MIN_OVERVIEW_PX / containerHeight;
  const maxRatio = 1 - MIN_DETAIL_PX / containerHeight;
  if (minRatio >= maxRatio) {
    return Math.min(Math.max(ratio, 0.55), 0.82);
  }
  return Math.min(Math.max(ratio, minRatio), maxRatio);
}

export function JourneyResizableSplit({
  overview,
  detail,
  collapsedSummary,
  footer,
  contentHeight,
  inspectorCollapsed = false,
  onInspectorCollapsedChange,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  const [ratio, setRatio] = useState(DEFAULT_OVERVIEW_RATIO);
  const [stackedTabs, setStackedTabs] = useState(false);
  const [mobilePane, setMobilePane] = useState<"overview" | "detail">("overview");

  const measureAndClamp = useCallback(
    (nextRatio?: number) => {
      const node = containerRef.current;
      if (!node) return;
      const height = node.getBoundingClientRect().height;
      const screenHeight =
        contentHeight ??
        (typeof window !== "undefined" ? window.innerHeight : height);
      setStackedTabs(screenHeight > 0 && screenHeight < 700);

      const preferred =
        nextRatio ??
        readPreference()?.ratio ??
        defaultOverviewRatioForHeight(screenHeight);
      const stored = readPreference();
      let candidate = preferred;
      if (stored && Math.abs(stored.viewportHeight - screenHeight) > 180) {
        candidate = defaultOverviewRatioForHeight(screenHeight);
      }
      const clamped = clampOverviewRatio(candidate, height);
      setRatio(clamped);
    },
    [contentHeight],
  );

  useEffect(() => {
    measureAndClamp();
    const node = containerRef.current;
    if (!node) return;
    const observer = new ResizeObserver(() => measureAndClamp());
    observer.observe(node);
    return () => observer.disconnect();
  }, [measureAndClamp]);

  const persist = useCallback(
    (value: number) => {
      const node = containerRef.current;
      const height = node?.getBoundingClientRect().height ?? 0;
      const clamped = clampOverviewRatio(value, height);
      setRatio(clamped);
      const screenHeight =
        contentHeight ??
        (typeof window !== "undefined" ? window.innerHeight : height);
      writePreference(clamped, screenHeight);
      if (onInspectorCollapsedChange && inspectorCollapsed) {
        onInspectorCollapsedChange(false);
      }
    },
    [contentHeight, inspectorCollapsed, onInspectorCollapsedChange],
  );

  const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (stackedTabs || inspectorCollapsed) return;
    dragging.current = true;
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const onPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!dragging.current || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const next = (event.clientY - rect.top) / rect.height;
    persist(next);
  };

  const onPointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    dragging.current = false;
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      /* ignore */
    }
  };

  const resetDefault = () => {
    const height =
      contentHeight ?? containerRef.current?.getBoundingClientRect().height ?? 800;
    onInspectorCollapsedChange?.(true);
    persist(defaultOverviewRatioForHeight(height));
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (stackedTabs) return;
    const step = 0.02;
    if (event.key === "ArrowUp") {
      event.preventDefault();
      persist(ratio - step);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      persist(ratio + step);
    } else if (event.key === "Home") {
      event.preventDefault();
      const height = containerRef.current?.getBoundingClientRect().height ?? 0;
      persist(MIN_OVERVIEW_PX / Math.max(height, 1));
    } else if (event.key === "End") {
      event.preventDefault();
      const height = containerRef.current?.getBoundingClientRect().height ?? 0;
      persist(1 - MIN_DETAIL_PX / Math.max(height, 1));
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onInspectorCollapsedChange?.(!inspectorCollapsed);
    }
  };

  if (stackedTabs) {
    return (
      <div
        className="journey-resizable-split journey-resizable-stacked"
        data-testid="journey-resizable-split"
        data-inspector-collapsed={inspectorCollapsed ? "true" : "false"}
        ref={containerRef}
      >
        <div className="journey-resizable-tab-bar" data-testid="journey-overview-detail-tabs">
          <button
            type="button"
            className={mobilePane === "overview" ? "active" : ""}
            data-testid="journey-stack-overview"
            onClick={() => setMobilePane("overview")}
          >
            总览
          </button>
          <button
            type="button"
            className={mobilePane === "detail" ? "active" : ""}
            data-testid="journey-stack-detail"
            onClick={() => setMobilePane("detail")}
          >
            Scene 详情
          </button>
        </div>
        <div className="journey-resizable-stacked-body">
          {mobilePane === "overview" ? overview : detail}
        </div>
        {footer}
      </div>
    );
  }

  return (
    <div
      className={`journey-resizable-split ${inspectorCollapsed ? "inspector-collapsed" : ""}`}
      data-testid="journey-resizable-split"
      data-inspector-collapsed={inspectorCollapsed ? "true" : "false"}
      ref={containerRef}
      style={
        {
          "--journey-overview-ratio": String(inspectorCollapsed ? 1 : ratio),
        } as CSSProperties
      }
    >
      <div className="journey-resizable-overview" data-testid="journey-resizable-overview">
        {overview}
      </div>

      {inspectorCollapsed ? (
        <>
          <div
            className="journey-inspector-summary-bar"
            data-testid="journey-inspector-summary-bar"
            style={{ minHeight: COLLAPSED_SUMMARY_PX }}
          >
            {collapsedSummary}
          </div>
          <div
            className="journey-resizable-detail journey-detail-collapsed-slot"
            data-testid="journey-resizable-detail"
            hidden
            aria-hidden="true"
          >
            {detail}
          </div>
        </>
      ) : (
        <>
          <div
            className="journey-resize-handle"
            data-testid="journey-resize-handle"
            role="separator"
            aria-orientation="horizontal"
            aria-valuenow={Math.round(ratio * 100)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="调整旅程总览与详情高度"
            tabIndex={0}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onDoubleClick={resetDefault}
            onKeyDown={onKeyDown}
          >
            <span className="journey-resize-handle-grip" aria-hidden="true" />
            <button
              type="button"
              className="journey-reset-layout-btn"
              data-testid="journey-collapse-inspector"
              onClick={(event) => {
                event.stopPropagation();
                onInspectorCollapsedChange?.(true);
              }}
            >
              收起详情
            </button>
          </div>
          <div className="journey-resizable-detail" data-testid="journey-resizable-detail">
            {detail}
          </div>
        </>
      )}
      {footer}
    </div>
  );
}
