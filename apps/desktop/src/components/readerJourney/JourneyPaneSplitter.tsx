import {
  useCallback,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  PANE_RESIZE_STEP_LARGE_PX,
  PANE_RESIZE_STEP_PX,
} from "./journeyPaneWidth";

type Orientation = "vertical" | "horizontal";

type Props = {
  orientation: Orientation;
  /** Current effective value shown in aria-valuenow. */
  value: number;
  min: number;
  max: number;
  /** Called with the next preferred value (already clamped to min/max by caller if desired). */
  onChange: (next: number) => void;
  /** Restore default for this pane. */
  onReset: () => void;
  /** Accessible name, e.g. 调整正文区域宽度 */
  label: string;
  disabled?: boolean;
  testId: string;
  /** For vertical: grow means increase left/source width when dragging right.
   *  For horizontal: grow means increase dock height when dragging down. */
  growDirection?: "positive" | "negative";
  style?: CSSProperties;
  onDraggingChange?: (dragging: boolean) => void;
};

/**
 * Column / row separator with Pointer Events capture and keyboard adjustment.
 * Does not own preferred persistence — parent updates preferred + derives effective.
 */
export function JourneyPaneSplitter({
  orientation,
  value,
  min,
  max,
  onChange,
  onReset,
  label,
  disabled = false,
  testId,
  growDirection = "positive",
  style,
  onDraggingChange,
}: Props) {
  const draggingRef = useRef(false);
  const originRef = useRef(0);
  const startValueRef = useRef(0);
  const rafRef = useRef<number | null>(null);
  const pendingRef = useRef<number | null>(null);
  const [dragging, setDragging] = useState(false);

  const flush = useCallback(() => {
    rafRef.current = null;
    if (pendingRef.current == null) return;
    onChange(pendingRef.current);
    pendingRef.current = null;
  }, [onChange]);

  const schedule = useCallback(
    (next: number) => {
      pendingRef.current = next;
      if (rafRef.current != null) return;
      rafRef.current = requestAnimationFrame(flush);
    },
    [flush],
  );

  const endDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!draggingRef.current) return;
    draggingRef.current = false;
    setDragging(false);
    onDraggingChange?.(false);
    document.body.classList.remove("journey-pane-resizing");
    document.body.removeAttribute("data-row-resize");
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (pendingRef.current != null) {
      onChange(pendingRef.current);
      pendingRef.current = null;
    }
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      /* ignore */
    }
  };

  const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (disabled || event.button !== 0) return;
    event.preventDefault();
    draggingRef.current = true;
    setDragging(true);
    onDraggingChange?.(true);
    document.body.classList.add("journey-pane-resizing");
    if (orientation === "horizontal") {
      document.body.setAttribute("data-row-resize", "true");
    }
    originRef.current = orientation === "vertical" ? event.clientX : event.clientY;
    startValueRef.current = value;
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const onPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!draggingRef.current) return;
    const current = orientation === "vertical" ? event.clientX : event.clientY;
    const delta = current - originRef.current;
    const signed = growDirection === "positive" ? delta : -delta;
    const next = Math.round(startValueRef.current + signed);
    schedule(Math.min(max, Math.max(min, next)));
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (disabled) return;
    const large = event.shiftKey;
    const step = large ? PANE_RESIZE_STEP_LARGE_PX : PANE_RESIZE_STEP_PX;
    const growKeys =
      orientation === "vertical"
        ? { inc: "ArrowRight", dec: "ArrowLeft" }
        : { inc: "ArrowDown", dec: "ArrowUp" };

    if (event.key === growKeys.inc) {
      event.preventDefault();
      onChange(Math.min(max, value + step));
    } else if (event.key === growKeys.dec) {
      event.preventDefault();
      onChange(Math.max(min, value - step));
    } else if (event.key === "Home") {
      event.preventDefault();
      onChange(min);
    } else if (event.key === "End") {
      event.preventDefault();
      onChange(max);
    } else if (event.key === "Enter") {
      event.preventDefault();
      onReset();
    }
  };

  if (disabled) return null;

  return (
    <div
      className={`journey-pane-splitter journey-pane-splitter-${orientation}${dragging ? " is-dragging" : ""}`}
      data-testid={testId}
      data-orientation={orientation}
      data-dragging={dragging ? "true" : "false"}
      role="separator"
      aria-orientation={orientation}
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={Math.round(value)}
      aria-label={label}
      tabIndex={0}
      style={style}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onDoubleClick={(event) => {
        event.preventDefault();
        onReset();
      }}
      onKeyDown={onKeyDown}
    >
      <span className="journey-pane-splitter-grip" aria-hidden="true">
        ⋮
      </span>
    </div>
  );
}
