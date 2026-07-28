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
import { normalizeRunLifecycle } from "./runLifecycle";

export type ChapterPrimaryActionKind =
  | "start"
  | "progress"
  | "confirm"
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
  confirm: "继续确认场景",
  result: "查看分析结果",
  reanalyze: "重新分析",
};

const TEST_IDS: Record<Exclude<ChapterPrimaryActionKind, "none">, string> = {
  start: "shell-start-analysis",
  progress: "shell-view-analysis-progress",
  confirm: "shell-continue-boundary-confirm",
  result: "shell-view-analysis-result",
  reanalyze: "shell-reanalyze",
};

function action(kind: Exclude<ChapterPrimaryActionKind, "none">): ChapterPrimaryAction {
  return { kind, label: LABELS[kind], testId: TEST_IDS[kind] };
}

/**
 * Resolve the single primary chapter-analysis button.
 *
 * Priority: failed/cancelled → reanalyze; awaiting review → confirm;
 * in-flight → progress; completed → result; otherwise → start.
 *
 * When `lifecycleRun` is provided (discovered without URL bind), prefer
 * shared lifecycle over composition-only idle state.
 */
export function resolveChapterPrimaryAction(args: {
  hasChapter: boolean;
  run: Run | null | undefined;
  composition: ChapterAnalysisUiState;
  chapterComplete: boolean;
  inFlight: boolean;
  /** Optional discovered run when URL has no analysisRun. */
  lifecycleRun?: Run | null;
}): ChapterPrimaryAction {
  if (!args.hasChapter) {
    return { kind: "none", label: "", testId: "" };
  }

  const { run, composition, chapterComplete, inFlight } = args;
  const lifecycleSource = args.lifecycleRun ?? run;
  const phase = normalizeRunLifecycle(lifecycleSource);

  if (
    phase === "failed" ||
    phase === "cancelled" ||
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
    phase === "awaiting_user" ||
    composition === "boundary_review_required" ||
    composition === "awaiting_scene_boundary_confirmation" ||
    lifecycleSource?.status === "awaiting_boundary_review"
  ) {
    return action("confirm");
  }

  // CHG-20260727-019: Journey active / interrupted beats Parent succeeded.
  if (
    phase === "active" ||
    phase === "interrupted" ||
    inFlight ||
    isChapterAnalysisInFlight(run, composition) ||
    composition === "running" ||
    composition === "creating" ||
    composition === "partial" ||
    composition === "provider_recovery" ||
    composition === "awaiting_budget_adjustment" ||
    composition === "aborted_by_limit" ||
    composition === "awaiting_reader_journey_start" ||
    composition === "reader_journey_processing"
  ) {
    return action("progress");
  }

  // Scene-only / fully complete chapter → result.
  if (
    phase === "completed" ||
    chapterComplete ||
    isChapterAnalysisComplete(run) ||
    composition === "succeeded" ||
    (lifecycleSource?.status === "succeeded" && !lifecycleSource?.journey_status) ||
    lifecycleSource?.status === "completed"
  ) {
    return action("result");
  }

  return action("start");
}
