/**
 * CHG-20260729-011 — single ordinary-user chapter analysis presentation model.
 * All shell / nav / CTA / status surfaces should read this instead of re-deriving stage.
 */

import type { Run } from "../types";
import type { ChapterAnalysisUiState } from "../components/chapterAnalysis/mapAnalysisUiState";
import type { JourneyPageView } from "./resolveJourneyPageState";
import { normalizeRunLifecycle } from "./runLifecycle";

export type ChapterWorkflowState =
  | "chapter_ready"
  | "boundary_detecting"
  | "awaiting_scene_confirmation"
  | "scene_analysis_running"
  | "journey_running"
  | "journey_interrupted"
  | "journey_cancelled"
  | "journey_failed"
  | "journey_succeeded";

export type ChapterPrimaryCta =
  | "view_progress"
  | "confirm_scenes"
  | "continue_analysis"
  | "view_results"
  | "start_analysis"
  | "reanalyze"
  | "none";

export type ChapterAnalysisPresentationV1 = {
  chapter_id: number | null;
  active_analysis_run_id: number | null;
  active_journey_run_id: number | null;
  confirmed_revision_id: number | null;
  confirmed_scene_count: number | null;
  workflow_state: ChapterWorkflowState;
  completed_scene_count: number | null;
  total_scene_count: number | null;
  can_confirm_scenes: boolean;
  can_adjust_scenes: boolean;
  can_open_journey: boolean;
  can_resume_journey: boolean;
  can_view_results: boolean;
  can_resume: boolean;
  can_retry: boolean;
  can_restart_as_new: boolean;
  primary_action: ChapterPrimaryCta;
  status_title: string;
  status_description: string;
  show_confirm_nav: boolean;
  show_journey_nav: boolean;
  show_analysis_nav: boolean;
  show_results_nav: boolean;
  show_progress_nav: boolean;
  redirect_journey_to_confirm: boolean;
};

const PRIORITY: ChapterWorkflowState[] = [
  "journey_succeeded",
  "journey_cancelled",
  "journey_failed",
  "journey_interrupted",
  "journey_running",
  "scene_analysis_running",
  "awaiting_scene_confirmation",
  "boundary_detecting",
  "chapter_ready",
];

function higherPriority(a: ChapterWorkflowState, b: ChapterWorkflowState): ChapterWorkflowState {
  return PRIORITY.indexOf(a) <= PRIORITY.indexOf(b) ? a : b;
}

function mapComposition(composition: ChapterAnalysisUiState): ChapterWorkflowState | null {
  switch (composition) {
    case "awaiting_scene_boundary_confirmation":
    case "boundary_review_required":
      return "awaiting_scene_confirmation";
    case "reader_journey_processing":
      return "journey_running";
    case "awaiting_reader_journey_start":
      return "scene_analysis_running";
    case "running":
    case "creating":
    case "partial":
    case "provider_recovery":
      return "scene_analysis_running";
    case "cancelled":
      return "journey_cancelled";
    case "failed":
      return "journey_failed";
    case "succeeded":
      return "journey_succeeded";
    default:
      return null;
  }
}

function mapPageView(view: JourneyPageView | null | undefined): ChapterWorkflowState | null {
  switch (view) {
    case "interrupted":
      return "journey_interrupted";
    case "active":
      return "journey_running";
    case "completed":
      return "journey_succeeded";
    case "terminal_failed":
      return "journey_failed";
    default:
      return null;
  }
}

