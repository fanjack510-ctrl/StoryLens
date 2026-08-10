import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import analysisFixture from "./fixtures/analysisV2.json";
import { WholeBookV2ProductPage } from "./WholeBookV2ProductPage";
import * as v2Api from "./api";
import * as freeApiMod from "../../services/wholeBookFreeProductApi";

const REANALYSE_CONSENT_TEXT =
  "我已了解重新分析会调用我配置的大模型 API，并可能产生模型费用。";

const productFlagState = vi.hoisted(() => ({ enabled: true }));
const realProviderState = vi.hoisted(() => ({ enabled: true }));

vi.mock("../../services/wholeBookFreeProductFlag", async () => {
  const actual = await vi.importActual<typeof import("../../services/wholeBookFreeProductFlag")>(
    "../../services/wholeBookFreeProductFlag",
  );
  return {
    ...actual,
    isWholeBookFreeProductEnabled: () => productFlagState.enabled,
  };
});

vi.mock("../../services/wholeBookRealProviderFlag", async () => {
  const actual = await vi.importActual<typeof import("../../services/wholeBookRealProviderFlag")>(
    "../../services/wholeBookRealProviderFlag",
  );
  return {
    ...actual,
    isWholeBookRealProviderEnabled: () => realProviderState.enabled,
  };
});

vi.mock("../../services/settingsApi", () => ({
  settingsApi: {
    activeCloudProvider: vi.fn(async () => ({ provider_name: "deepseek" })),
  },
}));

const prepareSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "prepare");
const createRunSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "createRun");
const getV2Spy = vi.spyOn(v2Api, "getWholeBookV2");
const getProgressSpy = vi.spyOn(v2Api, "getWholeBookV2Progress");

const basePrepare = {
  book_id: 42,
  book_title: "余罪·V2验收样例",
  chapter_count: 36,
  character_count: 1683,
  mode: "free",
  mode_label: "原生全书分析",
  product_enabled: true,
  real_provider_enabled: true,
  run_creation_enabled: true,
  provider_available: true,
  active_provider_name: "deepseek",
  active_model_name: "deepseek-chat",
  context_safe: true,
  fixture_preview_enabled: false,
  recoverable_run: null,
  snapshot_rebuild_required: false,
  estimate: {
    estimate_id: 501,
    book_id: 42,
    mode: "free",
    estimated_windows: 12,
    estimated_provider_calls: 48,
    estimated_input_tokens: 120000,
    estimated_output_tokens: 32000,
    estimated_cost_min_cny: "2.50",
    estimated_cost_max_cny: "4.80",
    provider_name: "deepseek",
    model_name: "deepseek-chat",
    price_known: true,
    currency: "CNY",
  },
  recommended_limits: {
    max_provider_calls: 100,
    max_input_tokens: 200000,
    max_output_tokens: 50000,
    max_cost_budget_cny: "10.00",
  },
  blocking_reasons: [],
  warnings: [],
};

