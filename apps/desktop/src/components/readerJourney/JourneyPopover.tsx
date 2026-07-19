import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import {
  getJourneyOverlayRoot,
  JOURNEY_POPOVER_VIEWPORT_PAD_PX,
  JOURNEY_Z_INDEX,
} from "./journeyOverlayTokens";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  trigger: ReactNode;
  children: ReactNode;
  /** Preferred alignment relative to trigger. */
  align?: "start" | "end";
  "data-testid"?: string;
  labelledBy?: string;
  menuLabel?: string;
};

const VIEWPORT_PAD = JOURNEY_POPOVER_VIEWPORT_PAD_PX;

/**
 * Shared Journey popover (Portal → journey-overlay-root).
 * Fixed placement with flip / shift / collision padding ≥8px.
 * Use for 更多设置 / 导出 / simple action menus — NOT for metric selection.
 */
export function JourneyPopover({
  open,
  onOpenChange,
  trigger,
  children,
  align = "end",
  "data-testid": testId = "journey-anchored-menu",
  labelledBy,
  menuLabel = "菜单",
}: Props) {
  const triggerWrapRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const [coords, setCoords] = useState<{ top: number; left: number; width: number }>({
    top: 0,
    left: 0,
    width: 220,
  });

  const place = useCallback(() => {
    const triggerEl = triggerWrapRef.current;
    const panelEl = panelRef.current;
    if (!triggerEl || !panelEl) return;
    const tr = triggerEl.getBoundingClientRect();
    const pr = panelEl.getBoundingClientRect();
    const panelW = Math.max(pr.width || 220, 180);
    const panelH = pr.height || 120;
    let left = align === "end" ? tr.right - panelW : tr.left;
    left = Math.min(
      Math.max(VIEWPORT_PAD, left),
      window.innerWidth - panelW - VIEWPORT_PAD,
    );
    // Prefer below trigger; flip above if needed. Never cover trigger.
    let top = tr.bottom + 6;
    if (top + panelH > window.innerHeight - VIEWPORT_PAD) {
      const above = tr.top - panelH - 6;
      if (above >= VIEWPORT_PAD) top = above;
      else top = Math.max(VIEWPORT_PAD, window.innerHeight - panelH - VIEWPORT_PAD);
    }
    setCoords({ top, left, width: panelW });
  }, [align]);

  useLayoutEffect(() => {
    if (!open) return;
    place();
  }, [open, place, children]);

  useEffect(() => {
    if (!open) return;
    const onWin = () => place();
    window.addEventListener("resize", onWin);
    window.addEventListener("scroll", onWin, true);
    return () => {
      window.removeEventListener("resize", onWin);
      window.removeEventListener("scroll", onWin, true);
    };
  }, [open, place]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onOpenChange(false);
      }
    };
    const onDoc = (event: MouseEvent) => {
      const t = event.target as Node;
      if (triggerWrapRef.current?.contains(t)) return;
      if (panelRef.current?.contains(t)) return;
      onOpenChange(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDoc);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDoc);
    };
  }, [open, onOpenChange]);

  const panelStyle: CSSProperties = {
    position: "fixed",
    top: coords.top,
    left: coords.left,
    minWidth: Math.max(coords.width, 200),
    zIndex: JOURNEY_Z_INDEX.popoverMenu,
  };

  const overlayRoot = typeof document !== "undefined" ? getJourneyOverlayRoot() : null;

  return (
    <div className="journey-anchored-menu journey-popover" data-testid={testId} ref={triggerWrapRef}>
      {trigger}
      {open && overlayRoot
        ? createPortal(
            <div
              ref={panelRef}
              className="journey-anchored-menu-panel journey-popover-panel"
              id={menuId}
              role="menu"
              aria-label={menuLabel}
              aria-labelledby={labelledBy}
              data-testid={`${testId}-panel`}
              style={panelStyle}
            >
              {children}
            </div>,
            overlayRoot,
          )
        : null}
    </div>
  );
}

/** Alias — unified Shared Popover system. */
export const SharedPopover = JourneyPopover;
