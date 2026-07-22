import type { Run } from "../types";
import { isBudgetPauseRun } from "./budgetPauseDetect";

/**
 * Priority bands for auto-discovering the AnalysisRun for a chapter
 * when the URL has no explicit analysisRun.
 *
 * Within a band, the newest run (higher id / later created_at) wins.
 */
const PROCESSING_STATUSES = new Set([
  "queued",
  "running",
  "boundary_candidates_running",
  "boundary_confirmed",
  "scene_analysis_running",
  "reader_journey_processing",
  "reader_journey_running",
  "reader_journey_scene_profiles_running",
  "reader_journey_chapter_running",
]);

function createdAtMs(run: Run): number {
  const t = Date.parse(run.created_at || "");
  return Number.isFinite(t) ? t : 0;
}

function preferNewer(a: Run, b: Run): Run {
  if (a.id !== b.id) return a.id > b.id ? a : b;
  return createdAtMs(a) >= createdAtMs(b) ? a : b;
}

function pickNewest(runs: Run[]): Run | null {
  if (!runs.length) return null;
  return runs.reduce((best, item) => preferNewer(best, item));
}

function isProcessing(run: Run): boolean {
  return PROCESSING_STATUSES.has(run.status);
}

function isActivePriority(run: Run): boolean {
  if (isProcessing(run)) return true;
  if (run.status === "scene_analysis_partial") return true;
  if (
    run.status === "reader_journey_processing" ||
    String(run.current_stage || "").startsWith("reader_journey")
  ) {
    if (run.status !== "succeeded" && run.status !== "failed" && run.status !== "cancelled") {
      return true;
    }
  }
  // Scene-pipeline succeeded is not chapter-complete until Journey finishes.
  if (run.status === "succeeded" && run.chapter_complete !== true) return true;
  if (
    run.effective_status === "partial_complete" ||
    run.effective_status === "journey_running" ||
    run.effective_status === "journey_failed"
  ) {
    return true;
  }
  if (run.status === "awaiting_provider_recovery") return true;
  if (isBudgetPauseRun(run)) return true;
  if (run.status === "awaiting_boundary_review") return true;
  return false;
}

function activeBandRank(run: Run): number {
  // Lower rank = higher priority within the active band list from the phase brief.
  if (isProcessing(run)) return 0;
  if (run.status === "scene_analysis_partial") return 1;
  if (
    run.status === "succeeded" &&
    run.chapter_complete !== true
  ) {
    return 1;
  }
  if (
    run.effective_status === "partial_complete" ||
    run.effective_status === "journey_running" ||
    run.effective_status === "journey_failed"
  ) {
    return 1;
  }
  if (
    run.status === "reader_journey_processing" ||
    (String(run.current_stage || "").startsWith("reader_journey") &&
      run.status !== "succeeded")
  ) {
    return 2;
  }
  if (run.status === "awaiting_provider_recovery") return 3;
  if (isBudgetPauseRun(run)) return 4;
  if (run.status === "awaiting_boundary_review") return 5;
  return 99;
}

/**
 * Select the AnalysisRun to bind for a chapter when URL omits analysisRun.
 * Never invents a run; never creates one.
 */
export function discoverActiveChapterRun(
  runs: Run[] | null | undefined,
  chapterId: number | null | undefined,
): Run | null {
  if (!chapterId || !runs?.length) return null;
  const chapterRuns = runs.filter(
    (run) => String(run.subject_id) === String(chapterId),
  );
  if (!chapterRuns.length) return null;

  const active = chapterRuns.filter(isActivePriority);
  if (active.length) {
    const bestRank = Math.min(...active.map(activeBandRank));
    const band = active.filter((run) => activeBandRank(run) === bestRank);
    return pickNewest(band);
  }

  const chapterDone = chapterRuns.filter(
    (run) => run.status === "succeeded" && run.chapter_complete === true,
  );
  const latestChapterDone = pickNewest(chapterDone);
  if (latestChapterDone) return latestChapterDone;

  const succeeded = chapterRuns.filter((run) => run.status === "succeeded");
  const latestSucceeded = pickNewest(succeeded);
  if (latestSucceeded) return latestSucceeded;

  const failed = chapterRuns.filter(
    (run) =>
      run.status === "failed" ||
      run.status === "failed_provider" ||
      run.status === "failed_structural" ||
      String(run.status).startsWith("failed"),
  );
  return pickNewest(failed);
}

export function chapterProgressHref(args: {
  bookId: number;
  chapterId: number | string;
  analysisRunId: number;
}): string {
  const params = new URLSearchParams();
  params.set("chapter", String(args.chapterId));
  params.set("analysisRun", String(args.analysisRunId));
  params.set("view", "progress");
  return `/books/${args.bookId}?${params.toString()}`;
}

/** Chapter shell result entry; optional reader-journey tab for resume / workspace. */
export function chapterResultHref(args: {
  bookId: number;
  chapterId: number | string;
  analysisRunId: number;
  tab?: "reader-journey" | "analysis";
}): string {
  const params = new URLSearchParams();
  params.set("chapter", String(args.chapterId));
  params.set("analysisRun", String(args.analysisRunId));
  params.set("view", "result");
  if (args.tab === "reader-journey") {
    params.set("tab", "reader-journey");
  }
  return `/books/${args.bookId}?${params.toString()}`;
}
