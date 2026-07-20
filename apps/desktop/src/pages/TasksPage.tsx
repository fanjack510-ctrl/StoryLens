import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { analysisApi } from "../services/analysisApi";
import { booksApi } from "../services/booksApi";
import { ApiError } from "../services/apiClient";
import { Badge, Empty, ErrorState, Loading } from "../components/common/States";
import { UnifiedAnalysisRecoveryCard } from "../components/chapterAnalysis/UnifiedAnalysisRecoveryCard";
import { isBudgetPauseRun } from "../services/budgetPauseDetect";
import { BUDGET_ERROR_USER_COPY } from "../services/budgetErrorCopy";
import {
  chapterProgressHref,
  chapterResultHref,
} from "../services/discoverActiveChapterRun";
import { isSceneAnalysisComplete } from "../services/chapterJourneyComposition";
import { maybeTrackAnalysisCompleted } from "../services/telemetry/analysisRunTelemetry";

type RecoveryState = "idle" | "checking" | "creating_recovery" | "created" | "failed";
type SceneResumeState = "idle" | "checking" | "resuming" | "done" | "failed";
type OfflineReplayState = "idle" | "replaying" | "succeeded" | "failed";

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

  if (hasJourney) {
    return (
      <button
        type="button"
        className="primary"
        data-testid={`view-results-${run.id}`}
        disabled={busy}
        onClick={() => onOpen("reader-journey")}
      >
        查看阅读旅程
      </button>
    );
  }
  if (journeyActive) {
    return (
      <button
        type="button"
        className="primary"
        data-testid={`view-journey-progress-${run.id}`}
        disabled={busy}
        onClick={() => onOpen("reader-journey")}
      >
        查看阅读旅程进度
      </button>
    );
  }
  if (sceneDone) {
    return (
      <>
        <button
          type="button"
          className="primary"
          data-testid={`unified-recover-open-${run.id}`}
          disabled={busy}
          onClick={() => onOpen("reader-journey")}
        >
          修复并继续
        </button>
        <button
          type="button"
          className="secondary"
          data-testid={`view-results-${run.id}`}
          disabled={busy}
          onClick={() => onOpen("analysis")}
        >
          查看详情
        </button>
      </>
    );
  }
  return (
    <button
      type="button"
      className="primary"
      data-testid={`view-results-${run.id}`}
      disabled={busy}
      onClick={() => onOpen("analysis")}
    >
      查看Scene分析
    </button>
  );
}

