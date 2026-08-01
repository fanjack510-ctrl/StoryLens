/**
 * CHG-20260729-011 — single ordinary-user chapter analysis presentation model.
 * All shell / nav / CTA / status surfaces should read this instead of re-deriving stage.
 */

import type { Run } from "../types";
import type { ChapterAnalysisUiState } from "../components/chapterAnalysis/mapAnalysisUiState";
import type { JourneyPageView } from "./resolveJourneyPageState";
import { normalizeRunLifecycle } from "./runLifecycle";
import {
  isJourneyActiveWorkflow,
  resolveJourneyActionFlags,
  resolveShowRecoveryCard,
} from "./journeyActiveRecoveryGuard";

export type ChapterWorkflowState =
  | "chapter_ready"
  | "boundary_detecting"
  | "awaiting_scene_confirmation"
  | "scene_analysis_running"
  | "waiting_scene_analysis"
  | "scene_analysis_failed"
  | "journey_starting"
  | "journey_running"
  | "journey_interrupted"
  | "journey_cancelled"
  | "journey_failed"
  | "journey_succeeded";

/** Ordinary top-nav「阅读旅程」— only after journey generation has started. */
export const JOURNEY_NAV_WORKFLOW_STATES: ReadonlySet<ChapterWorkflowState> = new Set([
  "journey_starting",
  "journey_running",
  "journey_interrupted",
  "journey_failed",
  "journey_cancelled",
  "journey_succeeded",
]);

/** Deep-link to Journey must leave these states (no empty / 尚未开始 intermediate page). */
export const JOURNEY_DEEP_LINK_REDIRECT_TO_PROGRESS: ReadonlySet<ChapterWorkflowState> =
  new Set([
    "boundary_detecting",
    "scene_analysis_running",
    "waiting_scene_analysis",
  ]);

export function shouldShowJourneyNav(workflowState: ChapterWorkflowState): boolean {
  return JOURNEY_NAV_WORKFLOW_STATES.has(workflowState);
}

/** Top-nav / toolbar: which surface owns the single green primary CTA. */
export type CompletedJourneyNavPrimary =
  | "view_progress"
  | "view_reading_journey"
  | "none";

/**
 * CHG-017 amendment: after journey_succeeded, green primary moves to 阅读旅程.
 * While journey_starting / journey_running, keep 查看分析进度 as green primary.
 */
export function resolveCompletedJourneyNavPrimary(input: {
  workflowState: ChapterWorkflowState;
  /** Current shell view: progress | reading | result | confirm | … */
  currentView: string;
  /** When on result, which tab is active. */
  resultTab?: "scenes" | "journey" | string | null;
}): CompletedJourneyNavPrimary {
  const { workflowState, currentView, resultTab } = input;
  if (
    workflowState === "journey_starting" ||
    workflowState === "journey_running" ||
    workflowState === "waiting_scene_analysis" ||
    workflowState === "scene_analysis_running"
  ) {
    return "view_progress";
  }
  if (workflowState !== "journey_succeeded") {
    return "none";
  }
  const onJourneyResult =
    currentView === "result" && (resultTab === "journey" || resultTab === "reader-journey");
  if (onJourneyResult) {
    return "none";
  }
  return "view_reading_journey";
}

/** Progress nav remains visible on journey_succeeded but must not stay primary. */
export function shouldShowProgressNavSecondary(workflowState: ChapterWorkflowState): boolean {
  return (
    workflowState === "boundary_detecting" ||
    workflowState === "journey_succeeded" ||
    workflowState === "journey_starting" ||
    workflowState === "journey_running" ||
    workflowState === "waiting_scene_analysis" ||
    workflowState === "scene_analysis_running" ||
    workflowState === "journey_interrupted" ||
    workflowState === "journey_failed" ||
    workflowState === "journey_cancelled" ||
    workflowState === "scene_analysis_failed"
  );
}

export type ChapterPrimaryCta =
  | "view_progress"
  | "confirm_scenes"
  | "continue_analysis"
  | "retry_journey"
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
  redirect_journey_to_progress: boolean;
  /** CHG-018 presentation flags — components must not override from stale recovery. */
  is_journey_active: boolean;
  show_recovery_card: boolean;
  show_resume_action: boolean;
  show_stop_action: boolean;
};

