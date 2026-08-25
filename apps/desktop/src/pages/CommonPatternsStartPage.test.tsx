import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CommonPatternsStartPage } from "./CommonPatternsStartPage";

/** 共性视图的第一步：挑几本要比的书。
 *
 *  这一页是从书库首页搬过来的。用户的原话：「这里两个书单是什么意思？为啥上来要建书单？
 *  这个功能最终不就是为了提炼共性，那是不是应该统一在共性分析大功能下？」
 *
 *  搬家最容易丢的就是搬走的那几条判断。下面钉的正是它们：
 *  工具书比不了、一本书没有共性、不起名也能比。
 */
const library = vi.fn();
const collectionsList = vi.fn();
const collectionsCreate = vi.fn();
const collectionsAdd = vi.fn();
const navigate = vi.fn();

vi.mock("../services/booksApi", () => ({
  booksApi: { library: (...a: unknown[]) => library(...a) },
}));

vi.mock("../services/collectionsApi", () => ({
  collectionsApi: {
    list: (...a: unknown[]) => collectionsList(...a),
    create: (...a: unknown[]) => collectionsCreate(...a),
    addBooks: (...a: unknown[]) => collectionsAdd(...a),
  },
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<Record<string, unknown>>("react-router-dom");
  return { ...actual, useNavigate: () => navigate };
});

function row(id: number, title: string, kind: "fiction" | "reference") {
  return {
    id,
    title,
    source_file_name: "",
    format: "TXT",
    created_at: null,
    material_kind: kind,
    material_kind_confirmed: true,
    kind_label: kind === "reference" ? "工具书" : "小说 · 长篇",
    chapter_count: 100,
    analysis_state: "done" as const,
    analysis_state_label: "已拆文",
    last_activity_at: null,
  };
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <CommonPatternsStartPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => cleanup());

describe("挑书这一步", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    library.mockResolvedValue([
      row(1, "甲书", "fiction"),
      row(2, "乙书", "fiction"),
      row(3, "手册", "reference"),
    ]);
    collectionsList.mockResolvedValue([]);
  });

  it("工具书比不了，灰掉并说明原因", async () => {
    // 共性视图比的是小说怎么写；「读懂」的产出不在这个维度上。
    // 让人选完拿到一屏空结果，比一开始就说清楚更糟。
    renderPage();
    const blocked = await screen.findByTestId("cp-pick-3");
    expect(blocked).toBeDisabled();
    expect(blocked).toHaveTextContent("比不了");
  });

  it("只挑一本时开始按钮点不动", async () => {
    // 一本书没有「共性」可言。两本才谈得上「它们共同做对了什么」。
    renderPage();
    fireEvent.click(await screen.findByTestId("cp-pick-1"));
    expect(await screen.findByTestId("cp-count")).toHaveTextContent("已选 1 本");
    expect(screen.getByTestId("cp-start")).toBeDisabled();
  });

  it("书很多时可以搜索，比较篮子仍单独显示已选书", async () => {
    renderPage();
    fireEvent.click(await screen.findByTestId("cp-pick-1"));
    expect(screen.getByTestId("cp-selected-list")).toHaveTextContent("甲书");

    fireEvent.change(screen.getByLabelText("搜索要比较的小说"), { target: { value: "乙书" } });
    expect(screen.queryByTestId("cp-pick-1")).toBeNull();
    expect(screen.getByTestId("cp-pick-2")).toHaveTextContent("乙书");
    expect(screen.getByTestId("cp-selected-list")).toHaveTextContent("甲书");
  });

  it("挑够两本就能比，不起名也能比", async () => {
    // 起名是可选的——**要求人在还不知道要比什么之前先给一个组命名，顺序就是反的**。
    // 不起名时自动打一个显然是临时的标签，而不是拦住他。
    collectionsCreate.mockResolvedValue({ id: 9, name: "临时", note: "", book_count: 0 });
    collectionsAdd.mockResolvedValue({ added: 2, book_count: 2 });
    renderPage();
    fireEvent.click(await screen.findByTestId("cp-pick-1"));
    fireEvent.click(await screen.findByTestId("cp-pick-2"));
    expect(screen.getByTestId("cp-start")).not.toBeDisabled();
    fireEvent.click(screen.getByTestId("cp-start"));
    await waitFor(() => expect(collectionsCreate).toHaveBeenCalled());
    const arg = collectionsCreate.mock.calls[0][0] as { name: string };
    expect(arg.name).toContain("临时比较");
    await waitFor(() => expect(collectionsAdd).toHaveBeenCalledWith(9, [1, 2]));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/collections/9/patterns"));
  });

  it("起了名字就用那个名字", async () => {
    collectionsCreate.mockResolvedValue({ id: 4, name: "扫榜", note: "", book_count: 0 });
    collectionsAdd.mockResolvedValue({ added: 2, book_count: 2 });
    renderPage();
    fireEvent.click(await screen.findByTestId("cp-pick-1"));
    fireEvent.click(await screen.findByTestId("cp-pick-2"));
    fireEvent.change(screen.getByLabelText("这一组的名字"), { target: { value: "扫榜" } });
    fireEvent.click(screen.getByTestId("cp-start"));
    await waitFor(() => expect(collectionsCreate).toHaveBeenCalledWith({ name: "扫榜" }));
  });

  it("存过的组直接列出来，不用重挑", async () => {
    collectionsList.mockResolvedValue([
      { id: 7, name: "上次那批", note: "", book_count: 3, created_at: null, updated_at: null },
    ]);
    renderPage();
    const saved = await screen.findByTestId("cp-saved");
    expect(saved).toHaveTextContent("上次那批");
    expect(saved.querySelector('a[href="/collections/7/patterns"]')).not.toBeNull();
  });
});
