import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TasksPage } from "./TasksPage";
import { analysisApi } from "../services/analysisApi";
import { analysisRecoveryApi } from "../services/analysisRecoveryApi";
import { ApiError } from "../services/apiClient";

vi.mock("../services/analysisApi", () => ({
  analysisApi: {
    runs: vi.fn(),
    run: vi.fn(),
    retry: vi.fn(),
    resumeSceneAnalysis: vi.fn(),
    replaySceneAnalysisOffline: vi.fn(),
    sceneAnalysisResumePreflight: vi.fn(),
    invocations: vi.fn(),
    recoveryPreflight: vi.fn(),
    recoverPreflight: vi.fn(),
    continueFromCheckpoints: vi.fn(),
    readerJourney: vi.fn(async () => null),
  },
}));


vi.mock("../services/analysisRecoveryApi", () => ({
  analysisRecoveryApi: {
    recoveryPlan: vi.fn(async () => ({
      run_id: 55,
      status: "failed",
      user_status: "paused_recoverable",
      recoverable: true,
      blockers: [],
      warnings: [],
      checks: [
        {
          id: "scene_artifacts",
          label: "scene",
          status: "warn",
          user_label: "Scene分析进行中",
        },
      ],
      recommended_actions: [{ action: "fix_and_continue", label: "修复并继续" }],
      resume_stage: "scene_analysis",
      will_reuse_artifacts: ["AnalysisRun", "BoundaryRevision"],
      will_create_entities: [],
      estimated_requests: 2,
      estimated_tokens: 1000,
      estimated_cost: 0.1,
      currency: "CNY",
      recovery_attempts: 0,
      details: {},
    })),
    recover: vi.fn(),
  },
}));

vi.mock("../services/booksApi", () => ({
  booksApi: {
    list: vi.fn(async () => [{ id: 1, title: "测试书" }]),
    chapters: vi.fn(async () => [{ id: 2, section_type: "chapter", title: "开端" }]),
  },
}));

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
});

const failedRun54 = {
  id: 54,
  subject_id: "2",
  provider: "aliyun_qwen_plus",
  model: "qwen3.7-plus",
  status: "failed",
  progress_current: 0,
  progress_total: 1,
  execution_mode: "cloud",
  cloud_consent: true,
  sends_content_to_cloud: true,
  error_code: "SCENE_PIPELINE_FAILED",
  root_error_code: "BUSINESS_VALIDATION_FAILED",
  root_error_message: "candidate decision conflicts with deterministic enum rules",
  failed_stage: "business_validation",
  actual_failed_stage: "business_validation",
  failed_invocation_id: 96,
  failed_batch_index: 3,
  failed_transition_id: "T0017",
  validation_error_code: "CANDIDATE_TRUE_WITHOUT_LEGAL_REASON",
  retryable: false,
  user_action_hint: "从已有结果继续",
  created_at: "2026-07-17T00:00:00Z",
  checkpoint_available: true,
  detection_recovery_available: true,
  remaining_detection_batch_count: 7,
  scene_analysis_resume_available: false,
  reusable_checkpoint_count: 3,
  conflicted_checkpoint_count: 1,
  checkpoint_total_count: 10,
  reservation_status: "released",
  failed_invocation: {
    id: 96,
    http_status: 200,
    json_valid: true,
    schema_valid: true,
    error_message: "candidate decision conflicts with deterministic enum rules",
  },
};