const PRIORITY: ChapterWorkflowState[] = [
  "journey_succeeded",
  "journey_cancelled",
  "scene_analysis_failed",
  "journey_failed",
  "journey_interrupted",
  "journey_running",
  "journey_starting",
  "waiting_scene_analysis",
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
      return "journey_starting";
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
  const journeyError = String((run as any).journey_error_code || (run as any).root_error_code || "");
  const parentStatus = String(run.status || "").toLowerCase();
  // CHG-015: scene-analysis stage failure must not look like journey synthesis failure.
  if (
    effective === "scene_analysis" ||
    journeyError === "WAITING_SCENE_ANALYSIS" ||
    journeyError === "SCENE_ANALYSIS_INCOMPLETE" ||
    parentStatus === "scene_analysis_partial" ||
    parentStatus === "failed_structural"
  ) {
    if (
      parentStatus.includes("fail") ||
      journeyError === "SCENE_ANALYSIS_INCOMPLETE" ||
      (journeyStatus === "failed" && journeyError === "SCENE_ANALYSIS_INCOMPLETE")
    ) {
      return "scene_analysis_failed";
    }
    if (journeyError === "WAITING_SCENE_ANALYSIS") {
      return "waiting_scene_analysis";
    }
    if (effective === "scene_analysis") {
      return "scene_analysis_running";
    }
  }
  // CHG-023: failed journey (incl. retryable) is never rewritten as interrupted.
  if (
    journeyStatus === "failed" ||
    effective === "journey_failed" ||
    effective === "failed"
  ) {
    return "journey_failed";
  }
  // Parent AnalysisRun may stay "succeeded" after scenes while journey is interrupted.
  if (
    journeyStatus === "interrupted" ||
    journeyStatus === "paused" ||
    journeyStatus === "scene_profiles_partial" ||
    journeyStatus === "budget_blocked" ||
    effective === "journey_interrupted" ||
    (journeyError === "JOURNEY_INTERRUPTED" && journeyStatus !== "succeeded")
  ) {
    return "journey_interrupted";
  }
  if (journeyStatus === "cancelled" || effective === "cancelled") {
    return "journey_cancelled";
  }
  if (
    journeyStatus === "starting" ||
    journeyStatus === "queued" ||
    journeyStatus === "pending"
  ) {
    return "journey_starting";
  }
  const phase = normalizeRunLifecycle(run);
  switch (phase) {
    case "awaiting_user":
      return "awaiting_scene_confirmation";
    case "active":
      if (journeyError === "WAITING_SCENE_ANALYSIS") {
        return "waiting_scene_analysis";
      }
      if (
        effective === "scene_analysis" ||
        parentStatus === "scene_analysis_running" ||
        parentStatus === "boundary_confirmed"
      ) {
        return "scene_analysis_running";
      }
      if (
        journeyStatus === "starting" ||
        journeyStatus === "queued" ||
        journeyStatus === "pending"
      ) {
        return "journey_starting";
      }
      if (
        journeyStatus === "running" ||
        journeyStatus === "scene_profiles_running" ||
        journeyStatus === "chapter_synthesis_running" ||
        effective === "journey_running"
      ) {
        return "journey_running";
      }
      if (
        parentStatus.includes("boundary") ||
        parentStatus === "running" ||
        parentStatus === "queued"
      ) {
        // Prefer boundary / scene over falsely advertising journey nav.
        return parentStatus === "boundary_confirmed" || parentStatus === "scene_analysis_running"
          ? "scene_analysis_running"
          : "boundary_detecting";
      }
      // Unknown active: keep journey nav hidden until journey status is explicit.
      return "scene_analysis_running";
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
  confirmedRevisionId?: number | null;
  /** Live bound journey status — CHG-023 succeeds over sticky interrupted pageView. */
  journeyStatus?: string | null;
}): ChapterWorkflowState {
  const liveJourney = String(args.journeyStatus || "").toLowerCase();
  // CHG-023: succeeded journey must never stay on interrupted workflow from sticky pageView.
  if (liveJourney === "succeeded") {
    return "journey_succeeded";
  }
  if (liveJourney === "cancelled") {
    return "journey_cancelled";
  }
  const candidates: ChapterWorkflowState[] = [];
  if (args.awaitingConfirmation) candidates.push("awaiting_scene_confirmation");
  const fromPage = mapPageView(args.pageView);
  if (fromPage) candidates.push(fromPage);
  const fromLife = mapLifecycle(args.lifecycleRun);
  const lifeIsSceneFailed = fromLife === "scene_analysis_failed";
  const lifeIsSceneRunning =
    fromLife === "scene_analysis_running" || fromLife === "waiting_scene_analysis";
  if (fromLife) candidates.push(fromLife);
  const fromComp = mapComposition(args.composition);
  // Parent AnalysisRun may stay "succeeded" after scenes while journey failed/interrupted.
  // Composition "succeeded" must not override an open journey terminal/active state.
  const terminalOpen =
    fromPage === "journey_interrupted" ||
    fromPage === "journey_failed" ||
    fromPage === "journey_cancelled" ||
    fromPage === "journey_running" ||
    fromPage === "journey_starting" ||
    fromLife === "journey_interrupted" ||
    fromLife === "journey_failed" ||
    fromLife === "journey_cancelled" ||
    fromLife === "journey_running" ||
    fromLife === "journey_starting" ||
    lifeIsSceneFailed ||
    lifeIsSceneRunning;
  if (
    fromComp &&
    !(
      fromComp === "journey_succeeded" &&
      (terminalOpen || lifeIsSceneFailed || lifeIsSceneRunning)
    )
  ) {
    if (
      fromComp === "scene_analysis_running" &&
      !lifeIsSceneRunning &&
      args.confirmedRevisionId == null &&
      !args.awaitingConfirmation
    ) {
      candidates.push("boundary_detecting");
    } else {
      candidates.push(fromComp);
    }
  }
  if (args.chapterComplete && !terminalOpen) {
    candidates.push("journey_succeeded");
  }
  if (args.inFlight && !fromPage && !args.awaitingConfirmation && !terminalOpen) {
    if (
      args.confirmedRevisionId == null &&
      (args.composition === "running" ||
        args.composition === "creating" ||
        args.composition === "partial")
    ) {
      candidates.push("boundary_detecting");
    } else {
      candidates.push("scene_analysis_running");
    }
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
  /** Live journey row status (starting/running/interrupted/…). */
  journeyStatus?: string | null;
  hasValidWorkerLease?: boolean | null;
  hasActiveTask?: boolean | null;
  hasCheckpointOrRecoveryBasis?: boolean | null;
  statusVersion?: number | null;
}): ChapterAnalysisPresentationV1 {
  // Explicit bound journey status only — do not inject parent/sibling lifecycle
  // journey_status into the CHG-023 succeed override (CHG-015 recoverable split).
  const workflow_state = resolveChapterWorkflowState({
    ...args,
    journeyStatus: args.journeyStatus,
  });
  const journeyStatus =
    args.journeyStatus ??
    (args.lifecycleRun as { journey_status?: string } | null | undefined)?.journey_status ??
    null;
  const total =
    args.confirmedSceneCount ??
    args.totalSceneCount ??
    null;
  const completed = args.completedSceneCount ?? null;
  const can_resume =
    workflow_state === "journey_interrupted" && args.canResumeJourney !== false;
  // CHG-023: retryable gate is independent of failure presentation.
  const can_retry =
    workflow_state === "journey_failed" && args.canResumeJourney !== false;
  const can_restart_as_new =
    workflow_state === "journey_cancelled" ||
    workflow_state === "journey_failed" ||
    workflow_state === "journey_succeeded";

  let primary_action: ChapterPrimaryCta = "none";
  let status_title = "";
  let status_description = "";

  const journeyStatusLower = String(journeyStatus || "").toLowerCase();
  const isResuming = journeyStatusLower === "resuming";

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
    case "waiting_scene_analysis":
      primary_action = "view_progress";
      status_title = "正在分析场景";
      status_description =
        "StoryLens 正在分析确认后的场景。全部场景完成后，将自动生成阅读旅程。";
      break;
    case "scene_analysis_failed":
      primary_action = "reanalyze";
      status_title = "场景分析未完成";
      status_description =
        completed != null && total != null
          ? `已完成 ${completed} / ${total} 个场景。第一个场景分析时发生错误，阅读旅程尚未开始生成。`
          : "场景分析未完成，阅读旅程尚未开始生成。";
      break;
    case "journey_starting":
      primary_action = "view_progress";
      if (isResuming) {
        status_title = "正在恢复阅读旅程";
        status_description = "正在从已保存的进度继续，无需重复操作。";
      } else {
        status_title = "正在启动阅读旅程";
        status_description = "任务已经创建，StoryLens 正在准备分析。";
      }
      break;
    case "journey_running":
      primary_action = "view_progress";
      if (isResuming) {
        status_title = "正在恢复阅读旅程";
        status_description = "正在从已保存的进度继续，无需重复操作。";
      } else {
        status_title = "正在生成阅读旅程";
        status_description =
          "StoryLens 正在整合场景之间的情绪、节奏和阅读牵引变化。";
      }
      break;
    case "journey_interrupted":
      primary_action = "continue_analysis";
      status_title = "阅读旅程已中断";
      status_description = "当前进度已保存，可以继续分析。";
      break;
    case "journey_cancelled":
      primary_action = "reanalyze";
      status_title = "本次分析已停止";
      status_description = "可重新开始分析本章。";
      break;
    case "journey_failed":
      // CHG-023: failure presentation first; retryable only gates retry CTA label.
      primary_action = can_retry ? "retry_journey" : "none";
      status_title = "阅读旅程生成失败";
      status_description =
        "StoryLens 在生成阅读旅程时遇到问题，已完成的场景分析结果仍会保留。";
      break;
    case "journey_succeeded":
      primary_action = "view_results";
      status_title = "阅读旅程已生成";
      status_description = "可从顶部进入阅读旅程查看最终结果。";
      break;
    default:
      primary_action = "start_analysis";
      status_title = "尚未开始分析";
      status_description = "开始分析本章，生成场景划分与阅读旅程。";
  }

  const show_confirm_nav = workflow_state === "awaiting_scene_confirmation";
  const show_journey_nav = shouldShowJourneyNav(workflow_state);
  const show_results_nav = workflow_state === "journey_succeeded";
  const show_progress_nav = shouldShowProgressNavSecondary(workflow_state);

  const show_recovery_card = resolveShowRecoveryCard({
    workflowState: workflow_state,
    journeyStatus,
    journeyPageActive: false,
    canResume: can_resume,
    hasValidWorkerLease: args.hasValidWorkerLease ?? false,
    hasActiveTask: args.hasActiveTask ?? isJourneyActiveWorkflow(workflow_state, journeyStatus),
    hasCheckpointOrRecoveryBasis: args.hasCheckpointOrRecoveryBasis ?? can_resume,
    currentAnalysisRunId: args.analysisRunId ?? null,
    planAnalysisRunId: args.analysisRunId ?? null,
    currentJourneyRunId: args.journeyRunId ?? null,
    planJourneyRunId: args.journeyRunId ?? null,
    currentConfirmedRevisionId: args.confirmedRevisionId ?? null,
    planConfirmedRevisionId: args.confirmedRevisionId ?? null,
    currentStatusVersion: args.statusVersion ?? null,
    planStatusVersion: args.statusVersion ?? null,
  });
  const actionFlags = resolveJourneyActionFlags({
    workflowState: workflow_state,
    journeyStatus,
    canResume: can_resume,
    showRecoveryCard: show_recovery_card,
  });

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
    can_resume_journey: can_resume && !actionFlags.isJourneyActive,
    can_view_results: show_results_nav,
    can_resume: can_resume && !actionFlags.isJourneyActive,
    can_retry,
    can_restart_as_new,
    primary_action: actionFlags.isJourneyActive ? "view_progress" : primary_action,
    status_title,
    status_description,
    show_confirm_nav,
    show_journey_nav,
    show_analysis_nav: false,
    show_results_nav,
    show_progress_nav,
    redirect_journey_to_confirm: workflow_state === "awaiting_scene_confirmation",
    redirect_journey_to_progress: JOURNEY_DEEP_LINK_REDIRECT_TO_PROGRESS.has(workflow_state),
    is_journey_active: actionFlags.isJourneyActive,
    show_recovery_card: actionFlags.showRecoveryCard,
    show_resume_action: actionFlags.showResumeAction,
    show_stop_action: actionFlags.showStopAction,
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
    case "retry_journey":
      return "重试阅读旅程";
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
