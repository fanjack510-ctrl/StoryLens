import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../apiClient";
import { CAPABILITY_KEYS } from "./keys";
import {
  PHASE1C_CONTRACT_ANALYSIS_MODES,
  PHASE1C_CONTRACT_CAPABILITY_KEYS,
} from "./contractKeys.fixture";
import {
  CapabilityDtoError,
  denyDecision,
  parseCapabilityDecision,
  parseCapabilityList,
} from "./capabilityDto";
import {
  capabilityClient,
  CapabilityClientError,
  offlineFallbackDecision,
} from "./capabilityClient";
import {
  clearCapabilityCache,
  getCapabilityAvailability,
  getCapabilityDecision,
  hasCapability,
  mergeDecisionSafely,
  useCapabilityStore,
} from "./capabilityStore";
import {
  getCapabilityPresentation,
  presentationStateFromDecision,
} from "./presentation";
import {
  isAnalysisModeKey,
  legacyVipBooleanIsNotAllowed,
  mapLegacyFeatureKeyStrict,
  resolveLegacyKey,
} from "./legacyCompatibility";
import { mapLegacyFeatureKey } from "./legacyMapper";
import { PRO_FEATURE_KEYS } from "../entitlementApi";

vi.mock("../apiClient", async () => {
  const actual = await vi.importActual<typeof import("../apiClient")>("../apiClient");
  return {
    ...actual,
    api: vi.fn(),
  };
});

import { api } from "../apiClient";

function decisionFixture(overrides: Record<string, unknown> = {}) {
  return {
    capability_key: "whole_book_analysis",
    allowed: false,
    reason_code: "CAPABILITY_NOT_SHIPPED",
    availability: "unavailable",
    message: "该功能尚未发布",
    preview_only: false,
    ...overrides,
  };
}

