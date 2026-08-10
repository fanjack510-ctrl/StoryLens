import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import analysisFixture from "./fixtures/analysisV2.json";
import { WholeBookV2ProductPage } from "./WholeBookV2ProductPage";
import * as v2Api from "./api";
import * as freeApiMod from "../../services/wholeBookFreeProductApi";

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
const getV2Spy = vi.spyOn(v2Api, "getWholeBookV2");

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
      fixture_preview_enabled: false,
      latest_run: {
        run_id: 901,
        book_id: 42,
        status: "completed",
        mode: "free",
        engine_id: "hierarchical_v2",
        result_origin: "provider",
        snapshot_id: 1,
        started_at: null,
        completed_at: null,
      },
      recoverable_run: null,
      snapshot_rebuild_required: false,
      estimate: null,
      recommended_limits: {
        max_provider_calls: 100,
        max_input_tokens: 100000,
        max_output_tokens: 50000,
        max_cost_budget_cny: "10.00",
      },
      blocking_reasons: [],
      warnings: [],
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

  it("shows legacy notice when v2 returns 404", async () => {
    prepareSpy.mockResolvedValue({
      book_id: 42,
      book_title: "旧版书",
      chapter_count: 10,
      character_count: 1000,
      mode: "free",
      mode_label: "原生全书分析",
      product_enabled: true,
      real_provider_enabled: true,
      run_creation_enabled: true,
      provider_available: true,
      fixture_preview_enabled: false,
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
      recoverable_run: null,
      snapshot_rebuild_required: false,
      estimate: null,
      recommended_limits: {
        max_provider_calls: 100,
        max_input_tokens: 100000,
        max_output_tokens: 50000,
        max_cost_budget_cny: "10.00",
      },
      blocking_reasons: [],
      warnings: [],
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
      book_id: 42,
      book_title: "错误书",
      chapter_count: 10,
      character_count: 1000,
      mode: "free",
      mode_label: "原生全书分析",
      product_enabled: true,
      real_provider_enabled: true,
      run_creation_enabled: true,
      provider_available: true,
      fixture_preview_enabled: false,
      latest_run: {
        run_id: 903,
        book_id: 42,
        status: "completed",
        mode: "free",
        engine_id: "hierarchical_v2",
        result_origin: "provider",
        snapshot_id: 1,
        started_at: null,
        completed_at: null,
      },
      recoverable_run: null,
      snapshot_rebuild_required: false,
      estimate: null,
      recommended_limits: {
        max_provider_calls: 100,
        max_input_tokens: 100000,
        max_output_tokens: 50000,
        max_cost_budget_cny: "10.00",
      },
      blocking_reasons: [],
      warnings: [],
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
