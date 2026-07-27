/** Single source for product boundary review UX mode. */

export type BoundaryReviewMode = "confirm_only" | "manual_editor";

const ENV_KEY = "VITE_STORYLENS_BOUNDARY_REVIEW_MODE";

export function getBoundaryReviewMode(): BoundaryReviewMode {
  try {
    const fromVite = (import.meta as { env?: Record<string, string> }).env?.[ENV_KEY];
    if (fromVite === "manual_editor") return "manual_editor";
  } catch {
    /* ignore */
  }
  try {
    const injected = (globalThis as { __STORYLENS_BOUNDARY_REVIEW_MODE__?: string })
      .__STORYLENS_BOUNDARY_REVIEW_MODE__;
    if (injected === "manual_editor") return "manual_editor";
  } catch {
    /* ignore */
  }
  return "confirm_only";
}

export function isConfirmOnlyBoundaryReview(): boolean {
  return getBoundaryReviewMode() === "confirm_only";
}
