import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { analysisApi } from "../services/analysisApi";
import { booksApi } from "../services/booksApi";
import { ApiError } from "../services/apiClient";
import { Badge, Empty, ErrorState, Loading } from "../components/common/States";
import { OverflowMenu, type OverflowMenuItem } from "../components/layout/OverflowMenu";
import { UnifiedAnalysisRecoveryCard } from "../components/chapterAnalysis/UnifiedAnalysisRecoveryCard";
import { isBudgetPauseRun } from "../services/budgetPauseDetect";
import { BUDGET_ERROR_USER_COPY } from "../services/budgetErrorCopy";
import {
  chapterProgressHref,
  chapterResultHref,
} from "../services/discoverActiveChapterRun";
import { isSceneAnalysisComplete } from "../services/chapterJourneyComposition";
import { maybeTrackAnalysisCompleted } from "../services/telemetry/analysisRunTelemetry";
import { formatRunProgress } from "../services/runProgressDisplay";
import {
  isNativeOverviewRun,
  normalizeRunLifecycle,
  resolveTaskCenterPrimaryAction,
} from "../services/runLifecycle";
import {
  STOP_CONFIRM_BODY,
  STOP_CONFIRM_TITLE,
  canShowStopAnalysis,
  cancellationReasonLabel,
  formatCancelDetailHint,
  isCancelledStatus,
  isStoppingStatus,
  taskCancelStatusLabel,
} from "../services/taskCancellationUi";
import { isProNativeOverviewUiEnabled } from "../services/proNativeOverviewFlag";
import {
  formatCompletedScenesProgress,
  formatSceneOrdinalLabel,
  formatSceneOrdinalRange,
} from "../services/chapterAnalysisPresentation";
import "./tasksPage.css";

function taskContinueAvailabilityLabel(detail: {
  retryable?: boolean;
  journey_retryable?: boolean | null;
  status?: string;
  journey_status?: string | null;
  effective_status?: string | null;
}): string {
  const phase = normalizeRunLifecycle(detail as any);
  if (phase === "interrupted") {
    return detail.journey_retryable !== false ? "可继续本次分析" : "可重新开始分析";
  }
  return detail.retryable ? "可重试" : "不可重试";
}

type RecoveryState = "idle" | "checking" | "creating_recovery" | "created" | "failed";
type SceneResumeState = "idle" | "checking" | "resuming" | "done" | "failed";
type OfflineReplayState = "idle" | "replaying" | "succeeded" | "failed";
type StatusFilter = "all" | "running" | "failed" | "paused" | "succeeded" | "cancelled";

type RecoveryErrorView = {
  code: string;
  message: string;
  hint: string;
  httpStatus: number;
  requestId?: string;
  retryable?: boolean;
  providerName?: string;
  blockers?: string[];
};

const BLOCKER_LABELS: Record<string, string> = {
  cloud_master_switch_off: "云端总开关关闭",
  provider_disabled: "Provider未启用",
  provider_not_configured: "Provider未配置",
  credential_missing: "缺少API凭据",
  provider_disconnected: "Provider未连接",
  pricing_unavailable: "定价不可用",
  budget_unavailable: "预算不足",
  boundary_candidates_not_supported: "不支持边界候选",
  provider_unhealthy: "Provider传输不健康",
  provider_health_stale: "健康状态过期",
  provider_state_stale: "Provider状态已过期",
  RECOVERY_ALREADY_EXISTS: "已存在恢复任务",
  NO_RECOVERABLE_CHECKPOINTS: "无可复用检查点",
};

const RECOVERY_ERROR_COPY: Record<string, { message: string; hint: string }> = {
  CLOUD_CONSENT_REQUIRED: {
    message: "尚未确认发送正文到云端。",
    hint: "请勾选云端同意后再创建恢复任务。",
  },
  RECOVERY_ALREADY_EXISTS: {
    message: "已存在恢复任务。",
    hint: "请打开已有恢复任务，不要重复创建。",
  },
  PROVIDER_STATE_CHANGED: {
    message: "Provider状态已变化。",
    hint: "请刷新页面后重新确认预算与同意。",
  },
  INSUFFICIENT_BUDGET_RESERVATION: {
    message: BUDGET_ERROR_USER_COPY.INSUFFICIENT_BUDGET_RESERVATION,
    hint: "请使用「修复并继续」授权额度后重试；技术详情见下方。",
  },
  CLOUD_REQUEST_LIMIT_EXCEEDED: {
    message: BUDGET_ERROR_USER_COPY.CLOUD_REQUEST_LIMIT_EXCEEDED,
    hint: "请调整每日请求保护后继续同一任务。",
  },
  CLOUD_TOKEN_LIMIT_EXCEEDED: {
    message: BUDGET_ERROR_USER_COPY.CLOUD_TOKEN_LIMIT_EXCEEDED,
    hint: "请调整每日 Token 保护后继续同一任务。",
  },
  CLOUD_COST_LIMIT_EXCEEDED: {
    message: BUDGET_ERROR_USER_COPY.CLOUD_COST_LIMIT_EXCEEDED,
    hint: "请调整每日费用上限后继续同一任务。",
  },
  CLOUD_BUDGET_EXCEEDED: {
    message: BUDGET_ERROR_USER_COPY.CLOUD_BUDGET_EXCEEDED,
    hint: "请核对请求/Token/费用缺口后再继续。",
  },
  NO_RECOVERABLE_CHECKPOINTS: {
    message: "没有可复用的检查点。",
    hint: "请重新生成候选或检查历史Invocation。",
  },
  RECOVERY_RUN_CREATE_FAILED: {
    message: "创建恢复任务失败。",
    hint: "请查看技术详情后重试；不要重复付费点击。",
  },
  BACKEND_OFFLINE: {
    message: "无法连接后端服务。",
    hint: "请确认 StoryLens API 已启动。",
  },
  REQUEST_VALIDATION_ERROR: {
    message: "恢复请求参数不合法。",
    hint: "请刷新页面后重新勾选同意并提交。",
  },
  RECOVERY_CONFIRMATION_REQUIRED: {
    message: "尚未确认从已有结果继续。",
    hint: "请点击确认按钮创建恢复任务。",
  },
  NO_MANUAL_BOUNDARY_PROVIDER: {
    message: "当前Provider不可用于恢复。",
    hint: "请根据下方精确 blockers 处理后重试，不要重复发起真实连接测试。",
  },
};

function recoveryDisableReason(args: {
  consent: boolean;
  preflight?: any;
  state: RecoveryState;
}): string | null {
  if (args.state === "checking" || args.state === "creating_recovery") {
    return "正在创建恢复任务，请稍候";
  }
  if (!args.consent) return "未勾选云端同意";
  if (!args.preflight) return "正在加载恢复预算";
  if (args.preflight.blockers?.includes("RECOVERY_ALREADY_EXISTS")) {
    return `已存在恢复Run #${args.preflight.existing_recovery_run_id}`;
  }
  if (args.preflight.blockers?.includes("NO_RECOVERABLE_CHECKPOINTS")) {
    return "没有可复用检查点";
  }
  if (!args.preflight.within_budget) return "预算不足";
  return null;
}

