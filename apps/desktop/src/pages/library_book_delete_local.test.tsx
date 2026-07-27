/**
 * Library book delete — local Vitest (CHG-20260721-014).
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LibraryPage } from "./LibraryPage";
import { booksApi } from "../services/booksApi";
import { ApiError } from "../services/apiClient";
import { useOnboardingStore } from "../stores/onboardingStore";

vi.mock("../services/booksApi", () => ({
  booksApi: {
    list: vi.fn(),
    importFile: vi.fn(),
    preview: vi.fn(),
    delete: vi.fn(),
  },
}));

const sampleBooks = [
  {
    id: 11,
    title: "临时测试书",
    source_file_name: "temp.txt",
    source_file_hash: "abc",
    created_at: "2026-07-21T10:00:00Z",
    import_status: "imported",
  },
  {
    id: 12,
    title: "另一本书",
    source_file_name: "other.docx",
    source_file_hash: "def",
    created_at: "2026-07-20T10:00:00Z",
    import_status: "imported",
  },
];

let booksState = [...sampleBooks];

function renderLibrary() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <LibraryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("library book delete (CHG-014)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    booksState = [...sampleBooks];
    useOnboardingStore.setState({ status: "completed" } as any);
    vi.mocked(booksApi.list).mockImplementation(async () => booksState as any);
    vi.mocked(booksApi.delete).mockImplementation(async (id: number) => {
      booksState = booksState.filter((book) => book.id !== id);
    });
  });

  afterEach(() => cleanup());

  it("shows more menu with delete action", async () => {
    renderLibrary();
    expect(await screen.findByTestId("book-more-11-trigger")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("book-more-11-trigger"));
    expect(screen.getByTestId("book-delete-11")).toHaveTextContent("删除书籍");
  });

  it("does not call API until confirmed", async () => {
    renderLibrary();
    fireEvent.click(await screen.findByTestId("book-more-11-trigger"));
    fireEvent.click(screen.getByTestId("book-delete-11"));
    expect(await screen.findByTestId("book-delete-dialog-11")).toBeInTheDocument();
    expect(booksApi.delete).not.toHaveBeenCalled();
    expect(screen.getByTestId("book-delete-original-note-11")).toHaveTextContent("不会删除");
  });

  it("cancel keeps the book", async () => {
    renderLibrary();
    fireEvent.click(await screen.findByTestId("book-more-11-trigger"));
    fireEvent.click(screen.getByTestId("book-delete-11"));
    fireEvent.click(await screen.findByTestId("book-delete-cancel-11"));
    expect(screen.queryByTestId("book-delete-dialog-11")).not.toBeInTheDocument();
    expect(booksApi.delete).not.toHaveBeenCalled();
    expect(screen.getByTestId("book-row-11")).toBeInTheDocument();
  });

  it("Escape cancels without deleting", async () => {
    renderLibrary();
    fireEvent.click(await screen.findByTestId("book-more-11-trigger"));
    fireEvent.click(screen.getByTestId("book-delete-11"));
    await screen.findByTestId("book-delete-dialog-11");
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() =>
      expect(screen.queryByTestId("book-delete-dialog-11")).not.toBeInTheDocument(),
    );
    expect(booksApi.delete).not.toHaveBeenCalled();
  });

  it("confirm sends a single DELETE and removes the row", async () => {
    renderLibrary();
    fireEvent.click(await screen.findByTestId("book-more-11-trigger"));
    fireEvent.click(screen.getByTestId("book-delete-11"));
    fireEvent.click(await screen.findByTestId("book-delete-confirm-11"));
    await waitFor(() => expect(booksApi.delete).toHaveBeenCalledTimes(1));
    expect(booksApi.delete).toHaveBeenCalledWith(11);
    await waitFor(() => expect(screen.queryByTestId("book-row-11")).not.toBeInTheDocument());
    expect(screen.getByTestId("library-delete-toast")).toHaveTextContent("临时测试书");
    expect(screen.getByTestId("book-row-12")).toBeInTheDocument();
  });

  it("keeps row and shows message when active tasks block delete", async () => {
    vi.mocked(booksApi.delete).mockRejectedValue(
      new ApiError("BOOK_HAS_ACTIVE_TASKS", "busy", 409),
    );
    renderLibrary();
    fireEvent.click(await screen.findByTestId("book-more-11-trigger"));
    fireEvent.click(screen.getByTestId("book-delete-11"));
    fireEvent.click(await screen.findByTestId("book-delete-confirm-11"));
    expect(await screen.findByTestId("book-delete-error-11")).toHaveTextContent(
      "正在运行的分析任务",
    );
    expect(screen.getByTestId("book-row-11")).toBeInTheDocument();
    expect(screen.getByTestId("book-delete-goto-tasks-11")).toBeInTheDocument();
  });

  it("dialog title includes book name", async () => {
    renderLibrary();
    fireEvent.click(await screen.findByTestId("book-more-11-trigger"));
    fireEvent.click(screen.getByTestId("book-delete-11"));
    expect(await screen.findByRole("heading", { name: "删除《临时测试书》？" })).toBeInTheDocument();
  });
});
