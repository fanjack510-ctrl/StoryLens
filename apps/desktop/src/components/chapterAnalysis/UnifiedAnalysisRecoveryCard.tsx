import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { Run } from "../../types";
import { analysisRecoveryApi } from "../../services/analysisRecoveryApi";
import { mapRunToUiState } from "./mapAnalysisUiState";

type Props = {
  run: Run;
  variant?: "card" | "modal";
  onClose?: () => void;
  onContinued?: () => void;
  onLater?: () => void;
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

  const planQuery = useQuery({
    queryKey: ["analysis-recovery-plan", run.id],
    queryFn: () => analysisRecoveryApi.recoveryPlan(run.id),
    refetchInterval: 4000,
  });

  const plan = planQuery.data;
  const checks = plan?.checks || [];
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
  }, [checks]);

  const needsAuthRedirect = (plan?.blockers || []).some(
    (b) =>
      b.settings_focus === "api_key" ||
      b.reason === "credential_missing" ||
      b.reason === "credential_unauthorized",
  );

  const showFixContinue =
    !recoveryExhausted &&
    !providerNotRetryable &&
    (plan?.recommended_actions || []).some((a) => a.action === "fix_and_continue");

  const fixAndContinue = async (withBudgetAuth: boolean) => {
    if (busy) return;
    setBusy(true);
    setError(undefined);
    setStatusMessage("正在检查失败原因");
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
      if (resumeStage === "boundary_detection") {
        setStatusMessage("正在从场景边界识别继续");
      } else if (resumeStage === "scene_analysis") {
        setStatusMessage("正在从场景分析继续");
      } else if (resumeStage === "reader_journey") {
        setStatusMessage("正在继续生成阅读旅程");
      } else {
        setStatusMessage("正在修复并继续…");
      }
      const body: Parameters<typeof analysisRecoveryApi.recover>[1] = {
        client_request_id: clientRequestIdFor(run.id, { rotate: true }),
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
          {showFixContinue && (
            <button
              type="button"
              className="primary"
              data-testid="unified-recovery-fix-continue"
              disabled={busy || planQuery.isLoading || !plan}
              onClick={() => void fixAndContinue(false)}
            >
              {busy ? statusMessage || "正在修复…" : "修复并继续"}
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
  return (
    uiState === "awaiting_budget_adjustment" ||
    uiState === "provider_recovery" ||
    uiState === "awaiting_reader_journey_start" ||
    uiState === "partial" ||
    uiState === "failed" ||
    uiState === "aborted_by_limit"
  );
}
