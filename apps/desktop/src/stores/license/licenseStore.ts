import { create } from "zustand";
import {
  getLicenseService,
  type FeatureGateResult,
  type FeatureKey,
  type LicenseService,
  type LicenseSnapshot,
  type LicenseStatus,
} from "../../services/license";

type LicenseStoreState = {
  status: LicenseStatus;
  editionLabel: string;
  license: LicenseSnapshot["license"];
  usingMockService: boolean;
  commerceComingSoon: boolean;
  hydrated: boolean;
  busy: boolean;
  message: string;
  error: string;
  hydrate: () => Promise<void>;
  activateLicense: (code: string) => Promise<void>;
  refreshLicense: () => Promise<void>;
  deactivateLicense: () => Promise<void>;
  getLicenseStatus: () => LicenseSnapshot;
  hasFeature: (featureKey: FeatureKey) => FeatureGateResult;
  clearMessages: () => void;
};

function applySnapshot(
  set: (partial: Partial<LicenseStoreState>) => void,
  snapshot: LicenseSnapshot,
) {
  set({
    status: snapshot.status,
    editionLabel: snapshot.editionLabel,
    license: snapshot.license,
    usingMockService: snapshot.usingMockService,
    commerceComingSoon: snapshot.commerceComingSoon,
    hydrated: true,
  });
}

function service(): LicenseService {
  return getLicenseService();
}

export const useLicenseStore = create<LicenseStoreState>((set) => ({
  status: "FREE",
  editionLabel: "免费版",
  license: null,
  usingMockService: true,
  commerceComingSoon: true,
  hydrated: false,
  busy: false,
  message: "",
  error: "",

  clearMessages() {
    set({ message: "", error: "" });
  },

  getLicenseStatus() {
    return service().getLicenseStatus();
  },

  hasFeature(featureKey) {
    return service().hasFeature(featureKey);
  },

  async hydrate() {
    const snapshot = await service().hydrate();
    applySnapshot(set, snapshot);
  },

  async activateLicense(code: string) {
    set({ busy: true, message: "", error: "" });
    try {
      const snapshot = await service().activateLicense(code);
      applySnapshot(set, snapshot);
      set({
        message:
          snapshot.status === "VIP_ACTIVE"
            ? "Mock 激活成功（开发实现，非真实付费授权）。"
            : `Mock 激活完成，当前状态：${snapshot.status}`,
      });
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : "激活失败",
      });
    } finally {
      set({ busy: false });
    }
  },

  async refreshLicense() {
    set({ busy: true, message: "", error: "" });
    try {
      const snapshot = await service().refreshLicense();
      applySnapshot(set, snapshot);
      set({ message: `授权已刷新（Mock）：${snapshot.status}` });
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : "刷新失败",
      });
    } finally {
      set({ busy: false });
    }
  },

  async deactivateLicense() {
    set({ busy: true, message: "", error: "" });
    try {
      const snapshot = await service().deactivateLicense();
      applySnapshot(set, snapshot);
      set({ message: "已解除本机授权，当前为免费版。" });
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : "解除授权失败",
      });
    } finally {
      set({ busy: false });
    }
  },
}));

/** Status label helper for UI without scattering VIP checks. */
export function licenseStatusLabel(status: LicenseStatus): string {
  switch (status) {
    case "FREE":
      return "免费版";
    case "VIP_ACTIVE":
      return "VIP 已激活";
    case "VIP_EXPIRED":
      return "VIP 已过期";
    case "VIP_OFFLINE_GRACE":
      return "VIP 离线宽限";
    case "VIP_INVALID":
      return "VIP 无效";
    default:
      return status;
  }
}
