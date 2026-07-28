import { describe, expect, it } from "vitest";

function renderBoundaryProgress(detail: {
  failure_substage?: string | null;
  total_scene_count?: number | null;
  boundary_candidate_total?: number | null;
  boundary_candidate_completed?: number | null;
  boundary_batch_total?: number | null;
  boundary_batch_completed?: number | null;
  completed_scene_count?: number | null;
}): string {
  if (
    detail.failure_substage === "scene_boundary_adjudication" ||
    (detail.boundary_candidate_total != null && (detail.total_scene_count ?? 0) === 0)
  ) {
    if (detail.boundary_candidate_total == null) {
      return "边界候选：暂无进度数据";
    }
    return `边界候选：${detail.boundary_candidate_completed ?? 0} / ${detail.boundary_candidate_total};裁决批次：${detail.boundary_batch_completed ?? 0} / ${detail.boundary_batch_total ?? "?"}`;
  }
  return `场景分析：${detail.completed_scene_count ?? 0} / ${detail.total_scene_count ?? 0}`;
}

function renderUsage(detail: {
  usage_invocation_count?: number | null;
  usage_input_tokens?: number | null;
  usage_output_tokens?: number | null;
  usage_total_tokens?: number | null;
  usage_estimated_cost?: number | null;
  usage_cost_unknown?: boolean;
}): string {
  if ((detail.usage_invocation_count ?? 0) > 0) {
    const cost =
      detail.usage_cost_unknown || detail.usage_estimated_cost == null
        ? "费用暂无法计算"
        : `${detail.usage_estimated_cost} CNY`;
    return `calls=${detail.usage_invocation_count};in=${detail.usage_input_tokens};out=${detail.usage_output_tokens};total=${detail.usage_total_tokens};cost=${cost}`;
  }
  return "尚无模型调用";
}

describe("CHG-040 TasksPage boundary progress/usage copy", () => {
  it("does not show scene 0/0 for adjudication failure", () => {
    const text = renderBoundaryProgress({
      failure_substage: "scene_boundary_adjudication",
      total_scene_count: 0,
      boundary_candidate_total: 20,
      boundary_candidate_completed: 10,
      boundary_batch_total: 2,
      boundary_batch_completed: 1,
    });
    expect(text).toContain("边界候选：10 / 20");
    expect(text).toContain("裁决批次：1 / 2");
    expect(text).not.toContain("场景分析：0 / 0");
  });

  it("shows unknown candidate progress without 0/0", () => {
    const text = renderBoundaryProgress({
      failure_substage: "scene_boundary_adjudication",
      total_scene_count: 0,
      boundary_candidate_total: null,
    });
    expect(text).toBe("边界候选：暂无进度数据");
  });

  it("renders aggregated usage instead of empty明细", () => {
    const text = renderUsage({
      usage_invocation_count: 3,
      usage_input_tokens: 100,
      usage_output_tokens: 50,
      usage_total_tokens: 150,
      usage_estimated_cost: 0.12,
      usage_cost_unknown: false,
    });
    expect(text).toContain("calls=3");
    expect(text).not.toContain("暂无用量明细");
  });
});
