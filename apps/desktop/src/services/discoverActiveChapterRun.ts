import type { Run } from "../types";
import { selectChapterReentryRun } from "./runLifecycle";

/**
 * Select the AnalysisRun to bind for a chapter when URL omits analysisRun.
 * Never invents a run; never creates one.
 *
 * Priority (CHG-20260727-014): awaiting_user → active → completed → failed/cancelled.
 */
export function discoverActiveChapterRun(
  runs: Run[] | null | undefined,
  chapterId: number | null | undefined,
): Run | null {
  return selectChapterReentryRun(runs, chapterId);
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
