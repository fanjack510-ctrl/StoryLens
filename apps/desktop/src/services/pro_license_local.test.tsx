import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LicenseSettingsCard } from "../components/settings/LicenseSettingsCard";
import {
  canUseFeature,
  entitlementApi,
  maskLicenseCode,
  type EntitlementSnapshot,
} from "./entitlementApi";
import * as openExternal from "./openExternalUrl";
import { ApiError } from "./apiClient";

function freeSnapshot(): EntitlementSnapshot {
  return {
    edition: "free",
    edition_label: "StoryLens 免费版",
    license_id: null,
    license_id_masked: null,
    major_version: null,
    activated_at: null,
    features: {
      whole_book_analysis: false,
      narrative_asset_library: false,
      story_lab: false,
      cross_book_search: false,
      advanced_export: false,
    },
    pro_active: false,
    commerce: {
      afdian_product_url: "https://afdian.com/item/demo",
      product_code: "storylens_pro",
      product_label: "StoryLens Pro",
    },
    license_trust_mode: "development",
    license_issuance_ready: true,
    license_issuance_message: null,
  };
}

let current: EntitlementSnapshot = freeSnapshot();

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("StoryLens Pro entitlement UI", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    current = freeSnapshot();
    vi.spyOn(entitlementApi, "snapshot").mockImplementation(async () => current);
    vi.spyOn(entitlementApi, "feature").mockImplementation(async (featureKey: string) => ({
      enabled: Boolean(current.pro_active),
      reason: current.pro_active ? null : "PRO_LICENSE_REQUIRED",
      source: current.pro_active ? "signed_local_license" : "none",
      edition: current.edition,
      license_id: current.license_id,
      major_version: current.major_version,
      feature_key: featureKey,
    }));
    vi.spyOn(entitlementApi, "activate").mockReset();
    vi.spyOn(openExternal, "openExternalUrl").mockResolvedValue({ ok: true });
  });

  it("shows free edition and purchase actions", async () => {
    wrap(<LicenseSettingsCard />);
    await waitFor(() => {
      expect(screen.getByTestId("license-edition-label")).toHaveTextContent("免费版");
    });
    expect(screen.getByTestId("license-buy-pro")).toBeInTheDocument();
    expect(screen.getByTestId("license-open-activate")).toBeInTheDocument();
  });

  it("opens activate dialog and masks long codes by default", async () => {
    wrap(<LicenseSettingsCard />);
    await waitFor(() => screen.getByTestId("license-open-activate"));
    fireEvent.click(screen.getByTestId("license-open-activate"));
    const long =
      "SLP1-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.sigpart";
    fireEvent.change(screen.getByTestId("license-code-input"), { target: { value: long } });
    expect(screen.getByText(maskLicenseCode(long))).toBeInTheDocument();
    expect(screen.getByTestId("license-toggle-code-preview")).toHaveTextContent("显示完整授权码");
    fireEvent.click(screen.getByTestId("license-toggle-code-preview"));
    expect(screen.getByTestId("license-toggle-code-preview")).toHaveTextContent("隐藏授权码");
  });

  it("shows loading then success after activate", async () => {
    vi.spyOn(entitlementApi, "activate").mockImplementation(async () => {
      await new Promise((r) => setTimeout(r, 20));
      current = {
        ...current,
        edition: "pro",
        edition_label: "StoryLens Pro",
        pro_active: true,
        license_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        license_id_masked: "aaaaaaaa…eeee",
        major_version: 1,
        activated_at: "2026-07-22T00:00:00+00:00",
      };
      return {
        ok: true,
        user_message: "StoryLens Pro 已激活",
        entitlement: current,
      };
    });
    wrap(<LicenseSettingsCard />);
    await waitFor(() => screen.getByTestId("license-open-activate"));
    fireEvent.click(screen.getByTestId("license-open-activate"));
    fireEvent.change(screen.getByTestId("license-code-input"), {
      target: { value: "SLP1-demo.sig" },
    });
    fireEvent.click(screen.getByTestId("license-activate-submit"));
    expect(screen.getByTestId("license-activate-submit")).toHaveTextContent("正在激活");
    await waitFor(() => {
      expect(screen.getByTestId("license-pro-active")).toBeInTheDocument();
    });
    expect(screen.getByTestId("license-pro-status-heading")).toHaveTextContent("专业版已激活");
    expect(screen.queryByText("StoryLens Pro 已激活")).not.toBeInTheDocument();
    expect(screen.getAllByTestId("capability-pending").length).toBeGreaterThan(0);
  });

  it("maps activation failure codes", async () => {
    vi.spyOn(entitlementApi, "activate").mockRejectedValue(
      new ApiError("LICENSE_SIGNATURE_INVALID", "授权签名无效。", 400),
    );
    wrap(<LicenseSettingsCard />);
    await waitFor(() => screen.getByTestId("license-open-activate"));
    fireEvent.click(screen.getByTestId("license-open-activate"));
    fireEvent.change(screen.getByTestId("license-code-input"), {
      target: { value: "SLP1-bad.sig" },
    });
    fireEvent.click(screen.getByTestId("license-activate-submit"));
    await waitFor(() => {
      expect(screen.getByTestId("license-activate-error-code")).toHaveTextContent(
        "LICENSE_SIGNATURE_INVALID",
      );
    });
  });

  it("maps runtime-rejected test license without leaking key ids", async () => {
    vi.spyOn(entitlementApi, "activate").mockRejectedValue(
      new ApiError("LICENSE_KEY_NOT_ALLOWED_IN_RUNTIME", "此授权码不能用于当前版本。", 400),
    );
    wrap(<LicenseSettingsCard />);
    await waitFor(() => screen.getByTestId("license-open-activate"));
    fireEvent.click(screen.getByTestId("license-open-activate"));
    fireEvent.change(screen.getByTestId("license-code-input"), {
      target: { value: "SLP1-test.sig" },
    });
    fireEvent.click(screen.getByTestId("license-activate-submit"));
    await waitFor(() => {
      expect(screen.getByTestId("license-activate-error-code")).toHaveTextContent(
        "LICENSE_KEY_NOT_ALLOWED_IN_RUNTIME",
      );
      expect(screen.getByTestId("license-message")).toHaveTextContent("此授权码不能用于当前版本");
      expect(screen.queryByText(/test-dev/i)).not.toBeInTheDocument();
    });
  });

  it("shows issuance-not-configured message from snapshot", async () => {
    current = {
      ...freeSnapshot(),
      license_issuance_ready: false,
      license_issuance_message: "专业版授权功能尚未配置。",
      license_trust_mode: "production",
    };
    wrap(<LicenseSettingsCard />);
    await waitFor(() => {
      expect(screen.getByTestId("license-issuance-message")).toHaveTextContent(
        "专业版授权功能尚未配置。",
      );
    });
  });

  it("buy button opens configured URL", async () => {
    wrap(<LicenseSettingsCard />);
    await waitFor(() => {
      expect(screen.getByTestId("license-edition-label")).toHaveTextContent("免费版");
    });
    await waitFor(() => {
      expect(entitlementApi.snapshot).toHaveBeenCalled();
    });
    fireEvent.click(screen.getByTestId("license-buy-pro"));
    await waitFor(() => {
      expect(openExternal.openExternalUrl).toHaveBeenCalledWith("https://afdian.com/item/demo");
    });
  });

  it("buy failure shows unconfigured copy without field names", async () => {
    vi.spyOn(openExternal, "openExternalUrl").mockResolvedValue({
      ok: false,
      code: "COMMERCE_URL_MISSING",
      message: "专业版购买地址尚未配置。",
    });
    wrap(<LicenseSettingsCard />);
    await waitFor(() => screen.getByTestId("license-buy-pro"));
    fireEvent.click(screen.getByTestId("license-buy-pro"));
    await waitFor(() => {
      expect(screen.getByTestId("license-message")).toHaveTextContent("专业版购买地址尚未配置。");
      expect(screen.queryByText(/afdian_product_url/i)).not.toBeInTheDocument();
    });
  });

  it("canUseFeature returns PRO_LICENSE_REQUIRED when free", async () => {
    const gate = await canUseFeature("story_lab");
    expect(gate.enabled).toBe(false);
    expect(gate.reason).toBe("PRO_LICENSE_REQUIRED");
  });
});
