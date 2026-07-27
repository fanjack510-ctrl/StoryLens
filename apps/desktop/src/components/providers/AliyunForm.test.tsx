import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AliyunForm } from "./AliyunForm";
import { providersApi } from "../../services/providersApi";

vi.mock("../../services/providersApi", () => ({
  providersApi: {
    configuration: vi.fn(),
    save: vi.fn(),
    action: vi.fn(),
    deleteCredentials: vi.fn(),
  },
}));

describe("AliyunForm hydrate", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("does not render enabled=false checkbox before backend hydrate", async () => {
    let resolveConfig: (v: any) => void = () => undefined;
    vi.mocked(providersApi.configuration).mockReturnValue(
      new Promise((resolve) => {
        resolveConfig = resolve;
      }),
    );
    render(<AliyunForm provider="aliyun_qwen_plus" onSaved={() => undefined} />);
    expect(screen.getByTestId("provider-form-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("provider-enabled-checkbox")).not.toBeInTheDocument();
    expect(screen.queryByTestId("provider-save-config")).not.toBeInTheDocument();

    resolveConfig({
      display_name: "阿里云百炼",
      region: "cn-beijing",
      workspace_id: "",
      base_url: "https://example.test/v1",
      plus_model: "qwen3.7-plus",
      max_model: "qwen3.7-max",
      flash_model: "qwen3.6-flash",
      timeout_seconds: 300,
      max_retries: 3,
      enabled: true,
      disconnected: false,
      allow_auto_route: false,
      raw_logging_enabled: false,
      credential_state: "configured",
    });

    expect(await screen.findByTestId("provider-enabled-checkbox")).toBeChecked();
    expect(screen.getByTestId("provider-form-hydrated")).toBeInTheDocument();
  });

  it("save after hydrate keeps enabled true from backend", async () => {
    vi.mocked(providersApi.configuration).mockResolvedValue({
      display_name: "阿里云百炼",
      region: "cn-beijing",
      enabled: true,
      disconnected: false,
      plus_model: "qwen3.7-plus",
      max_model: "qwen3.7-max",
      flash_model: "qwen3.6-flash",
      timeout_seconds: 300,
      max_retries: 3,
      allow_auto_route: false,
      raw_logging_enabled: false,
      workspace_id: "",
      base_url: "https://example.test/v1",
      credential_state: "configured",
    } as any);
    vi.mocked(providersApi.save).mockResolvedValue({} as any);

    render(<AliyunForm provider="aliyun_qwen_plus" onSaved={() => undefined} />);
    await screen.findByTestId("provider-enabled-checkbox");
    fireEvent.click(screen.getByTestId("provider-save-config"));
    await waitFor(() => {
      expect(providersApi.save).toHaveBeenCalledWith(
        "aliyun_qwen_plus",
        expect.objectContaining({ enabled: true }),
      );
    });
    expect(localStorage.getItem("api_key")).toBeNull();
    expect(localStorage.getItem("storylens.apiKey")).toBeNull();
  });
});
