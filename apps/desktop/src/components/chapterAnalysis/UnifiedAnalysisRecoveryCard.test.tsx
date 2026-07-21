import type { ReactNode } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { analysisRecoveryApi } from "../../services/analysisRecoveryApi";
import { UnifiedAnalysisRecoveryCard } from "./UnifiedAnalysisRecoveryCard";

vi.mock("../../services/analysisRecoveryApi", () => ({
  analysisRecoveryApi: {
    recoveryPlan: vi.fn(),
    recover: vi.fn(),
  },
}));

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const run = {
  id: 5,
  status: "boundary_confirmed_budget_blocked",
  error_code: "INSUFFICIENT_BUDGET_RESERVATION",
  root_error_code: "INSUFFICIENT_BUDGET_RESERVATION",
} as any;

afterEach(() => cleanup());

describe("UnifiedAnalysisRecoveryCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(analysisRecoveryApi.recoveryPlan).mockResolvedValue({
      run_id: 5,
      chapter_id: 2,
      status: "boundary_confirmed_budget_blocked",
      user_status: "paused_recoverable",
      pause_reason: "request_budget_insufficient",
      recoverable: true,
      blockers: [
        {
          code: "REQUEST_BUDGET_INSUFFICIENT",
          reason: "request_budget_insufficient",
          user_message: "今日云端请求额度不足",
        },
        {
          code: "PROVIDER_DISCONNECTED",
          reason: "provider_disconnected",
          user_message: "AI服务暂未连接",
        },
      ],
      warnings: [],
      checks: [
        { id: "scene_artifacts", label: "Scene", status: "pass", user_label: "Scene分析已完成" },
        { id: "request_budget", label: "req", status: "fail", user_label: "请求额度不足" },
        { id: "token_budget", label: "tok", status: "pass", user_label: "Token预算充足" },
        {
          id: "provider_connection",
          label: "prov",
          status: "fail",
          user_label: "AI服务暂未连接",
        },
      ],
      recommended_actions: [{ action: "fix_and_continue", label: "修复并继续" }],
      resume_stage: "scene_analysis",
      will_reuse_artifacts: ["AnalysisRun", "BoundaryRevision"],
      will_create_entities: [],
      estimated_requests: 13,
      estimated_tokens: 1000,
      estimated_cost: 0.1,
      currency: "CNY",
      recovery_attempts: 0,
      budget_authorization_proposal: {
        scope: "run_temporary",
        current_daily_request_limit: 50,
        current_remaining_requests: 13,
        required_requests: 26,
        suggested_extra_requests: 13,
        estimated_cost: 0.2,
        currency: "CNY",
        will_not_rerun: ["Boundary", "completed Scene Analysis"],
        message: "建议仅为本次Run临时授权",
      },
      details: { error_code: "INSUFFICIENT_BUDGET_RESERVATION" },
      provider: "aliyun_qwen_plus",
      model: "qwen-plus",
      request_hash: "abc",
    } as any);
  });

  it("shows one pause card with dual blockers and no competing CTAs", async () => {
    wrap(<UnifiedAnalysisRecoveryCard run={run} />);
    expect(await screen.findByTestId("unified-recovery-title")).toHaveTextContent(
      "分析已暂停",
    );
    expect(screen.getByTestId("unified-recovery-lead")).toHaveTextContent(
      "当前进度已保存，可以稍后继续。",
    );
    expect(screen.getByTestId("unified-recovery-card")).toHaveAttribute(
      "data-recovery-kind",
      "paused",
    );
    expect(screen.queryByText("分析未完成")).not.toBeInTheDocument();
    expect(await screen.findByTestId("unified-recovery-blockers")).toHaveTextContent(
      "今日云端请求额度不足",
    );
    expect(screen.getByTestId("unified-recovery-blockers")).toHaveTextContent(
      "AI服务暂未连接",
    );
    expect(screen.getByTestId("unified-recovery-fix-continue")).toHaveTextContent(
      "修复并继续",
    );
    expect(screen.getByTestId("unified-recovery-later")).toHaveTextContent("稍后处理");
    expect(screen.getByTestId("unified-recovery-details")).toHaveTextContent("查看详情");
    expect(screen.queryByText("调整额度并继续")).not.toBeInTheDocument();
    expect(screen.queryByText("继续生成阅读旅程")).not.toBeInTheDocument();
    expect(screen.queryByText("重新连接")).not.toBeInTheDocument();
    expect(screen.queryByText("INSUFFICIENT_BUDGET_RESERVATION")).not.toBeInTheDocument();
    expect(screen.queryByText("provider_disconnected")).not.toBeInTheDocument();
  });

  it("opens run-temporary budget proposal then recovers once", async () => {
    vi.mocked(analysisRecoveryApi.recover).mockResolvedValue({
      run_id: 5,
      status: "scene_analysis_running",
      user_status: "running",
      recoverable: true,
      actions_executed: ["provider_reconnect", "run_temporary_budget_authorization"],
      resume_stage: "scene_analysis",
      blockers: [],
      details: {},
      http_request_sent: false,
      model_invocations_started: false,
    } as any);
    wrap(<UnifiedAnalysisRecoveryCard run={run} />);
    await screen.findByTestId("unified-recovery-blockers");
    const primary = screen.getByTestId("unified-recovery-fix-continue");
    expect(primary).toBeEnabled();
    fireEvent.click(primary);
    expect(await screen.findByTestId("unified-recovery-proposal")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("unified-recovery-authorize-run"));
    await waitFor(() => {
      expect(analysisRecoveryApi.recover).toHaveBeenCalledWith(
        5,
        expect.objectContaining({
          recovery_mode: "unified",
          authorize_budget: expect.objectContaining({
            scope: "run_temporary",
            extra_requests: 13,
          }),
        }),
      );
    });
  });

  it("keeps internal codes only in details", async () => {
    wrap(<UnifiedAnalysisRecoveryCard run={run} />);
    await screen.findByTestId("unified-recovery-details");
    fireEvent.click(screen.getByTestId("unified-recovery-details"));
    const tech = await screen.findByTestId("unified-recovery-tech");
    expect(tech).toHaveTextContent("INSUFFICIENT_BUDGET_RESERVATION");
    expect(tech).toHaveTextContent("resume_stage");
  });

  it("shows boundary provider failure copy without journey root cause", async () => {
    vi.mocked(analysisRecoveryApi.recoveryPlan).mockResolvedValue({
      run_id: 2,
      chapter_id: 1,
      status: "failed_provider",
      user_status: "paused_recoverable",
      pause_reason: "detection_checkpoint_pending",
      recoverable: true,
      blockers: [],
      warnings: [],
      checks: [
        {
          id: "boundary_detection",
          label: "Boundary",
          status: "fail",
          user_label: "场景边界识别未完成",
        },
        {
          id: "reader_journey",
          label: "RJ",
          status: "skip",
          user_label: "后续影响：暂时无法生成阅读旅程",
        },
        { id: "request_budget", label: "req", status: "pass", user_label: "请求额度充足" },
      ],
      recommended_actions: [{ action: "fix_and_continue", label: "修复并继续" }],
      resume_stage: "boundary_detection",
      will_reuse_artifacts: ["DetectionCheckpoints"],
      will_create_entities: ["AnalysisRun(recovery)"],
      estimated_requests: 2,
      estimated_tokens: 1000,
      estimated_cost: 0.01,
      currency: "CNY",
      recovery_attempts: 3,
      details: {
        error_code: "SCENE_PIPELINE_FAILED",
        root_error_code: "PROVIDER_HTTP_ERROR",
        http_status: 429,
        error_category: "rate_limited",
        retryable: true,
        user_error: {
          title: "场景边界识别请求失败",
          stage_label: "场景边界识别未完成",
          explanation: "模型服务在识别场景边界时返回错误。已完成的结果将被保留。",
          reason: "请求受到服务商限流",
          impact: "场景边界识别尚未完成，因此暂时无法生成阅读旅程。",
          config_note: "AI 服务配置正常，但本次场景边界请求失败。",
        },
      },
      provider: "aliyun_qwen_plus",
      model: "qwen3.7-plus",
      request_hash: "ee89c29c327b4cb1",
    } as any);

    wrap(
      <UnifiedAnalysisRecoveryCard
        run={
          {
            id: 2,
            status: "failed_provider",
            error_code: "SCENE_PIPELINE_FAILED",
            root_error_code: "PROVIDER_HTTP_ERROR",
            failed_stage: "provider_request",
          } as any
        }
      />,
    );

    expect(await screen.findByText("场景边界识别请求失败")).toBeInTheDocument();
    expect(screen.getByTestId("unified-recovery-title")).toHaveTextContent(
      "场景边界识别请求失败",
    );
    expect(screen.getByTestId("unified-recovery-reason")).toHaveTextContent("请求受到服务商限流");
    expect(screen.getByTestId("unified-recovery-config-note")).toHaveTextContent(
      "AI 服务配置正常，但本次场景边界请求失败",
    );
    expect(screen.queryByText("阅读旅程未到阶段")).not.toBeInTheDocument();
    expect(screen.queryByTestId("unified-recovery-check-reader_journey")).not.toBeInTheDocument();
    expect(screen.getByTestId("unified-recovery-fix-continue")).toBeEnabled();

    fireEvent.click(screen.getByTestId("unified-recovery-details"));
    const tech = await screen.findByTestId("unified-recovery-tech");
    expect(tech).toHaveTextContent("http_status");
    expect(tech).toHaveTextContent("429");
    expect(tech).toHaveTextContent("PROVIDER_HTTP_ERROR");
  });

  it("shows loading on recover and blocks double click", async () => {
    let resolveRecover: (v: any) => void = () => undefined;
    vi.mocked(analysisRecoveryApi.recover).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveRecover = resolve;
        }),
    );
    vi.mocked(analysisRecoveryApi.recoveryPlan).mockResolvedValue({
      run_id: 2,
      chapter_id: 1,
      status: "failed_provider",
      user_status: "paused_recoverable",
      pause_reason: "detection_checkpoint_pending",
      recoverable: true,
      blockers: [],
      warnings: [],
      checks: [],
      recommended_actions: [{ action: "fix_and_continue", label: "修复并继续" }],
      resume_stage: "boundary_detection",
      will_reuse_artifacts: [],
      will_create_entities: [],
      estimated_requests: 1,
      estimated_tokens: 1,
      estimated_cost: 0,
      currency: "CNY",
      recovery_attempts: 0,
      details: {
        user_error: {
          title: "场景边界识别请求失败",
          explanation: "模型服务在识别场景边界时返回错误。已完成的结果将被保留。",
          reason: "请求受到服务商限流",
        },
      },
      provider: "aliyun_qwen_plus",
      model: "qwen3.7-plus",
    } as any);

    wrap(
      <UnifiedAnalysisRecoveryCard
        run={
          {
            id: 2,
            status: "failed_provider",
            error_code: "SCENE_PIPELINE_FAILED",
            root_error_code: "PROVIDER_HTTP_ERROR",
            failed_stage: "provider_request",
          } as any
        }
      />,
    );
    const btn = await screen.findByTestId("unified-recovery-fix-continue");
    fireEvent.click(btn);
    fireEvent.click(btn);
    expect(await screen.findByTestId("unified-recovery-status")).toHaveTextContent(
      "正在从场景边界识别继续",
    );
    expect(btn).toBeDisabled();
    await waitFor(() => expect(analysisRecoveryApi.recover).toHaveBeenCalledTimes(1));
    resolveRecover({
      run_id: 2,
      status: "boundary_candidates_running",
      user_status: "running",
      recoverable: true,
      actions_executed: ["resume_boundary_detection"],
      resume_stage: "boundary_detection",
      blockers: [],
      details: {},
      http_request_sent: false,
      model_invocations_started: true,
    });
  });

  it("shows error and re-enables button when recover fails", async () => {
    vi.mocked(analysisRecoveryApi.recover).mockRejectedValue(new Error("网络中断"));
    vi.mocked(analysisRecoveryApi.recoveryPlan).mockResolvedValue({
      run_id: 2,
      chapter_id: 1,
      status: "failed_provider",
      user_status: "paused_recoverable",
      pause_reason: "detection_checkpoint_pending",
      recoverable: true,
      blockers: [],
      warnings: [],
      checks: [],
      recommended_actions: [{ action: "fix_and_continue", label: "修复并继续" }],
      resume_stage: "boundary_detection",
      will_reuse_artifacts: [],
      will_create_entities: [],
      estimated_requests: 1,
      estimated_tokens: 1,
      estimated_cost: 0,
      currency: "CNY",
      recovery_attempts: 1,
      details: {
        user_error: {
          title: "场景边界识别请求失败",
          explanation: "模型服务在识别场景边界时返回错误。已完成的结果将被保留。",
        },
      },
    } as any);
    wrap(
      <UnifiedAnalysisRecoveryCard
        run={
          {
            id: 2,
            status: "failed_provider",
            error_code: "SCENE_PIPELINE_FAILED",
            root_error_code: "PROVIDER_HTTP_ERROR",
            failed_stage: "provider_request",
          } as any
        }
      />,
    );
    fireEvent.click(await screen.findByTestId("unified-recovery-fix-continue"));
    expect(await screen.findByTestId("unified-recovery-error")).toHaveTextContent("网络中断");
    expect(screen.getByTestId("unified-recovery-fix-continue")).toBeEnabled();
  });

  it("hides fix-continue when recovery exhausted", async () => {
    vi.mocked(analysisRecoveryApi.recoveryPlan).mockResolvedValue({
      run_id: 2,
      chapter_id: 1,
      status: "failed_provider",
      user_status: "failed",
      pause_reason: "detection_checkpoint_pending",
      recoverable: false,
      blockers: [],
      warnings: [],
      checks: [],
      recommended_actions: [
        { action: "revalidate_ai_service", label: "重新验证 AI 服务" },
        { action: "create_new_recovery_task", label: "新建恢复任务" },
      ],
      resume_stage: "boundary_detection",
      will_reuse_artifacts: [],
      will_create_entities: [],
      estimated_requests: 0,
      estimated_tokens: 0,
      estimated_cost: 0,
      currency: "CNY",
      recovery_attempts: 5,
      details: {
        recovery_exhausted: true,
        user_error: { title: "场景边界识别请求失败", explanation: "保留结果" },
      },
    } as any);
    wrap(
      <UnifiedAnalysisRecoveryCard
        run={
          {
            id: 2,
            status: "failed_provider",
            error_code: "SCENE_PIPELINE_FAILED",
            root_error_code: "PROVIDER_HTTP_ERROR",
            failed_stage: "provider_request",
          } as any
        }
      />,
    );
    await screen.findByTestId("unified-recovery-revalidate");
    expect(screen.queryByTestId("unified-recovery-fix-continue")).not.toBeInTheDocument();
  });

  it("shows config actions for non-retryable provider errors", async () => {
    vi.mocked(analysisRecoveryApi.recoveryPlan).mockResolvedValue({
      run_id: 2,
      chapter_id: 1,
      status: "failed_provider",
      user_status: "paused_recoverable",
      pause_reason: "detection_checkpoint_pending",
      recoverable: true,
      blockers: [
        {
          code: "PROVIDER_REQUEST_NOT_RETRYABLE",
          reason: "provider_request_not_retryable",
          user_message: "请求参数不被当前模型支持",
        },
      ],
      warnings: [],
      checks: [],
      recommended_actions: [
        { action: "check_model_config", label: "检查模型配置" },
        { action: "validate_and_save_provider", label: "验证并保存" },
      ],
      resume_stage: "boundary_detection",
      will_reuse_artifacts: [],
      will_create_entities: [],
      estimated_requests: 0,
      estimated_tokens: 0,
      estimated_cost: 0,
      currency: "CNY",
      recovery_attempts: 0,
      details: {
        provider_not_retryable: true,
        http_status: 400,
        user_error: {
          title: "场景边界识别请求失败",
          explanation: "模型服务在识别场景边界时返回错误。已完成的结果将被保留。",
          config_note: "AI 服务配置正常，但本次场景边界请求失败。",
        },
      },
    } as any);
    wrap(
      <UnifiedAnalysisRecoveryCard
        run={
          {
            id: 2,
            status: "failed_provider",
            error_code: "SCENE_PIPELINE_FAILED",
            root_error_code: "PROVIDER_HTTP_ERROR",
            failed_stage: "provider_request",
          } as any
        }
      />,
    );
    expect(await screen.findByTestId("unified-recovery-check-config")).toBeInTheDocument();
    expect(screen.queryByTestId("unified-recovery-fix-continue")).not.toBeInTheDocument();
    expect(screen.queryByText("分析配置尚未完成")).not.toBeInTheDocument();
  });

  it("shows failed copy without paused title", async () => {
    wrap(
      <UnifiedAnalysisRecoveryCard
        run={
          {
            id: 9,
            status: "failed",
            error_code: "SCENE_PIPELINE_FAILED",
            root_error_code: "SCENE_PIPELINE_FAILED",
            failed_stage: "scene_analysis",
          } as any
        }
      />,
    );
    expect(await screen.findByTestId("unified-recovery-title")).toHaveTextContent("分析未完成");
    expect(screen.getByTestId("unified-recovery-lead")).toHaveTextContent(
      "StoryLens 在分析过程中遇到了问题。已经完成的分析结果会被保留。",
    );
    expect(screen.getByTestId("unified-recovery-card")).toHaveAttribute(
      "data-recovery-kind",
      "failed",
    );
    expect(screen.queryByText("分析已暂停")).not.toBeInTheDocument();
  });
});
