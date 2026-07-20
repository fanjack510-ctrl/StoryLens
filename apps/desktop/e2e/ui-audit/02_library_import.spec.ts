import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { test, expect } from "@playwright/test";
import { installUiAuditMocks } from "./helpers/mockApi";
import { shot, prepareAuditSession, gotoReady } from "./helpers/shot";
import { FICTION_TXT } from "./fixtures/fictionTexts";

test.describe.configure({ mode: "serial" });
test.setTimeout(180_000);

function tmpImport(name: string, body: string | Buffer = FICTION_TXT): string {
  const file = path.join(os.tmpdir(), `storylens-ui-audit-${name}`);
  fs.writeFileSync(file, body);
  return file;
}

async function pickImportFile(page: import("@playwright/test").Page, filePath: string) {
  await page.locator('input[type="file"]').setInputFiles(filePath);
}

test.describe("02 library", () => {
  test.beforeEach(async ({ page }) => {
    await prepareAuditSession(page, { onboarding: "completed" });
  });

  test("empty library", async ({ page }) => {
    await installUiAuditMocks(page, { books: "empty" });
    await gotoReady(page, "/library");
    await shot(page, { id: "02-01", file: "02_library_empty.png", route: "/library", theme: "light" });
  });

  test("one book", async ({ page }) => {
    await installUiAuditMocks(page, { books: "one" });
    await gotoReady(page, "/library");
    await shot(page, { id: "02-02", file: "02_library_one_book.png", route: "/library", theme: "light" });
  });

  test("multi books", async ({ page }) => {
    await installUiAuditMocks(page, { books: "multi" });
    await gotoReady(page, "/library");
    await shot(page, { id: "02-03", file: "02_library_multi.png", route: "/library", theme: "light" });
    await shot(page, {
      id: "02-05",
      file: "02_library_list.png",
      route: "/library",
      theme: "light",
      notes: "List layout is the only library layout in 0.1.0",
    });
  });

  test("search hit and miss", async ({ page }) => {
    await installUiAuditMocks(page, { books: "multi" });
    await gotoReady(page, "/library");
    await page.getByTestId("library-search").fill("星港");
    await shot(page, { id: "02-06", file: "02_library_search_hit.png", route: "/library", theme: "light" });
    await page.getByTestId("library-search").fill("不存在的书名xyz");
    await shot(page, { id: "02-07", file: "02_library_search_miss.png", route: "/library", theme: "light" });
  });

  test("sort open", async ({ page }) => {
    await installUiAuditMocks(page, { books: "multi" });
    await gotoReady(page, "/library");
    await page.getByTestId("library-sort").click();
    await shot(page, { id: "02-08", file: "02_library_sort_open.png", route: "/library", theme: "light" });
  });

  test("book hover", async ({ page }) => {
    await installUiAuditMocks(page, { books: "one" });
    await gotoReady(page, "/library");
    await page.getByTestId("book-row-1").hover();
    await shot(page, { id: "02-09", file: "02_library_book_hover.png", route: "/library", theme: "light" });
  });

  test("import entry", async ({ page }) => {
    await installUiAuditMocks(page, { books: "empty" });
    await gotoReady(page, "/library");
    await expect(page.getByTestId("import-book")).toBeVisible();
    await shot(page, { id: "02-12", file: "02_library_import_entry.png", route: "/library", theme: "light" });
  });

  test("drop hint", async ({ page }) => {
    await installUiAuditMocks(page, { books: "one" });
    await gotoReady(page, "/library");
    await shot(page, {
      id: "03-04",
      file: "03_import_drop_hint.png",
      route: "/library",
      theme: "light",
      notes: "drop-hint footer in library list panel",
    });
  });
});

test.describe("02 import preview", () => {
  test.beforeEach(async ({ page }) => {
    await prepareAuditSession(page, { onboarding: "completed" });
    await installUiAuditMocks(page, { books: "empty", importPreview: "ok" });
    await gotoReady(page, "/library");
  });

  test("TXT preview", async ({ page }) => {
    await pickImportFile(page, tmpImport("fiction_starport.txt"));
    await page.getByText("章节识别预览").waitFor();
    await shot(page, { id: "03-01", file: "03_import_txt_ok.png", route: "/library", theme: "light" });
  });

  test("DOCX preview", async ({ page }) => {
    await pickImportFile(page, tmpImport("fiction_tides.docx", "PK\x03\x04mock-docx-audit"));
    await page.getByText("章节识别预览").waitFor();
    await shot(page, { id: "03-02", file: "03_import_docx_ok.png", route: "/library", theme: "light" });
  });

  test("EPUB preview", async ({ page }) => {
    await pickImportFile(page, tmpImport("fiction_bird.epub", "PK\x03\x04mock-epub-audit"));
    await page.getByText("章节识别预览").waitFor();
    await shot(page, { id: "03-03", file: "03_import_epub_ok.png", route: "/library", theme: "light" });
  });

  test("chapters ok", async ({ page }) => {
    await pickImportFile(page, tmpImport("fiction_starport.txt"));
    await page.getByText("章节识别预览").waitFor();
    await shot(page, { id: "03-06", file: "03_import_chapters_ok.png", route: "/library", theme: "light" });
  });
});

