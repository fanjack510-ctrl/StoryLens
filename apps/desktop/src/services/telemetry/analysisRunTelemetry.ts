import {
  isTerminalUiState,
  mapRunToUiState,
} from "../../components/chapterAnalysis/mapAnalysisUiState";
import type { Run } from "../../types";
import { getAppTelemetryClient } from "./telemetryRuntime";

const COMPLETED_RUNS_STORAGE_KEY = "storylens.telemetry.analysis_completed.sent";

function readCompletedRunIds(): Set<number> {
  try {
    const raw = localStorage.getItem(COMPLETED_RUNS_STORAGE_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.filter((id): id is number => typeof id === "number"));
  } catch {
    return new Set();
  }
}

function markRunCompletedSent(runId: number): void {
  const ids = readCompletedRunIds();
  ids.add(runId);
  try {
    localStorage.setItem(COMPLETED_RUNS_STORAGE_KEY, JSON.stringify([...ids].slice(-200)));
  } catch {
    /* ignore quota */
  }
}

export function bucketDurationMs(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "unknown";
  if (ms < 60_000) return "under_1m";
  if (ms < 5 * 60_000) return "1m_to_5m";
  if (ms < 15 * 60_000) return "5m_to_15m";
  if (ms < 60 * 60_000) return "15m_to_1h";
  return "over_1h";
}

export function bucketSceneCount(count: number): string {
  if (!Number.isFinite(count) || count < 0) return "unknown";
  if (count === 0) return "0";
  if (count <= 5) return "1_5";
  if (count <= 15) return "6_15";
  if (count <= 30) return "16_30";
  return "31_plus";
}

export function telemetryStatusForRun(run: Run): "succeeded" | "failed" | "cancelled" | null {
  const ui = mapRunToUiState(run);
  if (!isTerminalUiState(ui)) return null;
  if (ui === "succeeded") return "succeeded";
  if (ui === "cancelled") return "cancelled";
  return "failed";
}

export function trackAnalysisStarted(executionMode: string): void {
  getAppTelemetryClient().track("analysis_started", {
    execution_mode: executionMode,
  });
}

export function maybeTrackAnalysisCompleted(run: Run | null | undefined): void {
  if (!run?.id) return;
  if (readCompletedRunIds().has(run.id)) return;

  const status = telemetryStatusForRun(run);
  if (!status) return;

  const props: Record<string, string> = {
    execution_mode: run.execution_mode || "unknown",
    status,
  };

  if (run.created_at && run.completed_at) {
    const start = Date.parse(run.created_at);
    const end = Date.parse(run.completed_at);
    if (Number.isFinite(start) && Number.isFinite(end) && end >= start) {
      props.duration_bucket = bucketDurationMs(end - start);
    }
  }

  const sceneTotal = run.total_scene_count;
  if (typeof sceneTotal === "number" && Number.isFinite(sceneTotal)) {
    props.scene_count_bucket = bucketSceneCount(sceneTotal);
  }

  const sent = getAppTelemetryClient().track("analysis_completed", props);
  if (sent) {
    markRunCompletedSent(run.id);
  }
}
