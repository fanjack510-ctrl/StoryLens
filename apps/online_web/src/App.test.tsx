import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import * as api from "./api";

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return {
    ...actual,
    me: vi.fn(),
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    listJobs: vi.fn(),
    uploadTxt: vi.fn(),
    createJob: vi.fn(),
    getJobResult: vi.fn(),
  };
});

const user: api.User = {
  id: "user-1",
  email: "reader@example.com",
  available_pipelines: ["phase2a_smoke"],
};
const queuedJob: api.Job = {
  id: "job-12345678",
  upload_id: "upload-1",
  pipeline: "phase2a_smoke",
  status: "queued",
  progress: 0,
  public_error_code: null,
  created_at: "2026-08-30T00:00:00Z",
  started_at: null,
  finished_at: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.listJobs).mockResolvedValue([]);
  vi.mocked(api.logout).mockResolvedValue();
  vi.stubGlobal("crypto", { randomUUID: () => "browser-request-uuid" });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("StoryLens Online Beta", () => {
  it("shows login first and enters the authenticated workspace", async () => {
    vi.mocked(api.me).mockRejectedValue(new api.ApiError(401, "authentication_required", "请登录"));
    vi.mocked(api.login).mockResolvedValue(user);
    render(<App />);

    expect(await screen.findByRole("heading", { name: "登录 StoryLens Online" })).toBeVisible();
    fireEvent.change(screen.getByLabelText("邮箱"), { target: { value: user.email } });
    fireEvent.change(screen.getByLabelText("密码（至少 10 位）"), {
      target: { value: "safe-password-123" },
    });
    const loginButtons = screen.getAllByRole("button", { name: "登录" });
    fireEvent.click(loginButtons[loginButtons.length - 1]);

    expect(await screen.findByRole("heading", { name: "上传 UTF-8 TXT" })).toBeVisible();
    expect(screen.getByText("只执行本地文本统计，不调用 AI，不产生费用。")).toBeVisible();
    expect(api.login).toHaveBeenCalledWith(user.email, "safe-password-123");
  });

  it("uploads a TXT and creates a queued task", async () => {
    vi.mocked(api.me).mockResolvedValue(user);
    vi.mocked(api.uploadTxt).mockResolvedValue({
      id: "upload-1",
      original_filename: "book.txt",
      sha256: "a".repeat(64),
      file_size_bytes: 5,
      created_at: "2026-08-30T00:00:00Z",
    });
    vi.mocked(api.createJob).mockResolvedValue(queuedJob);
    vi.mocked(api.listJobs).mockResolvedValueOnce([]).mockResolvedValue([queuedJob]);
    render(<App />);

    const picker = await screen.findByLabelText("选择 TXT 文件");
    const file = new File(["hello"], "book.txt", { type: "text/plain" });
    fireEvent.change(picker, { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "上传并创建本地文本统计任务" }));

    await waitFor(() => expect(api.uploadTxt).toHaveBeenCalledWith(file));
    expect(api.createJob).toHaveBeenCalledWith(
      "upload-1",
      "browser-request-uuid",
      "phase2a_smoke",
    );
    expect(await screen.findByText("等待处理")).toBeVisible();
  });

  it("offers the real analysis pipeline only to an allowlisted user", async () => {
    const allowlistedUser: api.User = {
      ...user,
      available_pipelines: ["phase2a_smoke", "phase2b1_txt_evidence_summary"],
    };
    vi.mocked(api.me).mockResolvedValue(allowlistedUser);
    vi.mocked(api.uploadTxt).mockResolvedValue({
      id: "upload-1",
      original_filename: "book.txt",
      sha256: "a".repeat(64),
      file_size_bytes: 5,
      created_at: "2026-08-30T00:00:00Z",
    });
    vi.mocked(api.createJob).mockResolvedValue({
      ...queuedJob,
      pipeline: "phase2b1_txt_evidence_summary",
    });
    render(<App />);

    const picker = await screen.findByLabelText("选择 TXT 文件");
    fireEvent.change(screen.getByLabelText("任务类型"), {
      target: { value: "phase2b1_txt_evidence_summary" },
    });
    fireEvent.change(picker, {
      target: { files: [new File(["hello"], "book.txt", { type: "text/plain" })] },
    });
    fireEvent.click(screen.getByRole("button", { name: "上传并创建AI 证据摘要任务" }));

    await waitFor(() =>
      expect(api.createJob).toHaveBeenCalledWith(
        "upload-1",
        "browser-request-uuid",
        "phase2b1_txt_evidence_summary",
      ),
    );
    expect(screen.getByText("Phase 2B1 内部验证")).toBeVisible();
  });

  it("renders evidence results without internal Provider metadata", async () => {
    const allowlistedUser: api.User = {
      ...user,
      available_pipelines: ["phase2a_smoke", "phase2b1_txt_evidence_summary"],
    };
    vi.mocked(api.me).mockResolvedValue(allowlistedUser);
    vi.mocked(api.listJobs).mockResolvedValue([
      {
        ...queuedJob,
        pipeline: "phase2b1_txt_evidence_summary",
        status: "succeeded",
        progress: 100,
      },
    ]);
    vi.mocked(api.getJobResult).mockResolvedValue({
      job_id: queuedJob.id,
      result: {
        pipeline: "phase2b1_txt_evidence_summary",
        overview: {
          text: "故事围绕一次失踪展开。",
          evidence_paragraph_ids: ["P000001"],
        },
        findings: [
          {
            text: "失踪前出现异常征兆。",
            evidence_paragraph_ids: ["P000001"],
          },
        ],
        paragraph_count: 2,
        character_count: 20,
        real_ai_analysis: true,
        billing_status: "not_billable",
        charged_cny: 0,
      },
    });
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "查看统计结果" }));
    expect(await screen.findByText("故事围绕一次失踪展开。")).toBeVisible();
    expect(screen.getByText("失踪前出现异常征兆。")).toBeVisible();
    expect(screen.getByText("证据段落：P000001")).toBeVisible();
    expect(screen.queryByText(/provider/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/deepseek/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/内部成本/i)).not.toBeInTheDocument();
  });
});
