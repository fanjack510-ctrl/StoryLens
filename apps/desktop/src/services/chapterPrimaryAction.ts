/**
 * Single chapter primary CTA for the book workspace toolbar.
 * Reader Journey is a result view, not a second start button.
 */

import type { Run } from "../types";
import type { ChapterAnalysisUiState } from "../components/chapterAnalysis/mapAnalysisUiState";
import {
  isChapterAnalysisComplete,
  isChapterAnalysisInFlight,
} from "./chapterJourneyComposition";

export type ChapterPrimaryActionKind =
  | "start"
  | "progress"
  | "result"
  | "reanalyze"
  | "none";

export type ChapterPrimaryAction = {
  kind: ChapterPrimaryActionKind;
  label: string;
  testId: string;
};

const LABELS: Record<Exclude<ChapterPrimaryActionKind, "none">, string> = {
  start: "开始分析",
  progress: "查看分析进度",
  result: "查看分析结果",
  reanalyze: "重新分析",
};

const TEST_IDS: Record<Exclude<ChapterPrimaryActionKind, "none">, string> = {
  start: "shell-start-analysis",
  progress: "shell-view-analysis-progress",
  result: "shell-view-analysis-result",
  reanalyze: "shell-reanalyze",
};

function action(kind: Exclude<ChapterPrimaryActionKind, "none">): ChapterPrimaryAction {
  return { kind, label: LABELS[kind], testId: TEST_IDS[kind] };
}

/**
 * Resolve the single primary chapter-analysis button.
 *
 * Priority: failed/cancelled → reanalyze; in-flight → progress;
 * completed → result; otherwise → start.
 */
export function resolveChapterPrimaryAction(args: {
  hasChapter: boolean;
  run: Run | null | undefined;
  composition: ChapterAnalysisUiState;
  chapterComplete: boolean;
  inFlight: boolean;
}): ChapterPrimaryAction {
  if (!args.hasChapter) {
    return { kind: "none", label: "", testId: "" };
  }

  const { run, composition, chapterComplete, inFlight } = args;

  if (
    composition === "failed" ||
    composition === "cancelled" ||
    run?.status === "failed" ||
    run?.status === "failed_provider" ||
    run?.status === "failed_structural" ||
    run?.status === "cancelled" ||
    run?.status === "review_cancelled"
  ) {
    return action("reanalyze");
  }

  if (
    inFlight ||
    isChapterAnalysisInFlight(run, composition) ||
    composition === "running" ||
    composition === "creating" ||
    composition === "partial" ||
    composition === "boundary_review_required" ||
    composition === "provider_recovery" ||
    composition === "awaiting_budget_adjustment" ||
    composition === "aborted_by_limit" ||
    composition === "awaiting_reader_journey_start" ||
    composition === "reader_journey_processing"
  ) {
    return action("progress");
  }

  if (
    chapterComplete ||
    isChapterAnalysisComplete(run) ||
    composition === "succeeded"
  ) {
    return action("result");
  }

  return action("start");
}