describe("Phase 1C capability frontend foundation", () => {
  beforeEach(() => {
    vi.mocked(api).mockReset();
    clearCapabilityCache();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    clearCapabilityCache();
  });

  describe("key consistency", () => {
    it("frontend CAPABILITY_KEYS match Phase 1C contract fixture and are unique", () => {
      expect([...CAPABILITY_KEYS]).toEqual([...PHASE1C_CONTRACT_CAPABILITY_KEYS]);
      expect([...PRO_FEATURE_KEYS]).toEqual([...PHASE1C_CONTRACT_CAPABILITY_KEYS]);
      expect(new Set(CAPABILITY_KEYS).size).toBe(CAPABILITY_KEYS.length);
    });
  });

  describe("DTO guard", () => {
    it("parses snake_case decision and list", () => {
      const decision = parseCapabilityDecision(decisionFixture({ allowed: true, reason_code: "CAPABILITY_AVAILABLE", availability: "available", message: "ok" }));
      expect(decision.allowed).toBe(true);
      expect(decision.capabilityKey).toBe("whole_book_analysis");
      expect(decision.reasonCode).toBe("CAPABILITY_AVAILABLE");

      const list = parseCapabilityList([
        {
          key: "story_lab",
          label: "故事实验台",
          description: "x",
          shipped: false,
          availability: "unavailable",
          requires_license: true,
        },
      ]);
      expect(list[0]?.displayName).toBe("故事实验台");
      expect(list[0]?.requiresLicense).toBe(true);
    });

    it("rejects unknown key in DTO", () => {
      expect(() =>
        parseCapabilityDecision(decisionFixture({ capability_key: "not_a_real_key" })),
      ).toThrow(CapabilityDtoError);
    });
  });

  describe("capabilityClient", () => {
    it("list() calls GET /api/v1/capabilities", async () => {
      vi.mocked(api).mockResolvedValue([
        {
          key: "advanced_export",
          display_name: "进阶导出",
          description: "d",
          shipped: false,
          requires_license: true,
          availability: "unavailable",
        },
      ]);
      const list = await capabilityClient.list();
      expect(api).toHaveBeenCalledWith("/api/v1/capabilities");
      expect(list[0]?.key).toBe("advanced_export");
    });

    it("get() returns backend decision without recomputing allowed", async () => {
      vi.mocked(api).mockResolvedValue(
        decisionFixture({
          allowed: true,
          reason_code: "CAPABILITY_AVAILABLE",
          availability: "available",
          message: "可用",
        }),
      );
      const decision = await capabilityClient.get("whole_book_analysis");
      expect(api).toHaveBeenCalledWith("/api/v1/capabilities/whole_book_analysis");
      expect(decision.allowed).toBe(true);
      expect(decision.reasonCode).toBe("CAPABILITY_AVAILABLE");
    });

    it("evaluate() forwards context as query and keeps backend allowed", async () => {
      vi.mocked(api).mockResolvedValue(
        decisionFixture({
          capability_key: "story_lab",
          allowed: false,
          reason_code: "CAPABILITY_NOT_LICENSED",
          availability: "unavailable",
          message: "当前授权不包含故事实验台",
        }),
      );
      const decision = await capabilityClient.evaluate("story_lab", { book_id: 12 });
      expect(api).toHaveBeenCalledWith("/api/v1/capabilities/story_lab?book_id=12");
      expect(decision.allowed).toBe(false);
    });

    it("rejects unknown key", async () => {
      await expect(capabilityClient.get("totally_unknown")).rejects.toBeInstanceOf(
        CapabilityClientError,
      );
      expect(api).not.toHaveBeenCalled();
    });

    it("network failure falls back to deny (never default allow)", async () => {
      vi.mocked(api).mockRejectedValue(new ApiError("HTTP_ERROR", "boom", 500));
      const decision = await capabilityClient.evaluate("cross_book_search");
      expect(decision.allowed).toBe(false);
      expect(decision.reasonCode).toBe("CAPABILITY_UNKNOWN");
    });

    it("offline does not default to authorized", async () => {
      vi.mocked(api).mockRejectedValue(
        new ApiError("BACKEND_OFFLINE", "无法连接本地分析服务", 0),
      );
      const decision = await capabilityClient.get("advanced_export");
      expect(decision.allowed).toBe(false);
      expect(decision.reasonCode).toBe("CAPABILITY_OFFLINE_NOT_ALLOWED");
      expect(decision.displayMessage).toContain("离线");
      expect(offlineFallbackDecision("advanced_export").allowed).toBe(false);
    });
  });

  describe("capabilityStore", () => {
    it("defaults hasCapability to false when unloaded", () => {
      expect(hasCapability("whole_book_analysis")).toBe(false);
      expect(getCapabilityDecision("whole_book_analysis")).toBeNull();
      expect(getCapabilityAvailability("story_lab")).toBe("unknown");
    });

    it("loadCapabilities stores backend decisions", async () => {
      vi.mocked(api).mockImplementation(async (path: string) => {
        if (path === "/api/v1/capabilities") {
          return [
            {
              key: "narrative_asset_library",
              display_name: "叙事资产库",
              description: "foundation",
              shipped: false,
              requires_license: false,
              availability: "unavailable",
            },
            {
              key: "whole_book_analysis",
              display_name: "整书分析",
              description: "pro",
              shipped: false,
              requires_license: true,
              availability: "unavailable",
            },
          ];
        }
        if (path.includes("narrative_asset_library")) {
          return decisionFixture({
            capability_key: "narrative_asset_library",
            allowed: false,
            reason_code: "CAPABILITY_NOT_SHIPPED",
            message: "该功能尚未发布",
          });
        }
        return decisionFixture({
          capability_key: "whole_book_analysis",
          allowed: false,
          reason_code: "CAPABILITY_NOT_SHIPPED",
          message: "该功能尚未发布",
        });
      });

      await useCapabilityStore.getState().loadCapabilities();
      expect(hasCapability("whole_book_analysis")).toBe(false);
      expect(getCapabilityDecision("narrative_asset_library")?.reasonCode).toBe(
        "CAPABILITY_NOT_SHIPPED",
      );
      expect(useCapabilityStore.getState().metadata.whole_book_analysis?.displayName).toBe(
        "整书分析",
      );
    });

    it("refreshCapability updates a single key from backend", async () => {
      vi.mocked(api).mockResolvedValue(
        decisionFixture({
          capability_key: "story_lab",
          allowed: true,
          reason_code: "CAPABILITY_AVAILABLE",
          availability: "available",
          message: "可以使用该功能",
          evaluated_at: new Date().toISOString(),
        }),
      );
      const result = await useCapabilityStore.getState().refreshCapability("story_lab");
      expect(result?.allowed).toBe(true);
      expect(hasCapability("story_lab")).toBe(true);
    });

    it("clearCapabilityCache resets to default deny", async () => {
      useCapabilityStore.setState({
        decisions: {
          story_lab: denyDecision("story_lab", "CAPABILITY_AVAILABLE", "x", "available"),
        },
      });
      // Force an allowed decision into cache then clear.
      useCapabilityStore.setState({
        decisions: {
          story_lab: {
            capabilityKey: "story_lab",
            allowed: true,
            reasonCode: "CAPABILITY_AVAILABLE",
            availability: "available",
            displayMessage: "ok",
          },
        },
      });
      expect(hasCapability("story_lab")).toBe(true);
      clearCapabilityCache();
      expect(hasCapability("story_lab")).toBe(false);
    });

    it("onLicenseChanged clears cache then reloads", async () => {
      useCapabilityStore.setState({
        decisions: {
          story_lab: {
            capabilityKey: "story_lab",
            allowed: true,
            reasonCode: "CAPABILITY_AVAILABLE",
            availability: "available",
          },
        },
        licenseEpoch: 0,
      });
      vi.mocked(api).mockResolvedValue([]);
      await useCapabilityStore.getState().onLicenseChanged();
      expect(useCapabilityStore.getState().licenseEpoch).toBe(1);
      expect(hasCapability("story_lab")).toBe(false);
    });

    it("failed refresh does not promote previous deny to allow", () => {
      const previous = denyDecision("story_lab", "CAPABILITY_NOT_LICENSED", "no");
      const incoming = {
        capabilityKey: "story_lab" as const,
        allowed: true,
        reasonCode: "CAPABILITY_AVAILABLE" as const,
        availability: "available" as const,
      };
      expect(mergeDecisionSafely(previous, incoming, { fromFailure: true }).allowed).toBe(
        false,
      );
      expect(mergeDecisionSafely(previous, incoming).allowed).toBe(true);
    });
  });

  describe("legacy mapper", () => {
    it("maps legacy VIP keys to canonical capabilities", () => {
      expect(mapLegacyFeatureKey("batch_analysis")).toBe("whole_book_analysis");
      expect(mapLegacyFeatureKey("inspiration_center")).toBe("story_lab");
      expect(mapLegacyFeatureKey("novel_comparison")).toBe("cross_book_search");
      expect(mapLegacyFeatureKey("advanced_report")).toBe("advanced_export");
      expect(mapLegacyFeatureKeyStrict("character_arc")).toBe("whole_book_analysis");
    });

    it("unknown legacy key does not silently map", () => {
      expect(mapLegacyFeatureKey("scene_analysis")).toBeNull();
      expect(resolveLegacyKey("scene_analysis").kind).toBe("unmapped");
      expect(() => mapLegacyFeatureKeyStrict("scene_analysis")).toThrow(/Unknown legacy/);
    });

    it("whole_book_native/enhanced are analysis modes, not features", () => {
      expect(isAnalysisModeKey("whole_book_native")).toBe(true);
      expect(PHASE1C_CONTRACT_ANALYSIS_MODES).toContain("whole_book_enhanced");
      const resolved = resolveLegacyKey("whole_book_enhanced");
      expect(resolved.kind).toBe("analysis_mode");
      if (resolved.kind === "analysis_mode") {
        expect(resolved.parentCapability).toBe("whole_book_analysis");
        expect(resolved.mode).toBe("whole_book_enhanced");
      }
      expect(() => mapLegacyFeatureKeyStrict("whole_book_native")).toThrow(/analysis mode/);
    });

    it("legacy VIP boolean never becomes allowed", () => {
      expect(legacyVipBooleanIsNotAllowed(true)).toBe(false);
      expect(legacyVipBooleanIsNotAllowed(false)).toBe(false);
    });
  });

  describe("presentation", () => {
    it("available", () => {
      const p = getCapabilityPresentation("story_lab", {
        capabilityKey: "story_lab",
        allowed: true,
        reasonCode: "CAPABILITY_AVAILABLE",
        availability: "available",
        displayMessage: "可以使用该功能",
      });
      expect(p.state).toBe("available");
      expect(p.disabled).toBe(false);
      expect(p.showUpgradeAction).toBe(false);
    });

    it("preview", () => {
      const p = getCapabilityPresentation("story_lab", {
        capabilityKey: "story_lab",
        allowed: true,
        reasonCode: "CAPABILITY_PREVIEW_ONLY",
        availability: "preview",
        previewOnly: true,
        displayMessage: "当前为预览状态，完整能力尚未开放",
      });
      expect(p.state).toBe("preview");
      expect(p.showPreviewAction).toBe(true);
      expect(presentationStateFromDecision({
        capabilityKey: "story_lab",
        allowed: true,
        reasonCode: "CAPABILITY_PREVIEW_ONLY",
        availability: "preview",
      })).toBe("preview");
    });

    it("not licensed", () => {
      const p = getCapabilityPresentation("whole_book_analysis", {
        capabilityKey: "whole_book_analysis",
        allowed: false,
        reasonCode: "CAPABILITY_NOT_LICENSED",
        availability: "unavailable",
      });
      expect(p.state).toBe("not_licensed");
      expect(p.message).toContain("整书分析");
      expect(p.showUpgradeAction).toBe(true);
      expect(p.disabled).toBe(true);
    });

    it("not shipped", () => {
      const p = getCapabilityPresentation("cross_book_search", {
        capabilityKey: "cross_book_search",
        allowed: false,
        reasonCode: "CAPABILITY_NOT_SHIPPED",
        availability: "unavailable",
      });
      expect(p.state).toBe("not_shipped");
      expect(p.message).toContain("尚未发布");
    });

    it("quota exceeded", () => {
      const p = getCapabilityPresentation("whole_book_analysis", {
        capabilityKey: "whole_book_analysis",
        allowed: false,
        reasonCode: "CAPABILITY_QUOTA_EXCEEDED",
        availability: "unavailable",
      });
      expect(p.state).toBe("quota_exceeded");
      expect(p.message).toContain("额度");
    });

    it("license expired", () => {
      const p = getCapabilityPresentation("advanced_export", {
        capabilityKey: "advanced_export",
        allowed: false,
        reasonCode: "CAPABILITY_LICENSE_EXPIRED",
        availability: "unavailable",
      });
      expect(p.state).toBe("license_expired");
      expect(p.message).toContain("过期");
    });

    it("offline unavailable", () => {
      const p = getCapabilityPresentation("story_lab", {
        capabilityKey: "story_lab",
        allowed: false,
        reasonCode: "CAPABILITY_OFFLINE_NOT_ALLOWED",
        availability: "unavailable",
      });
      expect(p.state).toBe("offline_unavailable");
      expect(p.message).toContain("离线");
    });

    it("narrative_asset_library is not paywall-locked in presentation", () => {
      const p = getCapabilityPresentation("narrative_asset_library", null, null);
      expect(p.showUpgradeAction).toBe(false);
      expect(p.message).toMatch(/基础/);
    });

    it("mode not supported has dedicated presentation state", () => {
      const p = getCapabilityPresentation("whole_book_analysis", {
        capabilityKey: "whole_book_analysis",
        allowed: false,
        reasonCode: "CAPABILITY_MODE_NOT_SUPPORTED",
        availability: "preview",
        displayMessage: "分析模式不受支持: chapter_only",
        supportedModes: ["whole_book_native", "whole_book_enhanced"],
      });
      expect(p.state).toBe("mode_not_supported");
      expect(p.disabled).toBe(true);
      expect(p.message).toContain("不受支持");
    });

    it("preview_visible not shipped is visible but not startable", () => {
      const p = getCapabilityPresentation(
        "whole_book_analysis",
        {
          capabilityKey: "whole_book_analysis",
          allowed: false,
          reasonCode: "CAPABILITY_NOT_SHIPPED",
          availability: "preview",
          previewOnly: true,
          displayMessage: "该功能尚未发布",
        },
        {
          key: "whole_book_analysis",
          displayName: "整书分析",
          description: "…",
          shipped: false,
          requiresLicense: true,
          availability: "preview",
          previewVisible: true,
          supportedModes: ["whole_book_native", "whole_book_enhanced"],
        },
      );
      expect(p.state).toBe("not_shipped");
      expect(p.disabled).toBe(true);
      expect(p.showPreviewAction).toBe(true);
      expect(p.message).toMatch(/尚未发布|预览/);
    });
  });

  describe("backend payload fixtures", () => {
    it("parses real backend list envelope", async () => {
      const { BACKEND_CAPABILITIES_LIST_WIRE } = await import("./backendPayload.fixture");
      const list = parseCapabilityList(BACKEND_CAPABILITIES_LIST_WIRE);
      const whole = list.find((m) => m.key === "whole_book_analysis");
      expect(whole?.previewVisible).toBe(true);
      expect(whole?.shipped).toBe(false);
      expect(whole?.availability).toBe("preview");
    });

    it("parses backend decision allowed=false as-is", async () => {
      const { BACKEND_WHOLE_BOOK_DECISION } = await import("./backendPayload.fixture");
      expect(BACKEND_WHOLE_BOOK_DECISION.allowed).toBe(false);
      expect(presentationStateFromDecision(BACKEND_WHOLE_BOOK_DECISION)).toBe("not_shipped");
    });

    it("parses mode-not-supported decision", async () => {
      const { BACKEND_MODE_NOT_SUPPORTED_DECISION } = await import(
        "./backendPayload.fixture"
      );
      const parsed = parseCapabilityDecision(BACKEND_MODE_NOT_SUPPORTED_DECISION);
      expect(parsed.reasonCode).toBe("CAPABILITY_MODE_NOT_SUPPORTED");
      expect(presentationStateFromDecision(parsed)).toBe("mode_not_supported");
    });
  });
});