const preflightOk = {
  recovered_batch_count: 3,
  total_detection_batch_count: 10,
  remaining_detection_batch_count: 7,
  expected_request_count: 8,
  worst_case_request_count: 16,
  estimated_total_tokens: 10384,
  worst_case_total_tokens: 25565,
  worst_case_cost: 0.171994,
  currency: "CNY",
  within_budget: true,
  exceeded_dimensions: [],
  blockers: [],
  existing_recovery_run_id: null,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <TasksPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("TasksPage 传输错误展示", () => {
  it("显示retryable与旧错误提示", async () => {
    const run = {
      id: 52,
      subject_id: "2",
      provider: "aliyun_qwen_plus",
      model: "qwen3.7-plus",
      status: "failed",
      progress_current: 0,
      progress_total: 1,
      execution_mode: "cloud",
      cloud_consent: true,
      sends_content_to_cloud: true,
      error_code: "SCENE_PIPELINE_FAILED",
      root_error_code: "BUSINESS_VALIDATION_FAILED",
      root_error_message: "",
      failed_stage: "business_validation",
      failed_invocation_id: 91,
      retryable: false,
      user_action_hint: "查看脱敏技术详情",
      created_at: "2026-07-16T16:31:56Z",
      legacy_classification_warning: true,
      exception_type: "StructuredOutputError",
      transport_kind: null,
    };
    vi.mocked(analysisApi.runs).mockResolvedValue([run] as any);
    vi.mocked(analysisApi.run).mockResolvedValue(run as any);
    vi.mocked(analysisApi.invocations).mockResolvedValue([]);
    renderPage();
    fireEvent.click(await screen.findByText("查看详情"));
    expect(screen.getByText("不可重试")).toBeInTheDocument();
    expect(screen.getByTestId("legacy-classification-warning")).toBeInTheDocument();
  });

  it("Provider传输错误中文化阶段", async () => {
    const run = {
      id: 99,
      subject_id: "2",
      provider: "aliyun_qwen_plus",
      model: "qwen3.7-plus",
      status: "failed",
      progress_current: 0,
      progress_total: 1,
      execution_mode: "cloud",
      cloud_consent: true,
      sends_content_to_cloud: true,
      error_code: "SCENE_PIPELINE_FAILED",
      root_error_code: "PROVIDER_CONNECT_TIMEOUT",
      root_error_message: "连接Provider超时",
      failed_stage: "provider_request",
      failed_invocation_id: 100,
      retryable: true,
      user_action_hint: "可先运行传输诊断",
      created_at: "2026-07-17T00:00:00Z",
      exception_type: "ConnectTimeout",
      transport_kind: "connect_timeout",
    };
    vi.mocked(analysisApi.runs).mockResolvedValue([run] as any);
    vi.mocked(analysisApi.run).mockResolvedValue(run as any);
    vi.mocked(analysisApi.invocations).mockResolvedValue([]);
    renderPage();
    fireEvent.click(await screen.findByText("查看详情"));
    expect(screen.getByText("服务请求")).toBeInTheDocument();
    expect(screen.getByText("可重试")).toBeInTheDocument();
    expect(screen.getByTestId("provider-transport-error-label")).toBeInTheDocument();
  });

  it("显示真实失败阶段、冲突Invocation和恢复预算", async () => {
    vi.mocked(analysisApi.runs).mockResolvedValue([failedRun54] as any);
    vi.mocked(analysisApi.run).mockResolvedValue(failedRun54 as any);
    vi.mocked(analysisApi.invocations).mockResolvedValue([]);
    vi.mocked(analysisApi.recoveryPreflight).mockResolvedValue(preflightOk as any);
    renderPage();
    fireEvent.click(await screen.findByText("查看详情"));
    fireEvent.click(screen.getByText("原始错误（默认折叠）"));
    expect(await screen.findAllByText("T0017")).not.toHaveLength(0);
    expect(screen.getAllByText("CANDIDATE_TRUE_WITHOUT_LEGAL_REASON").length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByTestId("checkpoint-summary")).toHaveTextContent("3/10");
    expect(screen.queryByText("exceeded_dimensions")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("查看脱敏技术详情"));
    expect(screen.getByText("#96")).toBeInTheDocument();
    expect(screen.getByText("released")).toBeInTheDocument();
  });
});

const recoverPreflightOk = {
  source_run_id: 54,
  provider_name: "aliyun_qwen_plus",
  eligible: true,
  blockers: [],
  provider_state_version: "abc123version",
  capability_schema_version: "1c-a-2",
  health_state: "healthy",
  health_source: "cached_connection_test",
  reused_batch_count: 3,
  remaining_batch_count: 7,
  expected_requests: 8,
  worst_case_requests: 16,
  estimated_tokens: 10384,
  worst_case_tokens: 25565,
  estimated_cost: 0.057632,
  worst_case_cost: 0.171994,
  currency: "CNY",
  remaining_budget: { requests: 145, tokens: 190562, estimated_cost: 4.97 },
  within_budget: true,
  exceeded_dimensions: [],
  requires_cloud_consent: true,
};

describe("TasksPage 从已有结果继续", () => {
  beforeEach(() => {
    vi.mocked(analysisApi.run).mockResolvedValue(failedRun54 as any);
  });

  it("未勾选时显示明确提示且不发请求", async () => {
    vi.mocked(analysisApi.runs).mockResolvedValue([failedRun54] as any);
    vi.mocked(analysisApi.invocations).mockResolvedValue([]);
    vi.mocked(analysisApi.recoveryPreflight).mockResolvedValue(preflightOk as any);
    renderPage();
    fireEvent.click(await screen.findByText("查看详情"));
    const button = await screen.findByTestId("continue-from-checkpoints");
    expect(button).toBeDisabled();
    expect(screen.getByTestId("recovery-disabled-reason")).toHaveTextContent("未勾选云端同意");
    expect(analysisApi.recoverPreflight).not.toHaveBeenCalled();
    expect(analysisApi.continueFromCheckpoints).not.toHaveBeenCalled();
  });

  it("勾选后先recover/preflight再recover并显示新Run", async () => {
    vi.mocked(analysisApi.runs).mockResolvedValue([failedRun54] as any);
    vi.mocked(analysisApi.invocations).mockResolvedValue([]);
    vi.mocked(analysisApi.recoveryPreflight).mockResolvedValue(preflightOk as any);
    vi.mocked(analysisApi.recoverPreflight).mockResolvedValue(recoverPreflightOk as any);
    vi.mocked(analysisApi.continueFromCheckpoints).mockImplementation(async () => {
      await new Promise((resolve) => setTimeout(resolve, 30));
      return {
        run_id: 55,
        recovered_from_run_id: 54,
        status: "boundary_candidates_running",
        reused_batch_count: 3,
        remaining_batch_count: 7,
        reservation_id: 11,
        request_id: "req-1",
      };
    });
    renderPage();
    fireEvent.click(await screen.findByText("查看详情"));
    fireEvent.click(screen.getByRole("checkbox"));
    const button = await screen.findByTestId("continue-from-checkpoints");
    expect(button).toBeEnabled();
    fireEvent.click(button);
    expect(await screen.findByTestId("recovery-loading")).toBeInTheDocument();
    await waitFor(() => expect(analysisApi.recoverPreflight).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(analysisApi.continueFromCheckpoints).toHaveBeenCalledTimes(1));
    expect(analysisApi.continueFromCheckpoints).toHaveBeenCalledWith(
      54,
      expect.objectContaining({
        cloud_consent: true,
        confirmed: true,
        provider_state_version: "abc123version",
      }),
    );
    expect(await screen.findByTestId("recovery-created")).toHaveTextContent("任务 ID：55");
    expect(screen.getByTestId("recovery-created")).toHaveTextContent("来源任务 54");
  });

  it("loading期间禁用并防止双击", async () => {
    let resolveContinue: (value: any) => void = () => undefined;
    vi.mocked(analysisApi.runs).mockResolvedValue([failedRun54] as any);
    vi.mocked(analysisApi.invocations).mockResolvedValue([]);
    vi.mocked(analysisApi.recoveryPreflight).mockResolvedValue(preflightOk as any);
    vi.mocked(analysisApi.recoverPreflight).mockResolvedValue(recoverPreflightOk as any);
    vi.mocked(analysisApi.continueFromCheckpoints).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveContinue = resolve;
        }),
    );
    renderPage();
    fireEvent.click(await screen.findByText("查看详情"));
    fireEvent.click(screen.getByRole("checkbox"));
    const button = await screen.findByTestId("continue-from-checkpoints");
    fireEvent.click(button);
    fireEvent.click(button);
    fireEvent.click(button);
    expect(await screen.findByTestId("recovery-loading")).toBeInTheDocument();
    expect(button).toBeDisabled();
    await waitFor(() => expect(analysisApi.recoverPreflight).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(analysisApi.continueFromCheckpoints).toHaveBeenCalledTimes(1));
    resolveContinue({
      run_id: 55,
      recovered_from_run_id: 54,
      status: "boundary_candidates_running",
      reused_batch_count: 3,
      remaining_batch_count: 7,
    });
    expect(await screen.findByTestId("recovery-created")).toBeInTheDocument();
  });

  it("preflight blockers准确显示并保留checkbox", async () => {
    vi.mocked(analysisApi.runs).mockResolvedValue([failedRun54] as any);
    vi.mocked(analysisApi.invocations).mockResolvedValue([]);
    vi.mocked(analysisApi.recoveryPreflight).mockResolvedValue(preflightOk as any);
    vi.mocked(analysisApi.recoverPreflight).mockResolvedValue({
      ...recoverPreflightOk,
      eligible: false,
      blockers: ["credential_missing"],
    } as any);
    renderPage();
    fireEvent.click(await screen.findByText("查看详情"));
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(await screen.findByTestId("continue-from-checkpoints"));
    expect(await screen.findByTestId("recovery-error")).toHaveTextContent("aliyun_qwen_plus");
    expect(screen.getByTestId("recovery-blockers")).toHaveTextContent("缺少API凭据");
    expect(analysisApi.continueFromCheckpoints).not.toHaveBeenCalled();
    expect(screen.getByRole("checkbox")).toBeChecked();
  });

  it("失败时显示结构化错误并保留checkbox", async () => {
    vi.mocked(analysisApi.runs).mockResolvedValue([failedRun54] as any);
    vi.mocked(analysisApi.invocations).mockResolvedValue([]);
    vi.mocked(analysisApi.recoveryPreflight).mockResolvedValue(preflightOk as any);
    vi.mocked(analysisApi.recoverPreflight).mockResolvedValue(recoverPreflightOk as any);
    vi.mocked(analysisApi.continueFromCheckpoints).mockRejectedValue(
      new ApiError(
        "INSUFFICIENT_BUDGET_RESERVATION",
        "继续运行的剩余预算不足",
        409,
        {},
        "req-budget",
        true,
        "请提高云端预算后重试",
      ),
    );
    renderPage();
    fireEvent.click(await screen.findByText("查看详情"));
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(await screen.findByTestId("continue-from-checkpoints"));
    expect(await screen.findByTestId("recovery-error")).toHaveTextContent(
      /预算不足|云端请求额度/,
    );
    expect(screen.getByTestId("recovery-error")).toHaveTextContent("INSUFFICIENT_BUDGET_RESERVATION");
    expect(screen.getByTestId("recovery-error")).toHaveTextContent("req-budget");
    expect(screen.getByRole("checkbox")).toBeChecked();
  });
});