test.describe("02 import errors and states", () => {
  test.beforeEach(async ({ page }) => {
    await prepareAuditSession(page, { onboarding: "completed" });
    await gotoReady(page, "/library");
  });

  test("parsing pending", async ({ page }) => {
    await installUiAuditMocks(page, { books: "empty", importPreview: "pending" });
    await page.reload({ waitUntil: "domcontentloaded" });
    await pickImportFile(page, tmpImport("pending.txt"));
    await page.getByText("章节识别预览").waitFor({ state: "hidden" }).catch(() => undefined);
    await shot(page, {
      id: "03-05",
      file: "03_import_parsing.png",
      route: "/library",
      theme: "light",
      notes: "Loading panel while preview mock delays",
    });
  });

  test("suspect chapters", async ({ page }) => {
    await installUiAuditMocks(page, { books: "empty", importPreview: "suspect" });
    await page.reload({ waitUntil: "domcontentloaded" });
    await pickImportFile(page, tmpImport("suspect.txt"));
    await page.getByText("章节识别预览").waitFor();
    await shot(page, { id: "03-07", file: "03_import_chapters_suspect.png", route: "/library", theme: "light" });
  });

  test("format error", async ({ page }) => {
    await installUiAuditMocks(page, { books: "empty", importPreview: "format_error" });
    await page.reload({ waitUntil: "domcontentloaded" });
    await pickImportFile(page, tmpImport("bad.bin", "not-a-book"));
    await page.locator(".notice, [role=alert]").first().waitFor({ timeout: 15_000 }).catch(() => undefined);
    await shot(page, { id: "03-08", file: "03_import_format_error.png", route: "/library", theme: "light" });
  });

  test("too large", async ({ page }) => {
    await installUiAuditMocks(page, { books: "empty", importPreview: "too_large" });
    await page.reload({ waitUntil: "domcontentloaded" });
    await pickImportFile(page, tmpImport("huge.txt"));
    await page.locator(".notice, [role=alert]").first().waitFor({ timeout: 15_000 }).catch(() => undefined);
    await shot(page, { id: "03-09", file: "03_import_too_large.png", route: "/library", theme: "light" });
  });

  test("encoding error", async ({ page }) => {
    await installUiAuditMocks(page, { books: "empty", importPreview: "encoding_error" });
    await page.reload({ waitUntil: "domcontentloaded" });
    await pickImportFile(page, tmpImport("bad-encoding.txt"));
    await page.locator(".notice, [role=alert]").first().waitFor({ timeout: 15_000 }).catch(() => undefined);
    await shot(page, { id: "03-10", file: "03_import_encoding_error.png", route: "/library", theme: "light" });
  });

  test("duplicate upload", async ({ page }) => {
    await installUiAuditMocks(page, { books: "one", importPreview: "duplicate_on_upload" });
    await page.reload({ waitUntil: "domcontentloaded" });
    await pickImportFile(page, tmpImport("dup.txt"));
    await page.getByText("章节识别预览").waitFor();
    await page.getByRole("button", { name: "按当前结果继续导入" }).click();
    await page.locator(".notice, [role=alert]").first().waitFor({ timeout: 15_000 }).catch(() => undefined);
    await shot(page, { id: "03-11", file: "03_import_duplicate.png", route: "/library", theme: "light" });
  });

  test("import done", async ({ page }) => {
    await installUiAuditMocks(page, { books: "empty", importPreview: "ok" });
    await page.reload({ waitUntil: "domcontentloaded" });
    await pickImportFile(page, tmpImport("new.txt"));
    await page.getByText("章节识别预览").waitFor();
    await page.getByRole("button", { name: "按当前结果继续导入" }).click();
    await installUiAuditMocks(page, { books: "one" });
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.getByTestId("book-row-1").waitFor({ timeout: 15_000 }).catch(() => undefined);
    await shot(page, {
      id: "03-15",
      file: "03_import_done.png",
      route: "/library",
      theme: "light",
      notes: "Reload after mock switches to one-book library",
    });
  });
});
