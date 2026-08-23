import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CrossBookSearchPage } from "./CrossBookSearchPage";
import { ApiError } from "../services/apiClient";

/** 跨书检索：在所有分析过的书里找东西。
 *
 *  这一页最要紧的一条不是「能不能搜到」，是**两种找法的覆盖面不一样这件事有没有说出来**。
 *  用户以为搜过了全部、其实只搜了写法层，「没找到」就会被读成「这些书里没有」——
 *  那是一个错的结论，而且他不会再问第二遍。
 */
const scope = vi.fn();
const search = vi.fn();
const byMeaning = vi.fn();

vi.mock("../services/crossBookApi", () => ({
  crossBookApi: {
    scope: (...a: unknown[]) => scope(...a),
    search: (...a: unknown[]) => search(...a),
    byMeaning: (...a: unknown[]) => byMeaning(...a),
  },
}));

const SCOPE = {
  book_count: 3,
  books: [{ book_id: 1, title: "甲书" }],
  item_count: 12388,
  craft_count: 195,
  kinds: [{ kind: "evidence", label: "原文证据", count: 5472 }],
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <CrossBookSearchPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function runSearch(text = "反转") {
  const input = await screen.findByTestId("cb-input");
  fireEvent.change(input, { target: { value: text } });
  fireEvent.click(screen.getByTestId("cb-run"));
}

afterEach(cleanup);

describe("跨书检索", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    scope.mockResolvedValue(SCOPE);
    search.mockResolvedValue({
      query: "反转",
      hits: [
        {
          book_id: 1,
          book_title: "甲书",
          kind: "technique",
          kind_label: "可复用技法",
          title: "身份倒转制造情感爆点",
          snippet: "在关键时刻揭示主角最亲近的人其实是凶手",
          chapter: null,
          matched: ["反转"],
          score: 9,
        },
      ],
      total: 5,
      truncated: false,
      searched_items: 12388,
      message: "",
    });
  });

  it("搜之前就说清楚两种找法各覆盖多少", async () => {
    // 「没找到」在「搜了 12388 条」和「搜了 195 条」之下是完全不同的两个结论。
    renderPage();
    const hint = await screen.findByTestId("cb-hint");
    expect(hint).toHaveTextContent("12,388");
    expect(hint).toHaveTextContent("195");
    expect(hint).toHaveTextContent("写法层");
  });

  it("关键词结果说清楚在多大范围里命中了几条", async () => {
    renderPage();
    await runSearch();
    const count = await screen.findByTestId("cb-keyword-count");
    expect(count).toHaveTextContent("12,388");
    expect(count).toHaveTextContent("5 条");
  });

  it("关键词零命中时把「按意思找」指出来，而不是只说没有", async () => {
    // 字面搜不到不等于书里没有——这正是另一半存在的理由。
    search.mockResolvedValue({
      query: "打破读者预期",
      hits: [],
      total: 0,
      truncated: false,
      searched_items: 12388,
      message: "",
    });
    renderPage();
    await runSearch("打破读者预期");
    const none = await screen.findByTestId("cb-keyword-none");
    expect(none).toHaveTextContent("一次都没出现");
    expect(none).toHaveTextContent("按意思找");
  });

  it("按意思找的结果带着「为什么符合」", async () => {
    // 没有这句，一条结果和一次随机命中没法区分。
    byMeaning.mockResolvedValue({
      query: "开场就打破预期",
      matches: [
        {
          book_id: 2,
          book_title: "乙书",
          kind: "technique",
          kind_label: "可复用技法",
          title: "用一句反常识的话立住人物",
          detail: "",
          chapter: null,
          why: "直接要求角色说一句与周围认知相悖的话，正是打破读者预期的核心手段。",
        },
      ],
      dropped: [],
      searched_craft_items: 195,
      total_craft_items: 195,
      truncated: false,
      scope_note: "按意思检索只覆盖「写法」层。",
      provider_name: "deepseek",
      model_name: "deepseek-v4-flash",
    });
    renderPage();
    await runSearch();
    fireEvent.click(await screen.findByTestId("cb-meaning-run"));
    const match = await screen.findByTestId("cb-match-technique");
    expect(match).toHaveTextContent("用一句反常识的话立住人物");
    expect(match).toHaveTextContent("正是打破读者预期的核心手段");
  });

  it("按意思找的结果里再说一遍它只看了写法层", async () => {
    byMeaning.mockResolvedValue({
      query: "x",
      matches: [],
      dropped: [],
      searched_craft_items: 195,
      total_craft_items: 195,
      truncated: false,
      scope_note: "按意思检索只覆盖「写法」层——技法、高光片段、配角功能、主要人物。",
      provider_name: "deepseek",
      model_name: "m",
    });
    renderPage();
    await runSearch();
    fireEvent.click(await screen.findByTestId("cb-meaning-run"));
    const note = await screen.findByTestId("cb-meaning-scope");
    expect(note).toHaveTextContent("只覆盖「写法」层");
    // 一条都没有时，说的是「写法层里没有」，不是「没有」。
    expect(await screen.findByTestId("cb-meaning-none")).toHaveTextContent("写法层里没有");
  });

  it("没有 Pro 时，免费那一半照样在", async () => {
    byMeaning.mockRejectedValue(
      new ApiError(
        "CROSS_BOOK_SEARCH_REQUIRES_PRO",
        "「按意思找」是 Pro 功能。上面的关键词检索保持免费。",
        403,
        { afdian_product_url: "https://example.test/pro", product_label: "StoryLens Pro" },
      ),
    );
    renderPage();
    await runSearch();
    fireEvent.click(await screen.findByTestId("cb-meaning-run"));
    const notice = await screen.findByTestId("cb-pro-required");
    expect(notice).toHaveTextContent("关键词检索保持免费");
    expect(notice.querySelector("a")).toHaveAttribute("href", "https://example.test/pro");
    expect(screen.getByTestId("cb-keyword")).toBeInTheDocument();
  });

  it("空输入不发请求", async () => {
    renderPage();
    await screen.findByTestId("cb-input");
    expect(screen.getByTestId("cb-run")).toBeDisabled();
    await waitFor(() => expect(search).not.toHaveBeenCalled());
  });
});
