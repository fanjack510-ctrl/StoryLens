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

  if (journey?.status === "succeeded" && journey.visualization) {
    return "succeeded";
  }
  if (journey?.status && JOURNEY_ACTIVE.has(journey.status)) {
    return "reader_journey_processing";
  }
  // null / missing / failed / partial → user can start or resume journey
  if (journey == null || journey?.status == null || JOURNEY_NEEDS_RESUME.has(journey.status)) {
    return "awaiting_reader_journey_start";
  }
  return "awaiting_reader_journey_start";
}

export function isSceneAnalysisComplete(run: Run | null | undefined): boolean {
  if (!run || run.status !== "succeeded") return false;
  const total = run.total_scene_count ?? 0;
  const done = run.completed_scene_count ?? 0;
  return total > 0 && done >= total;
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
