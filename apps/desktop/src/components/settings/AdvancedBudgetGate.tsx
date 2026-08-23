import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { settingsApi } from "../../services/settingsApi";
import "./settings.css";

const ADVANCED_BUDGET_FIELDS = [
  ["cloud_max_input_tokens_per_request", "单请求最大输入 Token", 1],
  ["cloud_max_output_tokens_per_request", "单请求最大输出 Token", 1],
  ["cloud_max_requests_per_run", "单次分析最大请求数", 1],
  ["cloud_daily_request_limit", "每日最大请求数", 1],
  ["cloud_daily_token_limit", "每日最大 Token", 1],
] as const;

/** 逐项的用量闸门。
 *
 *  这一块原本住在「开发者设置」里。开发者模式整个删掉之后它需要一个新家——而它本来就该在
 *  「使用额度」：它设的是花多少钱、单次能发多大，跟诊断和路由预览不是一回事。
 *
 *  它也确实**不能删**：上面那些简单开关只管总额，单请求的 Token 上限只有这里能设。
 */
export function AdvancedBudgetGate() {
  const qc = useQueryClient();
  const [budget, setBudget] = useState<any>(null);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);

  const budgetQuery = useQuery({ queryKey: ["cloud-budget"], queryFn: settingsApi.cloudBudget });
  const pricing = useQuery({ queryKey: ["cloud-pricing"], queryFn: settingsApi.cloudPricing });

  useEffect(() => {
    if (budgetQuery.data) setBudget(budgetQuery.data);
  }, [budgetQuery.data]);

  const save = async () => {
    setMessage("");
    setFailed(false);
    if (
      !budget ||
      ADVANCED_BUDGET_FIELDS.some(
        ([key]) => !Number.isInteger(Number(budget[key])) || Number(budget[key]) <= 0,
      )
    ) {
      setFailed(true);
      setMessage("保存失败：Token、请求数必须为正整数。");
      return;
    }
    try {
      await settingsApi.saveCloudBudget({ ...budget, currency: "CNY" });
      setMessage("已保存。");
      await qc.invalidateQueries({ queryKey: ["cloud-budget"] });
    } catch (error) {
      setFailed(true);
      setMessage(`保存失败：${error instanceof Error ? error.message : "未知错误"}`);
    }
  };

  if (!budget) return null;

  return (
    <details className="advanced-section" data-testid="advanced-budget-gate">
      <summary>逐项用量上限</summary>
      <p className="hint">
        上面的开关管总额；这里管单次请求能发多大、每天最多发几次。改小可以更保守，但太小会让
        长书分析中途被拦下来。
      </p>
      {ADVANCED_BUDGET_FIELDS.map(([key, label, min]) => (
        <label key={key} className="settings-field">
          <span>{label}</span>
          <input
            type="number"
            min={min}
            step={1}
            aria-label={label}
            value={budget[key]}
            onChange={(e) => setBudget({ ...budget, [key]: Number(e.target.value) })}
          />
        </label>
      ))}
      <label className="settings-switch-row">
        <span>价格未知时停止</span>
        <input
          type="checkbox"
          role="switch"
          className="settings-switch"
          checked={budget.cloud_stop_on_unknown_pricing}
          aria-label="价格未知时停止"
          onChange={(e) => setBudget({ ...budget, cloud_stop_on_unknown_pricing: e.target.checked })}
        />
      </label>
      <p className="hint">价格版本：{pricing.data?.pricing_version || "无"}</p>
      {message && (
        <p role="status" className={failed ? "wbv2-error" : "hint"} data-testid="advanced-budget-message">
          {message}
        </p>
      )}
      <button type="button" className="primary" data-testid="advanced-budget-save" onClick={() => void save()}>
        保存用量上限
      </button>
    </details>
  );
}