const completedV2Run = {
  run_id: 901,
  book_id: 42,
  status: "completed",
  mode: "free",
  engine_id: "hierarchical_v2",
  result_origin: "real_provider",
  snapshot_id: 1,
  started_at: null,
  completed_at: null,
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/books/42/whole-book"]}>
        <Routes>
          <Route path="/books/:bookId/whole-book" element={<WholeBookV2ProductPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("WholeBookV2ProductPage", () => {
  beforeEach(() => {
    productFlagState.enabled = true;
    realProviderState.enabled = true;
  });

  it("shows V2 nav labels when completed with v2 result", async () => {
    prepareSpy.mockResolvedValue({
      ...basePrepare,
      latest_run: completedV2Run,
      completed_v2_run: completedV2Run,
      active_run: null,
    } as never);

    getV2Spy.mockResolvedValue(analysisFixture as never);

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("whole-book-v2-report")).toBeInTheDocument();
    });
    expect(screen.getByTestId("whole-book-v2-formal-page")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /综合诊断/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /全书总览/ })).toBeInTheDocument();
    expect(screen.queryByText("DEV")).not.toBeInTheDocument();
    expect(getV2Spy).toHaveBeenCalled();
  });

  it("test_completed_v2_has_reanalyse_button", async () => {
    prepareSpy.mockResolvedValue({
      ...basePrepare,
      latest_run: completedV2Run,
      completed_v2_run: completedV2Run,
      active_run: null,
    } as never);
    getV2Spy.mockResolvedValue(analysisFixture as never);

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("whole-book-v2-reanalyse-button")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "重新分析 V2" })).toBeInTheDocument();
  });

  it("test_reanalyse_opens_estimate_confirmation (no create until confirm)", async () => {
    prepareSpy.mockResolvedValue({
      ...basePrepare,
      latest_run: completedV2Run,
      completed_v2_run: completedV2Run,
      active_run: null,
    } as never);
    getV2Spy.mockResolvedValue(analysisFixture as never);

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("whole-book-v2-reanalyse-button")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("whole-book-v2-reanalyse-button"));

    await waitFor(() => {
      expect(screen.getByTestId("whole-book-v2-reanalyse-confirm")).toBeInTheDocument();
    });
    expect(
      screen.getByText(/重新分析会创建新的 V2 分析任务。当前分析结果不会立即删除/),
    ).toBeInTheDocument();
    expect(createRunSpy).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    await waitFor(() => {
      expect(screen.queryByTestId("whole-book-v2-reanalyse-confirm")).not.toBeInTheDocument();
    });
    expect(screen.getByTestId("whole-book-v2-report")).toBeInTheDocument();
  });

  it("test_non_real_result_origin_shows_reanalysis_warning", async () => {
    const nonRealFixture = {
      ...analysisFixture,
      analysis_metadata: {
        ...analysisFixture.analysis_metadata,
        result_origin: "deterministic_test",
      },
      story: {
        ...analysisFixture.story,
        structure_stages: analysisFixture.story.structure_stages,
      },
    };

    prepareSpy.mockResolvedValue({
      ...basePrepare,
      latest_run: completedV2Run,
      completed_v2_run: completedV2Run,
      active_run: null,
    } as never);
    getV2Spy.mockResolvedValue(nonRealFixture as never);

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("whole-book-v2-nonreal-warning")).toBeInTheDocument();
    });
    expect(
      screen.getByText("当前结果不是完整真实 V2 分析，需要重新分析。"),
    ).toBeInTheDocument();
  });

  it("test_old_result_preserved_while_new_run_running (banner + view old)", async () => {
    const activeRun = {
      run_id: 902,
      book_id: 42,
      status: "running",
      mode: "free",
      engine_id: "hierarchical_v2",
      result_origin: "real_provider",
      snapshot_id: 1,
      started_at: null,
      completed_at: null,
    };

    prepareSpy.mockResolvedValue({
      ...basePrepare,
      latest_run: activeRun,
      active_run: activeRun,
      completed_v2_run: completedV2Run,
    } as never);

    getV2Spy.mockResolvedValue(analysisFixture as never);
    getProgressSpy.mockResolvedValue({
      schema_version: "whole-book-progress-v2.0",
      overall_percent: 35,
      current_stage: "extract_windows",
      stage_percent: 50,
      current_window: 3,
      total_windows: 12,
      current_chapter: 10,
      total_chapters: 36,
      provider_calls_completed: 5,
      provider_calls_estimated: 48,
      successful_calls: 5,
      failed_calls: 0,
      retry_calls: 0,
      repair_calls: 0,
      elapsed_seconds: 120,
      estimated_remaining_seconds: 300,
      estimated_cost: 1.2,
      estimated_actual_cost: 0.8,
      provider: "deepseek",
      model: "deepseek-chat",
      last_completed_action: "抽取窗口",
      current_action: "抽取窗口 3/12",
      last_activity_at: "2026-08-10T10:00:00Z",
    } as never);

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("whole-book-v2-reanalyse-running-banner")).toBeInTheDocument();
    });
    expect(screen.getByText("新的 V2 分析正在进行")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("whole-book-v2-progress")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "查看当前旧结果" }));

    await waitFor(() => {
      expect(screen.getByTestId("whole-book-v2-report")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("whole-book-v2-progress")).not.toBeInTheDocument();
    expect(getV2Spy).toHaveBeenCalledWith(901);
  });

  it("mock createRun asserts reanalyse/force flags and NEW client_request_id", async () => {
    const requestIds: string[] = [];
    createRunSpy.mockImplementation(async (_bookId, body) => {
      requestIds.push(body.client_request_id);
      return {
        run: {
          run_id: 903,
          book_id: 42,
          status: "running",
          mode: "free",
          engine_id: "hierarchical_v2",
          result_origin: "real_provider",
          snapshot_id: 1,
          started_at: null,
          completed_at: null,
        },
      } as never;
    });

    prepareSpy.mockResolvedValue({
      ...basePrepare,
      latest_run: completedV2Run,
      completed_v2_run: completedV2Run,
      active_run: null,
    } as never);
    getV2Spy.mockResolvedValue(analysisFixture as never);

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("whole-book-v2-reanalyse-button")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("whole-book-v2-reanalyse-button"));

    await waitFor(() => {
      expect(screen.getByTestId("whole-book-v2-reanalyse-confirm")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("whole-book-v2-force-full"));
    fireEvent.click(screen.getByRole("checkbox", { name: REANALYSE_CONSENT_TEXT }));
    fireEvent.click(screen.getByRole("button", { name: "确认开始重新分析" }));

    await waitFor(() => {
      expect(createRunSpy).toHaveBeenCalledTimes(1);
    });

    const call = createRunSpy.mock.calls[0];
    expect(call[0]).toBe(42);
    const body = call[1];
    expect(body.reanalyse).toBe(true);
    expect(body.force_full_reanalysis).toBe(true);
    expect(body.previous_run_id).toBe(901);
    expect(body.client_request_id).toBeTruthy();
    expect(typeof body.client_request_id).toBe("string");
    expect(requestIds).toHaveLength(1);
  });

  it("shows legacy notice when v2 returns 404", async () => {
    prepareSpy.mockResolvedValue({
      ...basePrepare,
      book_title: "旧版书",
      latest_run: {
        run_id: 902,
        book_id: 42,
        status: "completed",
        mode: "free",
        engine_id: "legacy",
        result_origin: "legacy",
        snapshot_id: 1,
        started_at: null,
        completed_at: null,
      },
      completed_v2_run: null,
      active_run: null,
    } as never);

    const { ApiError } = await import("../../services/apiClient");
    getV2Spy.mockRejectedValue(
      new ApiError("WHOLE_BOOK_V2_RESULT_NOT_FOUND", "V2 result is not available", 404, {
        error_code: "WHOLE_BOOK_V2_RESULT_NOT_FOUND",
      }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("whole-book-v2-legacy-notice")).toBeInTheDocument();
    });
    expect(
      screen.getByText("这是旧版全书分析结果，需要重新分析以生成 V2 完整结果。"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("whole-book-v2-report")).not.toBeInTheDocument();
  });

  it("does not fall back to mock fixture on non-404 API failure", async () => {
    prepareSpy.mockResolvedValue({
      ...basePrepare,
      book_title: "错误书",
      latest_run: completedV2Run,
      completed_v2_run: completedV2Run,
      active_run: null,
    } as never);

    const { ApiError } = await import("../../services/apiClient");
    getV2Spy.mockRejectedValue(new ApiError("INTERNAL_ERROR", "服务器错误", 500, {}));

    renderPage();

    await waitFor(() => {
      expect(screen.queryByTestId("whole-book-v2-report")).not.toBeInTheDocument();
    });
    expect(screen.queryByText("余罪·V2验收样例")).not.toBeInTheDocument();
  });
});
