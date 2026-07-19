/**
 * Unified overlay / stacking tokens for Reader Journey UI (v4.2).
 * Metric in-flow panel does not use elevated z-index.
 */

export const JOURNEY_Z_INDEX = {
  content: 0,
  stickyToolbar: 10,
  popoverMenu: 40,
  chartTooltip: 50,
  modalDialog: 100,
} as const;

export const JOURNEY_OVERLAY_ROOT_ID = "journey-overlay-root";

/** Collision padding for popover placement (viewport edges). */
export const JOURNEY_POPOVER_VIEWPORT_PAD_PX = 8;

/**
 * Ensure a single portal host exists under document.body.
 * Popovers escape Source/Main/Inspector overflow clipping.
 */
export function getJourneyOverlayRoot(): HTMLElement | null {
  if (typeof document === "undefined") return null;
  let root = document.getElementById(JOURNEY_OVERLAY_ROOT_ID);
  if (!root) {
    root = document.createElement("div");
    root.id = JOURNEY_OVERLAY_ROOT_ID;
    root.setAttribute("data-testid", "journey-overlay-root");
    root.style.position = "relative";
    root.style.zIndex = String(JOURNEY_Z_INDEX.popoverMenu);
    document.body.appendChild(root);
  }
  return root;
}
