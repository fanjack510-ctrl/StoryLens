/**
 * Local Vitest: recovery card copy for structured evidence errors (CHG-20260721-012).
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { UnifiedAnalysisRecoveryCard } from "./UnifiedAnalysisRecoveryCard";
import { analysisRecoveryApi } from "../../services/analysisRecoveryApi";
import type { Run } from "../../types";

vi.mock("../../services/analysisRecoveryApi", () => ({
  analysisRecoveryApi: {
    recoveryPlan: vi.fn(),
    recover: vi.fn(),
  },
}));

function wrap(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

function baseRun(id: number, overrides: Partial<Run> = {}): Run {
  return {
    id,
    status: "failed_structural",
    subject_type: "chapter",
    subject_id: "1",
    provider: "mock",
    model: "mock",
    retryable: false,
    error_code: "SCENE_ANALYSIS_FAILED",
    root_error_code: "BUSINESS_VALIDATION_FAILED",
    failed_stage: "scene_analysis",
    ...overrides,
  } as Run;
}

describe("UnifiedAnalysisRecoveryCard evidence semantics", () => {
  beforeEach(() => {
    vi.mocked(analysisRecoveryApi.recoveryPlan).mockReset();
    vi.mocked(analysisRecoveryApi.recover).mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it("shows 整理证据并继续 for EVIDENCE_OVERBROAD_REUSE", async () => {
    vi.mocked(analysisRecoveryApi.recoveryPlan).mockResolvedValue({
      run_id: 31,
      status: "failed_structural",
      user_status: "paused",
      recoverable: true,
      resume_stage: "scene_analysis",
      recommended_actions: [
        { action: "evidence_remap_repair", label: "整理证据并继续", automatic: false },
      ],
      blockers: [],
      warnings: [],
      checks: [],
      details: {
        evidence_error: {
          error_code: "EVIDENCE_OVERBROAD_REUSE",
          action: "evidence_remap_repair",
          repairable: true,
        },
        user_error: {
          title: "部分分析证据过于宽泛",
          explanation:
            "当前场景分析已经生成，但部分判断引用了过大的正文范围。StoryLens 将重新整理证据对应关系，不会重复分析已完成场景。",
        },
        recovery_exhausted: false,
        provider_not_retryable: false,
      },
    } as never);

    wrap(
      <UnifiedAnalysisRecoveryCard
        run={baseRun(31, { root_error_code: "EVIDENCE_OVERBROAD_REUSE" })}
      />,
    );
    expect(await screen.findByText("部分分析证据过于宽泛")).toBeInTheDocument();
    expect(screen.getByTestId("unified-recovery-evidence-remap")).toHaveTextContent(
      "整理证据并继续",
    );
    expect(screen.queryByTestId("unified-recovery-fix-continue")).not.toBeInTheDocument();
    expect(screen.queryByText(/all analysis fields must not cite/i)).not.toBeInTheDocument();
  });

  it("shows 重新检查场景边界 for SCENE_BOUNDARY_TOO_BROAD", async () => {
    vi.mocked(analysisRecoveryApi.recoveryPlan).mockResolvedValue({
      run_id: 32,
      status: "failed_structural",
      user_status: "paused",
      recoverable: true,
      resume_stage: "scene_analysis",
      recommended_actions: [
        { action: "rerun_scene_boundary", label: "重新检查场景边界", automatic: false },
      ],
      blockers: [],
      warnings: [],
      checks: [],
      details: {
        evidence_error: {
          error_code: "SCENE_BOUNDARY_TOO_BROAD",
          action: "rerun_scene_boundary",
          repairable: true,
        },
        user_error: {
          title: "当前场景可能包含多个事件",
          explanation: "场景范围可能过大，导致分析证据无法准确对应。需要重新检查该场景的边界。",
        },
        recovery_exhausted: false,
        provider_not_retryable: false,
      },
    } as never);

    wrap(
      <UnifiedAnalysisRecoveryCard
        run={baseRun(32, { root_error_code: "SCENE_BOUNDARY_TOO_BROAD" })}
      />,
    );
    expect(await screen.findByTestId("unified-recovery-boundary-rerun")).toHaveTextContent(
      "重新检查场景边界",
    );
  });

  it("does not show fix-and-continue when non-repairable business error", async () => {
    vi.mocked(analysisRecoveryApi.recoveryPlan).mockResolvedValue({
      run_id: 33,
      status: "failed",
      user_status: "failed",
      recoverable: false,
      resume_stage: "none",
      recommended_actions: [
        { action: "view_error_details", label: "查看问题", automatic: false },
        { action: "handle_later", label: "稍后处理", automatic: false },
      ],
      blockers: [],
      warnings: [],
      checks: [],
      details: {
        evidence_error: {
          error_code: "BUSINESS_VALIDATION_FAILED",
          action: "view_error_details",
          repairable: false,
        },
        user_error: {
          title: "分析未完成",
          explanation: "当前问题无法通过自动修复继续。已完成的分析结果会被保留。",
        },
        recovery_exhausted: false,
        provider_not_retryable: false,
      },
    } as never);

    wrap(<UnifiedAnalysisRecoveryCard run={baseRun(33, { retryable: false })} />);
    await screen.findByTestId("unified-recovery-view-issue");
    expect(screen.queryByTestId("unified-recovery-fix-continue")).not.toBeInTheDocument();
    expect(screen.queryByTestId("unified-recovery-evidence-remap")).not.toBeInTheDocument();
  });

  it("shows loading immediately on evidence remap click", async () => {
    vi.mocked(analysisRecoveryApi.recoveryPlan).mockResolvedValue({
      run_id: 34,
      status: "failed_structural",
      user_status: "paused",
      recoverable: true,
      resume_stage: "scene_analysis",
      recommended_actions: [
        { action: "evidence_remap_repair", label: "整理证据并继续", automatic: false },
      ],
      blockers: [],
      warnings: [],
      checks: [],
      details: {
        evidence_error: {
          error_code: "EVIDENCE_OVERBROAD_REUSE",
          action: "evidence_remap_repair",
          repairable: true,
        },
        user_error: { title: "部分分析证据过于宽泛", explanation: "说明" },
        recovery_exhausted: false,
        provider_not_retryable: false,
      },
    } as never);
    vi.mocked(analysisRecoveryApi.recover).mockImplementation(
      () => new Promise(() => undefined) as never,
    );

    wrap(<UnifiedAnalysisRecoveryCard run={baseRun(34)} />);
    fireEvent.click(await screen.findByTestId("unified-recovery-evidence-remap"));
    await waitFor(() => {
      expect(screen.getByTestId("unified-recovery-status")).toBeInTheDocument();
    });
  });
});
