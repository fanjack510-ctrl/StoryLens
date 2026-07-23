/**
 * Capability presentation helpers — clear copy, no vague “VIP不足”.
 */

import { PRO_CAPABILITY_LABELS } from "../productEdition";
import { isCapabilityKey, type CapabilityKey } from "./keys";
import {
  isProGatedCapability,
  type CapabilityDecisionDto,
  type CapabilityMetadata,
  type WholeBookAnalysisMode,
} from "./types";

export type CapabilityPresentationState =
  | "available"
  | "preview"
  | "not_licensed"
  | "not_shipped"
  | "quota_exceeded"
  | "license_expired"
  | "license_invalid"
  | "offline_unavailable"
  | "mode_not_supported"
  | "unknown";

export type CapabilityPresentation = {
  capabilityKey: CapabilityKey;
  state: CapabilityPresentationState;
  label: string;
  message: string;
  disabled: boolean;
  showUpgradeAction: boolean;
  showPreviewAction: boolean;
  supportedModes: WholeBookAnalysisMode[];
};

const DEFAULT_MESSAGES: Record<CapabilityPresentationState, string> = {
  available: "可以使用该功能",
  preview: "当前为预览状态，完整能力尚未开放",
  not_licensed: "当前授权不包含该功能",
  not_shipped: "该功能尚未发布",
  quota_exceeded: "本次使用额度已用完",
  license_expired: "授权已过期，请续期后再使用",
  license_invalid: "授权无效，请重新激活后再试",
  offline_unavailable: "离线状态下无法验证授权",
  mode_not_supported: "当前分析模式不受支持",
  unknown: "暂时无法确认该功能的授权状态",
};

function labelFor(key: CapabilityKey): string {
  return PRO_CAPABILITY_LABELS[key] || key;
}

function notLicensedMessage(key: CapabilityKey): string {
  switch (key) {
    case "whole_book_analysis":
      return "当前授权不包含整书分析";
    case "story_lab":
      return "当前授权不包含故事实验台";
    case "cross_book_search":
      return "当前授权不包含跨书检索";
    case "advanced_export":
      return "当前授权不包含进阶导出";
    case "narrative_asset_library":
      return "叙事资产库为基础能力，无需专业版锁定";
    default:
      return "当前授权不包含该功能";
  }
}

export function presentationStateFromDecision(
  decision: CapabilityDecisionDto,
): CapabilityPresentationState {
  switch (decision.reasonCode) {
    case "CAPABILITY_AVAILABLE":
      return "available";
    case "CAPABILITY_PREVIEW_ONLY":
      return "preview";
    case "CAPABILITY_NOT_SHIPPED":
      return "not_shipped";
    case "CAPABILITY_NOT_LICENSED":
      return "not_licensed";
    case "CAPABILITY_QUOTA_EXCEEDED":
      return "quota_exceeded";
    case "CAPABILITY_LICENSE_EXPIRED":
      return "license_expired";
    case "CAPABILITY_LICENSE_INVALID":
      return "license_invalid";
    case "CAPABILITY_OFFLINE_NOT_ALLOWED":
      return "offline_unavailable";
    case "CAPABILITY_MODE_NOT_SUPPORTED":
      return "mode_not_supported";
    case "CAPABILITY_UNKNOWN":
    default:
      if (decision.availability === "preview" || decision.previewOnly) return "preview";
      if (decision.allowed) return "available";
      return "unknown";
  }
}

export function getCapabilityPresentation(
  key: CapabilityKey | string,
  decision?: CapabilityDecisionDto | null,
  metadata?: CapabilityMetadata | null,
): CapabilityPresentation {
  if (!isCapabilityKey(key)) {
    return {
      capabilityKey: "whole_book_analysis",
      state: "unknown",
      label: String(key),
      message: "未知能力键，不允许使用",
      disabled: true,
      showUpgradeAction: false,
      showPreviewAction: false,
      supportedModes: [],
    };
  }

  const label = metadata?.displayName || labelFor(key);
  const supportedModes =
    decision?.supportedModes ?? metadata?.supportedModes ?? [];

  if (!decision) {
    // Foundation storage must not look “locked for paywall”.
    if (!isProGatedCapability(key)) {
      return {
        capabilityKey: key,
        state: "not_shipped",
        label,
        message: "叙事资产库为基础存储能力，不作为专业版锁定项展示",
        disabled: true,
        showUpgradeAction: false,
        showPreviewAction: false,
        supportedModes,
      };
    }
    return {
      capabilityKey: key,
      state: "unknown",
      label,
      message: DEFAULT_MESSAGES.unknown,
      disabled: true,
      showUpgradeAction: false,
      showPreviewAction: false,
      supportedModes,
    };
  }

  const state = presentationStateFromDecision(decision);
  const backendMessage = (decision.displayMessage || decision.message || "").trim();

  let message = backendMessage;
  if (!message) {
    message =
      state === "not_licensed" ? notLicensedMessage(key) : DEFAULT_MESSAGES[state];
  }

  // Public foundation: never push upgrade CTA.
  const foundation = !isProGatedCapability(key);
  const showUpgradeAction =
    !foundation &&
    (state === "not_licensed" ||
      state === "license_expired" ||
      state === "license_invalid");
  // preview_visible=true shows preview affordance even when not_shipped / not startable.
  const previewVisible = metadata?.previewVisible === true;
  const showPreviewAction =
    !foundation &&
    (state === "preview" ||
      decision.availability === "preview" ||
      (previewVisible && (state === "not_shipped" || decision.previewOnly === true)));

  // Never startable unless backend Decision.allowed === true.
  const disabled = decision.allowed !== true;

  return {
    capabilityKey: key,
    state,
    label,
    message,
    disabled: foundation && state === "not_shipped" ? true : disabled,
    showUpgradeAction,
    showPreviewAction,
    supportedModes: [...supportedModes],
  };
}
