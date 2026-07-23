/**
 * Backend-normalized Capability fixtures for Phase 1C Integration.
 * Generated from the same field contract as capability_api_payloads.py
 * (snake_case wire → camelCase via capabilityDto guards).
 */

import type { CapabilityDecisionDto, CapabilityMetadata } from "./types";

/** Mirrors DefaultCapabilityService list item for whole_book_analysis (shipped=false). */
export const BACKEND_WHOLE_BOOK_METADATA: CapabilityMetadata = {
  key: "whole_book_analysis",
  displayName: "整书分析",
  description: "全书结构化叙事分析流水线（Pro；未发货）。",
  shipped: false,
  requiresLicense: true,
  availability: "preview",
  previewVisible: true,
  supportedModes: ["whole_book_native", "whole_book_enhanced"],
  estimatedCostClass: "high",
  offlineAllowed: false,
};

export const BACKEND_WHOLE_BOOK_DECISION: CapabilityDecisionDto = {
  capabilityKey: "whole_book_analysis",
  allowed: false,
  reasonCode: "CAPABILITY_NOT_SHIPPED",
  availability: "preview",
  displayMessage: "该功能尚未发布",
  supportedModes: ["whole_book_native", "whole_book_enhanced"],
  previewOnly: true,
  offlineStatus: "n/a",
  licenseStatus: "n/a",
};

export const BACKEND_MODE_NOT_SUPPORTED_DECISION: CapabilityDecisionDto = {
  capabilityKey: "whole_book_analysis",
  allowed: false,
  reasonCode: "CAPABILITY_MODE_NOT_SUPPORTED",
  availability: "preview",
  displayMessage: "分析模式不受支持: chapter_only",
  supportedModes: ["whole_book_native", "whole_book_enhanced"],
};

export const BACKEND_UNKNOWN_KEY_ERROR = {
  error_code: "CAPABILITY_UNKNOWN",
  message: "Unknown capability key",
  details: {},
};

/** Wire-format list envelope matching build_capabilities_list_response. */
export const BACKEND_CAPABILITIES_LIST_WIRE = {
  items: [
    {
      key: "whole_book_analysis",
      label: "整书分析",
      description: "全书结构化叙事分析流水线（Pro；未发货）。",
      shipped: false,
      availability: "preview",
      requires_license: true,
      preview_visible: true,
      pro_gated: true,
      decision: {
        capability_key: "whole_book_analysis",
        allowed: false,
        reason_code: "CAPABILITY_NOT_SHIPPED",
        availability: "preview",
        display_message: "该功能尚未发布",
        message: "该功能尚未发布",
        supported_modes: ["whole_book_native", "whole_book_enhanced"],
        quota: null,
        usage: null,
        remaining: null,
        offline_status: "n/a",
        license_status: "n/a",
        evaluated_at: null,
        preview_only: true,
      },
      metadata: {
        key: "whole_book_analysis",
        display_name: "整书分析",
        label: "整书分析",
        description: "全书结构化叙事分析流水线（Pro；未发货）。",
        shipped: false,
        requires_license: true,
        availability: "preview",
        preview_visible: true,
        supported_modes: ["whole_book_native", "whole_book_enhanced"],
        quota_policy_key: "whole_book_analysis_default",
        estimated_cost_class: "high",
        offline_allowed: false,
        pro_gated: true,
        quota_policies: [],
      },
    },
    {
      key: "narrative_asset_library",
      label: "叙事资产库",
      description: "叙事实体/资产/关系存储基础层（免费基础；Pro 扩展未发货）。",
      shipped: false,
      availability: "unavailable",
      requires_license: false,
      preview_visible: false,
      pro_gated: false,
      decision: {
        capability_key: "narrative_asset_library",
        allowed: false,
        reason_code: "CAPABILITY_NOT_SHIPPED",
        availability: "unavailable",
        display_message: "该功能尚未发布",
        message: "该功能尚未发布",
        supported_modes: [],
        quota: null,
        usage: null,
        remaining: null,
        offline_status: "n/a",
        license_status: "n/a",
        evaluated_at: null,
        preview_only: false,
      },
      metadata: {
        key: "narrative_asset_library",
        display_name: "叙事资产库",
        label: "叙事资产库",
        description: "叙事实体/资产/关系存储基础层（免费基础；Pro 扩展未发货）。",
        shipped: false,
        requires_license: false,
        availability: "unavailable",
        preview_visible: false,
        supported_modes: [],
        estimated_cost_class: "free",
        offline_allowed: true,
        pro_gated: false,
        quota_policies: [],
      },
    },
  ],
  whole_book_runs_endpoint_disabled: true,
  run_creation_enabled: false,
};
