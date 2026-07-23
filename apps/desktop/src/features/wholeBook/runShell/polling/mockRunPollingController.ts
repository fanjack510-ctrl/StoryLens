/**
 * MockRunPollingController — Phase 2A polling contract.
 * No WebSocket. Network errors do not mark Run failed.
 */

import {
  DEFAULT_MOCK_RUN_POLLING_POLICY,
  intervalForStatus,
  type MockRunPollingPolicy,
} from "../contracts/polling";
import { discardStalePollResponse } from "../contracts/guards";
import type { WholeBookRunViewStatus } from "../../contracts/keys";
import type { MockWholeBookRunViewDto } from "../client/types";
import type { MockWholeBookRunClient } from "../client/mockWholeBookRunClient";
import { MockRunClientError } from "../client/types";

export type PollingSnapshot = {
  run: MockWholeBookRunViewDto | null;
  /** Last successful poll clock. */
  lastSuccessAt: number | null;
  consecutiveErrors: number;
  polling: boolean;
  pageVisible: boolean;
  lastError: MockRunClientError | null;
  intervalMs: number | null;
};

export type MockRunPollingControllerOptions = {
  client: Pick<MockWholeBookRunClient, "get">;
  policy?: MockRunPollingPolicy;
  onSnapshot?: (snap: PollingSnapshot) => void;
  /** Injected timers for tests. */
  setTimeoutFn?: typeof setTimeout;
  clearTimeoutFn?: typeof clearTimeout;
  nowFn?: () => number;
  /** Visibility API — default document. */
  getVisibilityState?: () => DocumentVisibilityState | "visible";
  addVisibilityListener?: (fn: () => void) => () => void;
};

function computeBackoff(
  policy: MockRunPollingPolicy,
  base: number,
  consecutiveErrors: number,
): number {
  if (consecutiveErrors <= 0 || policy.backoff_policy === "none") {
    return Math.max(base, policy.min_interval_ms);
  }
  if (policy.backoff_policy === "linear") {
    return Math.max(
      policy.min_interval_ms,
      base + consecutiveErrors * 1000,
    );
  }
  // exponential
  const factor = Math.min(2 ** consecutiveErrors, 16);
  return Math.max(policy.min_interval_ms, base * factor);
}

export class MockRunPollingController {
  private readonly client: Pick<MockWholeBookRunClient, "get">;
  private readonly policy: MockRunPollingPolicy;
  private readonly onSnapshot?: (snap: PollingSnapshot) => void;
  private readonly setTimeoutFn: typeof setTimeout;
  private readonly clearTimeoutFn: typeof clearTimeout;
  private readonly nowFn: () => number;
  private readonly getVisibilityState: () => DocumentVisibilityState | "visible";
  private removeVisibility: (() => void) | null = null;

  private runId: number | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private stopped = true;
  private inFlight = false;
  private generation = 0;

  private run: MockWholeBookRunViewDto | null = null;
  private lastSuccessAt: number | null = null;
  private consecutiveErrors = 0;
  private lastError: MockRunClientError | null = null;
  private pageVisible = true;

  constructor(options: MockRunPollingControllerOptions) {
    this.client = options.client;
    this.policy = options.policy ?? DEFAULT_MOCK_RUN_POLLING_POLICY;
    this.onSnapshot = options.onSnapshot;
    this.setTimeoutFn = options.setTimeoutFn ?? setTimeout;
    this.clearTimeoutFn = options.clearTimeoutFn ?? clearTimeout;
    this.nowFn = options.nowFn ?? Date.now;
    this.getVisibilityState =
      options.getVisibilityState ??
      (() =>
        typeof document !== "undefined" ? document.visibilityState : "visible");

    const addVis =
      options.addVisibilityListener ??
      ((fn: () => void) => {
        if (typeof document === "undefined") return () => undefined;
        const handler = () => fn();
        document.addEventListener("visibilitychange", handler);
        return () => document.removeEventListener("visibilitychange", handler);
      });
    this.removeVisibility = addVis(() => {
      this.pageVisible = this.getVisibilityState() !== "hidden";
      this.emit();
      // Reschedule with new interval when visibility flips.
      if (!this.stopped && this.runId != null) {
        this.clearTimer();
        this.scheduleNext();
      }
    });
    this.pageVisible = this.getVisibilityState() !== "hidden";
  }

