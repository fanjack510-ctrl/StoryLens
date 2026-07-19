import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { Run } from "../../types";
import { analysisApi } from "../../services/analysisApi";
import { settingsApi } from "../../services/settingsApi";
import {
  formatDimensionGaps,
  sufficientDimensionsNote,
  techBudgetDetails,
  userFacingBudgetMessage,
} from "../../services/budgetErrorCopy";
import { budgetGapFromRun } from "../../services/budgetPauseDetect";
import { computeRequestLimitSuggestion } from "../../services/budgetRecoveryMath";

type Props = {
  run: Run;
  variant: "modal" | "card";
  onCloseModal?: () => void;
  onContinued?: () => void;
};

export function BudgetPauseRecovery({ run, variant, onCloseModal, onContinued }: Props) {
  const qc = useQueryClient();
  const [step, setStep] = useState<"pause" | "confirm">("pause");
  const [techOpen, setTechOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const gap = useMemo(() => budgetGapFromRun(run), [run]);
  const budgetQuery = useQuery({
    queryKey: ["cloud-budget"],
    queryFn: settingsApi.cloudBudget,
  });
  const usageQuery = useQuery({
    queryKey: ["cloud-usage"],
    queryFn: settingsApi.cloudUsage,
  });

  const suggestion = useMemo(() => {
    const dailyLimit = Number(budgetQuery.data?.cloud_daily_request_limit) || 50;
    const remaining =
      typeof gap.remaining?.requests === "number"
        ? gap.remaining.requests
        : Number(usageQuery.data?.remaining_requests) || 0;
    const required =
      typeof gap.required?.requests === "number" ? gap.required.requests : 0;
    const costLimit =
      Number(budgetQuery.data?.cloud_daily_estimated_cost_limit) || 20;
    return computeRequestLimitSuggestion({
      currentDailyRequestLimit: dailyLimit,
      remainingRequests: remaining,
      requiredWorstRequests: required,
      dailyCostLimit: costLimit,
      estimatedStageCost:
        typeof gap.required?.estimated_cost === "number"
          ? gap.required.estimated_cost
          : undefined,
    });
  }, [budgetQuery.data, usageQuery.data, gap]);

  const title =
    gap.dimensions.includes("requests") && gap.dimensions.length === 1
      ? "分析已暂停：今日云端请求额度不足"
      : "分析已暂停：今日云端额度不足";

  const bodyLines = useMemo(() => {
    const need = gap.required?.requests;
    const left = gap.remaining?.requests;
    const lines: string[] = [];
    if (typeof need === "number" && typeof left === "number") {
      lines.push(`Scene Analysis最多需要${need}次云端请求，当前今日额度只剩${left}次。`);
    } else {
      lines.push(userFacingBudgetMessage(run.error_code || run.root_error_code));
      lines.push(formatDimensionGaps(gap));
    }
    const ok = sufficientDimensionsNote(gap);
    if (ok) lines.push(ok);
    lines.push("调整额度后将从Scene Analysis继续，不会重新执行场景边界识别。");
    return lines;
  }, [gap, run.error_code, run.root_error_code]);

  const adjustAndContinue = async () => {
    if (busy) return;
    setBusy(true);
    setError(undefined);
    try {
      const current = budgetQuery.data || (await settingsApi.cloudBudget());
      const nextLimit = suggestion.recommendedLimit;
      if (nextLimit > Number(current.cloud_daily_request_limit || 0)) {
        await settingsApi.saveCloudBudget({
          ...current,
          cloud_daily_request_limit: nextLimit,
          currency: current.currency || "CNY",
        });
        await qc.invalidateQueries({ queryKey: ["cloud-budget"] });
        await qc.invalidateQueries({ queryKey: ["cloud-usage"] });
      }
      const pre = await analysisApi.sceneAnalysisResumePreflight(run.id, {
        cloud_consent: true,
      });
      const need =
        pre.worst_case_requests ??
        (pre as { worst_case_request_count?: number }).worst_case_request_count ??
        gap.required?.requests;
      const left =
        pre.remaining_budget?.requests ??
        (pre as { remaining?: { requests?: number } }).remaining?.requests ??
        gap.remaining?.requests;
      if (!pre.eligible || !pre.within_budget) {
        throw new Error(
          typeof need === "number" && typeof left === "number"
            ? `额度仍不足：最多需要 ${need} 次，当前剩余 ${left} 次。`
            : "调整后额度仍不足，请提高每日请求保护后重试。",
        );
      }
      await analysisApi.resumeSceneAnalysis(run.id, {
        client_request_id: crypto.randomUUID(),
        cloud_consent: true,
        confirmed: true,
        provider_state_version: pre.provider_state_version,
      });
      await qc.invalidateQueries({ queryKey: ["current-page-analysis-run", run.id] });
      await qc.invalidateQueries({ queryKey: ["runs"] });
      onContinued?.();
      onCloseModal?.();
    } catch (err) {
      setError((err as Error).message || "调整并继续失败");
    } finally {
      setBusy(false);
    }
  };

  const content =
    step === "confirm" ? (
      <div data-testid="budget-adjust-confirm">
        <h3>确认调整额度</h3>
        <ul className="budget-adjust-summary">
          <li data-testid="budget-adjust-current">
            当前每日请求保护：{suggestion.currentDailyRequestLimit}次
          </li>
          <li data-testid="budget-adjust-min">
            完成本章建议至少：{suggestion.minSuggestedLimit}次
          </li>
          <li data-testid="budget-adjust-recommended">
            推荐调整到：{suggestion.recommendedLimit}次
          </li>
          <li data-testid="budget-adjust-cost-cap">
            预计本阶段新增费用：不超过{suggestion.estimatedStageCostCap} CNY
          </li>
          <li data-testid="budget-adjust-cost-limit">
            每日费用上限仍保持{suggestion.dailyCostLimit} CNY
          </li>
        </ul>
        <div className="budget-pause-actions">
          <button
            type="button"
            className="primary"
            data-testid="budget-confirm-adjust-continue"
            disabled={busy}
            onClick={() => void adjustAndContinue()}
          >
            {busy ? "正在调整并继续…" : "确认调整并继续"}
          </button>
          <button
            type="button"
            className="secondary"
            data-testid="budget-adjust-cancel"
            disabled={busy}
            onClick={() => setStep("pause")}
          >
            取消
          </button>
        </div>
      </div>
    ) : (
      <div data-testid="budget-pause-body">
        <h3 data-testid="budget-pause-title">{title}</h3>
        {bodyLines.map((line) => (
          <p key={line}>{line}</p>
        ))}
        <div className="budget-pause-actions">
          <button
            type="button"
            className="primary"
            data-testid="budget-adjust-and-continue"
            onClick={() => setStep("confirm")}
          >
            调整额度并继续
          </button>
          {variant === "modal" ? (
            <button
              type="button"
              className="secondary"
              data-testid="budget-pause-later"
              onClick={onCloseModal}
            >
              稍后继续
            </button>
          ) : null}
          <button
            type="button"
            className="ghost"
            data-testid="budget-pause-tech-toggle"
            onClick={() => setTechOpen((v) => !v)}
          >
            {techOpen ? "收起技术详情" : "查看技术详情"}
          </button>
        </div>
      </div>
    );

  const tech = techOpen ? (
    <pre className="chapter-analysis-tech" data-testid="budget-pause-tech-details">
      {JSON.stringify(
        techBudgetDetails(gap, run.error_code || run.root_error_code),
        null,
        2,
      )}
    </pre>
  ) : null;

  if (variant === "modal") {
    return (
      <div className="modal-backdrop" data-testid="budget-pause-modal">
        <div className="modal budget-pause-modal" role="dialog" aria-modal="true">
          <header className="modal-header">
            <h2>分析已暂停</h2>
            <button type="button" className="modal-close" aria-label="关闭" onClick={onCloseModal}>
              ×
            </button>
          </header>
          <div className="modal-body">
            {content}
            {error && (
              <p className="notice error" data-testid="budget-pause-error">
                {error}
              </p>
            )}
            {tech}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="budget-pause-card" data-testid="budget-pause-card">
      {content}
      {error && (
        <p className="notice error" data-testid="budget-pause-error">
          {error}
        </p>
      )}
      {tech}
    </div>
  );
}
