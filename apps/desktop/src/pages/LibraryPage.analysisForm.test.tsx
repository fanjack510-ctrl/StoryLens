import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LibraryPage } from "./LibraryPage";

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

async function dropFile(
  suggested: "short" | "long",
  chapters: number,
  shortFormAllowed = true,
) {
  preview.mockResolvedValue({
    encoding: "utf-8",
    byte_count: 1000,
    candidate_count: chapters,
    final_chapter_count: chapters,
    chapter_titles: [],
    warning: null,
    suggested_analysis_form: suggested,
    short_form_allowed: shortFormAllowed,
    hard_max_chars: 150000,
  });
  importFile.mockResolvedValue({ book_id: 1 });
  renderLibrary();
  const target = await screen.findByTestId("library-list");
  const file = new File(["x"], "a.txt", { type: "text/plain" });
  const drop = new Event("drop", { bubbles: true, cancelable: true }) as DragEvent;
  Object.defineProperty(drop, "dataTransfer", { value: { files: [file] } });
  target.dispatchEvent(drop);
  await screen.findByTestId("import-panel");
  return file;
}

describe("导入时选长篇还是短篇", () => {
  afterEach(cleanup);
  beforeEach(() => {
    vi.clearAllMocks();
    list.mockResolvedValue([]);
  });

  it("默认勾选服务端给的建议，所以常见情况仍是一路点过去", async () => {
    await dropFile("short", 3);
    const short = screen.getByRole("radio", { name: /短篇/ }) as HTMLInputElement;
    const long = screen.getByRole("radio", { name: /长篇/ }) as HTMLInputElement;
    expect(short.checked).toBe(true);
    expect(long.checked).toBe(false);
  });

  it("改成长篇后，导入时送的是用户的答案而不是建议", async () => {
    // The point of the whole mechanism: the reader outranks the inference. 《一梦如初》 is two
    // chapters over the old limit, and no threshold move fixes that for every book.
    const file = await dropFile("short", 3);
    fireEvent.click(screen.getByRole("radio", { name: /长篇/ }));
    fireEvent.click(screen.getByRole("button", { name: "完成导入" }));
    await waitFor(() => expect(importFile).toHaveBeenCalled());
    expect(importFile).toHaveBeenCalledWith(file, "long");
  });

  it("不动它就按建议导入", async () => {
    const file = await dropFile("long", 40);
    fireEvent.click(screen.getByRole("button", { name: "完成导入" }));
    await waitFor(() => expect(importFile).toHaveBeenCalled());
    expect(importFile).toHaveBeenCalledWith(file, "long");
  });

  it("服务端没给建议时不至于没有选中项", async () => {
    // An older sidecar, or a preview stored before the field existed.
    preview.mockResolvedValue({
      encoding: "utf-8",
      byte_count: 1000,
      candidate_count: 1,
      final_chapter_count: 1,
      chapter_titles: [],
      warning: null,
    });
    importFile.mockResolvedValue({ book_id: 1 });
    renderLibrary();
    const target = await screen.findByTestId("library-list");
    const file = new File(["x"], "a.txt", { type: "text/plain" });
    const drop = new Event("drop", { bubbles: true, cancelable: true }) as DragEvent;
    Object.defineProperty(drop, "dataTransfer", { value: { files: [file] } });
    target.dispatchEvent(drop);
    await screen.findByTestId("import-panel");
    const long = screen.getByRole("radio", { name: /长篇/ }) as HTMLInputElement;
    expect(long.checked).toBe(true);
  });

  it("超过上限时短篇被禁用，并就地说明为什么", async () => {
    // The ceiling is not a preference: segmentation sends the whole piece in one call, so past
    // it there is no reading to be had. Shown disabled rather than removed — an option that
    // vanishes between one file and the next reads as a bug, not as a rule.
    await dropFile("long", 2, false);
    const short = screen.getByRole("radio", { name: /短篇/ }) as HTMLInputElement;
    expect(short.disabled).toBe(true);
    expect(short.checked).toBe(false);
    expect(screen.getByText(/超过 150,000 字，切段装不下/)).toBeTruthy();
    const long = screen.getByRole("radio", { name: /长篇/ }) as HTMLInputElement;
    expect(long.disabled).toBe(false);
    expect(long.checked).toBe(true);
  });

  it("上限之内两项都可选", async () => {
    await dropFile("short", 3, true);
    expect((screen.getByRole("radio", { name: /短篇/ }) as HTMLInputElement).disabled).toBe(false);
    expect((screen.getByRole("radio", { name: /长篇/ }) as HTMLInputElement).disabled).toBe(false);
  });
});
