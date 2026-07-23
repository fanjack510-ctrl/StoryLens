import type { CapabilityPresentationState } from "../../services/capability/presentation";
import { isProGatedCapability, type CapabilityKey } from "../../services/capability/types";
import "./capability.css";

const STATE_LABEL: Record<CapabilityPresentationState, string> = {
  available: "可用",
  preview: "预览",
  not_licensed: "未授权",
  not_shipped: "未发布",
  quota_exceeded: "额度已用完",
  license_expired: "授权过期",
  license_invalid: "授权无效",
  offline_unavailable: "离线不可用",
  mode_not_supported: "模式不支持",
  unknown: "状态未知",
};

export type CapabilityStatusBadgeProps = {
  capabilityKey: CapabilityKey;
  state: CapabilityPresentationState;
  /** Optional override label */
  label?: string;
};

export function CapabilityStatusBadge({
  capabilityKey,
  state,
  label,
}: CapabilityStatusBadgeProps) {
  const foundation = !isProGatedCapability(capabilityKey);
  const text =
    label ??
    (foundation && state === "not_shipped"
      ? "基础能力"
      : STATE_LABEL[state]);

  return (
    <span
      className="capability-badge capability-root"
      data-testid="capability-status-badge"
      data-capability={capabilityKey}
      data-state={state}
      data-foundation={foundation ? "true" : "false"}
      role="status"
      aria-label={`${capabilityKey}: ${text}`}
    >
      {text}
    </span>
  );
}
