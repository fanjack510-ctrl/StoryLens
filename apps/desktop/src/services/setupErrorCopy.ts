/**
 * Central mapping for AI setup / budget / eligibility codes.
 * Ordinary UI shows Chinese labels + guidance; raw codes stay in tech details.
 */

export type SetupErrorInfo = {
  title: string;
  message: string;
  suggestion: string;
  code: string;
};

const MAP: Record<string, Omit<SetupErrorInfo, "code">> = {
  BUDGET_NOT_AVAILABLE: {
    title: "当前无法计算本次分析费用",
    message: "StoryLens 暂时无法计算本次分析费用，因此无法为任务预留预算。",
    suggestion: "检查模型映射和计价配置，或切换到已有计价信息的模型。",
  },
  MODEL_PRICING_NOT_FOUND: {
    title: "当前模型缺少计价信息",
    message: "StoryLens 暂时无法计算该模型的分析费用，因此无法为任务预留预算。",
    suggestion: "检查模型映射和计价配置，或切换到已有计价信息的模型。",
  },
  pricing_unavailable: {
    title: "当前模型缺少计价信息",
    message: "StoryLens 暂时无法计算该模型的分析费用，因此无法为任务预留预算。",
    suggestion: "检查模型映射和计价配置，或切换到已有计价信息的模型。",
  },
  INSUFFICIENT_BUDGET_RESERVATION: {
    title: "当前预算不足，无法开始分析",
    message: "当前预算不足以完成本次分析预留。",
    suggestion: "提高每日预算，或等待今日用量重置后再试。",
  },
  budget_unavailable: {
    title: "每日预算不足",
    message: "当前剩余预算不足以开始分析。",
    suggestion: "提高每日预算，或等待今日用量重置后再试。",
  },
  CREDENTIAL_MISSING: {
    title: "尚未保存 API Key",
    message: "还未保存可用于分析的 API Key。",
    suggestion: "填写 API Key 后点击“验证并保存”。",
  },
  credential_missing: {
    title: "尚未填写 API Key",
    message: "还未填写 API Key。",
    suggestion: "填写 API Key 后验证模型服务。",
  },
  CREDENTIAL_INVALID: {
    title: "API Key 无效或已失效",
    message: "模型服务拒绝了当前 API Key。",
    suggestion: "在模型服务商控制台核对 Key 后重新验证并保存。",
  },
  AUTHENTICATION_FAILED: {
    title: "API Key 无效或已失效",
    message: "模型服务拒绝了当前 API Key。",
    suggestion: "在模型服务商控制台核对 Key 后重新验证并保存。",
  },
  PROVIDER_AUTHENTICATION_FAILED: {
    title: "API Key 无效或已失效",
    message: "模型服务拒绝了当前 API Key。",
    suggestion: "在模型服务商控制台核对 Key 后重新验证并保存。",
  },
  MODEL_NOT_AVAILABLE: {
    title: "当前模型不可用",
    message: "模型服务无法使用当前所选模型。",
    suggestion: "切换分析模式或核对模型名称后重试。",
  },
  MODEL_NOT_FOUND: {
    title: "当前模型不可用",
    message: "模型服务无法使用当前所选模型。",
    suggestion: "切换分析模式或核对模型名称后重试。",
  },
  PROVIDER_MODEL_NOT_FOUND: {
    title: "当前模型不可用",
    message: "模型服务无法使用当前所选模型。",
    suggestion: "切换分析模式或核对模型名称后重试。",
  },
  CLOUD_DISABLED: {
    title: "云端模型服务尚未开启",
    message: "云端分析开关未开启，因此无法开始分析。",
    suggestion: "在 AI 服务设置中开启云端分析并保存。",
  },
  cloud_master_switch_off: {
    title: "云端模型服务尚未开启",
    message: "云端分析开关未开启，因此无法开始分析。",
    suggestion: "确认正文发送说明并保存配置。",
  },
  CLOUD_MASTER_SWITCH_OFF: {
    title: "云端模型服务尚未开启",
    message: "云端分析开关未开启，因此无法开始分析。",
    suggestion: "确认正文发送说明并保存配置。",
  },
  API_KEY_NOT_SAVED: {
    title: "API Key 尚未保存",
    message: "模型服务已验证，但配置还未保存。",
    suggestion: "点击“验证并保存”完成配置。",
  },
  SETUP_INCOMPLETE: {
    title: "分析配置尚未完成",
    message: "模型服务可用，但分析就绪检查未通过。",
    suggestion: "根据下方原因完成计价或预算配置。",
  },
};

export function mapSetupError(
  code: string | null | undefined,
  opts?: { model?: string },
): SetupErrorInfo {
  const key = code || "SETUP_INCOMPLETE";
  const mapped = MAP[key] || {
    title: "分析配置尚未完成",
    message: "当前无法开始分析。",
    suggestion: "请完成 AI 服务配置后重试。",
  };
  let message = mapped.message;
  if (opts?.model && /该模型|当前模型/.test(message)) {
    message = message.replace(/该模型|当前模型/, opts.model);
  }
  if (opts?.model && key === "MODEL_PRICING_NOT_FOUND") {
    message = `StoryLens 暂时无法计算 ${opts.model} 的分析费用，因此无法为任务预留预算。`;
  }
  return { ...mapped, message, code: key };
}

export function formatSetupErrorBlock(
  code: string | null | undefined,
  opts?: { model?: string },
): string {
  const info = mapSetupError(code, opts);
  return `${info.title}\n\n${info.message}\n\n处理方式：\n${info.suggestion}`;
}

export function nextBlockedReason(input: {
  hasApiKeyInput: boolean;
  credentialConfigured: boolean;
  modelValidated: boolean;
  persisted: boolean;
  analysisReady: boolean;
  cloudEnabled: boolean;
  blockers: string[];
}): string | null {
  if (input.analysisReady) return null;
  if (!input.hasApiKeyInput && !input.credentialConfigured) {
    return `还不能继续：${mapSetupError("credential_missing").title}`;
  }
  if (input.modelValidated && !input.persisted) {
    return `还不能继续：${mapSetupError("API_KEY_NOT_SAVED").title}`;
  }
  if (!input.cloudEnabled && input.persisted) {
    return `还不能继续：${mapSetupError("CLOUD_DISABLED").title}`;
  }
  const primary = input.blockers[0];
  if (primary) {
    return `还不能继续：${mapSetupError(primary).title}`;
  }
  if (!input.persisted) {
    return "还不能继续：请先验证并保存配置";
  }
  return "还不能继续：分析配置尚未完成";
}

/** Hide raw technical codes from primary UI strings. */
export function stripRawErrorCodes(text: string): string {
  return text
    .replace(/\bBUDGET_NOT_AVAILABLE\b/g, "当前无法计算本次分析费用")
    .replace(/\bINSUFFICIENT_BUDGET_RESERVATION\b/g, "当前预算不足，无法开始分析")
    .replace(/\bMODEL_PRICING_NOT_FOUND\b/g, "当前模型缺少计价信息")
    .replace(/\bCREDENTIAL_MISSING\b/g, "尚未保存 API Key")
    .replace(/\bCREDENTIAL_INVALID\b/g, "API Key 无效或已失效")
    .replace(/\bMODEL_NOT_AVAILABLE\b/g, "当前模型不可用")
    .replace(/\bCLOUD_DISABLED\b/g, "云端模型服务尚未开启")
    .replace(/\bCLOUD_MASTER_SWITCH_OFF\b/g, "云端模型服务尚未开启");
}
