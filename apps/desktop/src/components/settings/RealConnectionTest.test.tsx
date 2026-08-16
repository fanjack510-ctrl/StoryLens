import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RealConnectionTest } from "./RealConnectionTest";
import { providersApi } from "../../services/providersApi";

vi.mock("../../services/providersApi", () => ({
  providersApi: { connectionTestPreflight: vi.fn(), testConnection: vi.fn() },
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const preflight = {
  configured_model: "qwen3.7-plus",
  max_output_tokens: 32,
  estimated_cost: 0.001,
  currency: "CNY",
  remaining_requests: 70,
  remaining_tokens: 90000,
  within_budget: true,
  blockers: [],
};

describe("真实连接测试（从已删除的 /providers 页迁移）", () => {
  it("先确认再花钱：打开只做预检，取消不发请求", async () => {
    vi.mocked(providersApi.connectionTestPreflight).mockResolvedValue(preflight as never);
    render(<RealConnectionTest provider="aliyun_qwen_plus" />);
    fireEvent.click(screen.getByTestId("real-connection-test-open"));
    const dialog = await screen.findByTestId("real-connection-test-confirm");
    expect(dialog).toHaveTextContent("qwen3.7-plus");
    await waitFor(() => expect(dialog).toHaveTextContent("0.001"));
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(providersApi.testConnection).not.toHaveBeenCalled();
  });

  it("说明它不发送小说正文", () => {
    vi.mocked(providersApi.connectionTestPreflight).mockResolvedValue(preflight as never);
    render(<RealConnectionTest provider="aliyun_qwen_plus" />);
    expect(screen.getByText(/不发送小说正文/)).toBeInTheDocument();
  });

  it("确认后执行并展示结果", async () => {
    vi.mocked(providersApi.connectionTestPreflight).mockResolvedValue(preflight as never);
    vi.mocked(providersApi.testConnection).mockResolvedValue({
      status: "healthy",
      http_status: 200,
      total_tokens: 43,
    } as never);
    render(<RealConnectionTest provider="aliyun_qwen_plus" />);
    fireEvent.click(screen.getByTestId("real-connection-test-open"));
    fireEvent.click(await screen.findByTestId("real-connection-test-confirm-run"));
    const result = await screen.findByTestId("real-connection-test-result");
    expect(result).toHaveTextContent("healthy");
    expect(providersApi.testConnection).toHaveBeenCalledWith("aliyun_qwen_plus", 32);
  });

  it("预算门禁不通过时不发请求，并说明原因", async () => {
    vi.mocked(providersApi.connectionTestPreflight).mockResolvedValue({
      ...preflight,
      within_budget: false,
      blockers: ["MODEL_PRICING_NOT_FOUND"],
    } as never);
    render(<RealConnectionTest provider="aliyun_qwen_plus" />);
    fireEvent.click(screen.getByTestId("real-connection-test-open"));
    fireEvent.click(await screen.findByTestId("real-connection-test-confirm-run"));
    const err = await screen.findByTestId("real-connection-test-error");
    expect(err).toHaveTextContent("MODEL_PRICING_NOT_FOUND");
    expect(providersApi.testConnection).not.toHaveBeenCalled();
  });
});
