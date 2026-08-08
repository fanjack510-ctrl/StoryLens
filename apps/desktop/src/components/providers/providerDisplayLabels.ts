/**
 * User-facing Chinese labels for Provider UI.
 * Raw IDs / enums stay for API calls and diagnostics — not primary labels.
 */

import { serviceDisplayNameFor } from "../../services/aiServiceViewModel";

export function providerDisplayName(providerId: string, fallback?: string): string {
  return serviceDisplayNameFor(providerId, fallback);
}

const CREDENTIAL_LABELS: Record<string, string> = {
  configured: "凭据已配置",
  missing: "未配置凭据",
  unknown: "凭据状态未知",
  invalid: "凭据无效",
  expired: "凭据已过期",
};

const CLOUD_STATE_LABELS: Record<string, string> = {
  available: "云端可用",
  enabled: "云端已开启",
  disabled: "云端已关闭",
  blocked: "云端已阻止",
  unknown: "状态未知",
};

const HEALTH_LABELS: Record<string, string> = {
  healthy: "健康",
  unhealthy: "不健康",
  unknown: "未知",
  stale: "状态过期",
};

/** Primary list badge: 当前默认 / 已启用 / 已停用 / … (enabled ≠ active). */
export function providerListStatusLabel(
  p: {
    name?: string;
    enabled?: boolean;
    healthy?: boolean;
    running?: boolean;
    connected?: boolean;
    credential_state?: string;
    health_state?: string;
    capabilities?: { enabled?: boolean };
  },
  options?: { isDefault?: boolean },
): { label: string; tone: "success" | "warning" | "danger" | "neutral" } {
  const enabled = p.enabled ?? p.capabilities?.enabled;
  if (options?.isDefault && enabled) {
    return { label: "当前默认", tone: "success" };
  }
  if (!enabled) {
    return { label: "已停用", tone: "neutral" };
  }
  if (p.credential_state === "invalid") {
    return { label: "凭据无效", tone: "danger" };
  }
  // Enabled + configured path: never confuse connection failure with "not default".
  if (p.connected === false || p.health_state === "unhealthy") {
    return { label: "已启用 · 连接失败", tone: "warning" };
  }
  if (p.healthy || p.credential_state === "configured") {
    return { label: "已启用", tone: "success" };
  }
  if (p.running) {
    return { label: "已启用", tone: "warning" };
  }
  return { label: "已启用", tone: "success" };
}

export function credentialStateLabel(state?: string | null): string {
  if (!state) return CREDENTIAL_LABELS.unknown;
  return CREDENTIAL_LABELS[state] || state;
}

export function cloudStateLabel(state?: string | null): string {
  if (!state) return CLOUD_STATE_LABELS.disabled;
  return CLOUD_STATE_LABELS[state] || state;
}

export function healthStateLabel(state?: string | null, healthy?: boolean): string {
  if (state && HEALTH_LABELS[state]) return HEALTH_LABELS[state];
  if (healthy === true) return HEALTH_LABELS.healthy;
  if (healthy === false) return HEALTH_LABELS.unhealthy;
  return HEALTH_LABELS.unknown;
}

export function formatUnknown(value: unknown, suffix = ""): string {
  if (value == null || value === "") return "—";
  if (typeof value === "number" && Number.isNaN(value)) return "—";
  return suffix ? `${value}${suffix}` : String(value);
}
