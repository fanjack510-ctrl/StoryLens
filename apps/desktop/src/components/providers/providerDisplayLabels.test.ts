import { describe, expect, it } from "vitest";
import {
  cloudStateLabel,
  credentialStateLabel,
  formatUnknown,
  healthStateLabel,
  providerDisplayName,
  providerListStatusLabel,
} from "./providerDisplayLabels";

describe("providerDisplayLabels", () => {
  it("maps provider ids to Chinese display names", () => {
    expect(providerDisplayName("aliyun_qwen_plus")).toBe("阿里云百炼");
  });

  it("distinguishes enabled, disabled, invalid credential, connection failure", () => {
    expect(providerListStatusLabel({ enabled: false }).label).toBe("已停用");
    expect(providerListStatusLabel({ enabled: true, healthy: true }).label).toBe("已启用");
    expect(
      providerListStatusLabel({ enabled: true, credential_state: "invalid" }).label,
    ).toBe("凭据无效");
    expect(
      providerListStatusLabel({
        enabled: true,
        healthy: false,
        connected: false,
      }).label,
    ).toBe("已启用 · 连接失败");
    expect(
      providerListStatusLabel(
        { enabled: true, healthy: true, connected: true },
        { isDefault: true },
      ).label,
    ).toBe("当前默认");
  });

  it("localizes credential / cloud / health states", () => {
    expect(credentialStateLabel("configured")).toBe("凭据已配置");
    expect(credentialStateLabel("invalid")).toBe("凭据无效");
    expect(cloudStateLabel("disabled")).toBe("云端已关闭");
    expect(healthStateLabel("healthy")).toBe("健康");
    expect(healthStateLabel("unhealthy")).toBe("不健康");
  });

  it("formats unknown values as em dash", () => {
    expect(formatUnknown(null)).toBe("—");
    expect(formatUnknown(undefined, " CNY")).toBe("—");
    expect(formatUnknown(0, " CNY")).toBe("0 CNY");
  });
});