const failedRun55 = {
  id: 55,
  subject_id: "2",
  provider: "aliyun_qwen_plus",
  model: "qwen3.7-plus",
  status: "failed",
  progress_current: 1,
  progress_total: 1,
  execution_mode: "cloud",
  cloud_consent: true,
  sends_content_to_cloud: true,
  error_code: "SCENE_ANALYSIS_FAILED",
  root_error_code: "PROVIDER_DISABLED",
  root_error_message: "Provider已停用，拒绝发送请求",
  failed_stage: "scene_analysis",
  actual_failed_stage: "scene_analysis",
  failed_invocation_id: 106,
  failed_scene_id: 6,
  failed_scene_index: 1,
  retryable: false,
  created_at: "2026-07-17T04:00:00Z",
  checkpoint_available: false,
  detection_recovery_available: false,
  remaining_detection_batch_count: 0,
  scene_analysis_resume_available: true,
  boundary_revision_id: 1,
  total_scene_count: 14,
  completed_scene_count: 0,
  remaining_scene_count: 14,
  scene_analysis_coverage_rate: 1,
  reusable_checkpoint_count: 10,
  checkpoint_total_count: 10,
  reservation_status: "released",
  recovered_from_run_id: 54,
};

const sceneResumePreflightOk = {
  run_id: 55,
  boundary_revision_id: 1,
  total_scene_count: 14,
  completed_scene_count: 0,
  remaining_scene_count: 14,
  remaining_scene_ids: [6, 7, 8],
  expected_requests: 14,
  worst_case_requests: 28,
  estimated_tokens: 40000,
  worst_case_tokens: 47788,
  estimated_cost: 0.2,
  worst_case_cost: 0.364376,
  remaining_budget: { requests: 100, tokens: 100000, estimated_cost: 4 },
  within_budget: true,
  exceeded_dimensions: [],
  provider_state_version: "scene-ver-1",
  provider_name: "aliyun_qwen_plus",
  eligible: true,
  blockers: [],
  requires_cloud_consent: true,
  estimated: true,
  currency: "CNY",
  coverage_rate: 1,
};