  getSnapshot(): PollingSnapshot {
    return {
      run: this.run,
      lastSuccessAt: this.lastSuccessAt,
      consecutiveErrors: this.consecutiveErrors,
      polling: !this.stopped && this.runId != null,
      pageVisible: this.pageVisible,
      lastError: this.lastError,
      intervalMs: this.currentInterval(),
    };
  }

  /** Start or switch polling to runId. Cancels previous schedule. */
  start(runId: number, initial?: MockWholeBookRunViewDto | null): void {
    this.clearTimer();
    this.generation += 1;
    this.runId = runId;
    this.stopped = false;
    this.consecutiveErrors = 0;
    this.lastError = null;
    if (initial && initial.run_id === runId) {
      this.run = initial;
    }
    this.emit();
    void this.tick(this.generation);
  }

  /** Stop polling. Does NOT cancel the backend run. */
  stop(): void {
    this.stopped = true;
    this.clearTimer();
    this.emit();
  }

  dispose(): void {
    this.stop();
    this.removeVisibility?.();
    this.removeVisibility = null;
    this.runId = null;
  }

  private currentInterval(): number | null {
    if (this.stopped || this.runId == null) return null;
    const status: WholeBookRunViewStatus = this.run?.status ?? "pending";
    const base = intervalForStatus(this.policy, status, this.pageVisible);
    if (base == null) return null;
    return computeBackoff(this.policy, base, this.consecutiveErrors);
  }

  private emit(): void {
    this.onSnapshot?.(this.getSnapshot());
  }

  private clearTimer(): void {
    if (this.timer != null) {
      this.clearTimeoutFn(this.timer);
      this.timer = null;
    }
  }

  private scheduleNext(): void {
    if (this.stopped || this.runId == null) return;
    const interval = this.currentInterval();
    if (interval == null) {
      // Terminal — stop.
      this.stopped = true;
      this.emit();
      return;
    }
    const gen = this.generation;
    this.timer = this.setTimeoutFn(() => {
      void this.tick(gen);
    }, interval) as ReturnType<typeof setTimeout>;
  }

  private async tick(gen: number): Promise<void> {
    if (this.stopped || this.runId == null || gen !== this.generation) return;
    if (this.inFlight) {
      this.scheduleNext();
      return;
    }
    this.inFlight = true;
    const runId = this.runId;
    try {
      const next = await this.client.get(runId);
      if (gen !== this.generation || this.runId !== runId) return;

      const stale = discardStalePollResponse({
        incomingUpdatedAt: next.updated_at ?? "",
        currentUpdatedAt: this.run?.updated_at ?? null,
        incomingVersion: next.version,
        currentVersion: this.run?.version ?? null,
      });
      if (!stale) {
        this.run = next;
        this.lastSuccessAt = this.nowFn();
        this.consecutiveErrors = 0;
        this.lastError = null;
      }
      this.emit();

      const terminal =
        next.status === "completed" ||
        next.status === "failed" ||
        next.status === "cancelled";
      if (terminal && this.policy.terminal_stop) {
        this.stopped = true;
        this.emit();
        return;
      }
      this.scheduleNext();
    } catch (error) {
      if (gen !== this.generation || this.runId !== runId) return;
      // Network / transport failure: do NOT mark run failed.
      this.consecutiveErrors += 1;
      this.lastError =
        error instanceof MockRunClientError
          ? error
          : new MockRunClientError(
              error instanceof Error ? error.message : "poll failed",
              "NETWORK",
              0,
              error,
              true,
            );
      // Keep previous run status untouched.
      this.emit();
      if (this.consecutiveErrors >= this.policy.max_consecutive_errors) {
        // Stop polling after max errors — still leave run status as-is.
        this.stopped = true;
        this.emit();
        return;
      }
      this.scheduleNext();
    } finally {
      this.inFlight = false;
    }
  }
}