function toRecoveryError(error: unknown): RecoveryErrorView {
  if (error instanceof ApiError) {
    const copy = RECOVERY_ERROR_COPY[error.code];
    const blockers = error.blockers || [];
    return {
      code: error.code,
      message: copy?.message || error.message,
      hint: copy?.hint || error.userActionHint || "请根据错误码处理后重试",
      httpStatus: error.status,
      requestId: error.requestId,
      retryable: error.retryable,
      providerName: error.providerName,
      blockers,
    };
  }
  const message = error instanceof Error ? error.message : "未知错误";
  return {
    code: "RECOVERY_RUN_CREATE_FAILED",
    message,
    hint: "请查看技术详情后重试",
    httpStatus: 0,
    retryable: true,
  };
}

async function resolveBookIdForChapter(chapterId: number): Promise<number | null> {
  const books = await booksApi.list();
  for (const book of books) {
    const chapters = await booksApi.chapters(book.id);
    if (chapters.some((chapter) => Number(chapter.id) === Number(chapterId))) {
      return book.id;
    }
  }
  return books[0]?.id ?? null;
}

function badgeToneForRun(run: any): string {
  if (isStoppingStatus(run?.status)) return "warning";
  if (isCancelledStatus(run?.status)) return "neutral";
  if (isBudgetPauseRun(run) || run.status === "awaiting_provider_recovery") {
    return "warning";
  }
  if (run.status === "succeeded" || run.status === "completed") {
    if (run.chapter_complete === true || run.status === "completed") return "success";
    if (isSceneAnalysisComplete(run)) return "warning";
    return "success";
  }
  if (
    run.status === "failed" ||
    run.status === "failed_structural" ||
    run.status === "failed_provider"
  ) {
    return "danger";
  }
  if (run.status === "cancelled" || run.status === "review_cancelled") return "neutral";
  return "info";
}

function SucceededRunRowActions({
  run,
  busy,
  onOpen,
}: {
  run: any;
  busy: boolean;
  onOpen: (tab: "reader-journey" | "analysis") => void;
}) {
  const journey = useQuery({
    queryKey: ["reader-journey", run.id],
    queryFn: () => analysisApi.readerJourney(run.id),
    enabled: run.status === "succeeded",
    staleTime: 5000,
  });
  const hasJourney = Boolean(
    journey.data?.status === "succeeded" && journey.data.visualization,
  );
  const journeyActive = Boolean(
    journey.data?.status &&
      ["queued", "running", "scene_profiles_running", "chapter_synthesis_running"].includes(
        journey.data.status,
      ),
  );
  const sceneDone = isSceneAnalysisComplete(run);

  const primaryOpen = () => {
    if (hasJourney || journeyActive) onOpen("reader-journey");
    else onOpen("analysis");
  };

  const moreItems: OverflowMenuItem[] = [];
  if (hasJourney) {
    moreItems.push({
      id: "open-analysis",
      label: "查看场景分析",
      onSelect: () => onOpen("analysis"),
    });
  } else if (journeyActive) {
    moreItems.push({
      id: "open-analysis",
      label: "查看场景分析",
      onSelect: () => onOpen("analysis"),
    });
  } else if (sceneDone) {
    moreItems.push({
      id: "fix-continue",
      label: "继续生成阅读旅程",
      testId: `unified-recover-open-${run.id}`,
      onSelect: () => onOpen("reader-journey"),
      disabled: busy,
    });
  }

  return (
    <div className="tasks-row-actions">
      <button
        type="button"
        className="primary"
        data-testid={
          journeyActive ? `view-journey-progress-${run.id}` : `view-results-${run.id}`
        }
        disabled={busy}
        onClick={primaryOpen}
      >
        查看详情
      </button>
      {moreItems.length > 0 && (
        <OverflowMenu
          data-testid={`run-more-${run.id}`}
          items={moreItems.map((item) => ({
            ...item,
            disabled: item.disabled || busy,
          }))}
        />
      )}
    </div>
  );
}

