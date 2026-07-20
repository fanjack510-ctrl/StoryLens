/**
 * Front-end view model for AI service UX.
 * Maps internal provider/readiness codes to user-facing copy.
 * Does not alter backend budget or provider semantics.
 */

export const DEFAULT_AI_SERVICE_ID = "aliyun_qwen_plus";
export const DEFAULT_AI_SERVICE_DISPLAY_NAME = "阿里云百炼 · Qwen";
export const DEFAULT_AI_MODEL = "qwen3.7-plus";

export type AiUserStatusCode =
  | "provider_not_configured"
  | "credential_missing"
  | "provider_disabled"
  | "provider_disconnected"
  | "dns_failed"
  | "auth_failed"
  | "healthy"
  | "awaiting_provider_recovery"
  | "unknown";

export type AiServiceViewModel = {
  providerId: string;
  serviceDisplayName: string;
  modelDisplayName: string;
  userStatusCode: AiUserStatusCode;
  userStatusLabel: string;
  connected: boolean;
  canStartAnalysis: boolean;
  apiKeyConfigured: boolean;
  cloudEnabled: boolean;
  /** Raw / engineering fields — only for diagnostic details */
  diagnostics: {
    providerId: string;
    healthState: string | null;
    healthSource: string | null;
    status: string | null;
    blockers: string[];
    rawCodes: string[];
  };
};

const USER_STATUS_LABELS: Record<AiUserStatusCode, string> = {
  provider_not_configured: "尚未配置AI服务",
  credential_missing: "尚未填写API Key",
  provider_disabled: "云端AI尚未开启",
  provider_disconnected: "尚未连接AI服务",
  dns_failed: "无法连接云端服务，请检查网络或代理设置",
  auth_failed: "API Key 无效，请检查后重新测试。",
  healthy: "已连接，可以开始分析",
  awaiting_provider_recovery: "云端服务暂时波动，系统正在自动恢复",
  unknown: "AI服务状态未知",
};

/** Internal codes that must never appear as primary UI labels. */
export const HIDDEN_PRIMARY_STATUS_CODES = [
  "unhealthy",
  "configured_readiness",
  "provider_disabled",
  "provider_not_configured",
  "provider_disconnected",
] as const;

const SERVICE_DISPLAY_NAMES: Record<string, string> = {
  aliyun_qwen_plus: "阿里云百炼",
  aliyun_qwen_max: "阿里云百炼 Max",
  aliyun_qwen_flash: "阿里云百炼 Flash",
};

export function serviceDisplayNameFor(providerId: string, fallback?: string): string {
  return SERVICE_DISPLAY_NAMES[providerId] || fallback || "AI服务";
}

export function mapUserStatusLabel(code: AiUserStatusCode): string {
  return USER_STATUS_LABELS[code];
}

function hasBlocker(blockers: string[], ...needles: string[]): boolean {
  const lower = blockers.map((b) => b.toLowerCase());
  return needles.some((n) => lower.some((b) => b.includes(n.toLowerCase())));
}

function detectAuthFailure(raw: string[]): boolean {
  return raw.some((c) =>
    /401|403|AUTHENTICATION_FAILED|PROVIDER_AUTHENTICATION_FAILED|auth_failed/i.test(c),
  );
}

function detectDnsFailure(raw: string[]): boolean {
  return raw.some((c) => /DNS|PROVIDER_DNS_ERROR|dns failed/i.test(c));
}

function detectRecovery(raw: string[]): boolean {
  return raw.some((c) =>
    /awaiting_provider_recovery|provider_recovery|PROVIDER_UNHEALTHY|PROVIDER_HEALTH_STALE/i.test(c),
  );
}

export type BuildAiServiceInput = {
  provider?: {
    name?: string;
    default_model?: string;
    configured?: boolean;
    connected?: boolean;
    healthy?: boolean;
    enabled?: boolean;
    status?: string;
    health_state?: string;
    health_source?: string;
    manual_selection_blockers?: string[];
    capabilities?: { enabled?: boolean; cloud?: boolean };
  } | null;
  configuration?: {
    display_name?: string;
    plus_model?: string;
    credential_state?: string;
    enabled?: boolean;
    disconnected?: boolean;
    connection_state?: string;
  } | null;
  cloudEnabled?: boolean;
  transportErrorCode?: string | null;
  connectionErrorCode?: string | null;
  httpStatus?: number | null;
};

/**
 * Connection status from ProviderConfiguration (backend) preferred over the
 * providers list snapshot, so AI服务 and 开始分析 share one durable source.
 */
export function resolveProviderConnected(input: {
  provider?: { connected?: boolean } | null;
  configuration?: {
    disconnected?: boolean;
    connection_state?: string;
    credential_state?: string;
  } | null;
}): boolean {
  const cfg = input.configuration;
  if (cfg) {
    if (cfg.connection_state === "connected") return true;
    if (cfg.connection_state === "disconnected" || cfg.disconnected === true) {
      return false;
    }
    if (cfg.disconnected === false && cfg.credential_state === "configured") {
      return true;
    }
  }
  return Boolean(input.provider?.connected);
}

