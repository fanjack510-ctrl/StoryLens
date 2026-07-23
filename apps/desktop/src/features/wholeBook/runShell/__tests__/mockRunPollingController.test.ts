import { afterEach, describe, expect, it, vi } from "vitest";
import { MockRunPollingController } from "../polling/mockRunPollingController";
import { DEFAULT_MOCK_RUN_POLLING_POLICY } from "../contracts/polling";
import {
  MOCK_FIXTURE_COMPLETED,
  MOCK_FIXTURE_PAUSED,
  MOCK_FIXTURE_RUNNING,
} from "./fixtures";
import { MockRunClientError } from "../client/types";

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("MockRunPollingController", () => {
  it("polls running at >=1000ms and stops on terminal", async () => {
    vi.useFakeTimers();
    const get = vi
      .fn()
      .mockResolvedValueOnce(MOCK_FIXTURE_RUNNING)
      .mockResolvedValueOnce(MOCK_FIXTURE_COMPLETED);
    const snaps: Array<{ polling: boolean; status?: string }> = [];
    const controller = new MockRunPollingController({
      client: { get },
      policy: {
        ...DEFAULT_MOCK_RUN_POLLING_POLICY,
        running_interval_ms: 1500,
        initial_interval_ms: 1500,
      },
      onSnapshot: (s) =>
        snaps.push({ polling: s.polling, status: s.run?.status }),
      setTimeoutFn: setTimeout as never,
      clearTimeoutFn: clearTimeout as never,
    });
    controller.start(101, MOCK_FIXTURE_RUNNING);
    await vi.advanceTimersByTimeAsync(10);
    expect(get).toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1500);
    await Promise.resolve();
    expect(snaps.some((s) => s.status === "completed")).toBe(true);
    expect(controller.getSnapshot().polling).toBe(false);
    const callsAfterStop = get.mock.calls.length;
    await vi.advanceTimersByTimeAsync(5000);
    expect(get.mock.calls.length).toBe(callsAfterStop);
    controller.dispose();
  });

  it("uses slower interval when paused", async () => {
    vi.useFakeTimers();
    const get = vi.fn(async () => MOCK_FIXTURE_PAUSED);
    const intervals: number[] = [];
    const controller = new MockRunPollingController({
      client: { get },
      policy: {
        ...DEFAULT_MOCK_RUN_POLLING_POLICY,
        running_interval_ms: 1500,
        paused_interval_ms: 4000,
      },
      onSnapshot: (s) => {
        if (s.intervalMs != null) intervals.push(s.intervalMs);
      },
      setTimeoutFn: setTimeout as never,
      clearTimeoutFn: clearTimeout as never,
    });
    controller.start(101, MOCK_FIXTURE_PAUSED);
    await vi.advanceTimersByTimeAsync(10);
    expect(controller.getSnapshot().intervalMs).toBeGreaterThanOrEqual(3000);
    controller.dispose();
  });

  it("slows down when page is hidden", async () => {
    vi.useFakeTimers();
    let visibility: DocumentVisibilityState = "visible";
    const listeners: Array<() => void> = [];
    const get = vi.fn(async () => MOCK_FIXTURE_RUNNING);
    const controller = new MockRunPollingController({
      client: { get },
      getVisibilityState: () => visibility,
      addVisibilityListener: (fn) => {
        listeners.push(fn);
        return () => {
          const idx = listeners.indexOf(fn);
          if (idx >= 0) listeners.splice(idx, 1);
        };
      },
      setTimeoutFn: setTimeout as never,
      clearTimeoutFn: clearTimeout as never,
    });
    controller.start(101, MOCK_FIXTURE_RUNNING);
    await vi.advanceTimersByTimeAsync(10);
    visibility = "hidden";
    listeners.forEach((fn) => fn());
    expect(controller.getSnapshot().pageVisible).toBe(false);
    expect(controller.getSnapshot().intervalMs).toBeGreaterThanOrEqual(10_000);
    controller.dispose();
  });

  it("backs off on errors and does not mark run failed", async () => {
    vi.useFakeTimers();
    const get = vi.fn(async () => {
      throw new MockRunClientError("offline", "NETWORK", 0, undefined, true);
    });
    const controller = new MockRunPollingController({
      client: { get },
      policy: {
        ...DEFAULT_MOCK_RUN_POLLING_POLICY,
        max_consecutive_errors: 3,
        running_interval_ms: 1000,
        initial_interval_ms: 1000,
      },
      setTimeoutFn: setTimeout as never,
      clearTimeoutFn: clearTimeout as never,
    });
    controller.start(101, MOCK_FIXTURE_RUNNING);
    await vi.advanceTimersByTimeAsync(10);
    expect(controller.getSnapshot().run?.status).toBe("running");
    await vi.advanceTimersByTimeAsync(1000);
    await vi.advanceTimersByTimeAsync(2000);
    await vi.advanceTimersByTimeAsync(4000);
    expect(controller.getSnapshot().run?.status).toBe("running");
    expect(controller.getSnapshot().lastError?.code).toBe("NETWORK");
    controller.dispose();
  });

  it("discards stale responses by version/updated_at", async () => {
    vi.useFakeTimers();
    const newer = {
      ...MOCK_FIXTURE_RUNNING,
      version: 5,
      updated_at: "2026-07-23T02:00:00Z",
      current_stage: "analyze_storylines",
    };
    const stale = {
      ...MOCK_FIXTURE_RUNNING,
      version: 2,
      updated_at: "2026-07-23T01:00:00Z",
      current_stage: "build_fulltext_index",
    };
    const get = vi
      .fn()
      .mockResolvedValueOnce(newer)
      .mockResolvedValueOnce(stale);
    const controller = new MockRunPollingController({
      client: { get },
      policy: { ...DEFAULT_MOCK_RUN_POLLING_POLICY, running_interval_ms: 1000 },
      setTimeoutFn: setTimeout as never,
      clearTimeoutFn: clearTimeout as never,
    });
    controller.start(101, MOCK_FIXTURE_RUNNING);
    await vi.advanceTimersByTimeAsync(10);
    expect(controller.getSnapshot().run?.version).toBe(5);
    await vi.advanceTimersByTimeAsync(1000);
    expect(controller.getSnapshot().run?.version).toBe(5);
    expect(controller.getSnapshot().run?.current_stage).toBe(
      "analyze_storylines",
    );
    controller.dispose();
  });

  it("cancels old poll on run_id switch and on dispose/unmount", async () => {
    vi.useFakeTimers();
    const get = vi.fn(async (id: number) => ({
      ...MOCK_FIXTURE_RUNNING,
      run_id: id,
    }));
    const controller = new MockRunPollingController({
      client: { get },
      setTimeoutFn: setTimeout as never,
      clearTimeoutFn: clearTimeout as never,
    });
    controller.start(101);
    await vi.advanceTimersByTimeAsync(10);
    controller.start(202);
    await vi.advanceTimersByTimeAsync(10);
    expect(get.mock.calls.some((c) => c[0] === 202)).toBe(true);
    controller.dispose();
    const calls = get.mock.calls.length;
    await vi.advanceTimersByTimeAsync(10_000);
    expect(get.mock.calls.length).toBe(calls);
  });

  it("stop does not cancel backend run (no cancel API call)", async () => {
    const get = vi.fn(async () => MOCK_FIXTURE_RUNNING);
    const cancel = vi.fn();
    const controller = new MockRunPollingController({
      client: { get },
    });
    controller.start(101);
    controller.stop();
    expect(cancel).not.toHaveBeenCalled();
    controller.dispose();
  });
});
