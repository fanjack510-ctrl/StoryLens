import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BookWorkspacePage } from "./BookWorkspacePage";
import { booksApi } from "../services/booksApi";
import { analysisApi } from "../services/analysisApi";
import { useUiStore } from "../stores/uiStore";

vi.mock("../services/booksApi", () => ({
  booksApi: {
    detail: vi.fn(),
    chapters: vi.fn(),
    paragraphs: vi.fn(),
    diagnostics: vi.fn(),
  },
}));

vi.mock("../services/analysisApi", () => ({
  analysisApi: {
    scenes: vi.fn(),
    artifacts: vi.fn(),
    evidence: vi.fn(),
  },
}));

vi.mock("../components/analysis/StartAnalysisDialog", () => ({
  StartAnalysisDialog: () => null,
}));

vi.mock("../components/books/ReparseDialog", () => ({
  ReparseDialog: () => null,
}));

vi.mock("../components/analysis/BoundaryReviewPanel", () => ({
  BoundaryReviewPanel: () => null,
}));

function renderWorkspace(path = "/books/1") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/books/:bookId" element={<BookWorkspacePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("BookWorkspacePage polish", () => {
  beforeEach(() => {
    useUiStore.setState({
      fontSize: 17,
      lineHeight: 1.9,
      contentWidth: "wide",
      showParagraphIds: false,
    });
    vi.mocked(booksApi.detail).mockResolvedValue({
      id: 1,
      title: "虚构星港编年史",
      source_file_name: "harbor.txt",
      source_file_hash: "abc",
      created_at: "2026-01-01T00:00:00Z",
      revision_number: 1,
    } as any);
    vi.mocked(booksApi.chapters).mockResolvedValue([
      {
        id: 1,
        book_id: 1,
        chapter_index: 1,
        title: "第一章 潮汐钟",
        display_title: "第一章 潮汐钟",
        word_count: 100,
        section_type: "chapter",
        chapter_number_normalized: 1,
      },
      {
        id: 2,
        book_id: 1,
        chapter_index: 2,
        title: "第二章 星港夜航",
        display_title: "第二章 星港夜航",
        word_count: 100,
        section_type: "chapter",
        chapter_number_normalized: 2,
      },
    ] as any);
    vi.mocked(booksApi.paragraphs).mockResolvedValue({
      items: [
        { id: "B0001-C0001-P0001", chapter_id: 1, paragraph_index: 1, raw_text: "潮汐涌起。" },
      ],
      offset: 0,
      limit: 200,
      total: 1,
      has_more: false,
    } as any);
    vi.mocked(analysisApi.scenes).mockResolvedValue([]);
    vi.mocked(booksApi.diagnostics).mockResolvedValue({
      encoding: "utf-8",
      candidate_count: 2,
      final_chapter_count: 2,
    } as any);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("shows real book title, format meta, and chapter titles", async () => {
    renderWorkspace();
    expect(await screen.findByText("虚构星港编年史")).toBeInTheDocument();
    expect(screen.getByText(/TXT · 2 章/)).toBeInTheDocument();
    expect(screen.getAllByText("第一章 潮汐钟").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("第二章 星港夜航")).toBeInTheDocument();
    expect(screen.getAllByTitle("第一章 潮汐钟").length).toBeGreaterThanOrEqual(1);
  });

  it("keeps chapter switch behavior and does not render chapter items as inputs", async () => {
    renderWorkspace();
    await screen.findByText("第一章 潮汐钟");
    const chapter2 = screen.getByText("第二章 星港夜航").closest("button");
    expect(chapter2).toBeTruthy();
    expect(chapter2?.tagName).toBe("BUTTON");
    expect(chapter2?.querySelector("input")).toBeNull();
    fireEvent.click(chapter2!);
    await waitFor(() => {
      expect(booksApi.paragraphs).toHaveBeenCalledWith(2, 0, 200);
    });
  });

  it("shows scene empty state without input-like scene rows", async () => {
    renderWorkspace();
    expect(await screen.findByTestId("workspace-scene-empty")).toHaveTextContent("尚未生成场景");
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("renders scene ordinal and name from data without a lone S column", async () => {
    vi.mocked(analysisApi.scenes).mockResolvedValue([
      {
        id: 9,
        scene_key: "客厅",
        chapter_id: 1,
        ordinal: 1,
        start_paragraph_id: "a",
        end_paragraph_id: "b",
        created_by_run_id: 1,
        boundary_detected: false,
        boundary_confidence: 0.5,
      },
    ] as any);
    renderWorkspace();
    expect(await screen.findByText("S01")).toBeInTheDocument();
    expect(screen.getByText("客厅")).toBeInTheDocument();
    expect(screen.getByText("章末")).toBeInTheDocument();
    const sceneBtn = screen.getByText("客厅").closest("button");
    expect(sceneBtn?.querySelector("input")).toBeNull();
  });

  it("shows empty body state for chapters without paragraphs", async () => {
    vi.mocked(booksApi.paragraphs).mockResolvedValue({
      items: [],
      offset: 0,
      limit: 200,
      total: 0,
      has_more: false,
    } as any);
    renderWorkspace();
    expect(await screen.findByTestId("workspace-empty-body")).toHaveTextContent(
      "这个章节没有可显示的正文",
    );
  });

  it("preserves import diagnostics and reparse entry points", async () => {
    renderWorkspace();
    await screen.findByText("虚构星港编年史");
    fireEvent.click(screen.getByRole("button", { name: "导入诊断" }));
    await waitFor(() => expect(booksApi.diagnostics).toHaveBeenCalledWith(1));
    expect(screen.getByRole("button", { name: "重新识别章节" })).toBeInTheDocument();
  });

  it("tool labels stay on a single visual line", async () => {
    renderWorkspace();
    await screen.findByText("虚构星港编年史");
    const tools = document.querySelector(".workspace-book-tools-actions");
    expect(tools).toBeTruthy();
    expect(within(tools as HTMLElement).getByText("导入诊断").className).toContain(
      "workspace-tool-link",
    );
    expect(within(tools as HTMLElement).getByText("重新识别章节").className).toContain(
      "workspace-tool-link",
    );
  });
});
