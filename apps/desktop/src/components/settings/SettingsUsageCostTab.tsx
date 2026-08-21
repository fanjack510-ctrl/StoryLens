import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  DEFAULT_ANALYSIS_MODE,
  ordinaryModeOptions,
  presetFor,
  readStoredAnalysisMode,
} from "../../services/analysisModePresets";
import { settingsApi } from "../../services/settingsApi";
import "./settings.css";

const DEFAULT_REQUEST_LIMIT = 100;
const DEFAULT_TOKEN_LIMIT = 500000;
const DEFAULT_COST_LIMIT = 20;

function displayAmount(value: number | null | undefined, ready: boolean): string {
  if (!ready || value == null || Number.isNaN(value)) return "—";
  return `${Number(value).toLocaleString("zh-CN", { maximumFractionDigits: 2 })} CNY`;
}

function displayCount(value: number | null | undefined, ready: boolean): string {
  if (!ready || value == null || Number.isNaN(value)) return "—";
  return Number(value).toLocaleString("zh-CN");
}

function nextLocalMidnightLabel(): string {
  const now = new Date();
  const next = new Date(now);
  next.setHours(24, 0, 0, 0);
  return next.toLocaleString("zh-CN", {
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function SettingsUsageCostTab() {
  const qc = useQueryClient();
  const [costLimit, setCostLimit] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const mode = readStoredAnalysisMode();
  const preset = presetFor(mode === "CUSTOM" ? DEFAULT_ANALYSIS_MODE : mode);

  const budgetQuery = useQuery({ queryKey: ["cloud-budget"], queryFn: settingsApi.cloudBudget });
  const usage = useQuery({ queryKey: ["cloud-usage"], queryFn: settingsApi.cloudUsage });

  useEffect(() => {
    if (budgetQuery.data?.cloud_daily_estimated_cost_limit != null) {
      setCostLimit(String(budgetQuery.data.cloud_daily_estimated_cost_limit));
    }
  }, [budgetQuery.data?.cloud_daily_estimated_cost_limit]);

  const saveLimits = async () => {
    setMessage("");
    const costValue = Number(costLimit);
    if (!Number.isFinite(costValue) || costValue <= 0) {
      setMessage("保存失败：费用上限必须大于 0。");
      return;
    }
    setSaving(true);
    try {
      await settingsApi.saveCloudBudget({
        ...budgetQuery.data,
        cloud_daily_estimated_cost_limit: costValue,
        currency: "CNY",
      });
      setMessage("额度设置已保存。");
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["cloud-budget"] }),
        qc.invalidateQueries({ queryKey: ["cloud-usage"] }),
      ]);
    } catch (error) {
      setMessage(`保存失败：${error instanceof Error ? error.message : "未知错误"}`);
    } finally {
      setSaving(false);
    }
  };

  const restoreDefaults = async () => {
    setCostLimit(String(DEFAULT_COST_LIMIT));
    setMessage("");
    setSaving(true);
    try {
      await settingsApi.saveCloudBudget({
        ...budgetQuery.data,
        cloud_daily_estimated_cost_limit: DEFAULT_COST_LIMIT,
        cloud_daily_request_limit: DEFAULT_REQUEST_LIMIT,
        cloud_daily_token_limit: DEFAULT_TOKEN_LIMIT,
        currency: "CNY",
      });
      setMessage("已恢复默认额度。");
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["cloud-budget"] }),
        qc.invalidateQueries({ queryKey: ["cloud-usage"] }),
      ]);
    } catch (error) {
      setMessage(`恢复默认失败：${error instanceof Error ? error.message : "未知错误"}`);
    } finally {
      setSaving(false);
    }
  };

  const chapterEstimate = preset?.estimatedCostPerChapterCny;
  const usageReady = usage.isSuccess && usage.data != null;
  const budgetReady = budgetQuery.isSuccess && budgetQuery.data != null;
  const usedToday = usage.data?.estimated_cost;
  const tokensToday = usage.data?.total_tokens;
  const requestsToday = usage.data?.request_count;
  const dailyLimit = budgetQuery.data?.cloud_daily_estimated_cost_limit;
  const remainingRequests = usage.data?.remaining_requests;
  const remainingTokens = usage.data?.remaining_tokens;
  const remainingCost = usage.data?.remaining_estimated_cost;
  const usageDate = usage.data?.date;

  return (
    <article className="settings-panel settings-module" data-testid="settings-panel-cost">
      <header className="settings-panel-header">
        <h2>使用额度</h2>
        <p data-testid="usage-local-limit-disclaimer">
          这是StoryLens本地使用上限，不代表模型服务商账户余额。
        </p>
      </header>

      <dl className="settings-stat-grid cost-summary cost-summary-remaining" data-testid="cost-stat-region">
        <div className="settings-stat settings-stat-emphasis">
          <dt>剩余费用</dt>
          <dd data-testid="cost-remaining-cost">{displayAmount(remainingCost, usageReady)}</dd>
        </div>
        <div className="settings-stat settings-stat-emphasis">
          <dt>剩余请求</dt>
          <dd data-testid="cost-remaining-requests">{displayCount(remainingRequests, usageReady)}</dd>
        </div>
        <div className="settings-stat settings-stat-emphasis">
          <dt>剩余Token</dt>
          <dd data-testid="cost-remaining-tokens">{displayCount(remainingTokens, usageReady)}</dd>
        </div>
      </dl>

      <details className="settings-fold" data-testid="cost-today-usage-fold">
        <summary>查看今日用量</summary>
        <dl className="settings-stat-grid settings-fold-body">
          <div className="settings-stat">
            <dt>今日已使用（费用）</dt>
            <dd data-testid="cost-today-usage">{displayAmount(usedToday, usageReady)}</dd>
          </div>
          <div className="settings-stat">
            <dt>今日已使用（请求）</dt>
            <dd data-testid="cost-today-requests">{displayCount(requestsToday, usageReady)}</dd>
          </div>
          <div className="settings-stat">
            <dt>今日已使用（Token）</dt>
            <dd data-testid="cost-today-tokens">{displayCount(tokensToday, usageReady)}</dd>
          </div>
          <div className="settings-stat">
            <dt>每日费用上限</dt>
            <dd data-testid="cost-daily-limit">{displayAmount(dailyLimit, budgetReady)}</dd>
          </div>
        </dl>
      </details>

      <section className="settings-zone" data-testid="cost-limits-zone">
        <h3>每日上限</h3>
        <label className="settings-field">
          <span>每日费用上限（CNY）</span>
          <input
            type="number"
            min={0.01}
            step={0.5}
            aria-label="每日费用上限"
            data-testid="cost-limit-input"
            value={costLimit}
            onChange={(e) => setCostLimit(e.target.value)}
          />
        </label>

        {/* 请求数和 Token 两个上限已经不再拦人——它们量的是同一件事的另外两种单位，
            用得多就是花得多，却各自独立地拦：曾出现实际只花了 ¥1.7、费用额度 ¥50 一分
            没动，却因为 Token 到顶而无法分析。用量仍然照常统计并显示在上面，只是能不能
            继续，只问钱。 */}
        <p className="muted" data-testid="cost-limits-note">
          能不能继续分析，只看费用这一条。请求数与 Token 仍然照常统计（见上方用量），但不再
          单独设闸——它们量的是同一件事的另外两种单位。
        </p>

        {message && <p role="status">{message}</p>}
        <div className="settings-actions">
          <button
            type="button"
            className="primary"
            disabled={saving}
            data-testid="cost-save"
            onClick={() => void saveLimits()}
          >
            {saving ? "保存中…" : "保存上限"}
          </button>
          <button
            type="button"
            disabled={saving}
            data-testid="cost-restore-defaults"
            onClick={() => void restoreDefaults()}
          >
            恢复默认
          </button>
        </div>
      </section>

      <details className="settings-fold" data-testid="cost-usage-details-fold">
        <summary>用量详情</summary>
        <div className="settings-fold-body">
          <p data-testid="cost-reset-time">重置时间：{nextLocalMidnightLabel()}（本地自然日）</p>
          <p data-testid="cost-chapter-estimate">
            单章预计费用：
            {chapterEstimate == null ? "—" : `约 ${chapterEstimate} CNY`}
            （
            {ordinaryModeOptions().find((o) => o.id === mode)?.shortLabel || "均衡"}
            模式估算）
          </p>
          {usageDate && (
            <p className="hint" data-testid="cost-month-usage">
              用量日期：{usageDate}
            </p>
          )}
        </div>
      </details>
    </article>
  );
}
