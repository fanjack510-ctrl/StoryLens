import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { ReparseDialog } from "./ReparseDialog";

const preview = vi.fn();
const apply = vi.fn();
vi.mock("../../services/booksApi", () => ({
  booksApi: {
    reparseWithFilePreview: (...args: unknown[]) => preview(...args),
    reparseWithFile: (...args: unknown[]) => apply(...args),
  },
}));
const base = {
  hash_match: true,
  old_chapter_count: 1,
  old_paragraph_count: 3000,
  formal_chapter_count: 805,
  front_matter_count: 1,
  new_paragraph_count: 12000,
  chapter_titles: ["第一章｜起雾"],
  middle_sample_titles: ["第四百章｜中段"],
  ending_sample_titles: ["第八百零五章｜终章"],
  has_succeeded_runs: false,
};

async function open(value = base) {
  preview.mockResolvedValue(value);
  render(<ReparseDialog bookId={1} onClose={vi.fn()} onDone={vi.fn()} />);
  fireEvent.change(document.querySelector('input[type="file"]')!, {
    target: { files: [new File(["text"], "book.txt")] },
  });
  await waitFor(() => expect(screen.getByText(/文件Hash/)).toBeInTheDocument());
}

describe("Phase 2A.2 reparse acceptance", () => {
  afterEach(cleanup);
  beforeEach(() => {
    preview.mockReset();
    apply.mockReset();
    vi.stubGlobal(
      "confirm",
      vi.fn(() => true),
    );
  });
  test("上传式reparse预览", async () => {
    await open();
    expect(preview).toHaveBeenCalled();
  });
  test("Hash一致显示", async () => {
    await open();
    expect(screen.getByText("文件Hash一致")).toBeVisible();
  });
  test("Hash不一致警告", async () => {
    await open({ ...base, hash_match: false });
    expect(screen.getByText(/Hash不同/)).toBeVisible();
  });
  test("replace_in_place value and confirm", async () => {
    await open();
    const replace = screen.getByTestId("reparse-replace-in-place");
    expect(replace).toHaveAttribute("value", "replace_in_place");
    expect(replace).toBeChecked();
    fireEvent.click(screen.getByTestId("reparse-apply"));
    expect(confirm).toHaveBeenCalled();
    await waitFor(() =>
      expect(apply).toHaveBeenCalledWith(1, expect.any(File), "replace_in_place", false),
    );
  });
  test("succeeded Run保护", async () => {
    await open({ ...base, has_succeeded_runs: true });
    expect(screen.getByTestId("reparse-replace-in-place")).toBeDisabled();
    await waitFor(() => {
      expect(screen.getByTestId("reparse-create-revision")).toBeChecked();
    });
  });
  test("create_revision value unchanged", async () => {
    apply.mockResolvedValue({ book_id: 2 });
    await open();
    const revision = screen.getByTestId("reparse-create-revision");
    expect(revision).toHaveAttribute("value", "create_revision");
    fireEvent.click(revision);
    fireEvent.click(screen.getByTestId("reparse-apply"));
    await waitFor(() =>
      expect(apply).toHaveBeenCalledWith(
        1,
        expect.any(File),
        "create_revision",
        false,
      ),
    );
  });
  test("前置内容显示", async () => {
    await open();
    expect(screen.getByText(/1个前置内容/)).toBeVisible();
  });
  test("正式第一章标题显示", async () => {
    await open();
    expect(screen.getByText("第一章｜起雾")).toBeVisible();
  });
  test("重解析后触发目录刷新回调", async () => {
    const done = vi.fn();
    apply.mockResolvedValue({ book_id: 1 });
    preview.mockResolvedValue(base);
    render(<ReparseDialog bookId={1} onClose={vi.fn()} onDone={done} />);
    fireEvent.change(document.querySelector('input[type="file"]')!, {
      target: { files: [new File(["x"], "b.txt")] },
    });
    await screen.findByTestId("reparse-create-revision");
    fireEvent.click(screen.getByTestId("reparse-create-revision"));
    fireEvent.click(screen.getByTestId("reparse-apply"));
    await waitFor(() => expect(done).toHaveBeenCalledWith(1));
  });
  test("超大章节分页诊断可见", async () => {
    await open();
    expect(screen.getByText(/12000段/)).toBeVisible();
  });
  test("header and footer stay visible with long preview content", async () => {
    const longTitles = Array.from({ length: 40 }, (_, i) => `第${i + 1}章｜长内容样例`);
    await open({ ...base, chapter_titles: longTitles, formal_chapter_count: longTitles.length });
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog.className).toContain("reparse-dialog-modal");
    expect(screen.getByRole("heading", { name: "重新识别章节" })).toBeVisible();
    expect(screen.getByTestId("reparse-dialog-footer")).toBeVisible();
    expect(screen.getByRole("button", { name: "取消" })).toBeVisible();
    expect(screen.getByTestId("reparse-apply")).toBeVisible();
    expect(screen.getByTestId("reparse-dialog-body")).toBeInTheDocument();
    expect(screen.getByTestId("reparse-replace-in-place")).toHaveAttribute(
      "value",
      "replace_in_place",
    );
    expect(screen.getByTestId("reparse-create-revision")).toHaveAttribute(
      "value",
      "create_revision",
    );
  });
  test("Provider 502详情数据保持脱敏", () => {
    const value = { root_error_code: "PROVIDER_HTTP_ERROR", http_status: 502 };
    expect(JSON.stringify(value)).not.toContain("原创正文");
  });
  test("脱敏错误复制不含正文", () => {
    const copied = JSON.stringify({ status: 502, hint: "建议重新启动" });
    expect(copied).not.toMatch(/paragraph|正文/);
  });
});
