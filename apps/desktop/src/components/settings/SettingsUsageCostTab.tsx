import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  DEFAULT_ANALYSIS_MODE,
  ordinaryModeOptions,
  presetFor,
  readStoredAnalysisMode,
} from "../../services/analysisModePresets";
import { settingsApi } from "../../services/settingsApi";
import "./settings.css";

function displayAmount(value: number | null | undefined, ready: boolean): string {
  if (!ready || value == null || Number.isNaN(value)) return "—";
  return `${value} CNY`;
}

function displayCount(value: number | null | undefined, ready: boolean): string {
  if (!ready || value == null || Number.isNaN(value)) return "—";
  return String(value);
}

export function SettingsUsageCostTab() {
  const [limit, setLimit] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const mode = readStoredAnalysisMode();
  const preset = presetFor(mode === "CUSTOM" ? DEFAULT_ANALYSIS_MODE : mode);

  const budgetQuery = useQuery({ queryKey: ["cloud-budget"], queryFn: settingsApi.cloudBudget });
  const usage = useQuery({ queryKey: ["cloud-usage"], queryFn: settingsApi.cloudUsage });

  useEffect(() => {
    if (budgetQuery.data?.cloud_daily_estimated_cost_limit != null) {
      setLimit(String(budgetQuery.data.cloud_daily_estimated_cost_limit));
    }
  }, [budgetQuery.data?.cloud_daily_estimated_cost_limit]);

  const saveLimit = async () => {
    setMessage("");
    const value = Number(limit);
    if (!Number.isFinite(value) || value <= 0) {
      setMessage("保存失败：费用上限必须大于 0。");
      return;
    }
    setSaving(true);
    try {
      await settingsApi.saveCloudBudget({
        ...budgetQuery.data,
        cloud_daily_estimated_cost_limit: value,
        currency: "CNY",
      });
      setMessage("费用上限已保存。");
    } catch (error) {
      setMessage(`保存失败：${error instanceof Error ? error.message : "未知错误"}`);
    } finally {
      setSaving(false);
    }
  };

  const chapterEstimate = preset?.estimatedCostPerChapterCny;
  const usageReady = usage.isSuccess && usage.data != null;
  const budgetReady = budgetQuery.isSuccess && budgetQuery.data != null;
  const usedToday = usage.data?.estimated_cost;
  const tokensToday = usage.data?.total_tokens;
  const dailyLimit = budgetQuery.data?.cloud_daily_estimated_cost_limit;
  const usageDate = usage.data?.date;

  return (
    <article className="settings-panel settings-module" data-testid="settings-panel-cost">
      <header className="settings-panel-header">
        <h2>使用费用</h2>
        <p>了解分析花费并设置费用上限。实际账单以 AI 服务商为准。</p>
      </header>

      <dl className="settings-stat-grid cost-summary" data-testid="cost-stat-region">
        <div className="settings-stat">
          <dt>今日费用</dt>
          <dd data-testid="cost-today-usage">{displayAmount(usedToday, usageReady)}</dd>
        </div>
        <div className="settings-stat">
          <dt>今日 Token</dt>
          <dd data-testid="cost-today-tokens">{displayCount(tokensToday, usageReady)}</dd>
        </div>
        <div className="settings-stat">
          <dt>每日上限</dt>
          <dd data-testid="cost-daily-limit">{displayAmount(dailyLimit, budgetReady)}</dd>
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
        <span>费用上限（CNY / 自然日）</span>
        <input
          type="number"
          min={0.01}
          step={0.5}
          aria-label="费用上限"
          data-testid="cost-limit-input"
          value={limit}
          onChange={(e) => setLimit(e.target.value)}
        />
      </label>
      <p className="hint">
        达到上限后将暂停新的云端分析。可在高级设置中查看 Token 与请求明细（不影响后端预算能力）。
      </p>

      <section className="privacy-note">
        <h3>费用说明</h3>
        <p>
          单章费用为基于当前分析模式（
          {ordinaryModeOptions().find((o) => o.id === mode)?.shortLabel || "均衡"}
          ）的估算，实际消耗因章节长度与模型响应而异。StoryLens 不代收费用。未知数据以「—」显示，不会伪造金额。
        </p>
      </section>

      {message && <p role="status">{message}</p>}
      <div className="settings-actions">
        <button
          type="button"
          className="primary"
          disabled={saving}
          data-testid="cost-save"
          onClick={() => void saveLimit()}
        >
          {saving ? "保存中…" : "保存上限"}
        </button>
      </div>
    </article>
  );
}
