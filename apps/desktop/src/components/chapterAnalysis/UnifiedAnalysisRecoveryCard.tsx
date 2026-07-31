import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { Run } from "../../types";
import { analysisApi } from "../../services/analysisApi";
import { analysisRecoveryApi } from "../../services/analysisRecoveryApi";
import { mapRunToUiState } from "./mapAnalysisUiState";
import {
  isJourneyActivelyRunning,
  recoveryPlanQueryKey,
  shouldShowUnifiedRecoveryForJourney,
} from "../../services/journeyActiveRecoveryGuard";
import { getOrCreateJourneyClientRequestId } from "../../services/chapterJourneyComposition";

type Props = {
  run: Run;
  variant?: "card" | "modal";
  onClose?: () => void;
  onContinued?: () => void;
  onLater?: () => void;
  /** Live journey status for the current task (suppresses stale paused card). */
  journeyStatus?: string | null;
  /** True when journey page view is already active / generating. */
  journeyPageActive?: boolean;
  journeyRunId?: number | null;
  confirmedRevisionId?: number | null;
  canResume?: boolean | null;
  workflowState?: string | null;
};

function newClientRequestId(runId: number): string {
  const key = `unified-recover:${runId}`;
  const next = globalThis.crypto?.randomUUID?.() || `unified-recover-${runId}-${Date.now()}`;
  try {
    sessionStorage.setItem(key, next);
  } catch {
    /* ignore */
  }
  return next;
}

function clientRequestIdFor(runId: number, options?: { rotate?: boolean }): string {
  if (options?.rotate) return newClientRequestId(runId);
  const key = `unified-recover:${runId}`;
  try {
    const existing = sessionStorage.getItem(key);
    if (existing && existing.length >= 8) return existing;
  } catch {
    /* ignore */
  }
  return newClientRequestId(runId);
}

type UserErrorCopy = {
  title?: string;
  stage_label?: string;
  explanation?: string;
  reason?: string;
  impact?: string;
  config_note?: string;
};

