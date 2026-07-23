/** MockRunPollingPolicy mirror (Phase 2A-P). No WebSocket. */

import type { WholeBookRunViewStatus } from "../../contracts/keys";

export const POLLING_BACKOFF_POLICIES = ["exponential", "linear", "none"] as const;
export type PollingBackoffPolicy = (typeof POLLING_BACKOFF_POLICIES)[number];

export type MockRunPollingPolicy = {
  initial_interval_ms: number;
  running_interval_ms: number;
  paused_interval_ms: number;
  terminal_stop: boolean;
  max_consecutive_errors: number;
  backoff_policy: PollingBackoffPolicy;
  hidden_page_interval_ms: number;
  min_interval_ms: number;
  websocket_forbidden: true;
};

export const DEFAULT_MOCK_RUN_POLLING_POLICY: MockRunPollingPolicy = {
  initial_interval_ms: 1500,
  running_interval_ms: 1500,
  paused_interval_ms: 4000,
  terminal_stop: true,
  max_consecutive_errors: 5,
  backoff_policy: "exponential",
  hidden_page_interval_ms: 10_000,
  min_interval_ms: 1000,
  websocket_forbidden: true,
};

export function intervalForStatus(
  policy: MockRunPollingPolicy,
  status: WholeBookRunViewStatus,
  pageVisible = true,
): number | null {
  if (status === "completed" || status === "failed" || status === "cancelled") {
    return policy.terminal_stop ? null : policy.paused_interval_ms;
  }
  let base = policy.initial_interval_ms;
  if (status === "running") base = policy.running_interval_ms;
  if (status === "paused" || status === "interrupted") base = policy.paused_interval_ms;
  if (!pageVisible) return Math.max(base, policy.hidden_page_interval_ms);
  return base;
}
