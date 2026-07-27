/** Run state machine mirror (Phase 2A-P). Frontend must not invent transitions. */

import type { WholeBookRunViewStatus } from "../../contracts/keys";
import { WHOLE_BOOK_RUN_VIEW_STATUSES } from "../../contracts/keys";

export const ACTIVE_RUN_STATUSES = [
  "pending",
  "running",
  "paused",
  "interrupted",
] as const satisfies readonly WholeBookRunViewStatus[];

export const TERMINAL_RUN_STATUSES = [
  "completed",
  "cancelled",
] as const satisfies readonly WholeBookRunViewStatus[];

export const ALLOWED_RUN_TRANSITIONS: Record<WholeBookRunViewStatus, readonly WholeBookRunViewStatus[]> = {
  pending: ["running", "cancelled"],
  running: ["paused", "interrupted", "completed", "failed", "cancelled"],
  paused: ["running", "cancelled"],
  interrupted: ["running", "cancelled", "failed"],
  failed: ["running", "cancelled"],
  completed: [],
  cancelled: [],
};

export function isAllowedRunTransition(
  current: WholeBookRunViewStatus,
  target: WholeBookRunViewStatus,
): boolean {
  if (current === target) return true;
  return ALLOWED_RUN_TRANSITIONS[current].includes(target);
}

export function isActiveRunStatus(status: WholeBookRunViewStatus): boolean {
  return (ACTIVE_RUN_STATUSES as readonly string[]).includes(status);
}

export function canResume(status: WholeBookRunViewStatus): boolean {
  // Resume from paused/interrupted only. failed uses retry policy.
  if ((TERMINAL_RUN_STATUSES as readonly string[]).includes(status)) return false;
  return status === "paused" || status === "interrupted";
}

export const RUN_VIEW_STATUS_VALUES = WHOLE_BOOK_RUN_VIEW_STATUSES;
