/** Sanitize and map technical errors to ordinary Chinese copy. */

const API_KEY_PATTERN = /sk-[a-zA-Z0-9]{8,}/g;

export function redactSecrets(text: string): string {
  return text.replace(API_KEY_PATTERN, "sk-****");
}

export function mapConnectionError(error: {
  code?: string;
  status?: number;
  message?: string;
}): string {
  const code = error.code || "";
  const msg = (error.message || "").toLowerCase();
  const status = error.status;

  if (status === 401 || status === 403 || /unauthorized|authentication_failed/i.test(code)) {
    return "API Key 无效，请检查后重新测试。";
  }
  if (/timeout|timed out|connect_timeout|provider_connect_timeout/i.test(code + msg)) {
    return "连接 AI 服务超时，请检查网络后重试。";
  }
  if (/connection refused|econnrefused|connect_error|network unreachable/i.test(code + msg)) {
    return "当前无法连接 AI 服务，请稍后重试。";
  }
  if (
    /budget|cost_limit|insufficient_budget|cloud_cost_limit|cloud_budget_exceeded/i.test(code)
  ) {
    return "已达到本月费用上限，可在设置中调整。";
  }
  if (/dns|provider_dns/i.test(code)) {
    return "无法连接 AI 服务，请检查网络或代理设置。";
  }
  const fallback = error.message ? redactSecrets(error.message) : "操作失败，请稍后重试。";
  return fallback;
}
