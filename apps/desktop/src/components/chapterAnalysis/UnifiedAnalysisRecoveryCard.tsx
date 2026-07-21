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

function clientRequestIdFor(runId: number): string {
  const key = `unified-recover:${runId}`;
  try {
    const existing = sessionStorage.getItem(key);
    if (existing && existing.length >= 8) return existing;
    const next = globalThis.crypto?.randomUUID?.() || `unified-recover-${runId}-${Date.now()}`;
    sessionStorage.setItem(key, next);
    return next;
  } catch {
    return `unified-recover-${runId}-${Date.now()}`;
  }
}

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
  const [error, setError] = useState<string>();
  const [proposalOpen, setProposalOpen] = useState(false);
  const uiState = mapRunToUiState(run);
  const isFailed = uiState === "failed";
  const title = isFailed ? "分析未完成" : "分析已暂停";
  const lead = isFailed
    ? "StoryLens 在分析过程中遇到了问题。已经完成的分析结果会被保留。"
    : "当前进度已保存，可以稍后继续。";

  const planQuery = useQuery({
    queryKey: ["analysis-recovery-plan", run.id],
    queryFn: () => analysisRecoveryApi.recoveryPlan(run.id),
    refetchInterval: 4000,
  });

  const plan = planQuery.data;
  const checks = plan?.checks || [];
  const proposal = plan?.budget_authorization_proposal;

  const checkRows = useMemo(() => {
    return checks
      .filter((c) => c.user_label)
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

  const fixAndContinue = async (withBudgetAuth: boolean) => {
    if (busy) return;
    setBusy(true);
    setError(undefined);
    try {
      if (needsAuthRedirect) {
        navigate("/settings?tab=ai&focus=api_key");
        onClose?.();
        return;
      }
      if (proposal && !withBudgetAuth) {
        setProposalOpen(true);
        setBusy(false);
        return;
      }
      const body: Parameters<typeof analysisRecoveryApi.recover>[1] = {
        client_request_id: clientRequestIdFor(run.id),
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
      }
      await qc.invalidateQueries({ queryKey: ["current-page-analysis-run", run.id] });
      await qc.invalidateQueries({ queryKey: ["runs"] });
      await qc.invalidateQueries({ queryKey: ["analysis-recovery-plan", run.id] });
      setProposalOpen(false);
      onContinued?.();
      onClose?.();
    } catch (err) {
      setError((err as Error).message || "修复并继续失败");
    } finally {
      setBusy(false);
    }
  };

  const body = (
    <div data-testid="unified-recovery-body" data-recovery-kind={isFailed ? "failed" : "paused"}>
      <h3 data-testid="unified-recovery-title">{title}</h3>
      <p data-testid="unified-recovery-lead">{lead}</p>
      {planQuery.isLoading && <p data-testid="unified-recovery-loading">正在诊断可恢复项…</p>}
      {checkRows.length > 0 && (
        <ul className="unified-recovery-checks" data-testid="unified-recovery-checks">
          {checkRows.map((row) => (
            <li key={row.id} data-testid={`unified-recovery-check-${row.id}`}>
              {row.ok ? "✓" : "✕"} {row.label}
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
          <button
            type="button"
            className="primary"
            data-testid="unified-recovery-fix-continue"
            disabled={busy || planQuery.isLoading || !plan}
            onClick={() => void fixAndContinue(false)}
          >
            {busy ? "正在修复…" : "修复并继续"}
          </button>
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
              internal_error_code: plan.details?.error_code || run.error_code,
              root_error_code: plan.details?.root_error_code || run.root_error_code,
              blockers: plan.blockers,
              required_available_shortfall: plan.checks
                .filter((c) => c.status === "fail")
                .map((c) => ({
                  id: c.id,
                  required: c.required,
                  available: c.available,
                  shortfall: c.shortfall,
                })),
              provider: plan.provider,
              model: plan.model,
              request_hash: plan.request_hash,
              run_id: plan.run_id,
              resume_stage: plan.resume_stage,
              recovery_attempts: plan.recovery_attempts,
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
