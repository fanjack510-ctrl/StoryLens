/**
 * WB-2.2 / CHG-20260803-041 — chapter functions Free Desktop UI (Vitest).
 * Uses TEST-ONLY harness + fixtures; no formal DB / real provider.
 * Final WholeBookFreeProductPage module swap is NOT under test (Integration-owned).
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChapterFunctionsHarnessPage } from "./ChapterFunctionsHarnessPage";
import { ChapterFunctionsPanel } from "../components/wholeBookFree/chapterFunctions";
import { WHOLE_BOOK_FREE_MODULES } from "../services/wholeBookFreeProductApi";
import * as freeApiMod from "../services/wholeBookFreeProductApi";
import { functionLabelDisplayZh } from "../services/chapterFunctionsResultV2";
import {
  CHAPTER_FUNCTIONS_UI_FIXTURES,
  longBookPage,
} from "../components/wholeBookFree/chapterFunctions/fixtures/chapterFunctionsUiFixtures";
import { ApiError } from "../services/apiClient";

const getChapterFunctionsSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "getChapterFunctions");
const getChapterFunctionChapterSpy = vi.spyOn(
  freeApiMod.wholeBookFreeProductApi,
  "getChapterFunctionChapter",
);

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderHarness(search = "?fixture=A") {
  return render(
    <MemoryRouter initialEntries={[`/dev/whole-book-free-chapter-functions-harness${search}`]}>
      <Routes>
        <Route
          path="/dev/whole-book-free-chapter-functions-harness"
          element={<ChapterFunctionsHarnessPage />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("WB-2.2 chapter functions module table", () => {
  it("marks chapter_functions available in desktop module table (not Python registry)", () => {
    expect(WHOLE_BOOK_FREE_MODULES.find((m) => m.key === "chapter_functions")?.status).toBe(
      "available",
    );
    expect(WHOLE_BOOK_FREE_MODULES.filter((m) => m.status !== "pro_planned")).toHaveLength(4);
  });
});

describe("WB-2.2 chapter functions harness UI", () => {
  beforeEach(() => {
    getChapterFunctionsSpy.mockResolvedValue(CHAPTER_FUNCTIONS_UI_FIXTURES.A_available);
    getChapterFunctionChapterSpy.mockResolvedValue(CHAPTER_FUNCTIONS_UI_FIXTURES.A_available);
  });

  it("renders available primary/secondary and freeze labels", async () => {
    renderHarness("?fixture=A");
    const root = await screen.findByTestId("whole-book-free-chapter-functions");
    expect(root).toHaveAttribute("data-state", "available");
    const primaries = screen.getAllByTestId("cf-primary-label");
    expect(primaries[0]).toHaveAttribute("data-wire", "setup");
    expect(primaries[0]).toHaveTextContent("开篇/建立");
    expect(functionLabelDisplayZh("setup")).toBe("开篇/建立");
    expect(screen.queryByText("购买")).not.toBeInTheDocument();
    expect(screen.queryByText("VIP")).not.toBeInTheDocument();
    expect(screen.getByTestId("chapter-functions-harness-banner")).toHaveTextContent("TEST DATA");
  });

  it("renders primary=null and secondary empty without error UX", async () => {
    renderHarness("?fixture=C");
    await screen.findByTestId("cf-primary-null");
    expect(screen.getByTestId("cf-primary-null")).toHaveTextContent(
      "未识别出足够可靠的主要功能",
    );
    expect(screen.queryByText("分析失败")).not.toBeInTheDocument();

    cleanup();
    renderHarness("?fixture=D");
    await screen.findByTestId("cf-secondary-empty");
    expect(screen.getByTestId("cf-secondary-empty")).toHaveTextContent(
      "未识别出明确的辅助功能",
    );
  });

  it("renders multi-label secondary", async () => {
    renderHarness("?fixture=B");
    const secondary = await screen.findByTestId("cf-secondary-labels");
    expect(within(secondary).getByText("回溯")).toBeInTheDocument();
    expect(within(secondary).getByText("支线章")).toBeInTheDocument();
  });

  it("covers partial / insufficient / failed / canceled / conflict / absent / unsupported / loading", async () => {
    renderHarness("?fixture=E");
    expect(await screen.findByTestId("whole-book-free-chapter-functions")).toHaveAttribute(
      "data-state",
      "partial",
    );
    expect(screen.getByTestId("whole-book-free-chapter-functions-partial-banner")).toBeInTheDocument();

    cleanup();
    renderHarness("?fixture=F");
    expect(await screen.findByTestId("whole-book-free-chapter-functions")).toHaveAttribute(
      "data-state",
      "insufficient",
    );

    cleanup();
    renderHarness("?fixture=G");
    expect(await screen.findByTestId("whole-book-free-chapter-functions")).toHaveAttribute(
      "data-state",
      "failed",
    );

    cleanup();
    renderHarness("?fixture=H");
    expect(await screen.findByTestId("whole-book-free-chapter-functions")).toHaveAttribute(
      "data-state",
      "canceled",
    );

    cleanup();
    renderHarness("?fixture=I");
    expect(await screen.findByTestId("whole-book-free-chapter-functions")).toHaveAttribute(
      "data-state",
      "conflict",
    );

    cleanup();
    renderHarness("?fixture=K");
    expect(await screen.findByTestId("whole-book-free-chapter-functions")).toHaveAttribute(
      "data-state",
      "absent",
    );

    cleanup();
    renderHarness("?fixture=P");
    expect(await screen.findByTestId("whole-book-free-chapter-functions")).toHaveAttribute(
      "data-state",
      "unsupported_contract",
    );

    cleanup();
    renderHarness("?fixture=J");
    expect(await screen.findByTestId("whole-book-free-chapter-functions")).toHaveAttribute(
      "data-state",
      "loading",
    );
  });

  it("shows empty / non_mainline / unknown semantics notes", async () => {
    renderHarness("?fixture=U");
    expect(await screen.findByTestId("cf-semantics-empty")).toBeInTheDocument();
    cleanup();
    renderHarness("?fixture=V");
    expect(await screen.findByTestId("cf-semantics-non_mainline")).toBeInTheDocument();
    cleanup();
    renderHarness("?fixture=W");
    expect(await screen.findByTestId("cf-semantics-unknown")).toBeInTheDocument();
  });

  it("shows WB-2.1 context available / absent / insufficient without failing CF", async () => {
    renderHarness("?fixture=R");
    expect(await screen.findByTestId("whole-book-free-chapter-functions-wb21-context")).toHaveTextContent(
      "已使用",
    );
    expect(screen.getByTestId("whole-book-free-chapter-functions")).toHaveAttribute(
      "data-state",
      "available",
    );
    cleanup();
    renderHarness("?fixture=S");
    expect(await screen.findByTestId("whole-book-free-chapter-functions-wb21-context")).toHaveTextContent(
      "未使用",
    );
    cleanup();
    renderHarness("?fixture=T");
    expect(await screen.findByTestId("whole-book-free-chapter-functions-wb21-context")).toHaveTextContent(
      "不足",
    );
    expect(screen.getByTestId("whole-book-free-chapter-functions")).toHaveAttribute(
      "data-state",
      "available",
    );
  });

  it("paginates long-book fixture without rendering all 1299 rows", async () => {
    renderHarness("?fixture=L");
    await screen.findByTestId("whole-book-free-chapter-functions-list");
    const countEl = screen.getByTestId("chapter-functions-harness-item-count");
    expect(Number(countEl.textContent)).toBe(50);
    expect(screen.getByTestId("whole-book-free-chapter-functions-list").children.length).toBe(50);
    fireEvent.click(screen.getByTestId("whole-book-free-chapter-functions-load-more"));
    await waitFor(() => {
      expect(Number(screen.getByTestId("chapter-functions-harness-item-count").textContent)).toBe(
        100,
      );
    });
    expect(document.querySelectorAll('[data-testid^="whole-book-free-chapter-functions-row-"]').length).toBe(
      100,
    );
    expect(longBookPage(0).total_chapters).toBe(1299);
  });

  it("opens detail and preserves evidence return query state", async () => {
    renderHarness("?fixture=Q&restoreChapter=1&restoreFunction=climax");
    await screen.findByTestId("whole-book-free-chapter-functions-detail");
    expect(screen.getByTestId("whole-book-free-chapter-functions-detail")).toHaveAttribute(
      "data-chapter-id",
      "1",
    );
    expect(screen.getByTestId("whole-book-free-chapter-functions-filter-function")).toHaveValue(
      "climax",
    );
    fireEvent.click(screen.getByTestId("whole-book-free-chapter-functions-detail-evidence"));
    await waitFor(() => {
      expect(screen.getByTestId("chapter-functions-harness-evidence-opened")).toHaveTextContent(
        "601",
      );
    });
  });

  it("surfaces invalid cursor message", async () => {
    renderHarness("?fixture=O");
    expect(await screen.findByTestId("whole-book-free-chapter-functions-error-banner")).toHaveTextContent(
      "分页游标无效",
    );
  });

  it("calls server API for filters when online (not client full-book filter)", async () => {
    getChapterFunctionsSpy.mockResolvedValue(CHAPTER_FUNCTIONS_UI_FIXTURES.M_function_filter_setup);
    renderHarness("?runId=42");
    await screen.findByTestId("whole-book-free-chapter-functions");
    expect(getChapterFunctionsSpy).toHaveBeenCalled();
    fireEvent.change(screen.getByTestId("whole-book-free-chapter-functions-filter-function"), {
      target: { value: "setup" },
    });
    await waitFor(() => {
      expect(getChapterFunctionsSpy).toHaveBeenCalledWith(
        42,
        expect.objectContaining({ function: "setup" }),
      );
    });
  });

  it("maps 404 to CHAPTER_FUNCTIONS_RESULT_ABSENT via API client", async () => {
    getChapterFunctionsSpy.mockRejectedValue(
      new ApiError("CHAPTER_FUNCTIONS_RESULT_ABSENT", "absent", 404, {
        error_code: "CHAPTER_FUNCTIONS_RESULT_ABSENT",
      }),
    );
    renderHarness("?runId=99");
    expect(await screen.findByTestId("whole-book-free-chapter-functions")).toHaveAttribute(
      "data-state",
      "absent",
    );
  });
});

describe("ChapterFunctionsPanel presentational states", () => {
  it("renders presentational available body with no purchase UI", () => {
    const resp = CHAPTER_FUNCTIONS_UI_FIXTURES.A_available;
    render(
      <ChapterFunctionsPanel
        viewState="available"
        response={resp}
        items={resp.items}
        filters={{ function: "", status: "" }}
        onFiltersChange={() => undefined}
        onClearFilters={() => undefined}
        onSelectChapter={() => undefined}
        onOpenEvidence={() => undefined}
      />,
    );
    expect(screen.getByTestId("whole-book-free-chapter-functions-overview")).toBeInTheDocument();
    expect(screen.queryByText(/购买|License|VIP|升级套餐/)).not.toBeInTheDocument();
  });
});