export function UnifiedAnalysisRecoveryCard({
  run,
  variant = "card",
  onClose,
  onContinued,
  onLater,
  journeyStatus = null,
  journeyPageActive = false,
  journeyRunId = null,
  confirmedRevisionId = null,
  canResume = true,
  workflowState = null,
}: Props) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [techOpen, setTechOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string>();
  const [error, setError] = useState<string>();
  const [proposalOpen, setProposalOpen] = useState(false);
  const uiState = mapRunToUiState(run);
  const isFailed = uiState === "failed";
  const liveJourneyStatus =
    journeyStatus ||
    run.journey_status ||
    null;
  const statusVersion = run.status_version ?? null;

  const planQuery = useQuery({
    queryKey: recoveryPlanQueryKey({
      analysisRunId: run.id,
      journeyRunId: journeyRunId ?? run.journey_run_id ?? null,
      confirmedRevisionId,
      statusVersion,
    }),
    queryFn: () => analysisRecoveryApi.recoveryPlan(run.id),
    refetchInterval: (query) => {
      const status = query.state.data?.user_status;
      const jStatus = query.state.data?.reader_journey_status;
      if (status === "running" || isJourneyActivelyRunning(jStatus) || isJourneyActivelyRunning(liveJourneyStatus)) {
        return false;
      }
      return 4000;
    },
    enabled: !journeyPageActive && !isJourneyActivelyRunning(liveJourneyStatus),
  });

  const plan = planQuery.data;
  const proposal = plan?.budget_authorization_proposal;
  const details = (plan?.details || {}) as Record<string, unknown>;
  const userError = (details.user_error || null) as UserErrorCopy | null;
  const recoveryExhausted = Boolean(details.recovery_exhausted);
  const providerNotRetryable = Boolean(details.provider_not_retryable);
  const resumeStage = plan?.resume_stage || "";
  const boundaryFocus =
    resumeStage === "boundary_detection" ||
    Boolean(userError?.title) ||
    run.failed_stage === "provider_request" ||
    run.failed_stage === "boundary_detection";

  const title = userError?.title
    ? userError.title
    : isFailed
      ? "分析未完成"
      : "分析已暂停";
  const lead = userError?.explanation
    ? userError.explanation
    : isFailed
      ? "StoryLens 在分析过程中遇到了问题。已经完成的分析结果会被保留。"
      : "当前进度已保存，可以稍后继续。";

  const checkRows = useMemo(() => {
    const checks = plan?.checks || [];
    return checks
      .filter((c) => c.user_label && c.status !== "skip")
      .map((c) => {
        const metrics =
          c.required != null && c.available != null
            ? `（需要 ${c.required} · 可用 ${c.available}${
                c.shortfall != null && Number(c.shortfall) > 0 ? ` · 还差 ${c.shortfall}` : ""
              }）`
            : "";
        return {
          id: c.id,
          ok: c.status === "pass",
          warn: c.status === "warn",
          label: `${c.user_label}${metrics}`,
        };
      });
  }, [plan?.checks]);

  const suppressForActiveJourney =
    journeyPageActive ||
    isJourneyActivelyRunning(liveJourneyStatus) ||
    isJourneyActivelyRunning(plan?.reader_journey_status) ||
    plan?.user_status === "running" ||
    plan?.user_status === "succeeded" ||
    !shouldShowUnifiedRecoveryForJourney({
      uiState,
      journeyStatus: liveJourneyStatus || plan?.reader_journey_status,
      recoveryUserStatus: plan?.user_status,
      journeyPageActive,
      workflowState,
      canResume,
    });

  const needsAuthRedirect = (plan?.blockers || []).some(
    (b) =>
      b.settings_focus === "api_key" ||
      b.reason === "credential_missing" ||
      b.reason === "credential_unauthorized",
  );

  const evidenceError = (details.evidence_error || null) as {
    error_code?: string;
    action?: string;
    repairable?: boolean;
  } | null;

  const showFixContinue =
    !recoveryExhausted &&
    !providerNotRetryable &&
    evidenceError?.repairable !== false &&
    (plan?.recommended_actions || []).some((a) => a.action === "fix_and_continue");

  const evidenceRemapAction = (plan?.recommended_actions || []).find(
    (a) => a.action === "evidence_remap_repair",
  );
  const boundaryRerunAction = (plan?.recommended_actions || []).find(
    (a) => a.action === "rerun_scene_boundary",
  );
  const showEvidenceRemap =
    !recoveryExhausted && !providerNotRetryable && Boolean(evidenceRemapAction);
  const showBoundaryRerun =
    !recoveryExhausted && !providerNotRetryable && Boolean(boundaryRerunAction);
  const showNonRepairableActions =
    Boolean(evidenceError) && evidenceError?.repairable === false;

  const fixAndContinue = async (withBudgetAuth: boolean) => {
    if (busy) return;
    // CHG-018: never re-submit recovery against an already-active journey.
    if (
      journeyPageActive ||
      isJourneyActivelyRunning(liveJourneyStatus) ||
      isJourneyActivelyRunning(plan?.reader_journey_status) ||
      plan?.user_status === "running"
    ) {
      setStatusMessage("阅读旅程已在生成中");
      onContinued?.();
      return;
    }
    setBusy(true);
    setError(undefined);
    const initialStatus = showEvidenceRemap
      ? "正在整理证据…"
      : showBoundaryRerun
        ? "正在检查场景边界…"
        : "正在检查当前场景…";
    setStatusMessage(initialStatus);
    try {
      if (needsAuthRedirect) {
        navigate("/settings?tab=ai&focus=api_key");
        onClose?.();
        return;
      }
      if (proposal && !withBudgetAuth) {
        setProposalOpen(true);
        setBusy(false);
        setStatusMessage(undefined);
        return;
      }
      setStatusMessage(
        showEvidenceRemap
          ? "正在重新校验证据…"
          : showBoundaryRerun
            ? "正在检查场景边界…"
            : resumeStage === "boundary_detection"
              ? "正在从场景边界识别继续"
              : resumeStage === "scene_analysis"
                ? "正在继续分析…"
                : resumeStage === "reader_journey"
                  ? "正在继续生成阅读旅程"
                  : "正在修复并继续…",
      );
      // CHG-023: Journey-level recovery must call journey resume, not analysis-run recover.
      const boundJourneyId = journeyRunId ?? run.journey_run_id ?? null;
      const liveStatus = String(liveJourneyStatus || "").toLowerCase();
      const analysisStageResume =
        resumeStage === "boundary_detection" || resumeStage === "scene_analysis";
      const journeyLevelResume =
        !analysisStageResume &&
        (resumeStage === "reader_journey" ||
          [
            "scene_profiles_partial",
            "budget_blocked",
            "aborted_by_limit",
            "failed",
            "interrupted",
            "recoverable_failed",
          ].includes(liveStatus));
      if (boundJourneyId != null && journeyLevelResume && !withBudgetAuth) {
        setStatusMessage("正在恢复阅读旅程");
        await analysisApi.resumeReaderJourney(boundJourneyId, {
          client_request_id: getOrCreateJourneyClientRequestId(run.id),
          cloud_consent: true,
          confirmed: true,
        });
        await qc.invalidateQueries({ queryKey: ["reader-journey"] });
        await qc.invalidateQueries({ queryKey: ["reader-journey-progress"] });
        await qc.invalidateQueries({ queryKey: ["analysis-recovery-plan"] });
        await qc.invalidateQueries({ queryKey: ["current-page-analysis-run", run.id] });
        await qc.invalidateQueries({ queryKey: ["runs"] });
        setStatusMessage("已开始恢复，进度将自动更新");
        onContinued?.();
        onClose?.();
        return;
      }
      const body: Parameters<typeof analysisRecoveryApi.recover>[1] = {
        client_request_id: clientRequestIdFor(run.id, { rotate: false }),
        cloud_consent: true,
        confirmed: true,
        recovery_mode: "unified",
        resume: true,
      };
      if (withBudgetAuth && proposal) {
        body.authorize_budget = {
          scope: "run_temporary",
          extra_requests: proposal.suggested_extra_requests,
        };
      }
      const result = await analysisRecoveryApi.recover(run.id, body);
      if (result.details?.redirect === "settings_ai_service" || result.details?.settings_focus === "api_key") {
        navigate("/settings?tab=ai&focus=api_key");
        onClose?.();
        return;
      }
      if (result.budget_authorization_proposal && !withBudgetAuth) {
        setProposalOpen(true);
        await planQuery.refetch();
        return;
      }
      const detailMsg =
        typeof result.details?.user_message === "string"
          ? result.details.user_message
          : undefined;
      if (result.details?.recovery_exhausted || result.details?.resume_blocked) {
        await planQuery.refetch();
        setError(detailMsg || "当前错误无法自动继续，请查看建议操作");
        return;
      }
      if ((result.blockers || []).length > 0 && !result.model_invocations_started) {
        const auth = (result.blockers || []).find((b) => b.settings_focus === "api_key");
        if (auth) {
          navigate("/settings?tab=ai&focus=api_key");
          onClose?.();
          return;
        }
        await planQuery.refetch();
        const msgs = (result.blockers || []).map((b) => b.user_message).join("；");
        if (msgs) setError(msgs);
        else if (detailMsg) setError(detailMsg);
        return;
      }
      await qc.invalidateQueries({ queryKey: ["current-page-analysis-run", run.id] });
      await qc.invalidateQueries({ queryKey: ["runs"] });
      await planQuery.refetch();
      setProposalOpen(false);
      if (result.model_invocations_started || result.user_status === "running") {
        setStatusMessage("已开始恢复，进度将自动更新");
        onContinued?.();
        onClose?.();
      } else {
        setError(detailMsg || "恢复未启动模型请求，请查看原因后重试");
      }
    } catch (err) {
      setError((err as Error).message || "修复并继续失败");
    } finally {
      setBusy(false);
      if (!error) {
        /* status may remain briefly; clear when idle */
      }
    }
  };

  const openSettingsAi = () => {
    navigate("/settings?tab=ai");
    onClose?.();
  };

  const body = (
    <div data-testid="unified-recovery-body" data-recovery-kind={isFailed ? "failed" : "paused"}>
      <h3 data-testid="unified-recovery-title">{title}</h3>
      <p data-testid="unified-recovery-lead">{lead}</p>
      {userError?.reason && (
        <p data-testid="unified-recovery-reason">
          原因：{userError.reason}
        </p>
      )}
      {userError?.config_note && (
        <p data-testid="unified-recovery-config-note">{userError.config_note}</p>
      )}
      {userError?.impact && (
        <p data-testid="unified-recovery-impact">后续影响：{userError.impact}</p>
      )}
      {boundaryFocus && (
        <p data-testid="unified-recovery-results-retained">已完成的结果将被保留。</p>
      )}
      {planQuery.isLoading && <p data-testid="unified-recovery-loading">正在诊断可恢复项…</p>}
      {busy && statusMessage && (
        <p data-testid="unified-recovery-status" aria-live="polite">
          {statusMessage}
        </p>
      )}
      {checkRows.length > 0 && (
        <ul className="unified-recovery-checks" data-testid="unified-recovery-checks">
          {checkRows.map((row) => (
            <li key={row.id} data-testid={`unified-recovery-check-${row.id}`}>
              {row.ok ? "✓" : row.warn ? "!" : "✕"} {row.label}
            </li>
          ))}
        </ul>
      )}
      {(plan?.blockers || []).length > 0 && (
        <ul className="unified-recovery-blockers" data-testid="unified-recovery-blockers">
          {(plan?.blockers || []).map((b) => (
            <li key={b.code} data-testid={`unified-recovery-blocker-${b.code}`}>
              <span>{b.user_message}</span>
              {b.required != null && (
                <span className="unified-recovery-blocker-metrics" data-testid={`unified-recovery-blocker-metrics-${b.code}`}>
                  {" "}
                  required={b.required} · available={b.available}
                  {b.shortfall != null ? ` · shortfall=${b.shortfall}` : ""}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {proposalOpen && proposal && (
        <div className="unified-recovery-proposal" data-testid="unified-recovery-proposal">
          <h4>确认本次Run临时授权</h4>
          <ul>
            <li data-testid="unified-recovery-proposal-current">
              当前剩余请求：{proposal.current_remaining_requests}次（每日保护 {proposal.current_daily_request_limit}）
            </li>
            <li data-testid="unified-recovery-proposal-required">
              required：{proposal.required_requests}次
            </li>
            <li data-testid="unified-recovery-proposal-extra">
              建议仅为本次Run临时授权额外：{proposal.suggested_extra_requests}次（不修改每日请求设置）
            </li>
            <li data-testid="unified-recovery-proposal-cost">
              预计费用：约{proposal.estimated_cost} {proposal.currency}（不提高每日费用上限）
            </li>
            <li>不会重跑：{(proposal.will_not_rerun || []).join("、") || "已完成阶段"}</li>
          </ul>
          <p className="notice">{proposal.message}</p>
          <div className="budget-pause-actions">
            <button
              type="button"
              className="primary"
              data-testid="unified-recovery-authorize-run"
              disabled={busy}
              onClick={() => void fixAndContinue(true)}
            >
              {busy ? "正在授权并继续…" : "仅为本次Run授权"}
            </button>
            <button
              type="button"
              className="secondary"
              data-testid="unified-recovery-proposal-cancel"
              disabled={busy}
              onClick={() => setProposalOpen(false)}
            >
              取消
            </button>
          </div>
        </div>
      )}
      {!proposalOpen && (
        <div className="budget-pause-actions">
          {(showEvidenceRemap || showBoundaryRerun) && (
            <button
              type="button"
              className="primary"
              data-testid={
                showEvidenceRemap
                  ? "unified-recovery-evidence-remap"
                  : "unified-recovery-boundary-rerun"
              }
              disabled={busy || planQuery.isLoading || !plan}
              onClick={() => void fixAndContinue(false)}
            >
              {busy
                ? statusMessage || "处理中…"
                : showEvidenceRemap
                  ? evidenceRemapAction?.label || "整理证据并继续"
                  : boundaryRerunAction?.label || "重新检查场景边界"}
            </button>
          )}
          {showFixContinue && !showEvidenceRemap && !showBoundaryRerun && (
            <button
              type="button"
              className="primary"
              data-testid="unified-recovery-fix-continue"
              disabled={busy || planQuery.isLoading || !plan}
              onClick={() => void fixAndContinue(false)}
            >
              {busy
                ? statusMessage || "正在修复…"
                : resumeStage === "reader_journey"
                  ? "继续生成阅读旅程"
                  : "修复并继续"}
            </button>
          )}
          {showNonRepairableActions && (
            <button
              type="button"
              className="secondary"
              data-testid="unified-recovery-view-issue"
              disabled={busy}
              onClick={() => setTechOpen(true)}
            >
              查看问题
            </button>
          )}
          {recoveryExhausted && (
            <>
              <button
                type="button"
                className="primary"
                data-testid="unified-recovery-revalidate"
                disabled={busy}
                onClick={openSettingsAi}
              >
                重新验证 AI 服务
              </button>
              <button
                type="button"
                className="secondary"
                data-testid="unified-recovery-new-task"
                disabled={busy}
                onClick={() => {
                  setTechOpen(true);
                  setError("请在章节页新建分析任务以继续；已完成结果仍会保留。");
                }}
              >
                新建恢复任务
              </button>
            </>
          )}
          {providerNotRetryable && !recoveryExhausted && (
            <>
              <button
                type="button"
                className="primary"
                data-testid="unified-recovery-check-config"
                disabled={busy}
                onClick={openSettingsAi}
              >
                检查模型配置
              </button>
              <button
                type="button"
                className="secondary"
                data-testid="unified-recovery-validate-save"
                disabled={busy}
                onClick={openSettingsAi}
              >
                验证并保存
              </button>
            </>
          )}
          <button
            type="button"
            className="secondary"
            data-testid="unified-recovery-later"
            disabled={busy}
            onClick={() => {
              onLater?.();
              onClose?.();
            }}
          >
            稍后处理
          </button>
          <button
            type="button"
            className="ghost"
            data-testid="unified-recovery-details"
            onClick={() => setTechOpen((v) => !v)}
          >
            {techOpen ? "收起详情" : "查看详情"}
          </button>
        </div>
      )}
      {error && (
        <p className="notice error" data-testid="unified-recovery-error">
          {error}
        </p>
      )}
      {techOpen && plan && (
        <pre className="chapter-analysis-tech" data-testid="unified-recovery-tech">
          {JSON.stringify(
            {
              internal_error_code: details.error_code || run.error_code,
              root_error_code: details.root_error_code || run.root_error_code,
              http_status: details.http_status ?? null,
              provider_error_code: details.provider_error_code ?? null,
              provider_message: details.provider_message ?? null,
              evidence_error: details.evidence_error ?? null,
              affected_fields:
                ((details.evidence_error as { details?: { affected_fields?: string[] } } | null)
                  ?.details?.affected_fields) ??
                (details as { affected_fields?: string[] }).affected_fields ??
                null,
              provider_request_id: details.provider_request_id ?? null,
              endpoint_host: details.endpoint_host ?? null,
              error_category: details.error_category ?? null,
              retryable: details.retryable ?? plan.retry_eligible ?? null,
              retry_after: details.retry_after ?? null,
              timeout_stage: details.timeout_stage ?? null,
              response_content_type: details.response_content_type ?? null,
              sanitized_response_excerpt: details.sanitized_response_excerpt ?? null,
              occurred_at: details.occurred_at ?? null,
              request_hash: plan.request_hash,
              run_id: plan.run_id,
              resume_stage: plan.resume_stage,
              recovery_attempts: plan.recovery_attempts,
              manual_recovery_attempts: details.manual_recovery_attempts ?? null,
              auto_recovery_attempts: details.auto_recovery_attempts ?? null,
            },
            null,
            2,
          )}
        </pre>
      )}
    </div>
  );

  if (suppressForActiveJourney) {
    return null;
  }

  if (variant === "modal") {
    return (
      <div className="modal-backdrop" data-testid="unified-recovery-modal">
        <div
          className="modal budget-pause-modal"
          role="dialog"
          aria-modal="true"
          data-testid="budget-pause-modal"
        >
          <header className="modal-header">
            <h2>{title}</h2>
            <button type="button" className="modal-close" aria-label="关闭" onClick={onClose}>
              ×
            </button>
          </header>
          <div className="modal-body">{body}</div>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`budget-pause-card unified-recovery-card recovery-${isFailed ? "failed" : "paused"}`}
      data-testid="unified-recovery-card"
      data-recovery-kind={isFailed ? "failed" : "paused"}
    >
      {/* Compat alias for prior budget-pause shell tests */}
      <div data-testid="budget-pause-card" hidden aria-hidden="true" />
      {body}
    </div>
  );
}

/** Whether chapter/tasks should host the unified recovery card for this UI state. */
export function shouldShowUnifiedRecovery(uiState: string | undefined | null): boolean {
  return shouldShowUnifiedRecoveryForJourney({ uiState });
}