export function buildAiServiceViewModel(input: BuildAiServiceInput): AiServiceViewModel {
  const providerId = input.provider?.name || DEFAULT_AI_SERVICE_ID;
  const serviceDisplayName =
    input.configuration?.display_name ||
    serviceDisplayNameFor(providerId, DEFAULT_AI_SERVICE_DISPLAY_NAME);
  const modelDisplayName =
    input.configuration?.plus_model ||
    input.provider?.default_model ||
    DEFAULT_AI_MODEL;

  const blockers = [...(input.provider?.manual_selection_blockers || [])];
  const connected = resolveProviderConnected(input);
  // Once backend reports connected, ignore stale list blockers for disconnect.
  const effectiveBlockers = connected
    ? blockers.filter((b) => !/provider_disconnected/i.test(b))
    : blockers;
  const rawCodes = [
    ...effectiveBlockers,
    input.provider?.status,
    input.provider?.health_state,
    input.provider?.health_source,
    input.configuration?.connection_state,
    input.transportErrorCode,
    input.connectionErrorCode,
    input.httpStatus != null ? String(input.httpStatus) : null,
  ].filter(Boolean) as string[];

  const cloudEnabled = Boolean(input.cloudEnabled);
  const providerEnabled =
    input.provider?.enabled ??
    input.provider?.capabilities?.enabled ??
    input.configuration?.enabled ??
    false;
  const configured = Boolean(input.provider?.configured);
  const apiKeyConfigured =
    input.configuration?.credential_state === "configured" ||
    (configured && !hasBlocker(effectiveBlockers, "credential_missing"));
  // Transport-verified / configuration-ready connection counts as healthy for UX
  // when list health lags behind a successful zero-token connectivity check.
  const healthy =
    Boolean(input.provider?.healthy) ||
    input.provider?.health_state === "healthy" ||
    (connected &&
      apiKeyConfigured &&
      providerEnabled &&
      cloudEnabled &&
      !detectAuthFailure(rawCodes) &&
      !detectDnsFailure(rawCodes));

  let userStatusCode: AiUserStatusCode = "unknown";

  if (detectDnsFailure(rawCodes)) {
    userStatusCode = "dns_failed";
  } else if (detectAuthFailure(rawCodes) || input.httpStatus === 401 || input.httpStatus === 403) {
    userStatusCode = "auth_failed";
  } else if (!connected && detectRecovery(rawCodes)) {
    userStatusCode = "awaiting_provider_recovery";
  } else if (!configured && !apiKeyConfigured) {
    userStatusCode = "provider_not_configured";
  } else if (!apiKeyConfigured || hasBlocker(effectiveBlockers, "credential_missing")) {
    userStatusCode = "credential_missing";
  } else if (!cloudEnabled || !providerEnabled || hasBlocker(effectiveBlockers, "provider_disabled", "cloud_master")) {
    userStatusCode = "provider_disabled";
  } else if (!connected || hasBlocker(effectiveBlockers, "provider_disconnected")) {
    userStatusCode = "provider_disconnected";
  } else if (connected && healthy && cloudEnabled && providerEnabled) {
    userStatusCode = "healthy";
  } else if (connected && !healthy) {
    userStatusCode = "awaiting_provider_recovery";
  } else {
    userStatusCode = "provider_disconnected";
  }

  const canStartAnalysis = userStatusCode === "healthy";

  return {
    providerId,
    serviceDisplayName,
    modelDisplayName,
    userStatusCode,
    userStatusLabel: mapUserStatusLabel(userStatusCode),
    connected: canStartAnalysis,
    canStartAnalysis,
    apiKeyConfigured,
    cloudEnabled,
    diagnostics: {
      providerId,
      healthState: input.provider?.health_state ?? null,
      healthSource: input.provider?.health_source ?? null,
      status: input.provider?.status ?? null,
      blockers: effectiveBlockers,
      rawCodes,
    },
  };
}

export function mapTransportOrHttpError(error: {
  code?: string;
  status?: number;
  message?: string;
}): { userLabel: string; rawCode: string } {
  const code = error.code || "";
  const status = error.status;
  if (/DNS|PROVIDER_DNS_ERROR/i.test(code) || /dns failed/i.test(error.message || "")) {
    return { userLabel: mapUserStatusLabel("dns_failed"), rawCode: code || "DNS failed" };
  }
  if (status === 401 || status === 403 || /AUTHENTICATION_FAILED/i.test(code)) {
    return { userLabel: mapUserStatusLabel("auth_failed"), rawCode: code || String(status) };
  }
  if (/CREDENTIAL_MISSING/i.test(code)) {
    return { userLabel: mapUserStatusLabel("credential_missing"), rawCode: code };
  }
  if (/PROVIDER_DISABLED|CLOUD_MASTER/i.test(code)) {
    return { userLabel: mapUserStatusLabel("provider_disabled"), rawCode: code };
  }
  if (/PROVIDER_NOT_CONNECTED|PROVIDER_DISCONNECTED/i.test(code)) {
    return { userLabel: mapUserStatusLabel("provider_disconnected"), rawCode: code };
  }
  if (/PROVIDER_NOT_CONFIGURED/i.test(code)) {
    return { userLabel: mapUserStatusLabel("provider_not_configured"), rawCode: code };
  }
  return {
    userLabel: error.message || "连接失败，请稍后重试",
    rawCode: code || "UNKNOWN",
  };
}