function mapLifecycle(run: Run | null | undefined): ChapterWorkflowState | null {
  if (!run) return null;
  const journeyStatus = String(run.journey_status || "").toLowerCase();
  const effective = String(run.effective_status || "").toLowerCase();
  // Parent AnalysisRun may stay "succeeded" after scenes while journey is interrupted.
  if (
    journeyStatus === "interrupted" ||
    journeyStatus === "paused" ||
    effective === "journey_interrupted" ||
    effective.includes("interrupted")
  ) {
    return "journey_interrupted";
  }
  if (journeyStatus === "cancelled" || effective === "cancelled") {
    return "journey_cancelled";
  }
  if (
    journeyStatus === "failed" ||
    effective === "journey_failed" ||
    effective === "failed"
  ) {
    return "journey_failed";
  }
  const phase = normalizeRunLifecycle(run);
  switch (phase) {
    case "awaiting_user":
      return "awaiting_scene_confirmation";
    case "active":
      return "journey_running";
    case "interrupted":
      return "journey_interrupted";
    case "failed":
      return "journey_failed";
    case "cancelled":
      return "journey_cancelled";
    case "completed":
      return "journey_succeeded";
    default:
      return null;
  }
}

export function resolveChapterWorkflowState(args: {
  composition: ChapterAnalysisUiState;
  pageView?: JourneyPageView | null;
  lifecycleRun?: Run | null;
  inFlight?: boolean;
  awaitingConfirmation?: boolean;
  chapterComplete?: boolean;
}): ChapterWorkflowState {
  const candidates: ChapterWorkflowState[] = [];
  if (args.awaitingConfirmation) candidates.push("awaiting_scene_confirmation");
  const fromPage = mapPageView(args.pageView);
  if (fromPage) candidates.push(fromPage);
  const fromLife = mapLifecycle(args.lifecycleRun);
  if (fromLife) candidates.push(fromLife);
  const fromComp = mapComposition(args.composition);
  if (fromComp) candidates.push(fromComp);
  // chapterComplete must not override an explicit interrupted/failed/cancelled page/lifecycle.
  const terminalOpen =
    fromPage === "journey_interrupted" ||
    fromPage === "journey_failed" ||
    fromPage === "journey_cancelled" ||
    fromPage === "journey_running" ||
    fromLife === "journey_interrupted" ||
    fromLife === "journey_failed" ||
    fromLife === "journey_cancelled" ||
    fromLife === "journey_running";
  if (args.chapterComplete && !terminalOpen) {
    candidates.push("journey_succeeded");
  }
  if (args.inFlight && !fromPage && !args.awaitingConfirmation && !terminalOpen) {
    candidates.push("scene_analysis_running");
  }
  if (!candidates.length) return "chapter_ready";
  return candidates.reduce(higherPriority);
}

