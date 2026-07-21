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
  return `${value} CNY`;
}

function displayCount(value: number | null | undefined, ready: boolean): string {
  if (!ready || value == null || Number.isNaN(value)) return "—";
  return String(value);
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
  const [requestLimit, setRequestLimit] = useState("");
  const [tokenLimit, setTokenLimit] = useState("");
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
    if (budgetQuery.data?.cloud_daily_request_limit != null) {
      setRequestLimit(String(budgetQuery.data.cloud_daily_request_limit));
    }
    if (budgetQuery.data?.cloud_daily_token_limit != null) {
      setTokenLimit(String(budgetQuery.data.cloud_daily_token_limit));
    }
  }, [
    budgetQuery.data?.cloud_daily_estimated_cost_limit,
    budgetQuery.data?.cloud_daily_request_limit,
    budgetQuery.data?.cloud_daily_token_limit,
  ]);

  const saveLimits = async () => {
    setMessage("");
    const costValue = Number(costLimit);
    const requestValue = Number(requestLimit);
    const tokenValue = Number(tokenLimit);
    if (!Number.isFinite(costValue) || costValue <= 0) {
      setMessage("保存失败：费用上限必须大于 0。");
      return;
    }
    if (!Number.isInteger(requestValue) || requestValue <= 0) {
      setMessage("保存失败：每日请求额度必须为正整数。");
      return;
    }
    if (!Number.isInteger(tokenValue) || tokenValue <= 0) {
      setMessage("保存失败：每日 Token 额度必须为正整数。");
      return;
    }
    setSaving(true);
    try {
      await settingsApi.saveCloudBudget({
        ...budgetQuery.data,
        cloud_daily_estimated_cost_limit: costValue,
        cloud_daily_request_limit: requestValue,
        cloud_daily_token_limit: tokenValue,
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
    setRequestLimit(String(DEFAULT_REQUEST_LIMIT));
    setTokenLimit(String(DEFAULT_TOKEN_LIMIT));
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
        <p>设置 StoryLens 本地每日请求、Token 与费用上限，并查看今日已用与剩余。</p>
      </header>

      <p className="notice" data-testid="usage-local-limit-disclaimer">
        这是 StoryLens 本地使用上限，不代表模型服务商账户余额。
      </p>

      <dl className="settings-stat-grid cost-summary" data-testid="cost-stat-region">
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
        <div className="settings-stat">
          <dt>当前剩余（请求）</dt>
          <dd data-testid="cost-remaining-requests">{displayCount(remainingRequests, usageReady)}</dd>
        </div>
        <div className="settings-stat">
          <dt>当前剩余（Token）</dt>
          <dd data-testid="cost-remaining-tokens">{displayCount(remainingTokens, usageReady)}</dd>
        </div>
        <div className="settings-stat">
          <dt>当前剩余（费用）</dt>
          <dd data-testid="cost-remaining-cost">{displayAmount(remainingCost, usageReady)}</dd>
        </div>
        <div className="settings-stat">
          <dt>重置时间</dt>
          <dd data-testid="cost-reset-time">{nextLocalMidnightLabel()}（本地自然日）</dd>
        </div>
        <div className="settings-stat">
          <dt>单章预计费用</dt>
          <dd data-testid="cost-chapter-estimate">
            {chapterEstimate == null ? "—" : `约 ${chapterEstimate} CNY`}
          </dd>
        </div>
      </dl>

      {usageDate && (
        <p className="hint" data-testid="cost-month-usage">
          用量日期：{usageDate}
        </p>
      )}

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

      <label className="settings-field">
        <span>每日请求上限</span>
        <input
          type="number"
          min={1}
          step={1}
          aria-label="每日请求上限"
          data-testid="cost-request-limit-input"
          value={requestLimit}
          onChange={(e) => setRequestLimit(e.target.value)}
        />
      </label>

      <label className="settings-field">
        <span>每日 Token 上限</span>
        <input
          type="number"
          min={1}
          step={1000}
          aria-label="每日 Token 上限"
          data-testid="cost-token-limit-input"
          value={tokenLimit}
          onChange={(e) => setTokenLimit(e.target.value)}
        />
      </label>
      <p className="hint">
        达到任一上限后将暂停新的云端分析。单请求 Token / AnalysisRun 请求上限仍在高级设置中调整。
      </p>

      <section className="privacy-note">
        <h3>额度说明</h3>
        <p>
          单章费用为基于当前分析模式（
          {ordinaryModeOptions().find((o) => o.id === mode)?.shortLabel || "均衡"}
          ）的估算，实际消耗因章节长度与模型响应而异。StoryLens 不代收费用。未知数据以「—」显示，不会伪造金额。
          这是 StoryLens 本地使用上限，不代表模型服务商账户余额。
        </p>
      </section>

      {message && <p role="status">{message}</p>}
      <div className="settings-actions">
        <button
          type="button"
          className="primary"
          disabled={saving}
          data-testid="cost-save"
          onClick={() => void saveLimits()}
        >
          {saving ? "保存中…" : "保存"}
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
    </article>
  );
}
