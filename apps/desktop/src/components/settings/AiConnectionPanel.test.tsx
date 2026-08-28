/** 「AI 与模型」面板。
 *
 *  这个文件接下了 `ai_connection_state_local.test.tsx` 与 `SettingsAiServiceTab.test.tsx`
 *  守着的不变量。那两份测的是改版前的界面：两套服务商配置并存，各有自己的 API Key、同意
 *  勾选和按钮，状态由一条写死阿里云的接口给。那套界面已经整个删掉。
 *
 *  留下来的要求没变，只是现在由后端说了算（INV-P4）：
 *
 *  * 状态文案原样呈现后端给的，客户端不自己拼；
 *  * 拦路原因逐条列出，不混进一句话里；
 *  * 只有一个主按钮、一个 API Key 输入口；
 *  * 服务商下拉由后端 options 渲染；
 *  * 用不了的模型档位要变灰并说明原因。
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AiConnectionPanel } from "./AiConnectionPanel";
import * as aiConnection from "../../services/aiConnection";
import { providersApi } from "../../services/providersApi";
import { settingsApi } from "../../services/settingsApi";

const BASE_STATUS: aiConnection.AiConnectionStatus = {
  provider_name: "deepseek",
  display_name: "深度求索/DeepSeek",
  model: "deepseek-v4-flash",
  credential_configured: true,
  provider_enabled: true,
  cloud_enabled: true,
  cloud_body_consent: true,
  provider_eligible: true,
  analysis_ready: true,
  connection_state: "connected",
  ui_state: "READY",
  ui_label: "验证成功",
  ui_reason: "当前配置可以连接深度求索/DeepSeek（deepseek-v4-flash）。",
  validated_at: "2026-08-22T08:38:00Z",
  validated_at_display: "2026-08-22 08:38",
  validated_model: "deepseek-v4-flash",
  blockers: [],
  blocker_labels: [],
  blocker_guidance: null,
};

const OPTIONS = [
  { name: "aliyun_qwen_plus", display_name: "阿里云百炼", base_url: "", models: [] },
  {
    name: "deepseek",
    display_name: "深度求索/DeepSeek",
    base_url: "https://api.deepseek.com/",
    models: ["deepseek-v4-flash"],
    model_tiers: [
      { id: "deepseek-v4-flash", label: "V4 Flash", hint: "性价比优先", pricing_known: true, recommended: true },
      { id: "deepseek-v4-pro", label: "V4 Pro", hint: "质量更高", pricing_known: false },
    ],
  },
];

function mount(status: Partial<aiConnection.AiConnectionStatus> = {}) {
  vi.spyOn(aiConnection, "fetchAiConnection").mockResolvedValue({ ...BASE_STATUS, ...status });
  vi.spyOn(settingsApi, "activeCloudProvider").mockResolvedValue({
    provider_name: "deepseek",
    options: OPTIONS,
  } as never);
  vi.spyOn(providersApi, "configuration").mockResolvedValue({
    display_name: "深度求索/DeepSeek",
    base_url: "https://api.deepseek.com/",
    plus_model: "deepseek-v4-flash",
    timeout_seconds: 300,
    max_retries: 3,
    enabled: true,
    disconnected: false,
  } as never);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AiConnectionPanel />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("AiConnectionPanel", () => {
  it("状态文案原样来自后端，不由客户端拼", async () => {
    mount({ ui_label: "配置已更改，需要重新验证", ui_state: "CONFIG_CHANGED" });
    expect(await screen.findByTestId("ai-connection-label")).toHaveTextContent(
      "配置已更改，需要重新验证",
    );
    expect(screen.getByTestId("ai-connection-reason")).toHaveTextContent("deepseek-v4-flash");
  });

  it("拦路原因逐条列出，不并成一句话", async () => {
    mount({
      connection_state: "partial",
      provider_eligible: false,
      analysis_ready: false,
      blockers: ["budget_unavailable", "pricing_unavailable"],
      blocker_labels: ["每日预算不足", "该模型没有价格数据"],
    });
    const list = await screen.findByTestId("ai-connection-blockers");
    expect(list.querySelectorAll("li")).toHaveLength(2);
    expect(list).toHaveTextContent("每日预算不足");
    expect(list).toHaveTextContent("该模型没有价格数据");
  });

  it("只有一个主按钮和一个 API Key 输入口", async () => {
    const { container } = mount();
    await screen.findByTestId("ai-connection-status");
    expect(container.querySelectorAll(".ai-btn-primary")).toHaveLength(1);
    // 已保存时显示的是占位与「重新设置」；点开之后才出现唯一的输入框。
    expect(container.querySelectorAll('input[type="password"]')).toHaveLength(0);
    fireEvent.click(screen.getByTestId("ai-key-reset"));
    expect(container.querySelectorAll('input[type="password"]')).toHaveLength(1);
  });

  it("服务商下拉由后端 options 渲染", async () => {
    mount();
    const select = (await screen.findByTestId("ai-provider-select")) as HTMLSelectElement;
    expect([...select.options].map((o) => o.textContent)).toEqual([
      "阿里云百炼",
      "深度求索/DeepSeek",
    ]);
    expect(select.value).toBe("deepseek");
  });

  it("没有价格数据的档位变灰并说明原因——不能让人选了才发现用不了", async () => {
    mount();
    await screen.findByTestId("ai-model-tiers");
    const pro = screen.getByRole("radio", { name: /V4 Pro/ }) as HTMLInputElement;
    expect(pro).toBeDisabled();
    expect(screen.getByTestId("ai-model-tiers")).toHaveTextContent("暂无价格数据");
  });

  it("云端总开关在这一页可切换", async () => {
    const setCloud = vi.spyOn(settingsApi, "setCloud").mockResolvedValue({} as never);
    mount();
    await screen.findByTestId("ai-connection-status");
    fireEvent.click(screen.getByTestId("ai-advanced-toggle"));
    fireEvent.click(await screen.findByTestId("ai-cloud-switch"));
    await waitFor(() => expect(setCloud).toHaveBeenCalledWith(false));
  });

  it("没有密钥时，断开与删除都不可点", async () => {
    mount({ credential_configured: false, connection_state: "unconfigured", ui_state: "NOT_CONFIGURED" });
    await screen.findByTestId("ai-connection-status");
    fireEvent.click(screen.getByTestId("ai-advanced-toggle"));
    expect(await screen.findByTestId("ai-disconnect")).toBeDisabled();
    expect(screen.getByTestId("ai-delete-credential")).toBeDisabled();
  });

  it("保存设置只持久化，不偷偷发起真实连接测试", async () => {
    const save = vi.spyOn(providersApi, "save").mockResolvedValue({} as never);
    const setActive = vi.spyOn(settingsApi, "setActiveCloudProvider").mockResolvedValue({} as never);
    const transport = vi.spyOn(providersApi, "transportDiagnostic").mockResolvedValue({} as never);
    const test = vi.spyOn(providersApi, "testConnection").mockResolvedValue({} as never);
    mount();
    await screen.findByTestId("ai-connection-status");
    // 等配置真的读回来：保存需要它，没读到就会静默不做事——这正是这条断言要防的。
    await waitFor(() =>
      expect(screen.getByRole("radio", { name: /V4 Flash/ })).toBeChecked(),
    );
    fireEvent.click(screen.getByTestId("ai-save"));
    await waitFor(() => expect(save).toHaveBeenCalled());
    expect(setActive).toHaveBeenCalledWith("deepseek");
    expect(transport).not.toHaveBeenCalled();
    expect(test).not.toHaveBeenCalled();
    expect(await screen.findByTestId("ai-message")).toHaveTextContent("配置已保存");
  });

  it("测试连接严格先保存配置和当前 Provider，再发诊断与真实调用", async () => {
    const save = vi.spyOn(providersApi, "save").mockResolvedValue({} as never);
    const setActive = vi.spyOn(settingsApi, "setActiveCloudProvider").mockResolvedValue({} as never);
    const transport = vi.spyOn(providersApi, "transportDiagnostic").mockResolvedValue({} as never);
    const test = vi.spyOn(providersApi, "testConnection").mockResolvedValue({} as never);
    mount();
    await screen.findByTestId("ai-connection-status");
    await waitFor(() => expect(screen.getByRole("radio", { name: /V4 Flash/ })).toBeChecked());

    fireEvent.click(screen.getByTestId("ai-verify"));
    await waitFor(() => expect(test).toHaveBeenCalledWith("deepseek", 32));

    expect(save.mock.invocationCallOrder[0]).toBeLessThan(setActive.mock.invocationCallOrder[0]);
    expect(setActive.mock.invocationCallOrder[0]).toBeLessThan(transport.mock.invocationCallOrder[0]);
    expect(transport.mock.invocationCallOrder[0]).toBeLessThan(test.mock.invocationCallOrder[0]);
    expect(screen.getByTestId("ai-message")).toHaveTextContent("配置已保存，连接正常");
  });

  it("配置保存失败时绝不继续测试旧配置", async () => {
    vi.spyOn(providersApi, "save").mockRejectedValue(new Error("配置保存失败"));
    vi.spyOn(settingsApi, "setActiveCloudProvider").mockResolvedValue({} as never);
    const transport = vi.spyOn(providersApi, "transportDiagnostic").mockResolvedValue({} as never);
    const test = vi.spyOn(providersApi, "testConnection").mockResolvedValue({} as never);
    mount();
    await screen.findByTestId("ai-connection-status");
    await waitFor(() => expect(screen.getByRole("radio", { name: /V4 Flash/ })).toBeChecked());

    fireEvent.click(screen.getByTestId("ai-verify"));
    await waitFor(() => expect(screen.getByTestId("ai-message")).toHaveTextContent("配置保存失败"));
    expect(transport).not.toHaveBeenCalled();
    expect(test).not.toHaveBeenCalled();
  });

  it("没有已保存密钥时，必须填入 API Key 才能测试", async () => {
    mount({ credential_configured: false, connection_state: "unconfigured" });
    await screen.findByTestId("ai-connection-status");
    const verify = screen.getByTestId("ai-verify");
    expect(verify).toBeDisabled();
    fireEvent.change(screen.getByTestId("ai-api-key-input"), { target: { value: "sk-local-test" } });
    expect(verify).toBeEnabled();
    expect(verify).toHaveTextContent("保存并测试连接");
  });
});
