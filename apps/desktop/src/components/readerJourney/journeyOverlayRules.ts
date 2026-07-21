/** Overlay compare rules for observation lenses. */

import type { ObservationLensId } from "./observationLenses";
import { getObservationLens } from "./observationLenses";

export type OverlayDecision = {
  enabled: boolean;
  lineCount: number;
  reason: string;
};

/**
 * Default overlay off. Max two lines.
 * Hook/payoff is a paired mode (2 lines) and cannot add a third composite overlay.
 */
export function resolveOverlayLines(
  lensId: ObservationLensId,
  overlayEnabled: boolean,
): OverlayDecision {
  const lens = getObservationLens(lensId);
  if (lens.isPairedHookPayoff) {
    return {
      enabled: false,
      lineCount: 2,
      reason: "hook_payoff_paired",
    };
  }
  if (!overlayEnabled) {
    return { enabled: false, lineCount: 1, reason: "overlay_off" };
  }
  if (lens.id === "composite") {
    return { enabled: false, lineCount: 1, reason: "composite_is_base" };
  }
  if (!lens.allowsOverlayWithComposite) {
    return { enabled: false, lineCount: 1, reason: "lens_disallows_overlay" };
  }
  return { enabled: true, lineCount: 2, reason: "composite_plus_lens" };
}

export function maxOverlayLineCount(): number {
  return 2;
}
