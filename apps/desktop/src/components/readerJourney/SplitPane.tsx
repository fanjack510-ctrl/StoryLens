import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

const STORAGE_KEY = "storylens.journey.splitRatio";
const DEFAULT_RATIO = 0.52;
const MIN_LEFT = 420;
const MIN_RIGHT = 400;

/** Presentation default: left text share by viewport width (2.5B). */
function defaultRatioForWidth(width: number): number {
  if (width >= 1440) return 0.46;
  if (width >= 1280) return 0.52;
  return DEFAULT_RATIO;
}

type Layout = "horizontal" | "vertical" | "tabs";

type Props = {
  layout: Layout;
  left: ReactNode;
  right: ReactNode;
  activeTab?: "left" | "right";
  onActiveTabChange?: (tab: "left" | "right") => void;
};

function readStoredRatio(): number {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw == null) {
      const width = typeof window !== "undefined" ? window.innerWidth : 1280;
      return defaultRatioForWidth(width);
    }
    const parsed = Number(raw);
    if (Number.isFinite(parsed) && parsed > 0.2 && parsed < 0.8) return parsed;
  } catch {
    /* ignore */
  }
  return DEFAULT_RATIO;
}

function clampRatio(ratio: number, containerSize: number, horizontal: boolean): number {
  if (containerSize <= 0) return ratio;
  const minPrimary = horizontal ? MIN_LEFT : 200;
  const minSecondary = horizontal ? MIN_RIGHT : 200;
  const minRatio = minPrimary / containerSize;
  const maxRatio = 1 - minSecondary / containerSize;
  if (minRatio >= maxRatio) return 0.5;
  return Math.min(Math.max(ratio, minRatio), maxRatio);
}

const TEXT_COLLAPSE_KEY = "storylens.journey.textPaneCollapsed.v3_0";

function readTextCollapsed(): boolean {
  try {
    return localStorage.getItem(TEXT_COLLAPSE_KEY) === "1";
  } catch {
    return false;
  }
}

export function SplitPane({ layout, left, right, activeTab = "left", onActiveTabChange }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [ratio, setRatio] = useState(readStoredRatio);
  const [textCollapsed] = useState(readTextCollapsed);
  const dragging = useRef(false);

  const persistRatio = useCallback((value: number) => {
    setRatio(value);
    try {
      localStorage.setItem(STORAGE_KEY, String(value));
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    const node = containerRef.current;
    if (!node || layout === "tabs") return;

    const observer = new ResizeObserver(() => {
      const rect = node.getBoundingClientRect();
      const horizontal = layout === "horizontal";
      const size = horizontal ? rect.width : rect.height;
      setRatio((current) => clampRatio(current, size, horizontal));
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [layout]);

  useEffect(() => {
    if (layout === "tabs") return;

    const onMove = (event: MouseEvent | TouchEvent) => {
      if (!dragging.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const horizontal = layout === "horizontal";
      const client = "touches" in event ? event.touches[0] : event;
      const pos = horizontal ? client.clientX - rect.left : client.clientY - rect.top;
      const size = horizontal ? rect.width : rect.height;
      persistRatio(clampRatio(pos / size, size, horizontal));
    };

    const onUp = () => {
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    window.addEventListener("touchmove", onMove);
    window.addEventListener("touchend", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      window.removeEventListener("touchmove", onMove);
      window.removeEventListener("touchend", onUp);
    };
  }, [layout, persistRatio]);

  const startDrag = () => {
    dragging.current = true;
    document.body.style.cursor = layout === "horizontal" ? "col-resize" : "row-resize";
    document.body.style.userSelect = "none";
  };

  if (layout === "tabs") {
    return (
      <div className="journey-split-tabs" data-testid="journey-split-pane">
        <div className="journey-split-tab-bar">
          <button
            type="button"
            className={activeTab === "left" ? "active" : ""}
            data-testid="journey-split-tab-text"
            onClick={() => onActiveTabChange?.("left")}
          >
            正文
          </button>
          <button
            type="button"
            className={activeTab === "right" ? "active" : ""}
            data-testid="journey-split-tab-journey"
            onClick={() => onActiveTabChange?.("right")}
          >
            旅程
          </button>
        </div>
        <div className="journey-split-tab-panel">
          {activeTab === "left" ? left : right}
        </div>
      </div>
    );
  }

  const horizontal = layout === "horizontal";
  const primaryStyle = textCollapsed
    ? horizontal
      ? { flexBasis: "36px", minWidth: 36, maxWidth: 36 }
      : { flexBasis: "36px", minHeight: 36, maxHeight: 36 }
    : horizontal
      ? { flexBasis: `${ratio * 100}%`, minWidth: MIN_LEFT }
      : { flexBasis: `${ratio * 100}%`, minHeight: 200 };
  const secondaryStyle = textCollapsed
    ? horizontal
      ? { flexBasis: "calc(100% - 44px)", minWidth: MIN_RIGHT }
      : { flexBasis: "calc(100% - 44px)", minHeight: 200 }
    : horizontal
      ? { flexBasis: `${(1 - ratio) * 100}%`, minWidth: MIN_RIGHT }
      : { flexBasis: `${(1 - ratio) * 100}%`, minHeight: 200 };

  return (
    <div
      ref={containerRef}
      className={`journey-split-pane ${horizontal ? "horizontal" : "vertical"} ${
        textCollapsed ? "text-pane-collapsed" : ""
      }`}
      data-testid="journey-split-pane"
      data-text-collapsed={textCollapsed ? "true" : "false"}
    >
      <div className="journey-split-primary" style={primaryStyle}>
        {!textCollapsed ? left : null}
      </div>
      {!textCollapsed ? (
        <div
          className="journey-split-divider"
          data-testid="journey-split-divider"
          role="separator"
          aria-orientation={horizontal ? "vertical" : "horizontal"}
          onMouseDown={startDrag}
          onTouchStart={startDrag}
        />
      ) : (
        <div className="journey-split-divider journey-split-divider-collapsed" aria-hidden="true" />
      )}
      <div className="journey-split-secondary" style={secondaryStyle}>
        {right}
      </div>
    </div>
  );
}