export function buildChapterAnalysisPresentationV1(args: {
  chapterId: number | null;
  analysisRunId?: number | null;
  journeyRunId?: number | null;
  confirmedRevisionId?: number | null;
  confirmedSceneCount?: number | null;
  completedSceneCount?: number | null;
  totalSceneCount?: number | null;
  composition: ChapterAnalysisUiState;
  pageView?: JourneyPageView | null;
  lifecycleRun?: Run | null;
  inFlight?: boolean;
  awaitingConfirmation?: boolean;
  chapterComplete?: boolean;
  canResumeJourney?: boolean;
}): ChapterAnalysisPresentationV1 {
  const workflow_state = resolveChapterWorkflowState(args);
  const total =
    args.confirmedSceneCount ??
    args.totalSceneCount ??
    null;
  const completed = args.completedSceneCount ?? null;
  const can_resume =
    workflow_state === "journey_interrupted" && args.canResumeJourney !== false;
  const can_retry = workflow_state === "journey_failed";
  const can_restart_as_new =
    workflow_state === "journey_cancelled" ||
    workflow_state === "journey_failed" ||
    workflow_state === "journey_succeeded";

  let primary_action: ChapterPrimaryCta = "none";
  let status_title = "";
  let status_description = "";

  switch (workflow_state) {
    case "boundary_detecting":
      primary_action = "view_progress";
      status_title = "正在识别场景划分";
      status_description = "请稍候，场景划分建议生成后即可确认。";
      break;
    case "awaiting_scene_confirmation": {
      primary_action = "confirm_scenes";
      const n = total ?? args.confirmedSceneCount;
      status_title = "确认场景划分";
      status_description =
        n != null
          ? `已生成场景划分建议，共 ${n} 个场景。请确认是否采用，或手动调整场景边界。`
          : "已生成场景划分建议。请确认是否采用，或手动调整场景边界。";
      break;
    }
    case "scene_analysis_running":
      primary_action = "view_progress";
      status_title = "正在分析场景";
      status_description = "场景分析进行中，完成后将生成阅读旅程。";
      break;
    case "journey_running":
      primary_action = "view_progress";
      status_title = "正在生成阅读旅程";
      status_description =
        completed != null && total != null
          ? `已完成 ${completed} / ${total} 个场景。`
          : "阅读旅程生成中。";
      break;
    case "journey_interrupted":
      primary_action = "continue_analysis";
      status_title = "阅读旅程已中断";
      status_description =
        "已完成的场景分析不会受到影响，可继续本次分析或查看任务详情。";
      break;
    case "journey_cancelled":
      primary_action = "reanalyze";
      status_title = "本次分析已停止";
      status_description = "可重新开始分析本章。";
      break;
    case "journey_failed":
      primary_action = can_retry ? "continue_analysis" : "reanalyze";
      status_title = "阅读旅程生成失败";
      status_description = "请查看任务详情，或重新开始分析。";
      break;
    case "journey_succeeded":
      primary_action = "view_results";
      status_title = "阅读旅程已完成";
      status_description = "可以查看分析结果。";
      break;
    default:
      primary_action = "start_analysis";
      status_title = "尚未开始分析";
      status_description = "开始分析本章，生成场景划分与阅读旅程。";
  }

  const show_confirm_nav = workflow_state === "awaiting_scene_confirmation";
  const show_journey_nav =
    workflow_state === "journey_running" ||
    workflow_state === "journey_interrupted" ||
    workflow_state === "journey_succeeded" ||
    workflow_state === "scene_analysis_running";
  const show_results_nav = workflow_state === "journey_succeeded";
  const show_progress_nav =
    workflow_state === "boundary_detecting" ||
    workflow_state === "scene_analysis_running" ||
    workflow_state === "journey_running";

  return {
    chapter_id: args.chapterId,
    active_analysis_run_id: args.analysisRunId ?? null,
    active_journey_run_id: args.journeyRunId ?? null,
    confirmed_revision_id: args.confirmedRevisionId ?? null,
    confirmed_scene_count: total,
    workflow_state,
    completed_scene_count: completed,
    total_scene_count: total,
    can_confirm_scenes: show_confirm_nav,
    can_adjust_scenes: show_confirm_nav,
    can_open_journey: show_journey_nav,
    can_resume_journey: can_resume,
    can_view_results: show_results_nav,
    can_resume,
    can_retry,
    can_restart_as_new,
    primary_action,
    status_title,
    status_description,
    show_confirm_nav,
    show_journey_nav,
    show_analysis_nav: false,
    show_results_nav,
    show_progress_nav,
    redirect_journey_to_confirm: workflow_state === "awaiting_scene_confirmation",
  };
}

export function primaryCtaLabel(action: ChapterPrimaryCta, sceneCount?: number | null): string {
  switch (action) {
    case "view_progress":
      return "查看进度";
    case "confirm_scenes":
      return sceneCount != null ? `确认场景` : "确认场景";
    case "continue_analysis":
      return "继续分析";
    case "view_results":
      return "查看分析结果";
    case "start_analysis":
      return "开始分析";
    case "reanalyze":
      return "重新分析";
    default:
      return "";
  }
}

export function formatSceneOrdinalLabel(ordinal: number): string {
  return `S${String(ordinal).padStart(2, "0")}`;
}

export function formatSceneOrdinalRange(startOrdinal: number, count: number): string {
  if (count <= 0) return "无";
  if (count === 1) return formatSceneOrdinalLabel(startOrdinal);
  return `${formatSceneOrdinalLabel(startOrdinal)}–${formatSceneOrdinalLabel(startOrdinal + count - 1)}`;
}

export function formatCompletedScenesProgress(
  completed: number | null | undefined,
  total: number | null | undefined,
): string {
  if (completed == null || total == null) return "—";
  return `${completed} / ${total}`;
}
