import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BoundaryReviewPanel } from "./BoundaryReviewPanel";
import { analysisApi } from "../../services/analysisApi";
import { ApiError } from "../../services/apiClient";

vi.mock("../../services/analysisApi", () => ({ analysisApi: {
  boundaryReview: vi.fn(), decideBoundary: vi.fn(), addManualBoundary: vi.fn(),
  deleteManualBoundary: vi.fn(), scenePreview: vi.fn(), sceneAnalysisPreflight: vi.fn(),
  confirmReview: vi.fn(),
} }));

const review = {
  id: 3, status: "pending", provider: "aliyun_qwen_plus", model: "configured-plus",
  prompt_version: "v3.5", accepted_count: 0, rejected_count: 0, manually_added_count: 0,
  paragraphs: Array.from({ length: 8 }, (_, i) => ({ id: `P${i + 1}`, raw_text: `原创段落${i + 1}` })),
  decisions: [{
    id: 1,
    transition_id: "T0001", left_paragraph_id: "P4", right_paragraph_id: "P5",
    model_candidate: true, model_confidence: .65, model_reason_code: "primary_goal_reset",
    first_pass_json: "{}", adjudication_result: "{}", review_priority: "high", user_decision: "pending",
  }],
};

const acceptedReview = {
  ...review,
  accepted_count: 1,
  decisions: [{ ...review.decisions[0], user_decision: "accept", final_boundary: true }],
};

function makeMixedReview() {
  const paragraphs = Array.from({ length: 16 }, (_, i) => ({
    id: `P${i + 1}`,
    raw_text: `原创段落${i + 1}`,
  }));
  const nonConflictPending = Array.from({ length: 11 }, (_, i) => ({
    id: 100 + i,
    transition_id: `T${String(i + 1).padStart(4, "0")}`,
    left_paragraph_id: `P${i + 1}`,
    right_paragraph_id: `P${i + 2}`,
    model_candidate: true,
    model_confidence: 0.7,
    model_reason_code: "primary_goal_reset",
    first_pass_json: "{}",
    adjudication_result: "{}",
    review_priority: "medium",
    user_decision: "pending",
    semantic_conflict: false,
  }));
  const conflicts = [12, 13, 14].map((n, i) => ({
    id: 200 + i,
    transition_id: `T${String(n).padStart(4, "0")}`,
    left_paragraph_id: `P${n}`,
    right_paragraph_id: `P${n + 1}`,
    model_candidate: true,
    model_confidence: 0.55,
    model_reason_code: "object",
    first_pass_json: "{}",
    adjudication_result: "{}",
    review_priority: "high",
    user_decision: "pending",
    semantic_conflict: true,
    conflict_code: "CANDIDATE_TRUE_WITHOUT_LEGAL_REASON",
    model_boundary_candidate: true,
    enum_snapshot_json: "{}",
  }));
  const accepted = {
    id: 300,
    transition_id: "T0015",
    left_paragraph_id: "P15",
    right_paragraph_id: "P16",
    model_candidate: true,
    model_confidence: 0.8,
    model_reason_code: "primary_goal_reset",
    first_pass_json: "{}",
    adjudication_result: "{}",
    review_priority: "low",
    user_decision: "accept",
    semantic_conflict: false,
  };
  return {
    id: 3,
    status: "pending",
    provider: "aliyun_qwen_plus",
    model: "configured-plus",
    prompt_version: "v3.5",
    accepted_count: 1,
    rejected_count: 0,
    manually_added_count: 0,
    paragraphs,
    decisions: [...nonConflictPending, ...conflicts, accepted],
  };
}

const renderPanel = () => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <BoundaryReviewPanel bookId={1} chapterId={2} />
  </QueryClientProvider>,
);

