import { describe, expect, it } from "vitest";
import { resolveRunResultsViewState } from "./runResultsGuard";

const completed = {
  run: {
    id: 55,
    status: "succeeded",
    provider: "aliyun_qwen_plus",
    model: "qwen3.7-plus",
    prompt_version: "v3.5",
    schema_version: "1",
    analysis_mode: "assisted_boundary_review",
    execution_mode: "cloud",
  },
  chapter: { id: 2, book_id: 1, chapter_index: 1, title: "第二章" },
  boundary_revision: null,
  summary: {
    total_scene_count: 1,
    single_paragraph_scene_count: 0,
    longest_scene_paragraph_count: 2,
    manual_added_boundary_count: 0,
    model_accepted_boundary_count: 1,
    user_accepted_conflict_count: 0,
    artifact_coverage_rate: 1,
    evidence_coverage_rate: 1,
    offline_recovered_scene_count: 0,
  },
  scenes: [],
};

describe("resolveRunResultsViewState", () => {
  it("maps loading", () => {
    expect(resolveRunResultsViewState({ isLoading: true, error: null, data: undefined }).kind).toBe(
      "loading",
    );
  });

  it("maps missing for undefined and null", () => {
    expect(resolveRunResultsViewState({ isLoading: false, error: null, data: undefined }).kind).toBe(
      "missing",
    );
    expect(resolveRunResultsViewState({ isLoading: false, error: null, data: null }).kind).toBe(
      "missing",
    );
  });

  it("maps incomplete for empty object without run.status", () => {
    const state = resolveRunResultsViewState({ isLoading: false, error: null, data: {} });
    expect(state.kind).toBe("incomplete");
    if (state.kind === "incomplete") {
      expect(state.reason).toMatch(/run\.status/);
    }
  });

  it("maps incomplete when scenes missing", () => {
    const state = resolveRunResultsViewState({
      isLoading: false,
      error: null,
      data: { ...completed, scenes: undefined },
    });
    expect(state.kind).toBe("incomplete");
  });

  it("maps failed for non-succeeded status", () => {
    const state = resolveRunResultsViewState({
      isLoading: false,
      error: null,
      data: { ...completed, run: { ...completed.run, status: "failed" } },
    });
    expect(state.kind).toBe("failed");
    if (state.kind === "failed") expect(state.status).toBe("failed");
  });

  it("maps completed for valid results", () => {
    const state = resolveRunResultsViewState({
      isLoading: false,
      error: null,
      data: completed,
    });
    expect(state.kind).toBe("completed");
  });

  it("maps error", () => {
    const state = resolveRunResultsViewState({
      isLoading: false,
      error: new Error("boom"),
      data: undefined,
    });
    expect(state.kind).toBe("error");
  });
});
