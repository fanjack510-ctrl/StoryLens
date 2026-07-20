import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LibraryPage } from "./LibraryPage";
import { useOnboardingStore } from "../stores/onboardingStore";
import { ApiError } from "../services/apiClient";

const preview = vi.fn();
const importFile = vi.fn();
const list = vi.fn();

vi.mock("../services/booksApi", () => ({
  booksApi: {
    list: (...args: unknown[]) => list(...args),
    preview: (...args: unknown[]) => preview(...args),
    importFile: (...args: unknown[]) => importFile(...args),
  },
}));

vi.mock("../components/onboarding/QwenFirstLaunchBanner", () => ({
  QwenFirstLaunchBanner: () => null,
}));

vi.mock("../components/onboarding/FirstLaunchWizard", () => ({
  FirstLaunchWizard: () => null,
}));

function renderLibrary() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <LibraryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("LibraryPage polish", () => {
  afterEach(cleanup);

  beforeEach(() => {
    list.mockReset();
    preview.mockReset();
    importFile.mockReset();
    useOnboardingStore.setState({ status: "completed" });
    list.mockResolvedValue([
      {
        id: 1,
        title: "虚构星港编年史",
        source_file_name: "fiction_starport.txt",
        source_file_hash: "abc",
        created_at: "2026-07-01T00:00:00Z",
        revision_number: 1,
      },
      {
        id: 2,
        title: "另一本很长很长很长很长很长很长很长很长很长很长很长很长的书名需要被截断显示两行以内",
        source_file_name: "long.docx",
        source_file_hash: "def",
        created_at: "2026-07-02T00:00:00Z",
        revision_number: 1,
      },
    ]);
  });

  it("keeps search filtering", async () => {
    renderLibrary();
    expect(await screen.findByTestId("book-row-1")).toBeInTheDocument();
    fireEvent.change(screen.getByTestId("library-search"), { target: { value: "星港" } });
    expect(screen.getByTestId("book-row-1")).toBeInTheDocument();
    expect(screen.queryByTestId("book-row-2")).not.toBeInTheDocument();
    fireEvent.change(screen.getByTestId("library-search"), { target: { value: "不存在xyz" } });
    expect(await screen.findByTestId("library-search-miss")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("library-clear-filters"));
    expect(await screen.findByTestId("book-row-1")).toBeInTheDocument();
  });

  it("keeps format filter chips and filters rows", async () => {
    renderLibrary();
    await screen.findByTestId("book-row-1");
    const docx = screen.getByRole("checkbox", { name: "DOCX" });
    fireEvent.click(docx);
    expect(screen.queryByTestId("book-row-2")).not.toBeInTheDocument();
    expect(screen.getByTestId("book-row-1")).toBeInTheDocument();
  });

  it("applies long title truncation class", async () => {
    renderLibrary();
    const row = await screen.findByTestId("book-row-2");
    const title = row.querySelector(".book-row-title");
    expect(title).toBeTruthy();
    expect(title?.textContent?.length).toBeGreaterThan(20);
  });

  it("drop handler still accepts files", async () => {
    preview.mockResolvedValue({
      encoding: "utf-8",
      byte_count: 1000,
      candidate_count: 1,
      final_chapter_count: 1,
      chapter_titles: ["第一章"],
      warning: null,
    });
    renderLibrary();
    const list = await screen.findByTestId("library-list");
    const file = new File(["hello"], "drop.txt", { type: "text/plain" });
    const dropEvent = new Event("drop", { bubbles: true, cancelable: true }) as DragEvent;
    Object.defineProperty(dropEvent, "dataTransfer", {
      value: { files: [file] },
    });
    list.dispatchEvent(dropEvent);
    await waitFor(() => expect(preview).toHaveBeenCalled());
    expect(preview.mock.calls[0][0]).toBe(file);
    expect(await screen.findByTestId("import-panel")).toHaveTextContent("文件已解析");
  });

  it("shows success and error import panels", async () => {
    preview.mockResolvedValue({
      encoding: "utf-8",
      byte_count: 1000,
      candidate_count: 3,
      final_chapter_count: 3,
      chapter_titles: ["一", "二", "三"],
      warning: null,
    });
    renderLibrary();
    await screen.findByTestId("import-book");
    fireEvent.change(document.querySelector('input[type="file"]') as HTMLInputElement, {
      target: { files: [new File(["a"], "ok.txt")] },
    });
    expect(await screen.findByTestId("import-panel")).toHaveTextContent("完成导入");

    cleanup();
    preview.mockRejectedValue(new ApiError("HTTP_ERROR", "不支持的文件格式", 400));
    renderLibrary();
    await screen.findByTestId("import-book");
    fireEvent.change(document.querySelector('input[type="file"]') as HTMLInputElement, {
      target: { files: [new File(["b"], "bad.bin")] },
    });
    expect(await screen.findByTestId("import-panel-error")).toHaveTextContent("文件格式不支持");
  });

  it("shows suspect import actions", async () => {
    preview.mockResolvedValue({
      encoding: "utf-8",
      byte_count: 12_000_000,
      candidate_count: 1,
      final_chapter_count: 1,
      chapter_titles: ["全文"],
      warning: "CHAPTER_DETECTION_SUSPECT",
    });
    renderLibrary();
    await screen.findByTestId("import-book");
    fireEvent.change(document.querySelector('input[type="file"]') as HTMLInputElement, {
      target: { files: [new File(["c"], "suspect.txt")] },
    });
    const panel = await screen.findByTestId("import-panel");
    expect(panel).toHaveTextContent("继续导入");
    expect(panel).toHaveTextContent("重新选择文件");
  });

  it("populated library does not force a large fixed min-height", async () => {
    renderLibrary();
    await screen.findByTestId("book-row-1");
    const list = screen.getByTestId("library-list");
    expect(list.className).toContain("library-main--populated");
    expect(list.className).not.toContain("library-main--empty");
    const globalCss = readFileSync(
      resolve(__dirname, "../styles/global.css"),
      "utf8",
    );
    expect(globalCss).toMatch(/\.library-main\s*\{[^}]*min-height:\s*0/);
    expect(globalCss).not.toMatch(/\.library-main\s*\{[^}]*min-height:\s*500px/);
  });
  it("empty library still shows EmptyState", async () => {
    list.mockResolvedValue([]);
    renderLibrary();
    expect(await screen.findByTestId("library-empty-state")).toBeInTheDocument();
    expect(screen.getByTestId("library-list").className).toContain("library-main--empty");
  });

  it("shows authentic duplicate upload warning", async () => {
    preview.mockResolvedValue({
      encoding: "utf-8",
      byte_count: 1000,
      candidate_count: 1,
      final_chapter_count: 1,
      chapter_titles: ["第一章"],
      warning: null,
    });
    importFile.mockRejectedValue(
      new ApiError("DUPLICATE_BOOK", "该文件已导入", 409, {}),
    );
    renderLibrary();
    await screen.findByTestId("import-book");
    fireEvent.change(document.querySelector('input[type="file"]') as HTMLInputElement, {
      target: { files: [new File(["dup"], "dup.txt")] },
    });
    expect(await screen.findByTestId("import-panel")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "完成导入" }));
    const alert = await screen.findByTestId("import-duplicate-alert");
    expect(alert).toHaveTextContent("书籍可能已存在");
    expect(alert).toHaveTextContent("该文件已导入");
    expect(alert.className).toContain("import-panel--warning");
  });

  it("ordinary library without duplicate alert cannot pass duplicate state check", async () => {
    renderLibrary();
    await screen.findByTestId("book-row-1");
    expect(screen.queryByTestId("import-duplicate-alert")).not.toBeInTheDocument();
    expect(screen.queryByText("书籍可能已存在")).not.toBeInTheDocument();
  });
});
