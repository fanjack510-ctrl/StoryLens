import { describe, expect, it, vi, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { BookProfilePage } from "./BookProfilePage";
import * as api from "./api";

/**
 * The confirmation gate.
 *
 * What matters here is whose answer wins and whether the page can be answered dishonestly:
 * the axes are closed sets because they dispatch extraction deltas, and a profile that is
 * incomplete must not be confirmable — an axis nothing filled would otherwise be sent as an
 * empty string and read downstream as a decision.
 */

const DRAFT: api.BookProfile = {
  book_id: 1,
  status: "draft",
  axes: {
    monetization: { value: "paid_subscription", source: "L0-A" },
    audience: { value: "", source: "" },
    engine: { value: "mystery", source: "L0-B" },
    pov: { value: "ensemble", source: "L0-C", evidence: { share_first: 0.44, share_second: 0.12 } },
    length: { value: "long", source: "L0-A" },
  },
  disagreements: [{ axis: "pov", counted: "ensemble", read: "single_lead", kept: "ensemble" }],
  statistics: {
    chapters: 806, total_chars: 2402385, chapter_chars_median: 3103,
    chapter_chars_p10: 2762, chapter_chars_p90: 3281,
    paragraphs_per_chapter_median: 56, dialogue_ratio: 0.547,
    vocabulary_per_10k: { mystery: 2.67, romance: 1.57, progression: 0.84 },
  },
  name_deciles: { 邓肯: [9, 8, 6, 6, 5, 4, 8, 7, 8, 7], 阿加莎: [0, 0, 0, 1, 5, 8, 3, 2, 1, 1] },
  candidate_names: ["邓肯", "阿加莎"],
  sample_chapters: [1, 2, 3, 90, 179],
  options: [
    { axis: "monetization", options: [
      { value: "fast_food_free", label: "快餐免费流（番茄 / 七猫 / 书旗）" },
      { value: "paid_subscription", label: "付费订阅流（起点 / 晋江）" }] },
    { axis: "audience", options: [
      { value: "male_gratification", label: "男频爽文向" },
      { value: "female_romance", label: "女频情感向" },
      { value: "neutral", label: "中性 / 双向" }] },
    { axis: "engine", options: [{ value: "mystery", label: "悬疑推理" }] },
    { axis: "pov", options: [
      { value: "single_lead", label: "单主角" },
      { value: "ensemble", label: "群像多线" }] },
    { axis: "length", options: [{ value: "long", label: "长篇（150–400 万字）" }] },
  ],
  active_deltas: ["pov_entity"],
};

function renderPage(search = "?from=whole-book") {
  return render(
    <MemoryRouter initialEntries={[`/books/1/profile${search}`]}>
      <Routes>
        <Route path="/books/:bookId/profile" element={<BookProfilePage />} />
        <Route path="/books/:bookId/whole-book" element={<p>报告页</p>} />
        <Route path="/books/:bookId" element={<p>书籍工作台</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  // Without this each test renders on top of the last one and every query finds two.
  cleanup();
  vi.restoreAllMocks();
  vi.spyOn(api, "getBookProfile").mockResolvedValue(structuredClone(DRAFT));
});

describe("画像确认门", () => {
  it("每个轴都以下拉呈现，取值来自后端而不是页面自带的表", async () => {
    renderPage();
    const select = await screen.findByLabelText("变现模式");
    const labels = [...select.querySelectorAll("option")].map((o) => o.textContent);
    expect(labels).toContain("付费订阅流（起点 / 晋江）");
    // No free-text entry anywhere: a value the engine cannot dispatch on must be unreachable.
    expect(document.querySelectorAll("input[type=text]")).toHaveLength(0);
  });

  it("统计与采样判读不一致时，把分歧摆在最上面", async () => {
    renderPage();
    expect(await screen.findByText(/两种方法给出了不同答案/)).toBeInTheDocument();
  });

  it("有轴没填就不能确认——空值会被下游当成已决定", async () => {
    renderPage();
    const confirm = await screen.findByRole("button", { name: "确认并开始全书分析" });
    expect(confirm).toBeDisabled();
    expect(screen.getByText(/还有 情感主轴 没有选择/)).toBeInTheDocument();
  });

  it("用户改动后来源标为「你的选择」，并盖过推断值", async () => {
    const confirmSpy = vi.spyOn(api, "confirmBookProfile")
      .mockResolvedValue({ ...structuredClone(DRAFT), status: "confirmed" });
    renderPage();

    fireEvent.change(await screen.findByLabelText("情感主轴"), { target: { value: "neutral" } });
    fireEvent.change(screen.getByLabelText("视角结构"), { target: { value: "single_lead" } });
    expect(screen.getAllByText("你的选择").length).toBeGreaterThanOrEqual(2);

    fireEvent.click(screen.getByRole("button", { name: "确认并开始全书分析" }));
    await waitFor(() =>
      expect(confirmSpy).toHaveBeenCalledWith(1, expect.objectContaining({
        audience: "neutral",
        pov: "single_lead",
      })),
    );
  });

  it("从单章来时确认后回到本章，而不是被丢进全书分析", async () => {
    renderPage("?from=chapter&chapterId=807");
    fireEvent.change(await screen.findByLabelText("情感主轴"), { target: { value: "neutral" } });
    fireEvent.change(screen.getByLabelText("视角结构"), { target: { value: "single_lead" } });
    fireEvent.click(screen.getByRole("button", { name: "确认并分析本章" }));
    await waitFor(() => expect(screen.getByText("书籍工作台")).toBeInTheDocument());
    expect(screen.queryByText("报告页")).not.toBeInTheDocument();
  });

  it("会说明这套选择将额外提取什么", async () => {
    renderPage();
    expect(await screen.findByText(/将额外提取：pov_entity/)).toBeInTheDocument();
  });

  it("没有候选人名时，说明曲线为何是空的，而不是画一张空图", async () => {
    vi.spyOn(api, "getBookProfile").mockResolvedValue({
      ...structuredClone(DRAFT), name_deciles: {},
    });
    renderPage();
    expect(await screen.findByText(/采样判读尚未运行/)).toBeInTheDocument();
  });
});
