import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CommonPatternsPage } from "./CommonPatternsPage";
import { ApiError } from "../services/apiClient";

/** 共性视图：把一组书摆在一起，看它们共同做对了什么。
 *
 *  这个功能最容易变成一段「看起来很有道理的废话」。后端用引用核对挡住编造的条目，
 *  界面这一层要做的是**把那些引用摆在结论旁边**——一条共性如果不能立刻看到它凭什么，
 *  它和一句漂亮话没有区别。
 */
const overview = vi.fn();
const synthesize = vi.fn();
const readCollection = vi.fn();
const exportPdf = vi.fn();

vi.mock("../services/commonPatternsApi", () => ({
  commonPatternsApi: {
    overview: (...a: unknown[]) => overview(...a),
    synthesize: (...a: unknown[]) => synthesize(...a),
  },
}));

vi.mock("../services/collectionsApi", () => ({
  collectionsApi: {
    read: (...a: unknown[]) => readCollection(...a),
  },
}));

vi.mock("../features/commonPatterns/commonPatternsExport", async (importOriginal) => {
  const original = await importOriginal<typeof import("../features/commonPatterns/commonPatternsExport")>();
  return { ...original, downloadCommonPatternsPdf: (...a: unknown[]) => exportPdf(...a) };
});

const BASE_OVERVIEW = {
  books: [
    {
      book_id: 1,
      title: "甲书",
      usable: true,
      excluded_reason: "",
      primary_genre: "悬疑",
      chapters_analysed: 100,
      chapters_total: 100,
      scope_kind: "full" as const,
      scope_label: "全书 100 章",
      technique_count: 8,
      hook_count: 96,
      hooks_per_chapter: 0.96,
      standout_moment_count: 12,
    },
    {
      book_id: 2,
      title: "乙书",
      usable: true,
      excluded_reason: "",
      primary_genre: "悬疑",
      chapters_analysed: 5,
      chapters_total: 542,
      scope_kind: "opening" as const,
      scope_label: "开篇 5 章 / 全书 542 章",
      technique_count: 6,
      hook_count: 2,
      hooks_per_chapter: 0.4,
      standout_moment_count: 2,
    },
    {
      book_id: 3,
      title: "丙工具书",
      usable: false,
      excluded_reason: "这是工具书——共性视图比的是小说怎么写",
      primary_genre: "",
      chapters_analysed: 0,
      chapters_total: 0,
      scope_kind: "full" as const,
      scope_label: "",
      technique_count: 0,
      hook_count: 0,
      hooks_per_chapter: null,
      standout_moment_count: 0,
    },
  ],
  usable_count: 2,
  total_count: 3,
  genres: [{ genre: "悬疑", count: 2 }],
  technique_total: 14,
  opening_only_count: 1,
  mixed_scope: true,
  can_synthesize: true,
  min_books: 2,
  blocked_reason: "",
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/collections/7/patterns"]}>
        <Routes>
          <Route path="/collections/:collectionId/patterns" element={<CommonPatternsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(cleanup);

describe("共性视图", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    readCollection.mockResolvedValue({ id: 7, name: "扫榜第一批", note: "", book_count: 3, books: [] });
    overview.mockResolvedValue(BASE_OVERVIEW);
  });

  it("数出来的那一半不需要付费就能看", async () => {
    // 把它一起锁上，用户在付钱之前无法判断这组书值不值得归纳。
    renderPage();
    await screen.findByTestId("cp-counted");
    expect(screen.getByTestId("cp-genres")).toHaveTextContent("悬疑");
    const table = screen.getByTestId("cp-book-table");
    expect(within(table).getByText("甲书")).toBeInTheDocument();
    expect(screen.getByTestId("cp-counted")).toHaveTextContent("数出来的");
  });

  it("只拆了开篇的书，范围一路跟到这一屏", async () => {
    // 五章的观察不能冒充整本的规律。这句提醒和每一行的「读到哪儿」是同一件事的两处说明。
    renderPage();
    const warn = await screen.findByTestId("cp-mixed-scope");
    expect(warn).toHaveTextContent("1 本只拆了开篇");
    expect(screen.getByTestId("cp-book-2")).toHaveTextContent("开篇 5 章 / 全书 542 章");
  });

  it("进不了比较的书说明原因，而不是消失", async () => {
    // 从比较里消失而不说明原因，用户会以为自己选错了书。
    renderPage();
    const row = await screen.findByTestId("cp-book-3");
    expect(row).toHaveAttribute("data-usable", "false");
    expect(row).toHaveTextContent("这是工具书");
  });

  it("钩子按每章报，不报原始计数", async () => {
    // 96 个钩子和 2 个钩子没有可比性，除非知道分别是 100 章和 5 章。
    renderPage();
    expect(await screen.findByTestId("cp-book-1")).toHaveTextContent("0.96");
    expect(screen.getByTestId("cp-book-2")).toHaveTextContent("0.4");
  });

  it("每条共性都摊开它引用的书和技法名", async () => {
    synthesize.mockResolvedValue({
      ...BASE_OVERVIEW,
      provider_name: "deepseek",
      model_name: "deepseek-v4-flash",
      patterns: [
        {
          name: "用认知冲突立人物",
          what_they_do: "让角色说一句与预期相反的话",
          why_it_works: "打破刻板印象",
          book_count: 2,
          instances: [
            { book_id: 1, book_title: "甲书", technique_name: "反常识开场", how_this_book_does_it: "" },
            { book_id: 2, book_title: "乙书", technique_name: "粗俗细节破严肃", how_this_book_does_it: "" },
          ],
        },
      ],
      not_shared: [],
    });
    renderPage();
    fireEvent.click(await screen.findByTestId("cp-run"));

    const card = await screen.findByTestId("cp-pattern-用认知冲突立人物");
    expect(card).toHaveTextContent("2 本书这么做");
    // 引用不是脚注，是这条结论能不能信的全部依据——所以它必须和结论同屏。
    expect(card).toHaveTextContent("甲书");
    expect(card).toHaveTextContent("反常识开场");
    expect(card).toHaveTextContent("乙书");
    expect(card).toHaveTextContent("粗俗细节破严肃");
  });

  it("说清楚这一半是谁归纳的", async () => {
    // 数出来的和归纳出来的可信度不一样，界面不标明来源，读的人就分不清哪一半可以直接信。
    synthesize.mockResolvedValue({
      ...BASE_OVERVIEW,
      provider_name: "deepseek",
      model_name: "deepseek-v4-flash",
      patterns: [],
      not_shared: [],
    });
    renderPage();
    fireEvent.click(await screen.findByTestId("cp-run"));
    expect(await screen.findByTestId("cp-provenance")).toHaveTextContent("deepseek-v4-flash");
  });

  it("共性结果生成后可以导出结构化 PDF", async () => {
    const result = {
      ...BASE_OVERVIEW,
      provider_name: "deepseek",
      model_name: "deepseek-v4-flash",
      patterns: [],
      not_shared: [],
    };
    synthesize.mockResolvedValue(result);
    exportPdf.mockResolvedValue(undefined);
    renderPage();
    expect(screen.queryByTestId("cp-export-pdf")).toBeNull();
    fireEvent.click(await screen.findByTestId("cp-run"));
    fireEvent.click(await screen.findByTestId("cp-export-pdf"));
    await waitFor(() => expect(exportPdf).toHaveBeenCalledWith(7, "扫榜第一批", result));
  });

  it("一条共性都没有时说的是「没找到」，不是空白", async () => {
    // 空白会被读成「还没跑」。而「没找到共同手法」对一组风格差得远的书来说是正确答案。
    synthesize.mockResolvedValue({
      ...BASE_OVERVIEW,
      provider_name: "deepseek",
      model_name: "m",
      patterns: [],
      not_shared: [],
    });
    renderPage();
    fireEvent.click(await screen.findByTestId("cp-run"));
    expect(await screen.findByTestId("cp-none")).toHaveTextContent("没有找到站得住的共同手法");
  });

  it("没有 Pro 时说清楚锁的是哪一半", async () => {
    synthesize.mockRejectedValue(
      new ApiError(
        "COMMON_PATTERNS_REQUIRES_PRO",
        "共性视图是 Pro 功能。上面那一屏保持免费。",
        403,
        { afdian_product_url: "https://example.test/pro", product_label: "StoryLens Pro" },
      ),
    );
    renderPage();
    fireEvent.click(await screen.findByTestId("cp-run"));
    const notice = await screen.findByTestId("cp-pro-required");
    expect(notice).toHaveTextContent("上面那一屏保持免费");
    expect(notice.querySelector("a")).toHaveAttribute("href", "https://example.test/pro");
    // 免费那一半仍然在，没有被一起锁掉。
    expect(screen.getByTestId("cp-book-table")).toBeInTheDocument();
  });

  it("书不够两本时，按钮不出现，说的是还差什么", async () => {
    overview.mockResolvedValue({
      ...BASE_OVERVIEW,
      usable_count: 1,
      can_synthesize: false,
      blocked_reason: "至少要有 2 本拆过文的书才谈得上共性——现在只有 1 本。",
    });
    renderPage();
    expect(await screen.findByTestId("cp-blocked")).toHaveTextContent("至少要有 2 本");
    expect(screen.queryByTestId("cp-run")).toBeNull();
  });
});