export function TasksPage() {
  const navigate = useNavigate();
  const [detail, setDetail] = useState<any>();
  const [detailInvocations, setDetailInvocations] = useState<unknown[]>([]);
  const [detailInvocationsError, setDetailInvocationsError] = useState<string>();
  const [recoveryPreflight, setRecoveryPreflight] = useState<any>();
  const [recoveryConsent, setRecoveryConsent] = useState(false);
  const [recoveryState, setRecoveryState] = useState<RecoveryState>("idle");
  const [recoveryError, setRecoveryError] = useState<RecoveryErrorView>();
  const [createdRecovery, setCreatedRecovery] = useState<any>();
  const [highlightRunId, setHighlightRunId] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [clientRequestId] = useState(
    () => globalThis.crypto?.randomUUID?.() || `recover-${Date.now()}`,
  );
  const [, setSceneResumePreflight] = useState<any>();
  const [, setSceneResumeConsent] = useState(false);
  const [, setSceneResumeState] = useState<SceneResumeState>("idle");
  const [, setSceneResumeError] = useState<RecoveryErrorView>();
  const [, setOfflineReplayState] = useState<OfflineReplayState>("idle");
  const [, setOfflineReplayMessage] = useState<string>();
  const [, setOfflineReplayError] = useState<RecoveryErrorView>();
  const [navBusyRunId, setNavBusyRunId] = useState<number | null>(null);
  const [stopConfirmRun, setStopConfirmRun] = useState<any | null>(null);
  const [stopSubmitting, setStopSubmitting] = useState(false);
  const [stopError, setStopError] = useState<{ code: string; message: string } | null>(null);
  const qc = useQueryClient();
  const runs = useQuery({
    queryKey: ["runs"],
    queryFn: () => analysisApi.runs(),
    refetchInterval: 5000,
    retry: 1,
    // Avoid infinite spinner if a request stalls; surface error/empty instead.
    networkMode: "always",
  });

  useEffect(() => {
    for (const run of runs.data ?? []) {
      maybeTrackAnalysisCompleted(run);
    }
  }, [runs.data]);

  const retry = async (id: number) => {
    await analysisApi.retry(id);
    await qc.invalidateQueries({ queryKey: ["runs"] });
  };

  const submitStopAnalysis = async () => {
    if (!stopConfirmRun || stopSubmitting) return;
    setStopSubmitting(true);
    setStopError(null);
    try {
      await analysisApi.cancel(stopConfirmRun.id, {
        reason: "user_requested",
        expected_version: stopConfirmRun.status_version,
        client_request_id:
          globalThis.crypto?.randomUUID?.() || `cancel-${Date.now()}`,
      });
      setStopConfirmRun(null);
      await qc.invalidateQueries({ queryKey: ["runs"] });
    } catch (error) {
      const code = error instanceof ApiError ? error.code : "CANCEL_FAILED";
      const message =
        error instanceof ApiError
          ? error.message
          : "提交停止请求失败，请稍后重试。";
      setStopError({ code: String(code || "CANCEL_FAILED"), message });
    } finally {
      setStopSubmitting(false);
    }
  };

  const openChapterProgress = async (run: any) => {
    const taskType = String(run.task_type || "");
    if (
      taskType === "whole_book_v2" ||
      run.analysis_type === "whole_book_v2" ||
      run.mode_label === "全书 V2" ||
      run.whole_book_run_id != null
    ) {
      const bookId = Number(run.book_id || run.subject_id);
      if (Number.isFinite(bookId) && bookId > 0) {
        navigate(`/books/${bookId}/whole-book-v2`);
        return;
      }
    }
    if (isNativeOverviewRun(run) || run.task_type === "whole_book_overview" || run.subject_type === "book") {
      const bookId = Number(run.book_id || run.subject_id);
      if (Number.isFinite(bookId) && bookId > 0) {
        navigate(`/books/${bookId}/pro-native-overview?run_id=${run.id}`);
        return;
      }
    }
    const chapterId = Number(run.subject_id);
    if (!Number.isFinite(chapterId) || chapterId <= 0) {
      setDetail(run);
      return;
    }
    setNavBusyRunId(run.id);
    try {
      const bookId = await resolveBookIdForChapter(chapterId);
      if (!bookId) {
        setDetail(run);
        return;
      }
      // Navigate only — do not adjust budget or call model APIs here.
      navigate(
        chapterProgressHref({
          bookId,
          chapterId,
          analysisRunId: run.id,
        }),
      );
    } finally {
      setNavBusyRunId(null);
    }
  };

  const openChapterResult = async (
    run: any,
    tab: "reader-journey" | "analysis" = "analysis",
  ) => {
    if (isNativeOverviewRun(run) || run.task_type === "whole_book_overview" || run.subject_type === "book") {
      const bookId = Number(run.book_id || run.subject_id);
      if (Number.isFinite(bookId) && bookId > 0) {
        navigate(`/books/${bookId}/pro-native-overview?run_id=${run.id}`);
        return;
      }
    }
    const chapterId = Number(run.subject_id);
    if (!Number.isFinite(chapterId) || chapterId <= 0) {
      setDetail(run);
      return;
    }
    setNavBusyRunId(run.id);
    try {
      const bookId = await resolveBookIdForChapter(chapterId);
      if (!bookId) {
        setDetail(run);
        return;
      }
      navigate(
        chapterResultHref({
          bookId,
          chapterId,
          analysisRunId: run.id,
          tab,
        }),
      );
    } finally {
      setNavBusyRunId(null);
    }
  };
  const openDetail = async (run: any) => {
    setDetail(run);
    setDetailInvocations([]);
    setDetailInvocationsError(undefined);
    setRecoveryPreflight(undefined);
    setRecoveryConsent(false);
    setRecoveryState("idle");
    setRecoveryError(undefined);
    setCreatedRecovery(undefined);
    setSceneResumePreflight(undefined);
    setSceneResumeConsent(false);
    setSceneResumeState("idle");
    setSceneResumeError(undefined);
    setOfflineReplayState("idle");
    setOfflineReplayMessage(undefined);
    setOfflineReplayError(undefined);
    try {
      const fresh = await analysisApi.run(run.id);
      setDetail(fresh);
      try {
        setDetailInvocations(await analysisApi.invocations(run.id));
      } catch (invocationError) {
        setDetailInvocations([]);
        setDetailInvocationsError(
          invocationError instanceof Error
            ? invocationError.message
            : "无法加载模型调用详情",
        );
      }
      if (fresh.detection_recovery_available || fresh.checkpoint_available) {
        setRecoveryPreflight(await analysisApi.recoveryPreflight(run.id));
      }
      if (fresh.scene_analysis_resume_available) {
        setSceneResumePreflight(await analysisApi.sceneAnalysisResumePreflight(run.id));
      }
    } catch (error) {
      setRecoveryError(toRecoveryError(error));
      setRecoveryState("failed");
    }
  };
  const continueFromCheckpoints = async () => {
    if (!detail) {
      setRecoveryState("failed");
      setRecoveryError({
        code: "REQUEST_VALIDATION_ERROR",
        message: "缺少任务详情，无法恢复。",
        hint: "请关闭弹窗后重新打开任务详情。",
        httpStatus: 0,
        retryable: true,
      });
      return;
    }
    if (recoveryState === "checking" || recoveryState === "creating_recovery") {
      return;
    }
    if (!recoveryConsent) {
      setRecoveryState("failed");
      setRecoveryError({
        code: "CLOUD_CONSENT_REQUIRED",
        message: RECOVERY_ERROR_COPY.CLOUD_CONSENT_REQUIRED.message,
        hint: RECOVERY_ERROR_COPY.CLOUD_CONSENT_REQUIRED.hint,
        httpStatus: 422,
        retryable: false,
      });
      return;
    }
    const disableReason = recoveryDisableReason({
      consent: recoveryConsent,
      preflight: recoveryPreflight,
      state: recoveryState,
    });
    if (disableReason && recoveryPreflight && !recoveryPreflight.within_budget) {
      setRecoveryState("failed");
      setRecoveryError({
        code: "INSUFFICIENT_BUDGET_RESERVATION",
        message: RECOVERY_ERROR_COPY.INSUFFICIENT_BUDGET_RESERVATION.message,
        hint: RECOVERY_ERROR_COPY.INSUFFICIENT_BUDGET_RESERVATION.hint,
        httpStatus: 409,
        retryable: true,
      });
      return;
    }
    if (recoveryPreflight?.existing_recovery_run_id) {
      setRecoveryState("failed");
      setRecoveryError({
        code: "RECOVERY_ALREADY_EXISTS",
        message: `已存在恢复任务 #${recoveryPreflight.existing_recovery_run_id}`,
        hint: RECOVERY_ERROR_COPY.RECOVERY_ALREADY_EXISTS.hint,
        httpStatus: 409,
        retryable: false,
      });
      setHighlightRunId(recoveryPreflight.existing_recovery_run_id);
      return;
    }

    setRecoveryError(undefined);
    setRecoveryState("checking");
    try {
      const fresh = await analysisApi.recoverPreflight(detail.id, {
        cloud_consent: true,
      });
      setRecoveryPreflight({
        ...recoveryPreflight,
        ...fresh,
        remaining_detection_batch_count: fresh.remaining_batch_count,
        expected_request_count: fresh.expected_requests,
        worst_case_request_count: fresh.worst_case_requests,
        estimated_total_tokens: fresh.estimated_tokens,
        worst_case_cost: fresh.worst_case_cost,
        within_budget: fresh.within_budget,
        blockers: fresh.blockers,
        existing_recovery_run_id: fresh.blockers.includes("RECOVERY_ALREADY_EXISTS")
          ? recoveryPreflight?.existing_recovery_run_id
          : null,
      });
      if (!fresh.eligible) {
        setRecoveryState("failed");
        setRecoveryError({
          code: fresh.blockers.includes("budget_unavailable")
            ? "INSUFFICIENT_BUDGET_RESERVATION"
            : fresh.blockers.includes("RECOVERY_ALREADY_EXISTS")
              ? "RECOVERY_ALREADY_EXISTS"
            : "NO_MANUAL_BOUNDARY_PROVIDER",
          message: fresh.blockers.includes("budget_unavailable")
            ? RECOVERY_ERROR_COPY.INSUFFICIENT_BUDGET_RESERVATION.message
            : `Provider ${fresh.provider_name} 当前不可用于恢复`,
          hint: fresh.blockers
            .map((item) => BLOCKER_LABELS[item] || item)
            .join("；") || RECOVERY_ERROR_COPY.NO_MANUAL_BOUNDARY_PROVIDER.hint,
          httpStatus: 409,
          retryable: false,
          providerName: fresh.provider_name,
          blockers: fresh.blockers,
        });
        return;
      }
      if (!fresh.within_budget) {
        setRecoveryState("failed");
        setRecoveryError({
          code: "INSUFFICIENT_BUDGET_RESERVATION",
          message: RECOVERY_ERROR_COPY.INSUFFICIENT_BUDGET_RESERVATION.message,
          hint: RECOVERY_ERROR_COPY.INSUFFICIENT_BUDGET_RESERVATION.hint,
          httpStatus: 409,
          retryable: true,
          providerName: fresh.provider_name,
          blockers: fresh.blockers,
        });
        return;
      }

      setRecoveryState("creating_recovery");
      const result = await analysisApi.continueFromCheckpoints(detail.id, {
        client_request_id: clientRequestId,
        cloud_consent: true,
        confirmed: true,
        provider_state_version: fresh.provider_state_version,
      });
      setCreatedRecovery(result);
      setRecoveryState("created");
      setHighlightRunId(result.run_id);
      await qc.invalidateQueries({ queryKey: ["runs"] });
      window.setTimeout(() => {
        setDetail(undefined);
      }, 900);
    } catch (error) {
      setRecoveryState("failed");
      setRecoveryError(toRecoveryError(error));
    }
  };

  const disableReason = recoveryDisableReason({
    consent: recoveryConsent,
    preflight: recoveryPreflight,
    state: recoveryState,
  });
  const recoveryBusy =
    recoveryState === "checking" || recoveryState === "creating_recovery";
  const recoveryDisabled = Boolean(disableReason) || recoveryBusy;

  const statusLabel: Record<string, string> = {
    queued: "排队中",
    pending: "排队中",
    preparing: "准备中",
    running: "进行中",
    boundary_candidates_running: "正在生成边界候选",
    awaiting_boundary_review: "等待边界审阅",
    awaiting_provider_recovery: "分析已暂停",
    boundary_confirmed: "边界已确认",
    boundary_confirmed_budget_blocked: "分析已暂停",
    aborted_by_limit: "分析已暂停",
    scene_analysis_running: "场景分析中",
    scene_analysis_partial: "场景分析部分完成",
    boundary_candidates_partial: "候选生成部分完成",
    failed_structural: "结构校验失败",
    failed_provider: "服务请求失败",
    succeeded: "已完成",
    completed: "已完成",
    cancelled: "已停止",
    review_cancelled: "已停止",
    cancellation_requested: "正在停止",
    stopping: "正在停止",
    review_expired: "审阅已过期",
    failed: "失败",
  };
  const overviewUserError = (run: any): string | null => {
    const code = run?.error_code || run?.root_error_code || run?.failure_reason_code;
    if (code === "PROVIDER_OUTPUT_INVALID") {
      return "模型返回的分析结果格式不符合要求，任务未完成。";
    }
    if (code === "PROVIDER_OUTPUT_EMPTY") {
      return "模型返回空结果，任务未完成。";
    }
    if (code === "SCENE_BOUNDARY_OUTPUT_TRUNCATED_AT_HARD_CAP") {
      return "模型输出达到当前上限，边界裁决未能生成完整结果。";
    }
    if (code === "SCENE_BOUNDARY_OUTPUT_BUDGET_TOO_LOW") {
      return "当前模型输出上限不足以完成边界裁决。请将最大输出 Token 调整到至少 1024 后重试。";
    }
    if (code === "SCENE_BOUNDARY_OUTPUT_TRUNCATED" || code === "OUTPUT_TRUNCATED") {
      return "模型输出达到上限，StoryLens 正在提高本次裁决的输出预算。";
    }
    return null;
  };
  const runStatusLabel = (run: any) => {
    const cancelLabel = taskCancelStatusLabel(run?.status);
    if (cancelLabel) return cancelLabel;
    if (
      (run.failure_reason_code === "SCENE_BOUNDARY_OUTPUT_TRUNCATED" ||
        run.root_error_code === "SCENE_BOUNDARY_OUTPUT_TRUNCATED") &&
      run.status === "running"
    ) {
      return "正在调整输出上限并重试";
    }
    if (isBudgetPauseRun(run)) return "分析已暂停";
    if (run.status === "awaiting_provider_recovery") return "分析已暂停";
    if (run.task_type === "whole_book_overview" || run.subject_type === "book") {
      if (run.status === "completed") return "已完成";
      if (run.status === "failed") return "失败";
    }
    const phase = normalizeRunLifecycle(run);
    if (phase === "active") {
      const js = String(run.journey_status || "");
      if (
        [
          "queued",
          "running",
          "scene_profiles_running",
          "chapter_synthesis_running",
          "summary_running",
          "phase_analysis_running",
        ].includes(js) ||
        run.effective_status === "journey_running"
      ) {
        return "正在生成阅读旅程";
      }
      if (run.effective_status === "partial_complete") {
        return "场景分析已完成";
      }
    }
    if (phase === "interrupted") {
      return "阅读旅程已中断";
    }
    if (run.status === "succeeded") {
      if (run.chapter_complete === true || phase === "completed") return "已完成";
      if (isSceneAnalysisComplete(run) || run.effective_status === "partial_complete") {
        return "场景分析已完成";
      }
      return "已完成";
    }
    return statusLabel[run.status] || "处理中";
  };
  const filteredRuns = useMemo(() => {
    const nativeOverviewVisible = isProNativeOverviewUiEnabled();
    const matchesStatusFilter = (run: any): boolean => {
      if (!nativeOverviewVisible && isNativeOverviewRun(run)) {
        return false;
      }
      if (statusFilter === "all") return true;
      if (statusFilter === "paused") {
        return (
          isBudgetPauseRun(run) ||
          run.status === "awaiting_provider_recovery" ||
          run.status === "boundary_confirmed_budget_blocked" ||
          run.status === "aborted_by_limit" ||
          run.effective_status === "partial_complete" ||
          run.effective_status === "journey_failed"
        );
      }
      if (statusFilter === "failed") {
        return (
          !isBudgetPauseRun(run) &&
          ["failed", "failed_structural", "failed_provider"].includes(run.status)
        );
      }
      if (statusFilter === "succeeded") {
        return (
          (run.status === "succeeded" && run.chapter_complete === true) ||
          run.status === "completed"
        );
      }
      if (statusFilter === "cancelled") {
        return isCancelledStatus(run.status) || isStoppingStatus(run.status);
      }
      if (statusFilter === "running") {
        return (
          [
            "queued",
            "running",
            "pending",
            "preparing",
            "analyzing",
            "materializing",
            "synthesizing",
            "paused",
            "boundary_candidates_running",
            "scene_analysis_running",
            "awaiting_boundary_review",
            "boundary_confirmed",
            "scene_analysis_partial",
            "boundary_candidates_partial",
          ].includes(run.status) ||
          run.effective_status === "journey_running" ||
          normalizeRunLifecycle(run) === "active" ||
          normalizeRunLifecycle(run) === "awaiting_user"
        );
      }
      return true;
    };
    return (runs.data ?? []).filter(matchesStatusFilter);
  }, [runs.data, statusFilter]);
  const showDetectionRecovery = Boolean(
    detail?.detection_recovery_available && detail?.remaining_detection_batch_count > 0,
  );
  const showSceneResume = Boolean(detail?.scene_analysis_resume_available);
  const copyRunError = (run: any) => {
    void navigator.clipboard?.writeText(
      JSON.stringify(
        {
          run_id: run.id,
          top_level_error_code: run.error_code,
          root_error_code: run.root_error_code,
          root_error_message: run.root_error_message,
          failed_stage: run.failed_stage,
          provider: run.provider,
          model: run.model,
          failed_invocation_id: run.failed_invocation_id,
          retryable: run.retryable,
          user_action_hint: run.user_action_hint,
          budget_required: run.budget_required,
          budget_remaining: run.budget_remaining,
          exceeded_dimensions: run.exceeded_dimensions,
          reservation_status: run.reservation_status,
        },
        null,
        2,
      ),
    );
  };
  const buildRowMoreItems = (run: any): OverflowMenuItem[] => {
    const items: OverflowMenuItem[] = [];
    const canRecover =
      isBudgetPauseRun(run) ||
      run.status === "awaiting_provider_recovery" ||
      run.scene_analysis_resume_available ||
      run.status === "scene_analysis_partial" ||
      (run.status === "failed" && run.failed_stage === "scene_analysis");
    if (run.status === "failed" && !isBudgetPauseRun(run)) {
      items.push({
        id: "retry",
        label: "重试",
        onSelect: () => void retry(run.id),
      });
    }
    if (canRecover) {
      items.push({
        id: "recover",
        label: "修复并继续",
        testId: `unified-recover-open-${run.id}`,
        disabled: navBusyRunId === run.id,
        onSelect: () => void openDetail(run),
      });
    }
    // Optional Reader Journey continue — never gates primary result routing.
    if (
      run.status === "succeeded" &&
      isSceneAnalysisComplete(run) &&
      run.chapter_complete !== true
    ) {
      items.push({
        id: "journey-continue",
        label: "继续生成阅读旅程",
        testId: `unified-recover-open-${run.id}`,
        disabled: navBusyRunId === run.id,
        onSelect: () => void openChapterResult(run, "reader-journey"),
      });
    }
    if (run.status !== "succeeded") {
      items.push({
        id: "copy-error",
        label: "复制错误",
        onSelect: () => copyRunError(run),
      });
    }
    return items;
  };
  return (
    <section className="page tasks-page">
      <div className="page-title">
        <div>
          <p className="eyebrow">执行与审计</p>
          <h1>任务中心</h1>
          <p>查看分析任务状态、进度、服务商与失败原因；支持重试、恢复与暂停处理。</p>
        </div>
        <select
          className="tasks-status-filter"
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}
          aria-label="按状态筛选"
        >
          <option value="all">全部状态</option>
          <option value="running">进行中</option>
          <option value="paused">已暂停</option>
          <option value="failed">失败</option>
          <option value="succeeded">已完成</option>
          <option value="cancelled">已停止</option>
        </select>
      </div>
      {highlightRunId && (
        <p className="notice" data-testid="recovery-highlight">
          已定位恢复任务 #{highlightRunId}
          {createdRecovery?.recovered_from_run_id
            ? `（来源任务 #${createdRecovery.recovered_from_run_id}）`
            : ""}
        </p>
      )}
      <div className="panel table-wrap">
        {runs.isLoading ? (
          <Loading />
        ) : runs.error ? (
          <ErrorState
            error={runs.error as Error}
            classifyTaskErrors
            retry={() => void runs.refetch()}
          />
        ) : filteredRuns.length ? (
          <table>
            <thead>
              <tr>
                <th>任务</th>
                <th>章节</th>
                <th>模式</th>
                <th>服务商 / 模型</th>
                <th>状态</th>
                <th>进度</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {filteredRuns.map((run: any) => {
                const phase = normalizeRunLifecycle(run);
                const primary = resolveTaskCenterPrimaryAction(run);
                const status = String(run.status || "").toLowerCase();
                const moreItems = buildRowMoreItems(run).filter((item) => {
                  if (item.id !== "recover") return true;
                  return (
                    phase === "failed" ||
                    phase === "active" ||
                    status === "scene_analysis_partial" ||
                    status === "boundary_candidates_partial"
                  );
                });
                const onPrimary = () => {
                  if (primary.kind === "confirm" || primary.kind === "progress") {
                    void openChapterProgress(run);
                    return;
                  }
                  if (primary.kind === "result") {
                    void openChapterResult(run, "analysis");
                    return;
                  }
                  if (primary.kind === "detail") {
                    openDetail(run);
                  }
                };
                return (
                <tr
                  key={run.id}
                  data-highlighted={highlightRunId === run.id ? "true" : undefined}
                  className={highlightRunId === run.id ? "selected" : undefined}
                >
                  <td>
                    <button
                      type="button"
                      className="linkish"
                      data-testid={`open-run-${run.id}`}
                      onClick={() => void openChapterProgress(run)}
                    >
                      #{run.id}
                    </button>
                  </td>
                  <td>{run.subject_id ?? "—"}</td>
                  <td>
                    {run.execution_mode === "cloud"
                      ? "云端"
                      : run.execution_mode === "local"
                        ? "本地"
                        : run.execution_mode === "hybrid"
                          ? "混合"
                          : run.execution_mode || "—"}
                    {run.sends_content_to_cloud && (
                      <Badge tone="warning">云端正文</Badge>
                    )}
                    {run.recovered_from_run_id && (
                      <small>来自 #{run.recovered_from_run_id}</small>
                    )}
                  </td>
                  <td>
                    <b>{run.provider || "—"}</b>
                    <small>{run.model || "—"}</small>
                  </td>
                  <td>
                    <Badge tone={badgeToneForRun(run)}>
                      {runStatusLabel(run)}
                    </Badge>
                    {run.current_stage && (
                      <small>
                        阶段：
                        {run.current_stage === "scene_analysis" ||
                        run.current_stage === "scene_analysis_budget"
                          ? `场景分析 ${run.completed_scene_count ?? 0}/${run.total_scene_count ?? 0}`
                          : statusLabel[run.current_stage] || "进行中"}
                      </small>
                    )}
                  </td>
                  <td>
                    <span
                      data-testid={
                        typeof run.total_scene_count === "number" && run.total_scene_count > 0
                          ? `run-${run.id}-scene-progress`
                          : `run-${run.id}-progress`
                      }
                    >
                      {formatRunProgress(run)}
                    </span>
                  </td>
                  <td>{run.created_at ? new Date(run.created_at).toLocaleString() : "—"}</td>
                  <td>
                    <div className="tasks-row-actions">
                      {primary.kind !== "none" ? (
                        <button
                          type="button"
                          className="primary"
                          data-testid={primary.testId}
                          disabled={navBusyRunId === run.id}
                          onClick={onPrimary}
                        >
                          {primary.label}
                        </button>
                      ) : null}
                      {canShowStopAnalysis(run) ? (
                        <button
                          type="button"
                          className="tasks-stop-btn"
                          data-testid={`stop-analysis-${run.id}`}
                          aria-label="停止分析"
                          disabled={stopSubmitting && stopConfirmRun?.id === run.id}
                          onClick={() => {
                            setStopError(null);
                            setStopConfirmRun(run);
                          }}
                        >
                          停止分析
                        </button>
                      ) : null}
                      {isCancelledStatus(run.status) ? (
                        <button
                          type="button"
                          className="ghost"
                          data-testid={`reanalyze-${run.id}`}
                          disabled={navBusyRunId === run.id}
                          onClick={() => void openChapterProgress(run)}
                        >
                          重新分析
                        </button>
                      ) : null}
                      {isStoppingStatus(run.status) ? (
                        <small className="tasks-stopping-hint" data-testid={`stopping-hint-${run.id}`}>
                          正在结束当前请求，不会再启动后续分析。
                        </small>
                      ) : null}
                      {moreItems.length > 0 && (
                        <OverflowMenu
                          data-testid={`run-more-${run.id}`}
                          items={moreItems}
                        />
                      )}
                    </div>
                  </td>
                </tr>
              );
              })}
            </tbody>
          </table>
        ) : (
          <Empty text={runs.data?.length ? "没有符合筛选条件的任务" : "暂无分析任务"} />
        )}
      </div>
      {detail && (
        <div className="modal-backdrop">
          <div className="modal tasks-detail-modal">
            <header>
              <h2>任务详情</h2>
              <button type="button" onClick={() => setDetail(undefined)}>×</button>
            </header>
            <div className="tasks-detail-sections">
              <section className="tasks-detail-section">
                <h3>基本信息</h3>
                <dl>
                  <dt>任务编号</dt>
                  <dd>#{detail.id}</dd>
                  <dt>状态</dt>
                  <dd>
                    <Badge tone={badgeToneForRun(detail)}>{runStatusLabel(detail)}</Badge>
                  </dd>
                  <dt>章节</dt>
                  <dd>{detail.subject_id ?? "—"}</dd>
                  <dt>模式</dt>
                  <dd>{detail.execution_mode || "—"}</dd>
                  <dt>服务商</dt>
                  <dd>{detail.provider || "—"}</dd>
                  <dt>模型</dt>
                  <dd>{detail.model || "—"}</dd>
                  <dt>边界修订</dt>
                  <dd>{detail.boundary_revision_id ? `#${detail.boundary_revision_id}` : "无"}</dd>
                </dl>
              </section>

              {(isCancelledStatus(detail.status) || isStoppingStatus(detail.status)) && (
                <section className="tasks-detail-section" data-testid="cancel-detail-section">
                  <h3>停止信息</h3>
                  <dl>
                    <dt>停止状态</dt>
                    <dd>{taskCancelStatusLabel(detail.status) || runStatusLabel(detail)}</dd>
                    <dt>停止请求时间</dt>
                    <dd>
                      {detail.cancellation_requested_at
                        ? new Date(detail.cancellation_requested_at).toLocaleString()
                        : "—"}
                    </dd>
                    <dt>实际停止时间</dt>
                    <dd>
                      {detail.cancelled_at
                        ? new Date(detail.cancelled_at).toLocaleString()
                        : "—"}
                    </dd>
                    <dt>停止原因</dt>
                    <dd>{cancellationReasonLabel(detail.cancellation_reason)}</dd>
                    <dt>场景进度</dt>
                    <dd data-testid="cancel-scene-progress">
                      {formatCancelDetailHint(detail) ||
                        `${detail.completed_scene_count ?? 0} / ${detail.total_scene_count ?? 0}`}
                    </dd>
                    <dt>实际用量</dt>
                    <dd data-testid="cancel-usage">
                      {detail.usage_invocation_count != null
                        ? `停止前已调用：${detail.usage_invocation_count} 次；Token：${
                            detail.usage_total_tokens ?? "—"
                          }；估算费用：${
                            detail.usage_estimated_cost != null
                              ? detail.usage_estimated_cost
                              : "—"
                          }`
                        : "暂无调用记录（可能尚未发起模型请求）"}
                    </dd>
                    <dt>预算预留</dt>
                    <dd>
                      {detail.reservation_status === "released" ||
                      detail.reservation_status === "consumed"
                        ? detail.reservation_status === "released"
                          ? "已释放"
                          : "已结算"
                        : detail.reservation_status || "—"}
                    </dd>
                    <dt>重新分析</dt>
                    <dd>{detail.can_restart_as_new_task !== false ? "可创建新任务" : "—"}</dd>
                  </dl>
                </section>
              )}

              <section className="tasks-detail-section">
                <h3>执行过程</h3>
                <dl>
                  <dt>失败阶段</dt>
                  <dd>
                    {(detail.actual_failed_stage || detail.failed_stage) === "scene_analysis"
                      ? "场景分析"
                      : (detail.actual_failed_stage || detail.failed_stage) === "provider_request"
                        ? "服务请求"
                        : (detail.actual_failed_stage || detail.failed_stage || detail.current_stage || "未知")}
                  </dd>
                  {detail.failure_substage ? (
                    <>
                      <dt>实际子阶段</dt>
                      <dd data-testid="detail-failure-substage">{detail.failure_substage}</dd>
                    </>
                  ) : null}
                  {detail.failure_reason_code ? (
                    <>
                      <dt>错误码</dt>
                      <dd data-testid="detail-failure-reason-code">{detail.failure_reason_code}</dd>
                    </>
                  ) : null}
                  <dt>场景进度</dt>
                  <dd data-testid="detail-scene-progress">
                    {detail.failure_substage === "scene_boundary_adjudication" ||
                    (detail.boundary_candidate_total != null && (detail.total_scene_count ?? 0) === 0) ? (
                      <>
                        {detail.boundary_candidate_total == null ? (
                          <>边界候选：暂无进度数据</>
                        ) : (
                          <>
                            边界候选：{detail.boundary_candidate_completed ?? 0} /{" "}
                            {detail.boundary_candidate_total}
                            <br />
                            裁决批次：{detail.boundary_batch_completed ?? 0} /{" "}
                            {detail.boundary_batch_total ?? "?"}
                          </>
                        )}
                      </>
                    ) : (
                      <>
                        已完成：{formatCompletedScenesProgress(
                          detail.completed_scene_count,
                          detail.total_scene_count,
                        )}
                        {detail.remaining_scene_count != null && detail.remaining_scene_count > 0
                          ? `（未完成 ${detail.remaining_scene_count}）`
                          : null}
                      </>
                    )}
                  </dd>
                  {(detail.last_requested_output_tokens != null ||
                    detail.last_finish_reason ||
                    detail.truncation_attempt_count != null) && (
                    <>
                      <dt>输出上限（最后请求）</dt>
                      <dd data-testid="detail-last-output-limit">
                        {detail.last_requested_output_tokens ?? "未知"}
                      </dd>
                      <dt>实际输出 Token</dt>
                      <dd data-testid="detail-last-output-tokens">
                        {detail.last_actual_output_tokens ?? "未知"}
                      </dd>
                      <dt>finish_reason</dt>
                      <dd data-testid="detail-finish-reason">
                        {detail.last_finish_reason || "未知"}
                      </dd>
                      <dt>截断尝试次数</dt>
                      <dd data-testid="detail-truncation-attempts">
                        {detail.truncation_attempt_count ?? 0}
                      </dd>
                    </>
                  )}
                  <dt>当前失败场景</dt>
                  <dd data-testid="detail-failed-scene">
                    {detail.failed_scene_id != null && detail.failed_scene_index != null
                      ? formatSceneOrdinalLabel(detail.failed_scene_index)
                      : "无"}
                  </dd>
                  <dt>历史失败场景</dt>
                  <dd data-testid="detail-historical-failed-scene">
                    {detail.historical_failed_scene_id != null &&
                    detail.historical_failed_scene_index != null
                      ? formatSceneOrdinalLabel(detail.historical_failed_scene_index)
                      : "无"}
                  </dd>
                  <dt>失败场景请求次数</dt>
                  <dd>
                    {detail.failed_scene_http_attempts ?? 0}
                    /{detail.scene_analysis_max_http_attempts ?? 4}
                  </dd>
                  <dt>已完成场景</dt>
                  <dd data-testid="detail-completed-scene-ids">
                    {formatSceneOrdinalRange(1, detail.completed_scene_count ?? detail.completed_scene_ids?.length ?? 0)}
                  </dd>
                  <dt>剩余场景</dt>
                  <dd data-testid="detail-remaining-scene-ids">
                    {formatSceneOrdinalRange(
                      (detail.completed_scene_count ?? 0) + 1,
                      detail.remaining_scene_count ?? detail.remaining_scene_ids?.length ?? 0,
                    )}
                  </dd>
                  <dt>可离线恢复</dt>
                  <dd>{detail.offline_replay_available ? "是" : "否"}</dd>
                  <dt>继续分析</dt>
                  <dd data-testid="detail-continue-availability">
                    {taskContinueAvailabilityLabel(detail)}
                  </dd>
                  <dt>处理建议</dt>
                  <dd>{detail.user_action_hint || "无"}</dd>
                </dl>
              </section>

              <section className="tasks-detail-section">
                <h3>用量</h3>
                <dl>
                  <dt>预留状态</dt>
                  <dd>{detail.reservation_status || "无"}</dd>
                  {(detail.usage_invocation_count ?? 0) > 0 ? (
                    <>
                      <dt>调用次数</dt>
                      <dd data-testid="detail-usage-calls">{detail.usage_invocation_count}</dd>
                      <dt>输入 Token</dt>
                      <dd data-testid="detail-usage-input">{detail.usage_input_tokens ?? 0}</dd>
                      <dt>输出 Token</dt>
                      <dd data-testid="detail-usage-output">{detail.usage_output_tokens ?? 0}</dd>
                      <dt>总 Token</dt>
                      <dd data-testid="detail-usage-total">{detail.usage_total_tokens ?? 0}</dd>
                      <dt>费用</dt>
                      <dd data-testid="detail-usage-cost">
                        {detail.usage_cost_unknown || detail.usage_estimated_cost == null
                          ? "费用暂无法计算"
                          : `${detail.usage_estimated_cost} CNY`}
                      </dd>
                    </>
                  ) : (detail.budget_required || detail.budget_remaining || detail.exceeded_dimensions?.length) ? (
                    <>
                      <dt>所需额度</dt>
                      <dd><pre>{JSON.stringify(detail.budget_required, null, 2)}</pre></dd>
                      <dt>剩余额度</dt>
                      <dd><pre>{JSON.stringify(detail.budget_remaining, null, 2)}</pre></dd>
                      <dt>超出维度</dt>
                      <dd>{(detail.exceeded_dimensions || []).join(", ") || "无"}</dd>
                    </>
                  ) : (
                    <>
                      <dt>预算摘要</dt>
                      <dd>尚无模型调用</dd>
                    </>
                  )}
                </dl>
              </section>

              <section className="tasks-detail-section">
                <h3>错误信息</h3>
                <dl>
                  <dt>错误说明</dt>
                  <dd>
                    {overviewUserError(detail) ||
                      detail.error_message ||
                      detail.root_error_message ||
                      "无"}
                  </dd>
                  {detail.root_error_message &&
                  detail.root_error_message !== detail.error_message ? (
                    <>
                      <dt>开发者详情</dt>
                      <dd>{detail.root_error_message}</dd>
                    </>
                  ) : null}
                  {detail.failed_stage ? (
                    <>
                      <dt>失败阶段</dt>
                      <dd>{detail.failed_stage}</dd>
                    </>
                  ) : null}
                  {(detail.task_type === "whole_book_overview" ||
                    detail.subject_type === "book") &&
                  detail.failed_scene_index != null ? (
                    <>
                      <dt>失败窗口</dt>
                      <dd>#{detail.failed_scene_index}</dd>
                    </>
                  ) : null}
                  {(detail.task_type === "whole_book_overview" ||
                    detail.subject_type === "book") ? (
                    <>
                      <dt>Provider</dt>
                      <dd>{detail.provider || "无"}</dd>
                      <dt>Model</dt>
                      <dd>{detail.model || "无"}</dd>
                      <dt>是否执行 Repair</dt>
                      <dd>
                        {detail.failed_invocation?.repair_attempted === true
                          ? "是"
                          : detail.failed_invocation
                            ? "否"
                            : "未知"}
                      </dd>
                    </>
                  ) : null}
                  {detail.validation_error_code ? (
                    <>
                      <dt>校验码</dt>
                      <dd>{detail.validation_error_code}</dd>
                    </>
                  ) : null}
                  {detail.failed_transition_id ? (
                    <>
                      <dt>相关转移</dt>
                      <dd>{detail.failed_transition_id}</dd>
                    </>
                  ) : null}
                  {detail.scene_validation_detail && (
                    <>
                      <dt>证据错误</dt>
                      <dd data-testid="detail-evidence-error">
                        {detail.scene_validation_detail.validation_error_message || "无"}
                      </dd>
                      <dt>合法段落范围</dt>
                      <dd data-testid="detail-allowed-paragraphs">
                        {(detail.scene_validation_detail.allowed_paragraph_ids ?? []).join(", ") || "无"}
                      </dd>
                      <dt>非法证据</dt>
                      <dd data-testid="detail-illegal-evidence">
                        {(detail.scene_validation_detail.illegal_evidence_ids ?? [])
                          .map(
                            (item: { field_path: string; paragraph_id: string }) =>
                              `${item.field_path}:${item.paragraph_id}`,
                          )
                          .join("; ") || "无"}
                      </dd>
                    </>
                  )}
                </dl>
                <details className="tasks-raw-error" data-testid="task-raw-error">
                  <summary>原始错误（默认折叠）</summary>
                  <dl>
                    <dt>错误码</dt>
                    <dd>{detail.error_code || "无"}</dd>
                    <dt>根错误码</dt>
                    <dd>{detail.root_error_code || "无"}</dd>
                    <dt>失败场景 ID</dt>
                    <dd>{detail.failed_scene_id ?? "无"}</dd>
                    <dt>失败场景序号</dt>
                    <dd>{detail.failed_scene_index ?? "无"}</dd>
                    <dt>历史失败场景 ID</dt>
                    <dd>{detail.historical_failed_scene_id ?? "无"}</dd>
                    <dt>已完成场景 ID</dt>
                    <dd>{(detail.completed_scene_ids ?? []).join(", ") || "无"}</dd>
                    <dt>剩余场景 ID</dt>
                    <dd>{(detail.remaining_scene_ids ?? []).join(", ") || "无"}</dd>
                    <dt>异常类型</dt>
                    <dd>{detail.exception_type || detail.failure_details?.exception_type || "无"}</dd>
                    <dt>传输类型</dt>
                    <dd>{detail.transport_kind || detail.failure_details?.transport_kind || "无"}</dd>
                    <dt>失败调用 ID</dt>
                    <dd>{detail.failed_invocation_id ?? "无"}</dd>
                    <dt>请求 ID</dt>
                    <dd>{(detail.failure_details as any)?.request_id || "无"}</dd>
                    <dt>失败批次序号</dt>
                    <dd>{detail.failed_batch_index ?? "无"}</dd>
                  </dl>
                </details>
                <details data-testid="invocation-safe-details">
                  <summary>查看脱敏技术详情</summary>
                  {detailInvocationsError ? (
                    <p className="notice" data-testid="detail-invocations-error" role="alert">
                      {detailInvocationsError}
                    </p>
                  ) : null}
                  {(() => {
                    const failed =
                      detail.failed_invocation ||
                      detailInvocations.find(
                        (item) =>
                          item != null &&
                          typeof item === "object" &&
                          "id" in item &&
                          (item as { id: unknown }).id === detail.failed_invocation_id,
                      );
                    return failed && typeof failed === "object" ? (
                      <dl>
                        <dt>调用</dt><dd>#{(failed as any).id}</dd>
                        <dt>HTTP</dt><dd>{(failed as any).http_status_code ?? (failed as any).http_status ?? "无响应"}</dd>
                        <dt>JSON</dt><dd>{(failed as any).json_valid ?? Boolean((failed as any).parsed_response_json) ? "通过" : "失败/无响应"}</dd>
                        <dt>Schema</dt><dd>{(failed as any).schema_valid ?? ((failed as any).error_code !== "SCHEMA_VALIDATION_FAILED") ? "通过" : "失败"}</dd>
                        <dt>错误消息</dt><dd>{(failed as any).error_message || "无"}</dd>
                        <dt>耗时</dt><dd>{(failed as any).latency_ms ?? "-"} ms</dd>
                        <dt>Token</dt><dd>{(failed as any).total_tokens ?? "-"}</dd>
                        <dt>安全详情</dt><dd><pre>{JSON.stringify(detail.failure_details || {}, null, 2)}</pre></dd>
                      </dl>
                    ) : (
                      <p>没有可用的 Invocation 摘要。</p>
                    );
                  })()}
                </details>
              </section>

              {(isBudgetPauseRun(detail) ||
                detail.status === "awaiting_provider_recovery" ||
                showSceneResume) && (
                <section className="tasks-detail-section" data-testid="task-unified-recovery">
                  <h3>恢复与继续</h3>
                  <UnifiedAnalysisRecoveryCard
                    run={detail}
                    variant="card"
                    onContinued={async () => {
                      const updated = await analysisApi.run(detail.id);
                      setDetail(updated);
                      await qc.invalidateQueries({ queryKey: ["runs"] });
                    }}
                  />
                </section>
              )}

              {showDetectionRecovery && (
                <section className="tasks-detail-section notice" data-testid="checkpoint-summary">
                  <h3>检查点恢复</h3>
                  <b>已有结果可复用</b>
                  <p>
                    可恢复批次 {detail.reusable_checkpoint_count}/{detail.checkpoint_total_count}
                    {detail.conflicted_checkpoint_count
                      ? `，其中 ${detail.conflicted_checkpoint_count} 个批次含人工语义冲突`
                      : ""}
                  </p>
                  {recoveryPreflight && (
                    <dl>
                      <dt>剩余检测批次</dt><dd>{recoveryPreflight.remaining_detection_batch_count}</dd>
                      <dt>预计请求</dt><dd>{recoveryPreflight.expected_request_count}</dd>
                      <dt>最坏请求</dt><dd>{recoveryPreflight.worst_case_request_count}</dd>
                      <dt>预计 Token</dt><dd>{recoveryPreflight.estimated_total_tokens}</dd>
                      <dt>最坏费用</dt><dd>{recoveryPreflight.worst_case_cost} {recoveryPreflight.currency}</dd>
                    </dl>
                  )}
                  <label>
                    <input
                      type="checkbox"
                      checked={recoveryConsent}
                      disabled={recoveryBusy}
                      onChange={(event) => setRecoveryConsent(event.target.checked)}
                    />
                    我同意新恢复任务按剩余批次发送必要正文到云端
                  </label>
                  {disableReason && (
                    <p className="notice" data-testid="recovery-disabled-reason">
                      当前不可创建：{disableReason}
                    </p>
                  )}
                  {(recoveryState === "checking" || recoveryState === "creating_recovery") && (
                    <p className="notice" data-testid="recovery-loading">
                      {recoveryState === "checking"
                        ? "正在检查恢复预算和服务商状态……"
                        : "正在创建恢复任务，已完成批次将被复用……"}
                    </p>
                  )}
                  {recoveryState === "created" && createdRecovery && (
                    <p className="notice" data-testid="recovery-created">
                      恢复任务已创建，任务 ID：{createdRecovery.run_id}
                      （来源任务 {createdRecovery.recovered_from_run_id}，
                      复用 {createdRecovery.reused_batch_count} 批，
                      剩余 {createdRecovery.remaining_batch_count} 批）
                    </p>
                  )}
                  {recoveryState === "failed" && recoveryError && (
                    <div className="notice" data-testid="recovery-error">
                      <b>{recoveryError.message}</b>
                      <p>{recoveryError.hint}</p>
                      <dl>
                        <dt>服务商</dt><dd>{recoveryError.providerName || "无"}</dd>
                        <dt>阻塞项</dt>
                        <dd data-testid="recovery-blockers">
                          {(recoveryError.blockers || []).length
                            ? recoveryError.blockers!.map((item) => BLOCKER_LABELS[item] || item).join("；")
                            : "无"}
                        </dd>
                        <dt>HTTP</dt><dd>{recoveryError.httpStatus || "无"}</dd>
                        <dt>错误码</dt><dd>{recoveryError.code}</dd>
                        <dt>请求 ID</dt><dd>{recoveryError.requestId || "无"}</dd>
                        <dt>是否可重试</dt><dd>{recoveryError.retryable ? "可重试" : "不可重试"}</dd>
                      </dl>
                    </div>
                  )}
                  <button
                    type="button"
                    className="primary"
                    data-testid="continue-from-checkpoints"
                    disabled={recoveryDisabled}
                    aria-busy={recoveryBusy}
                    onClick={continueFromCheckpoints}
                  >
                    {recoveryState === "checking"
                      ? "正在检查……"
                      : recoveryState === "creating_recovery"
                        ? "正在创建恢复任务……"
                        : "从已有结果继续"}
                  </button>
                </section>
              )}

              {detail.legacy_classification_warning && (
                <p className="notice" data-testid="legacy-classification-warning">
                  该历史错误可能由旧版本错误分类产生。
                </p>
              )}
              {(detail.root_error_code || "").startsWith("PROVIDER_") && (
                <p data-testid="provider-transport-error-label">服务商传输错误</p>
              )}
            </div>
          </div>
        </div>
      )}
      {stopConfirmRun && (
        <div className="modal-backdrop" data-testid="stop-confirm-dialog">
          <div className="modal tasks-stop-modal" role="dialog" aria-modal="true" aria-labelledby="stop-confirm-title">
            <header>
              <h2 id="stop-confirm-title">{STOP_CONFIRM_TITLE}</h2>
              <button
                type="button"
                aria-label="关闭"
                disabled={stopSubmitting}
                onClick={() => {
                  if (stopSubmitting) return;
                  setStopConfirmRun(null);
                  setStopError(null);
                }}
              >
                ×
              </button>
            </header>
            <p className="tasks-stop-body" style={{ whiteSpace: "pre-line" }}>
              {STOP_CONFIRM_BODY}
            </p>
            {stopSubmitting && (
              <p className="notice" data-testid="stop-submitting">
                正在提交停止请求……
              </p>
            )}
            {stopError && (
              <div className="notice" data-testid="stop-error">
                <b>{stopError.message}</b>
                <details>
                  <summary>技术详情</summary>
                  <code>{stopError.code}</code>
                </details>
              </div>
            )}
            <footer className="tasks-stop-actions">
              <button
                type="button"
                data-testid="stop-continue-analysis"
                disabled={stopSubmitting}
                onClick={() => {
                  setStopConfirmRun(null);
                  setStopError(null);
                }}
              >
                继续分析
              </button>
              <button
                type="button"
                className="tasks-stop-confirm"
                data-testid="stop-confirm-submit"
                disabled={stopSubmitting}
                aria-busy={stopSubmitting}
                onClick={() => void submitStopAnalysis()}
              >
                确认停止
              </button>
            </footer>
          </div>
        </div>
      )}
    </section>
  );
}
