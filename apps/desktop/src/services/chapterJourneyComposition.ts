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

/**
 * True while the chapter pipeline is still open (including scene-succeeded /
 * journey-pending). View must not treat this as a finished chapter.
 */
export function isChapterAnalysisInFlight(
  run: Run | null | undefined,
  composition?: ChapterAnalysisUiState,
): boolean {
  if (!run) return false;
  if (isChapterAnalysisComplete(run)) return false;
  if (composition === "succeeded" || composition === "cancelled") return false;
  if (composition === "failed" && run.chapter_complete === true) return false;

  if (
    composition === "awaiting_reader_journey_start" ||
    composition === "reader_journey_processing" ||
    composition === "running" ||
    composition === "creating" ||
    composition === "partial" ||
    composition === "boundary_review_required" ||
    composition === "provider_recovery" ||
    composition === "awaiting_budget_adjustment" ||
    composition === "aborted_by_limit"
  ) {
    return true;
  }

  if (run.status === "succeeded" && run.chapter_complete !== true) return true;
  if (
    run.effective_status === "partial_complete" ||
    run.effective_status === "journey_running" ||
    run.effective_status === "journey_failed"
  ) {
    return true;
  }
  if (String(run.current_stage || "").startsWith("reader_journey")) return true;
  return false;
}

export type WorkspaceView = "reading" | "progress" | "result";

/**
 * Decide BookRoutePage shell view. Run completeness is never inferred from view.
 *
 * Priority: in-flight pipeline (unless user pinned a view) → explicit user view →
 * full chapter result → default reading.
 */
export function resolveChapterWorkspaceView(args: {
  requestedView: string | null;
  userPinnedView: WorkspaceView | null;
  chapterComplete: boolean;
  inFlight: boolean;
  composition: ChapterAnalysisUiState;
}): WorkspaceView {
  const { requestedView, userPinnedView, chapterComplete, inFlight, composition } = args;

  // Stale bookmarks: view=result while journey still running → restore workspace.
  if (
    inFlight &&
    requestedView === "result" &&
    userPinnedView !== "result"
  ) {
    return "progress";
  }

  if (userPinnedView === "reading" || userPinnedView === "result" || userPinnedView === "progress") {
    if (userPinnedView === "result" && inFlight) return "result"; // manual Scene browse
    if (userPinnedView === "reading") return "reading";
    if (userPinnedView === "progress") return "progress";
    if (userPinnedView === "result" && chapterComplete) return "result";
  }

  if (requestedView === "reading" || requestedView === "progress" || requestedView === "result") {
    if (requestedView === "result" && inFlight && userPinnedView !== "result") {
      return "progress";
    }
    return requestedView;
  }

  if (inFlight) return "progress";
  if (chapterComplete || composition === "succeeded") return "result";
  return "reading";
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
