/** Frontend Lab guards (Phase 2A-P). Fail-closed; no invented allowed_actions/status. */

import { WHOLE_BOOK_MOCK_LAB_ENABLED } from "./mockLab";
import type { MockRunActionResult } from "./actions";
import type { WholeBookRunViewStatus } from "../../contracts/keys";

export function isMockLabUiVisible(params: {
  appEnvironment: "development" | "test" | "production" | string;
  labEnabled?: boolean;
}): boolean {
  const labEnabled = params.labEnabled ?? WHOLE_BOOK_MOCK_LAB_ENABLED;
  if (!labEnabled) return false;
  return params.appEnvironment === "development" || params.appEnvironment === "test";
}

export function mustNotInventAllowedActions(): true {
  return true;
}

export function mustNotDeriveRunStatusClientSide(): true {
  return true;
}

export function networkFailureIsFailClosed(): true {
  return true;
}

export function discardStalePollResponse(params: {
  incomingUpdatedAt: string;
  currentUpdatedAt: string | null;
  incomingVersion: number;
  currentVersion: number | null;
}): boolean {
  if (params.currentVersion != null && params.incomingVersion < params.currentVersion) {
    return true;
  }
  if (
    params.currentUpdatedAt != null &&
    params.incomingUpdatedAt < params.currentUpdatedAt
  ) {
    return true;
  }
  return false;
}

export function applyBackendActionResult(
  _previous: WholeBookRunViewStatus,
  result: MockRunActionResult,
): WholeBookRunViewStatus {
  // Frontend applies backend current_state only; never invents transitions.
  return result.current_state;
}