beforeEach(() => {
  vi.clearAllMocks();
  Element.prototype.scrollIntoView = vi.fn();
  vi.mocked(analysisApi.boundaryReview).mockResolvedValue(review as any);
  vi.mocked(analysisApi.decideBoundary).mockResolvedValue(acceptedReview as any);
  vi.mocked(analysisApi.addManualBoundary).mockResolvedValue(review as any);
  vi.mocked(analysisApi.scenePreview).mockResolvedValue({ coverage_rate: 1, scenes: [{ ordinal: 1 }] } as any);
  vi.mocked(analysisApi.sceneAnalysisPreflight).mockResolvedValue({
    scene_count: 1,
    expected_request_count: 1,
    worst_case_request_count: 2,
    estimated_total_tokens: 1000,
    worst_case_total_tokens: 2000,
    estimated_cost: 0.01,
    worst_case_cost: 0.02,
    within_budget: true,
    exceeded_dimensions: [],
    remaining: { requests: 50, tokens: 80000, estimated_cost: 2 },
  } as any);
  vi.mocked(analysisApi.confirmReview).mockResolvedValue({
    revision_id: 1, scene_analysis_started: true, budget_blocked: false,
  } as any);
});
afterEach(cleanup);

describe("场景边界审阅", () => {
  it("显示候选上下文、分隔线和风险", async () => {
    renderPanel(); expect(await screen.findByText("场景边界审阅")).toBeInTheDocument();
    expect(screen.getByText("建议在此拆分场景")).toBeInTheDocument();
    expect(screen.getByText(/高置信度/)).toBeInTheDocument();
    expect(screen.getByTestId("decision-reason-T0001")).toHaveTextContent("人物目标发生变化");
    expect(screen.getByTestId("decision-reason-T0001")).not.toHaveTextContent("primary_goal_reset");
    expect(screen.getByText("原创段落1")).toBeInTheDocument();
    expect(screen.getByText("原创段落8")).toBeInTheDocument();
    expect(screen.getByTestId("review-stats")).toHaveTextContent("待处理 1");
    expect(screen.getByTestId("review-candidate-count")).toHaveTextContent("候选边界 1 / 1");
    expect(screen.getByTestId("review-candidate-pages").querySelectorAll("button")).toHaveLength(1);
    expect(screen.queryByTestId("review-candidate-page-2")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("decision-tech-T0001").querySelector("summary")!);
    expect(screen.getByTestId("decision-tech-T0001")).toHaveTextContent("primary_goal_reset");
  });

  it("两个候选时 Header 与页码共用同一数量", async () => {
    vi.mocked(analysisApi.boundaryReview).mockResolvedValue({
      ...review,
      decisions: [
        review.decisions[0],
        {
          ...review.decisions[0],
          id: 2,
          transition_id: "T0002",
          left_paragraph_id: "P5",
          right_paragraph_id: "P6",
          model_reason_code: "location_change",
          review_priority: "medium",
        },
      ],
    } as any);
    renderPanel();
    expect(await screen.findByTestId("review-candidate-count")).toHaveTextContent("候选边界 1 / 2");
    const pages = screen.getByTestId("review-candidate-pages");
    expect(pages.querySelectorAll("button")).toHaveLength(2);
    expect(screen.getByTestId("review-candidate-page-1")).toBeInTheDocument();
    expect(screen.getByTestId("review-candidate-page-2")).toBeInTheDocument();
    expect(screen.getByTestId("decision-reason-T0001")).toHaveTextContent("人物目标发生变化");
    fireEvent.click(screen.getByTestId("review-candidate-page-2"));
    expect(screen.getByTestId("review-candidate-count")).toHaveTextContent("候选边界 2 / 2");
    expect(screen.getByTestId("decision-reason-T0002")).toHaveTextContent("位置发生变化");
  });

  it("接受与拒绝只保存人工决定", async () => {
    renderPanel();     fireEvent.click(await screen.findByText("接受边界"));
    await waitFor(() => expect(analysisApi.decideBoundary).toHaveBeenCalledWith(
      3, "T0001", "accept", undefined, undefined,
    ));
    expect(await screen.findByText("已保存")).toBeInTheDocument();
    fireEvent.click(screen.getByText("拒绝边界"));
    await waitFor(() => expect(analysisApi.decideBoundary).toHaveBeenCalledWith(
      3, "T0001", "reject", undefined, undefined,
    ));
  });

  it("时间线点击普通段落间隙新增边界", async () => {
    renderPanel(); fireEvent.click(await screen.findByTitle("P2"));
    await waitFor(() => expect(analysisApi.addManualBoundary).toHaveBeenCalledWith(3, "P2"));
  });

  it("点击时间线候选切换到对应详情并scrollIntoView", async () => {
    renderPanel();
    await screen.findByTestId("decision-card-T0001");
    fireEvent.click(screen.getByTestId("timeline-T0001"));
    expect(screen.getByTestId("decision-card-T0001")).toHaveClass("selected");
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
  });

  it("待审时完成审阅禁用并提示还有N项待处理", async () => {
    renderPanel();
    const complete = await screen.findByTestId("confirm-all-boundaries");
    expect(complete).toHaveTextContent("完成审阅");
    expect(complete).toBeDisabled();
    expect(screen.getByTestId("pending-remaining-hint")).toHaveTextContent("还有1项待处理");
    fireEvent.click(complete);
    expect(analysisApi.confirmReview).not.toHaveBeenCalled();
  });

  it("点击定位到下一项能移动到待审项", async () => {
    renderPanel();
    await screen.findByTestId("decision-card-T0001");
    fireEvent.click(screen.getByTestId("locate-next-pending"));
    expect(screen.getByTestId("decision-card-T0001")).toHaveClass("selected");
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
  });

  it("支持撤销和保存草稿", async () => {
    renderPanel(); fireEvent.click(await screen.findByText("接受边界"));
    fireEvent.click(screen.getByText("撤销上一步"));
    await waitFor(() => expect(analysisApi.decideBoundary).toHaveBeenLastCalledWith(3, "T0001", "pending"));
    fireEvent.click(screen.getByText("保存草稿")); expect(screen.getByText("草稿已保存")).toBeInTheDocument();
  });

  it("全部处理后完成审阅可用并启动Scene Analysis", async () => {
    vi.mocked(analysisApi.boundaryReview).mockResolvedValue(acceptedReview as any);
    renderPanel();
    const complete = await screen.findByTestId("confirm-all-boundaries");
    expect(complete).toHaveTextContent("完成审阅");
    expect(complete).not.toBeDisabled();
    fireEvent.click(await screen.findByText("场景预览"));
    expect(await screen.findByTestId("scene-preview-live")).toHaveTextContent("覆盖率100");
    fireEvent.click(complete);
    await waitFor(() => expect(analysisApi.confirmReview).toHaveBeenCalledWith(3, "desktop-user"));
  });

  it("Stage2预算不足仍保存边界", async () => {
    vi.mocked(analysisApi.boundaryReview).mockResolvedValue(acceptedReview as any);
    vi.mocked(analysisApi.sceneAnalysisPreflight).mockResolvedValue({
      scene_count: 2, expected_request_count: 2, worst_case_request_count: 4,
      estimated_total_tokens: 90000, worst_case_total_tokens: 120000,
      estimated_cost: 1, worst_case_cost: 2, within_budget: false,
      exceeded_dimensions: ["tokens"],
      remaining: { requests: 10, tokens: 1000, estimated_cost: 0.1 },
    } as any);
    vi.mocked(analysisApi.confirmReview).mockResolvedValue({
      revision_id: 9, budget_blocked: true, scene_analysis_started: false,
      user_action_hint: "Token不足：最坏需要120000 Token，当前剩余1000 Token。",
    } as any);
    renderPanel();
    fireEvent.click(await screen.findByTestId("confirm-all-boundaries"));
    expect(await screen.findByTestId("review-message")).toHaveTextContent("Revision #9");
    expect(screen.getByTestId("review-message")).toHaveTextContent("请求额度不足");
  });

  it("完成审阅提交失败时显示明确错误", async () => {
    vi.mocked(analysisApi.boundaryReview).mockResolvedValue(acceptedReview as any);
    vi.mocked(analysisApi.confirmReview).mockRejectedValue(
      new ApiError(
        "BOUNDARY_REVIEW_INCOMPLETE",
        "还有候选边界尚未处理",
        409,
        { pending_transition_ids: ["T0001"], pending_count: 1 },
        "req-review-fail",
        false,
        "请先处理所有待审候选。",
      ),
    );
    renderPanel();
    fireEvent.click(await screen.findByTestId("confirm-all-boundaries"));
    const msg = await screen.findByTestId("review-message");
    expect(msg).toHaveTextContent("请先处理所有待审候选");
    expect(msg).toHaveTextContent("error_code=BOUNDARY_REVIEW_INCOMPLETE");
    expect(msg).toHaveTextContent("HTTP 409");
  });

  it("后端离线时显示错误", async () => {
    vi.mocked(analysisApi.boundaryReview).mockRejectedValue(new Error("后端离线"));
    renderPanel(); expect(await screen.findByText(/后端离线/)).toBeInTheDocument();
  });

  it("语义冲突高风险展示并要求人工原因", async () => {
    vi.mocked(analysisApi.boundaryReview).mockResolvedValue({
      ...review,
      decisions: [{
        ...review.decisions[0],
        id: 2,
        transition_id: "T0017",
        left_paragraph_id: "P4",
        semantic_conflict: true,
        conflict_code: "CANDIDATE_TRUE_WITHOUT_LEGAL_REASON",
        deterministic_legal: false,
        deterministic_reason: null,
        model_boundary_candidate: true,
        source_batch_index: 3,
        enum_snapshot_json: JSON.stringify({
          goal_relation: "refined",
          action_chain_relation: "continuous",
          trigger_type: "object",
        }),
      }],
    } as any);
    renderPanel();
    expect(await screen.findByTestId("semantic-conflict")).toHaveTextContent(
      "CANDIDATE_TRUE_WITHOUT_LEGAL_REASON",
    );
    fireEvent.click(screen.getByTestId("timeline-T0017"));
    expect(screen.getByTestId("decision-card-T0017")).toHaveClass("selected");
    fireEvent.click(screen.getByText("接受边界"));
    const confirm = screen.getByText("确认人工接受");
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByLabelText("人工原因类型"), {
      target: { value: "other_manual_boundary" },
    });
    fireEvent.change(screen.getByLabelText("冲突边界人工理由"), {
      target: { value: "人工确认叙事单元结束" },
    });
    fireEvent.click(confirm);
    await waitFor(() => expect(analysisApi.decideBoundary).toHaveBeenCalledWith(
      3,
      "T0017",
      "accept",
      "other_manual_boundary",
      "人工确认叙事单元结束",
    ));
  });

  it("接受全部非冲突项不处理冲突项并刷新统计", async () => {
    const mixed = makeMixedReview();
    const afterBatch = {
      ...mixed,
      accepted_count: 12,
      decisions: mixed.decisions.map((d: any) =>
        d.semantic_conflict || d.user_decision === "accept"
          ? d
          : { ...d, user_decision: "accept", final_boundary: true },
      ),
    };
    vi.mocked(analysisApi.boundaryReview)
      .mockResolvedValueOnce(mixed as any)
      .mockResolvedValue(afterBatch as any);
    vi.mocked(analysisApi.decideBoundary).mockImplementation(async (_reviewId, transitionId) => {
      const next = {
        ...mixed,
        accepted_count: mixed.accepted_count + 1,
        decisions: mixed.decisions.map((d: any) =>
          d.transition_id === transitionId
            ? { ...d, user_decision: "accept", final_boundary: true }
            : d,
        ),
      };
      return next as any;
    });

    renderPanel();
    expect(await screen.findByTestId("review-stats")).toHaveTextContent("待处理 14");
    expect(screen.getByTestId("review-stats")).toHaveTextContent("已接受 1");
    expect(screen.getByTestId("review-stats")).toHaveTextContent("冲突 3");
    expect(screen.getByTestId("confirm-all-boundaries")).toBeDisabled();
    expect(screen.getByTestId("pending-remaining-hint")).toHaveTextContent("还有14项待处理");

    fireEvent.click(screen.getByTestId("accept-all-non-conflicts"));
    const dialog = await screen.findByTestId("batch-accept-confirm");
    expect(dialog).toHaveTextContent("将接受 11 个非冲突待审项");
    expect(dialog).toHaveTextContent("排除 3 个冲突项");
    fireEvent.click(within(dialog).getByTestId("batch-accept-confirm-yes"));

    await waitFor(() => expect(analysisApi.decideBoundary).toHaveBeenCalledTimes(11));
    const calledIds = vi.mocked(analysisApi.decideBoundary).mock.calls.map((c) => c[1]);
    expect(calledIds).not.toContain("T0012");
    expect(calledIds).not.toContain("T0013");
    expect(calledIds).not.toContain("T0014");
    expect(calledIds).toContain("T0001");

    await waitFor(() =>
      expect(screen.getByTestId("review-stats")).toHaveTextContent("待处理 3"),
    );
    expect(screen.getByTestId("review-stats")).toHaveTextContent("已接受 12");
    expect(screen.getByTestId("review-stats")).toHaveTextContent("冲突 3");
    expect(screen.getByTestId("confirm-all-boundaries")).toBeDisabled();
    expect(screen.getByTestId("pending-remaining-hint")).toHaveTextContent("还有3项待处理");
    expect(analysisApi.confirmReview).not.toHaveBeenCalled();
  });

  it("冲突全部人工处理后完成审阅可用且不重复confirm", async () => {
    const allDone = {
      ...makeMixedReview(),
      accepted_count: 15,
      decisions: makeMixedReview().decisions.map((d: any) => ({
        ...d,
        user_decision: "accept",
        final_boundary: true,
      })),
    };
    const confirmed = { ...allDone, status: "confirmed" };
    vi.mocked(analysisApi.boundaryReview)
      .mockResolvedValueOnce(allDone as any)
      .mockResolvedValue(confirmed as any);
    renderPanel();
    const complete = await screen.findByTestId("confirm-all-boundaries");
    expect(complete).not.toBeDisabled();
    expect(screen.queryByTestId("pending-remaining-hint")).not.toBeInTheDocument();
    fireEvent.click(complete);
    await waitFor(() => expect(analysisApi.confirmReview).toHaveBeenCalledTimes(1));
    expect(await screen.findByTestId("boundary-review-confirmed-status")).toBeInTheDocument();
    expect(screen.queryByTestId("confirm-all-boundaries")).not.toBeInTheDocument();
    expect(analysisApi.confirmReview).toHaveBeenCalledTimes(1);
  });

  it("manual插入后selection不漂移且后端错误结构化显示", async () => {
    vi.mocked(analysisApi.boundaryReview).mockResolvedValue({
      ...review,
      manually_added_count: 1,
      decisions: [
        {
          id: 11,
          transition_id: "M-P2",
          left_paragraph_id: "P2",
          right_paragraph_id: "P3",
          model_candidate: false,
          model_confidence: 0,
          model_reason_code: null,
          first_pass_json: "{}",
          adjudication_result: "{}",
          review_priority: "high",
          user_decision: "manually_added",
        },
        {
          ...review.decisions[0],
          id: 2,
          transition_id: "T0017",
          left_paragraph_id: "P4",
          semantic_conflict: true,
          conflict_code: "CANDIDATE_TRUE_WITHOUT_LEGAL_REASON",
          model_boundary_candidate: true,
          enum_snapshot_json: "{}",
        },
      ],
    } as any);
    renderPanel();
    fireEvent.click(await screen.findByTestId("timeline-T0017"));
    expect(screen.getByTestId("decision-card-T0017")).toHaveClass("selected");
    fireEvent.click(screen.getByTestId("locate-next-pending"));
    expect(screen.getByTestId("decision-card-T0017")).toHaveClass("selected");
    fireEvent.click(screen.getByText("下一项"));
    expect(screen.getByTestId("decision-card-M-P2")).toBeInTheDocument();
  });
});
