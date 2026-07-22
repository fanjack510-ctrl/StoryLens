import type { Run } from "../types";
import { mapRunToUiState, type ChapterAnalysisUiState } from "../components/chapterAnalysis/mapAnalysisUiState";

/** Minimal journey snapshot from GET /analysis-runs/{id}/reader-journey (+ progress). */
export type JourneySnapshot = {
  status?: string | null;
  journey_run_id?: number | null;
  visualization?: unknown;
} | null | undefined;

const JOURNEY_ACTIVE = new Set([
  "queued",
  "running",
  "scene_profiles_running",
  "chapter_synthesis_running",
  "reader_journey_processing",
]);

const JOURNEY_NEEDS_RESUME = new Set([
  "failed",
  "scene_profiles_partial",
  "budget_blocked",
  "aborted_by_limit",
]);

/**
 * Chapter-shell composition over AnalysisRun + optional ReaderJourneyRun.
 *
 * Backend AnalysisRun.status===succeeded means scene_pipeline complete (certified).
 * Full chapter "分析完成" in the shell requires a succeeded journey with visualization.
 */
export function mapChapterCompositionState(
  run: Run | null | undefined,
  journey: JourneySnapshot,
): ChapterAnalysisUiState {
  const base = mapRunToUiState(run);
  if (base !== "succeeded") return base;

  if (run?.chapter_complete === true) {
    return "succeeded";
  }
  if (journey?.status === "succeeded" && journey.visualization) {
    return "succeeded";
  }

  const journeyStatus = journey?.status || run?.journey_status || null;
  if (journeyStatus && JOURNEY_ACTIVE.has(journeyStatus)) {
    return "reader_journey_processing";
  }
  if (run?.effective_status === "journey_running") {
    return "reader_journey_processing";
  }
  // null / missing / failed / partial → user can start or resume journey
  if (
    journeyStatus == null ||
    JOURNEY_NEEDS_RESUME.has(journeyStatus) ||
    run?.effective_status === "partial_complete" ||
    run?.effective_status === "journey_failed"
  ) {
    return "awaiting_reader_journey_start";
  }
  return "awaiting_reader_journey_start";
}

export function isSceneAnalysisComplete(run: Run | null | undefined): boolean {
  if (!run) return false;
  if (run.scene_pipeline_complete === true) return true;
  if (run.status !== "succeeded") return false;
  const total = run.total_scene_count ?? 0;
  const done = run.completed_scene_count ?? 0;
  return total > 0 && done >= total;
}

/** Full chapter (scenes + journey) — shared by tasks / shell / navigation. */
export function isChapterAnalysisComplete(run: Run | null | undefined): boolean {
  if (!run) return false;
  if (run.chapter_complete === true) return true;
  return false;
}

export function journeyClientRequestKey(runId: number): string {
  return `storylens.readerJourney.clientRequest.${runId}`;
}

export function getOrCreateJourneyClientRequestId(runId: number): string {
  try {
    const existing = sessionStorage.getItem(journeyClientRequestKey(runId));
    if (existing && existing.length >= 8) return existing;
    const next = crypto.randomUUID();
    sessionStorage.setItem(journeyClientRequestKey(runId), next);
    return next;
  } catch {
    return crypto.randomUUID();
  }
}