export function TasksPage() {
  const navigate = useNavigate();
  const [detail, setDetail] = useState<any>();
  const [detailInvocations, setDetailInvocations] = useState<any[]>([]);
  const [recoveryPreflight, setRecoveryPreflight] = useState<any>();
  const [recoveryConsent, setRecoveryConsent] = useState(false);
  const [recoveryState, setRecoveryState] = useState<RecoveryState>("idle");
  const [recoveryError, setRecoveryError] = useState<RecoveryErrorView>();
  const [createdRecovery, setCreatedRecovery] = useState<any>();
  const [highlightRunId, setHighlightRunId] = useState<number | null>(null);
  const [clientRequestId] = useState(
    () => globalThis.crypto?.randomUUID?.() || `recover-${Date.now()}`,
  );
  const [sceneResumePreflight, setSceneResumePreflight] = useState<any>();
  const [sceneResumeConsent, setSceneResumeConsent] = useState(false);
  const [sceneResumeState, setSceneResumeState] = useState<SceneResumeState>("idle");
  const [sceneResumeError, setSceneResumeError] = useState<RecoveryErrorView>();
  const [offlineReplayState, setOfflineReplayState] = useState<OfflineReplayState>("idle");
  const [offlineReplayMessage, setOfflineReplayMessage] = useState<string>();
  const [offlineReplayError, setOfflineReplayError] = useState<RecoveryErrorView>();
  const [sceneResumeClientId, setSceneResumeClientId] = useState(
    () => globalThis.crypto?.randomUUID?.() || `scene-resume-${Date.now()}`,
  );
  const [navBusyRunId, setNavBusyRunId] = useState<number | null>(null);
  const qc = useQueryClient();
  const runs = useQuery({
    queryKey: ["runs"],
    queryFn: analysisApi.runs,
    refetchInterval: 5000,
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
  const openChapterProgress = async (run: any) => {
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
      setDetailInvocations(await analysisApi.invocations(run.id));
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
  const continueSceneAnalysis = async () => {
    if (!detail) return;
    if (sceneResumeState === "checking" || sceneResumeState === "resuming") return;
    if (detail.offline_replay_available) {
      setSceneResumeState("failed");
      setSceneResumeError({
        code: "OFFLINE_REPLAY_PREFERRED",
        message: "已有可离线恢复的模型响应，请先离线重放，避免重复费用。",
        hint: "点击「离线恢复失败Scene」；只有离线不可用时才继续云端调用。",
        httpStatus: 409,
        retryable: false,
      });
      return;
    }
    const attempts = detail.failed_scene_http_attempts ?? 0;
    const maxAttempts = detail.scene_analysis_max_http_attempts ?? 4;
    if (attempts >= maxAttempts) {
      setSceneResumeState("failed");
      setSceneResumeError({
        code: "SCENE_ANALYSIS_ATTEMPT_LIMIT",
        message: `失败Scene已达 HTTP 尝试上限（${attempts}/${maxAttempts}），拒绝再次付费调用。`,
        hint: "请使用离线恢复，或查看失败Scene详情后再决定。",
        httpStatus: 409,
        retryable: false,
      });
      return;
    }
    if (!sceneResumeConsent) {
      setSceneResumeState("failed");
      setSceneResumeError({
        code: "CLOUD_CONSENT_REQUIRED",
        message: "尚未确认发送未完成Scene正文到云端。",
        hint: "请勾选云端同意后再继续Scene Analysis。",
        httpStatus: 422,
        retryable: false,
      });
      return;
    }
    setSceneResumeError(undefined);
    setSceneResumeState("checking");
    try {
      const fresh = await analysisApi.sceneAnalysisResumePreflight(detail.id, {
        cloud_consent: true,
      });
      setSceneResumePreflight(fresh);
      if (!fresh.eligible || !fresh.within_budget) {
        setSceneResumeState("failed");
        setSceneResumeError({
          code: fresh.blockers?.includes("budget_unavailable") || !fresh.within_budget
            ? "INSUFFICIENT_BUDGET_RESERVATION"
            : "PROVIDER_NOT_ELIGIBLE",
          message: !fresh.within_budget
            ? (() => {
                const need = fresh.worst_case_requests;
                const left = fresh.remaining_budget?.requests;
                if (typeof need === "number" && typeof left === "number") {
                  return `请求不足：最多需要 ${need} 次，当前剩余 ${left} 次。`;
                }
                return BUDGET_ERROR_USER_COPY.INSUFFICIENT_BUDGET_RESERVATION;
              })()
            : `Provider ${fresh.provider_name} 当前不可用`,
          hint: (fresh.blockers || [])
            .map((item: string) => BLOCKER_LABELS[item] || item)
            .join("；") || "请检查Provider与预算后重试",
          httpStatus: 409,
          retryable: Boolean(fresh.within_budget === false),
          providerName: fresh.provider_name,
          blockers: fresh.blockers,
        });
        return;
      }
      setSceneResumeState("resuming");
      await analysisApi.resumeSceneAnalysis(detail.id, {
        client_request_id: sceneResumeClientId,
        cloud_consent: true,
        confirmed: true,
        provider_state_version: fresh.provider_state_version,
      });
      setSceneResumeState("done");
      setHighlightRunId(detail.id);
      setSceneResumeClientId(
        globalThis.crypto?.randomUUID?.() || `scene-resume-${Date.now()}`,
      );
      await qc.invalidateQueries({ queryKey: ["runs"] });
      const updated = await analysisApi.run(detail.id);
      setDetail(updated);
      window.setTimeout(() => setDetail(undefined), 900);
    } catch (error) {
      setSceneResumeState("failed");
      setSceneResumeError(toRecoveryError(error));
      try {
        const updated = await analysisApi.run(detail.id);
        setDetail(updated);
        await qc.invalidateQueries({ queryKey: ["runs"] });
      } catch {
        /* keep existing detail */
      }
    }
  };
  const offlineReplayFailedScene = async () => {
    if (!detail) return;
    if (offlineReplayState === "replaying" || sceneResumeState === "resuming") return;
    setOfflineReplayError(undefined);
    setOfflineReplayMessage(undefined);
    setOfflineReplayState("replaying");
    try {
      const result = await analysisApi.replaySceneAnalysisOffline(detail.id, {
        scene_id: detail.failed_scene_id ?? detail.historical_failed_scene_id,
        invocation_id: detail.historical_failed_invocation_id ?? detail.failed_invocation_id,
        confirmed: true,
        client_request_id: sceneResumeClientId,
      });
      setOfflineReplayState("succeeded");
      setOfflineReplayMessage(result.message);
      setHighlightRunId(detail.id);
      await qc.invalidateQueries({ queryKey: ["runs"] });
      const updated = await analysisApi.run(detail.id);
      setDetail(updated);
      setSceneResumePreflight(undefined);
      if (updated.scene_analysis_resume_available) {
        setSceneResumePreflight(
          await analysisApi.sceneAnalysisResumePreflight(updated.id, { cloud_consent: true }),
        );
      }
      if (result.remaining_scene_count === 0) {
        window.setTimeout(() => setDetail(undefined), 900);
      }
    } catch (error) {
      setOfflineReplayState("failed");
      setOfflineReplayError(toRecoveryError(error));
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
    queued: "云端候选生成中",
    running: "云端候选生成中",
    boundary_candidates_running: "云端候选生成中",
    awaiting_boundary_review: "等待边界审阅",
    awaiting_provider_recovery: "分析已暂停",
    boundary_confirmed: "边界已确认",
    boundary_confirmed_budget_blocked: "分析已暂停",
    aborted_by_limit: "分析已暂停",
    scene_analysis_running: "Scene Analysis中",
    scene_analysis_partial: "Scene Analysis部分完成，可继续",
    boundary_candidates_partial: "候选生成部分完成，可继续",
    failed_structural: "结构校验失败",
    failed_provider: "Provider请求失败",
    succeeded: "已完成",
    cancelled: "已取消",
    review_cancelled: "已取消",
    review_expired: "审阅已过期",
    failed: "失败",
  };
  const runStatusLabel = (run: any) => {
    if (isBudgetPauseRun(run)) return "分析已暂停";
    if (run.status === "awaiting_provider_recovery") return "分析已暂停";
    if (run.status === "succeeded" && isSceneAnalysisComplete(run)) {
      return "Scene分析已完成";
    }
    return statusLabel[run.status] || "处理中";
  };
  const sceneResumeBusy =
    sceneResumeState === "checking" || sceneResumeState === "resuming";
  const offlineReplayBusy = offlineReplayState === "replaying";
  const needsOfflineReplayFirst = Boolean(detail?.offline_replay_available);
  const showDetectionRecovery = Boolean(
    detail?.detection_recovery_available && detail?.remaining_detection_batch_count > 0,
  );
  const showSceneResume = Boolean(detail?.scene_analysis_resume_available);
  return (
    <section className="page">
      <div className="page-title">
        <div>
          <p className="eyebrow">执行与审计</p>
          <h1>任务中心</h1>
          <p>查看 AnalysisRun 状态、进度、Provider、云端同意与失败原因。</p>
        </div>
        <select>
          <option>全部状态</option>
          <option>failed</option>
          <option>succeeded</option>
        </select>
      </div>
      {highlightRunId && (
        <p className="notice" data-testid="recovery-highlight">
          已定位恢复任务 #{highlightRunId}
          {createdRecovery?.recovered_from_run_id
            ? `（来源 Run #${createdRecovery.recovered_from_run_id}）`
            : ""}
        </p>
      )}
      <div className="panel table-wrap">
        {runs.isLoading ? (
          <Loading />
        ) : runs.error ? (
          <ErrorState error={runs.error} />
        ) : runs.data?.length ? (
          <table>
            <thead>
              <tr>
                <th>Run</th>
                <th>章节</th>
                <th>模式</th>
                <th>Provider / 模型</th>
                <th>状态</th>
                <th>进度</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {runs.data.map((run: any) => (
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
                  <td>{run.subject_id}</td>
                  <td>
                    {run.execution_mode}
                    {run.sends_content_to_cloud && (
                      <Badge tone="warning">云端</Badge>
                    )}
                    {run.recovered_from_run_id && (
                      <small>来自 #{run.recovered_from_run_id}</small>
                    )}
                  </td>
                  <td>
                    <b>{run.provider}</b>
                    <small>{run.model}</small>
                  </td>
                  <td>
                    <Badge tone={isBudgetPauseRun(run) ? "aborted_by_limit" : run.status}>
                      {runStatusLabel(run)}
                    </Badge>
                    {run.current_stage && (
                      <small>
                        阶段：
                        {run.current_stage === "scene_analysis" ||
                        run.current_stage === "scene_analysis_budget"
                          ? `Scene Analysis ${run.completed_scene_count ?? 0}/${run.total_scene_count ?? 0}`
                          : statusLabel[run.current_stage] || "进行中"}
                      </small>
                    )}
                  </td>
                  <td>
                    {typeof run.total_scene_count === "number" && run.total_scene_count > 0
                      ? (
                        <span data-testid={`run-${run.id}-scene-progress`}>
                          Scene Analysis：{run.completed_scene_count ?? 0} / {run.total_scene_count}
                        </span>
                      )
                      : `${run.progress_current}/${run.progress_total}`}
                  </td>
                  <td>{new Date(run.created_at).toLocaleString()}</td>
                  <td>
                    {run.status === "succeeded" && (
                      <SucceededRunRowActions
                        run={run}
                        busy={navBusyRunId === run.id}
                        onOpen={(tab) => void openChapterResult(run, tab)}
                      />
                    )}
                    {run.status === "failed" && !isBudgetPauseRun(run) && (
                      <button onClick={() => retry(run.id)}>重试</button>
                    )}
                    {(isBudgetPauseRun(run) ||
                      run.status === "awaiting_provider_recovery" ||
                      run.scene_analysis_resume_available ||
                      run.status === "scene_analysis_partial" ||
                      (run.status === "failed" &&
                        run.failed_stage === "scene_analysis")) && (
                      <button
                        className="primary"
                        data-testid={`unified-recover-open-${run.id}`}
                        disabled={navBusyRunId === run.id}
                        onClick={() => void openChapterProgress(run)}
                      >
                        {navBusyRunId === run.id ? "正在打开章节…" : "修复并继续"}
                      </button>
                    )}
                    {run.status !== "succeeded" && (
                    <button
                      onClick={() =>
                        navigator.clipboard?.writeText(
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
                        )
                      }
                    >
                      复制错误
                    </button>
                    )}
                    {([
                      "failed",
                      "failed_structural",
                      "failed_provider",
                      "boundary_candidates_partial",
                      "boundary_confirmed_budget_blocked",
                      "scene_analysis_partial",
                      "aborted_by_limit",
                    ].includes(run.status) || isBudgetPauseRun(run)) && (
                      <button
                        data-testid={`view-detail-${run.id}`}
                        onClick={() => openDetail(run)}
                      >
                        查看详情
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Empty text="暂无分析任务" />
        )}
      </div>
      {detail && (
        <div className="modal-backdrop">
          <div className="modal">
            <header>
              <h2>任务详情</h2>
              <button type="button" onClick={() => setDetail(undefined)}>×</button>
            </header>
            <dl>
              <dt>失败阶段</dt>
              <dd>
                {(detail.actual_failed_stage || detail.failed_stage) === "scene_analysis"
                  ? "Scene Analysis"
                  : (detail.actual_failed_stage || detail.failed_stage) === "provider_request"
                    ? "Provider请求"
                    : (detail.actual_failed_stage || detail.failed_stage || detail.current_stage || "未知")}
              </dd>
              <dt>error_code</dt>
              <dd>{detail.error_code || "无"}</dd>
              <dt>root_error_code</dt>
              <dd>{detail.root_error_code || "无"}</dd>
              <dt>failed_scene_id</dt>
              <dd>{detail.failed_scene_id ?? "无"}</dd>
              <dt>failed_scene_index</dt>
              <dd>{detail.failed_scene_index ?? "无"}</dd>
              <dt>Scene进度</dt>
              <dd data-testid="detail-scene-progress">
                Scene Analysis：{detail.completed_scene_count ?? 0} / {detail.total_scene_count ?? 0}
                （未完成 {detail.remaining_scene_count ?? 0}）
              </dd>
              <dt>当前失败Scene</dt>
              <dd data-testid="detail-failed-scene">
                {detail.failed_scene_id != null
                  ? `#${detail.failed_scene_id}（index ${detail.failed_scene_index ?? "-"}）`
                  : "无"}
              </dd>
              <dt>历史失败Scene</dt>
              <dd data-testid="detail-historical-failed-scene">
                {detail.historical_failed_scene_id != null
                  ? `#${detail.historical_failed_scene_id}（index ${detail.historical_failed_scene_index ?? "-"}，Invocation #${detail.historical_failed_invocation_id ?? detail.failed_invocation_id ?? "-"})`
                  : "无"}
              </dd>
              <dt>失败Scene HTTP尝试</dt>
              <dd>
                {detail.failed_scene_http_attempts ?? 0}
                /{detail.scene_analysis_max_http_attempts ?? 4}
              </dd>
              <dt>已完成Scene ID</dt>
              <dd data-testid="detail-completed-scene-ids">
                {(detail.completed_scene_ids ?? []).join(", ") || "无"}
              </dd>
              <dt>剩余Scene ID</dt>
              <dd data-testid="detail-remaining-scene-ids">
                {(detail.remaining_scene_ids ?? []).join(", ") || "无"}
              </dd>
              <dt>可离线恢复</dt>
              <dd>{detail.offline_replay_available ? "是" : "否"}</dd>
              {detail.scene_validation_detail && (
                <>
                  <dt>Evidence错误</dt>
                  <dd data-testid="detail-evidence-error">
                    {detail.scene_validation_detail.validation_error_message || "无"}
                  </dd>
                  <dt>合法paragraph范围</dt>
                  <dd data-testid="detail-allowed-paragraphs">
                    {(detail.scene_validation_detail.allowed_paragraph_ids ?? []).join(", ") || "无"}
                  </dd>
                  <dt>非法Evidence ID</dt>
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
              <dt>BoundaryRevision</dt>
              <dd>{detail.boundary_revision_id ? `#${detail.boundary_revision_id}` : "无"}</dd>
              <dt>exception_type</dt>
              <dd>{detail.exception_type || detail.failure_details?.exception_type || "无"}</dd>
              <dt>transport_kind</dt>
              <dd>{detail.transport_kind || detail.failure_details?.transport_kind || "无"}</dd>
              <dt>retryable</dt>
              <dd>{detail.retryable ? "可重试" : "不可重试"}</dd>
              <dt>failed_invocation_id</dt>
              <dd>{detail.failed_invocation_id ?? "无"}</dd>
              <dt>request_id</dt>
              <dd>{(detail.failure_details as any)?.request_id || "无"}</dd>
              <dt>Reservation</dt>
              <dd>{detail.reservation_status || "无"}</dd>
              <dt>root_error_message</dt>
              <dd>{detail.root_error_message || detail.error_message || "无"}</dd>
              <dt>处理建议</dt>
              <dd>{detail.user_action_hint || "无"}</dd>
              <dt>validation_error_code</dt>
              <dd>{detail.validation_error_code || "无"}</dd>
              <dt>failed_transition_id</dt>
              <dd>{detail.failed_transition_id || "无"}</dd>
              <dt>failed_batch_index</dt>
              <dd>{detail.failed_batch_index ?? "无"}</dd>
              {(detail.budget_required || detail.budget_remaining || detail.exceeded_dimensions?.length) && <>
                <dt>required</dt>
                <dd><pre>{JSON.stringify(detail.budget_required, null, 2)}</pre></dd>
                <dt>remaining</dt>
                <dd><pre>{JSON.stringify(detail.budget_remaining, null, 2)}</pre></dd>
                <dt>exceeded_dimensions</dt>
                <dd>{(detail.exceeded_dimensions || []).join(", ")}</dd>
              </>}
            </dl>
            <details data-testid="invocation-safe-details">
              <summary>查看脱敏技术详情</summary>
              {(() => {
                const failed = detail.failed_invocation || detailInvocations.find(
                  (item) => item.id === detail.failed_invocation_id,
                );
                return failed ? <dl>
                  <dt>Invocation</dt><dd>#{failed.id}</dd>
                  <dt>HTTP</dt><dd>{failed.http_status_code ?? failed.http_status ?? "无响应"}</dd>
                  <dt>JSON</dt><dd>{failed.json_valid ?? Boolean(failed.parsed_response_json) ? "通过" : "失败/无响应"}</dd>
                  <dt>Schema</dt><dd>{failed.schema_valid ?? (failed.error_code !== "SCHEMA_VALIDATION_FAILED") ? "通过" : "失败"}</dd>
                  <dt>error_message</dt><dd>{failed.error_message || "无"}</dd>
                  <dt>耗时</dt><dd>{failed.latency_ms ?? "-"} ms</dd>
                  <dt>Token</dt><dd>{failed.total_tokens ?? "-"}</dd>
                  <dt>safe_details</dt><dd><pre>{JSON.stringify(detail.failure_details || {}, null, 2)}</pre></dd>
                </dl> : <p>没有可用的 Invocation 摘要。</p>;
              })()}
            </details>
            {(isBudgetPauseRun(detail) ||
              detail.status === "awaiting_provider_recovery" ||
              showSceneResume) && (
              <div data-testid="task-unified-recovery">
                <UnifiedAnalysisRecoveryCard
                  run={detail}
                  variant="card"
                  onContinued={async () => {
                    const updated = await analysisApi.run(detail.id);
                    setDetail(updated);
                    await qc.invalidateQueries({ queryKey: ["runs"] });
                  }}
                />
              </div>
            )}
                        {showDetectionRecovery && <div className="notice" data-testid="checkpoint-summary">
              <b>已有结果可复用</b>
              <p>
                可恢复批次 {detail.reusable_checkpoint_count}/{detail.checkpoint_total_count}
                {detail.conflicted_checkpoint_count
                  ? `，其中 ${detail.conflicted_checkpoint_count} 个批次含人工语义冲突`
                  : ""}
              </p>
              {recoveryPreflight && <dl>
                <dt>剩余Detection批次</dt><dd>{recoveryPreflight.remaining_detection_batch_count}</dd>
                <dt>预计请求</dt><dd>{recoveryPreflight.expected_request_count}</dd>
                <dt>最坏请求</dt><dd>{recoveryPreflight.worst_case_request_count}</dd>
                <dt>预计Token</dt><dd>{recoveryPreflight.estimated_total_tokens}</dd>
                <dt>最坏费用</dt><dd>{recoveryPreflight.worst_case_cost} {recoveryPreflight.currency}</dd>
              </dl>}
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
                    ? "正在检查恢复预算和Provider状态……"
                    : "正在创建恢复任务，已完成批次将被复用……"}
                </p>
              )}
              {recoveryState === "created" && createdRecovery && (
                <p className="notice" data-testid="recovery-created">
                  恢复任务已创建，Run ID：{createdRecovery.run_id}
                  （recovered_from_run_id={createdRecovery.recovered_from_run_id}，
                  复用 {createdRecovery.reused_batch_count} 批，
                  剩余 {createdRecovery.remaining_batch_count} 批）
                </p>
              )}
              {recoveryState === "failed" && recoveryError && (
                <div className="notice" data-testid="recovery-error">
                  <b>{recoveryError.message}</b>
                  <p>{recoveryError.hint}</p>
                  <dl>
                    <dt>Provider</dt><dd>{recoveryError.providerName || "无"}</dd>
                    <dt>blockers</dt>
                    <dd data-testid="recovery-blockers">
                      {(recoveryError.blockers || []).length
                        ? recoveryError.blockers!.map((item) => BLOCKER_LABELS[item] || item).join("；")
                        : "无"}
                    </dd>
                    <dt>HTTP</dt><dd>{recoveryError.httpStatus || "无"}</dd>
                    <dt>error_code</dt><dd>{recoveryError.code}</dd>
                    <dt>request_id</dt><dd>{recoveryError.requestId || "无"}</dd>
                    <dt>retryable</dt><dd>{recoveryError.retryable ? "可重试" : "不可重试"}</dd>
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
            </div>}
            {detail.legacy_classification_warning && (
              <p className="notice" data-testid="legacy-classification-warning">
                该历史错误可能由旧版本错误分类产生。
              </p>
            )}
            {(detail.root_error_code || "").startsWith("PROVIDER_") && (
              <p data-testid="provider-transport-error-label">Provider传输错误</p>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
