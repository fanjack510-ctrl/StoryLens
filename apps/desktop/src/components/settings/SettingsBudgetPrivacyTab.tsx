import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { settingsApi } from "../../services/settingsApi";
import { Loading } from "../common/States";

export function SettingsBudgetPrivacyTab() {
  const qc = useQueryClient();
  const [budget, setBudget] = useState<any>(null);
  const [message, setMessage] = useState("");
  const cloud = useQuery({ queryKey: ["cloud"], queryFn: settingsApi.cloud });
  const budgetQuery = useQuery({ queryKey: ["cloud-budget"], queryFn: settingsApi.cloudBudget });
  const usage = useQuery({ queryKey: ["cloud-usage"], queryFn: settingsApi.cloudUsage });

  useEffect(() => {
    if (budgetQuery.data) setBudget(budgetQuery.data);
  }, [budgetQuery.data]);

  const save = async () => {
    setMessage("");
    if (!budget || Number(budget.cloud_daily_estimated_cost_limit) <= 0) {
      setMessage("保存失败：每日预算上限必须大于 0。");
      return;
    }
    try {
      await settingsApi.saveCloudBudget({ ...budget, currency: "CNY" });
      setMessage("预算与隐私设置已保存。");
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["cloud-budget"] }),
        qc.invalidateQueries({ queryKey: ["cloud-usage"] }),
      ]);
    } catch (error) {
      setMessage(`保存失败：${error instanceof Error ? error.message : "未知错误"}`);
    }
  };

  const toggleCloud = async (enabled: boolean) => {
    await settingsApi.setCloud(enabled);
    await Promise.all([
      qc.invalidateQueries({ queryKey: ["cloud"] }),
      qc.invalidateQueries({ queryKey: ["cloud-usage"] }),
    ]);
  };

  if (budgetQuery.isLoading || !budget) {
    return (
      <article className="settings-panel">
        <Loading />
      </article>
    );
  }

  const remaining =
    usage.data?.remaining_estimated_cost ?? budget.cloud_daily_estimated_cost_limit;

  return (
    <article className="settings-panel" data-testid="settings-panel-budget">
      <header className="settings-panel-header">
        <h2>预算与隐私</h2>
        <p>控制云端AI开关、每日费用上限与正文发送确认。</p>
      </header>

      <div className="settings-fields">
        <label className="settings-switch-row" data-testid="cloud-ai-master-switch">
          <span>
            <b>启用云端AI</b>
            <small>关闭后不会发起新的云端分析请求</small>
          </span>
          <input
            type="checkbox"
            role="switch"
            className="settings-switch"
            checked={!!cloud.data?.enabled}
            aria-label="启用云端AI"
            onChange={(e) => void toggleCloud(e.target.checked)}
          />
        </label>

        <label className="settings-field">
          <span>每日预算上限（CNY）</span>
          <input
            type="number"
            min={0.01}
            step={0.01}
            aria-label="每日预算上限"
            value={budget.cloud_daily_estimated_cost_limit}
            onChange={(e) =>
              setBudget({
                ...budget,
                cloud_daily_estimated_cost_limit: Number(e.target.value),
              })
            }
          />
        </label>

        <div className="budget-summary-row" data-testid="budget-usage-summary">
          <div>
            <span className="muted">今日已使用</span>
            <strong>{usage.data?.estimated_cost ?? 0} CNY</strong>
          </div>
          <div>
            <span className="muted">剩余预算</span>
            <strong>{remaining} CNY</strong>
          </div>
        </div>

        <label className="settings-switch-row">
          <span>
            <b>每次收费测试需要确认</b>
            <small>真实连接测试前弹出二次确认</small>
          </span>
          <input
            type="checkbox"
            role="switch"
            className="settings-switch"
            checked={budget.cloud_confirm_each_paid_test}
            aria-label="每次收费测试需要确认"
            onChange={(e) =>
              setBudget({ ...budget, cloud_confirm_each_paid_test: e.target.checked })
            }
          />
        </label>

        <div className="privacy-note" data-testid="cloud-data-notice">
          <h3>云端数据发送说明</h3>
          <p>
            启用云端分析并确认后，所选章节正文会发送到你配置的云端模型服务以完成分析。
            传输诊断与页面加载不会发送小说正文，也不会消耗 Token。
          </p>
        </div>
      </div>

      {message && <p role="status">{message}</p>}
      <div className="settings-actions">
        <button type="button" className="primary" onClick={save} data-testid="budget-save">
          保存
        </button>
      </div>
    </article>
  );
}