describe("TasksPage Scene Analysis 恢复", () => {
  it("Scene失败隐藏Detection恢复卡并显示统一恢复卡", async () => {
    vi.mocked(analysisApi.runs).mockResolvedValue([failedRun55] as any);
    vi.mocked(analysisApi.run).mockResolvedValue(failedRun55 as any);
    vi.mocked(analysisApi.invocations).mockResolvedValue([]);
    vi.mocked(analysisApi.sceneAnalysisResumePreflight).mockResolvedValue(
      sceneResumePreflightOk as any,
    );
    renderPage();
    fireEvent.click(await screen.findByText("查看详情"));
    expect(await screen.findByTestId("task-unified-recovery")).toBeInTheDocument();
    expect(screen.queryByTestId("checkpoint-summary")).not.toBeInTheDocument();
    expect(screen.getByTestId("detail-scene-progress")).toHaveTextContent("0 / 14");
    expect(screen.getByText("场景分析")).toBeInTheDocument();
    fireEvent.click(screen.getByText("原始错误（默认折叠）"));
    expect(screen.getAllByText("PROVIDER_DISABLED").length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByTestId("unified-recovery-fix-continue")).toBeInTheDocument();
  });

  it("统一恢复修复并继续会调用recover且防双击", async () => {
    let resolveRecover: (value: any) => void = () => undefined;
    vi.mocked(analysisApi.runs).mockResolvedValue([failedRun55] as any);
    vi.mocked(analysisApi.run).mockResolvedValue(failedRun55 as any);
    vi.mocked(analysisApi.invocations).mockResolvedValue([]);
    vi.mocked(analysisApi.sceneAnalysisResumePreflight).mockResolvedValue(
      sceneResumePreflightOk as any,
    );
    vi.mocked(analysisRecoveryApi.recover).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveRecover = resolve;
        }),
    );
    renderPage();
    fireEvent.click(await screen.findByText("查看详情"));
    const button = await screen.findByTestId("unified-recovery-fix-continue");
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    fireEvent.click(button);
    expect(await screen.findByTestId("unified-recovery-status")).toHaveTextContent(
      "正在继续分析…",
    );
    await waitFor(() => expect(analysisRecoveryApi.recover).toHaveBeenCalledTimes(1));
    expect(analysisRecoveryApi.recover).toHaveBeenCalledWith(
      55,
      expect.objectContaining({
        cloud_consent: true,
        confirmed: true,
        recovery_mode: "unified",
        resume: true,
      }),
    );
    resolveRecover({
      run_id: 55,
      status: "scene_analysis_running",
      model_invocations_started: true,
      blockers: [],
    });
  });

  it("列表显示真实Scene进度", async () => {
    const partial = {
      ...failedRun55,
      status: "scene_analysis_partial",
      root_error_code: "BUSINESS_VALIDATION_FAILED",
      root_error_message: "all analysis fields must not cite the whole scene indiscriminately",
      failed_scene_id: 10,
      failed_scene_index: 5,
      failed_invocation_id: 116,
      historical_failed_scene_id: 10,
      historical_failed_scene_index: 5,
      historical_failed_invocation_id: 116,
      completed_scene_count: 4,
      remaining_scene_count: 10,
      offline_replay_available: true,
      failed_scene_http_attempts: 6,
      scene_analysis_max_http_attempts: 4,
    };
    vi.mocked(analysisApi.runs).mockResolvedValue([partial] as any);
    vi.mocked(analysisApi.run).mockResolvedValue(partial as any);
    vi.mocked(analysisApi.invocations).mockResolvedValue([]);
    vi.mocked(analysisApi.sceneAnalysisResumePreflight).mockResolvedValue({
      ...sceneResumePreflightOk,
      completed_scene_count: 4,
      remaining_scene_count: 10,
    } as any);
    renderPage();
    expect(await screen.findByTestId("run-55-scene-progress")).toHaveTextContent(
      "场景分析：4 / 14",
    );
    fireEvent.click(await screen.findByText("查看详情"));
    expect(await screen.findByTestId("detail-scene-progress")).toHaveTextContent("4 / 14");
    expect(await screen.findByTestId("task-unified-recovery")).toBeInTheDocument();
    expect(await screen.findByTestId("unified-recovery-fix-continue")).toBeInTheDocument();
  });

  it("Artifact已恢复后详情显示历史失败Scene且统一恢复可用", async () => {
    const recovered = {
      ...failedRun55,
      status: "scene_analysis_partial",
      completed_scene_count: 5,
      remaining_scene_count: 9,
      failed_scene_id: null,
      historical_failed_scene_id: 10,
      historical_failed_scene_index: 5,
      historical_failed_invocation_id: 116,
      offline_replay_available: false,
      failed_scene_http_attempts: 0,
      scene_analysis_resume_available: true,
    };
    vi.mocked(analysisApi.runs).mockResolvedValue([recovered] as any);
    vi.mocked(analysisApi.run).mockResolvedValue(recovered as any);
    vi.mocked(analysisApi.invocations).mockResolvedValue([]);
    vi.mocked(analysisApi.sceneAnalysisResumePreflight).mockResolvedValue({
      ...sceneResumePreflightOk,
      completed_scene_count: 5,
      remaining_scene_count: 9,
    } as any);
    renderPage();
    fireEvent.click(await screen.findByText("查看详情"));
    expect(await screen.findByTestId("detail-failed-scene")).toHaveTextContent("无");
    expect(screen.getByTestId("detail-historical-failed-scene")).toHaveTextContent("#10");
    expect(await screen.findByTestId("unified-recovery-fix-continue")).toBeEnabled();
  });

  it("显示12/14与Evidence错误详情", async () => {
    const partial = {
      ...failedRun55,
      status: "scene_analysis_partial",
      root_error_code: "EVIDENCE_VALIDATION_FAILED",
      root_error_message: "key_actions requires at least one evidenced action",
      validation_error_code: "EVIDENCE_VALIDATION_FAILED",
      failed_scene_id: 18,
      failed_scene_index: 13,
      failed_invocation_id: 127,
      historical_failed_scene_id: 18,
      historical_failed_scene_index: 13,
      historical_failed_invocation_id: 127,
      completed_scene_count: 12,
      remaining_scene_count: 2,
      completed_scene_ids: [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17],
      remaining_scene_ids: [18, 19],
      offline_replay_available: true,
      failed_scene_http_attempts: 4,
      scene_validation_detail: {
        validation_error_message: "key_actions requires at least one evidenced action",
        categories: ["key_actions_empty", "key_actions_missing_evidence"],
        allowed_paragraph_ids: ["B0001-C0002-P0063"],
        illegal_evidence_ids: [],
        offline_replay_eligible: true,
      },
    };
    vi.mocked(analysisApi.runs).mockResolvedValue([partial] as any);
    vi.mocked(analysisApi.run).mockResolvedValue(partial as any);
    vi.mocked(analysisApi.invocations).mockResolvedValue([]);
    renderPage();
    expect(await screen.findByTestId("run-55-scene-progress")).toHaveTextContent(
      "场景分析：12 / 14",
    );
    fireEvent.click(await screen.findByText("查看详情"));
    expect(screen.getByTestId("detail-evidence-error")).toHaveTextContent(
      "key_actions requires at least one evidenced action",
    );
    expect(screen.getByTestId("detail-allowed-paragraphs")).toHaveTextContent(
      "B0001-C0002-P0063",
    );
    expect(await screen.findByTestId("task-unified-recovery")).toBeInTheDocument();
    expect(await screen.findByTestId("unified-recovery-fix-continue")).toBeInTheDocument();
  });

  it("succeeded Run无旅程时显示继续生成阅读旅程且不显示复制错误", async () => {
    const done = {
      ...failedRun55,
      status: "succeeded",
      error_code: undefined,
      root_error_code: undefined,
      completed_scene_count: 14,
      total_scene_count: 14,
      remaining_scene_count: 0,
      scene_analysis_resume_available: false,
      chapter_complete: false,
      effective_status: "partial_complete",
    };
    vi.mocked(analysisApi.runs).mockResolvedValue([done] as any);
    vi.mocked(analysisApi.run).mockResolvedValue(done as any);
    vi.mocked(analysisApi.invocations).mockResolvedValue([]);
    vi.mocked(analysisApi.readerJourney).mockResolvedValue(null);
    renderPage();
    expect(await screen.findByTestId("view-results-55")).toHaveTextContent("查看详情");
    fireEvent.click(screen.getByTestId("run-more-55-trigger"));
    expect(screen.getByTestId("unified-recover-open-55")).toHaveTextContent(
      "继续生成阅读旅程",
    );
    expect(screen.getByText("场景分析已完成")).toBeInTheDocument();
    expect(screen.queryByText("复制错误")).not.toBeInTheDocument();
    expect(screen.queryByText("分析全部完成")).not.toBeInTheDocument();
  });

  it("进度缺字段时显示等待进度而不是 undefined", async () => {
    const run = {
      ...failedRun54,
      id: 77,
      progress_current: undefined,
      progress_total: undefined,
      total_scene_count: undefined,
      completed_scene_count: undefined,
    };
    vi.mocked(analysisApi.runs).mockResolvedValue([run] as any);
    renderPage();
    expect(await screen.findByTestId("run-77-progress")).toHaveTextContent("等待进度");
    expect(screen.getByTestId("run-77-progress").textContent).not.toMatch(/undefined|null|NaN/i);
  });

  it("任务详情正常打开并消费 invocations 数组", async () => {
    vi.mocked(analysisApi.runs).mockResolvedValue([failedRun54] as any);
    vi.mocked(analysisApi.run).mockResolvedValue({
      ...failedRun54,
      failed_invocation: undefined,
    } as any);
    vi.mocked(analysisApi.invocations).mockResolvedValue([
      { id: 96, http_status_code: 422, error_message: "schema failed", latency_ms: 10 },
    ] as any);
    vi.mocked(analysisApi.recoveryPreflight).mockResolvedValue(preflightOk as any);
    renderPage();
    fireEvent.click(await screen.findByText("查看详情"));
    expect(await screen.findByText("任务详情")).toBeInTheDocument();
    fireEvent.click(screen.getByText("查看脱敏技术详情"));
    expect(await screen.findByText("schema failed")).toBeInTheDocument();
    expect(screen.queryByTestId("detail-invocations-error")).not.toBeInTheDocument();
  });

  it("invocations 返回空数组时详情不崩溃", async () => {
    vi.mocked(analysisApi.runs).mockResolvedValue([failedRun54] as any);
    vi.mocked(analysisApi.run).mockResolvedValue({
      ...failedRun54,
      failed_invocation: undefined,
    } as any);
    vi.mocked(analysisApi.invocations).mockResolvedValue([]);
    vi.mocked(analysisApi.recoveryPreflight).mockResolvedValue(preflightOk as any);
    renderPage();
    fireEvent.click(await screen.findByText("查看详情"));
    fireEvent.click(await screen.findByText("查看脱敏技术详情"));
    expect(screen.getByText("没有可用的 Invocation 摘要。")).toBeInTheDocument();
  });

  it("invocations 非数组错误结构时显示明确错误且不崩溃", async () => {
    vi.mocked(analysisApi.runs).mockResolvedValue([failedRun54] as any);
    vi.mocked(analysisApi.run).mockResolvedValue({
      ...failedRun54,
      failed_invocation: undefined,
    } as any);
    vi.mocked(analysisApi.invocations).mockRejectedValue(
      new ApiError("INVOCATIONS_RESPONSE_INVALID", "模型调用列表响应格式异常（Run #54）", 502),
    );
    vi.mocked(analysisApi.recoveryPreflight).mockResolvedValue(preflightOk as any);
    renderPage();
    fireEvent.click(await screen.findByText("查看详情"));
    expect(await screen.findByTestId("detail-invocations-error")).toHaveTextContent(
      /模型调用列表响应格式异常/,
    );
    fireEvent.click(screen.getByText("查看脱敏技术详情"));
    expect(screen.getByText("没有可用的 Invocation 摘要。")).toBeInTheDocument();
  });
});
