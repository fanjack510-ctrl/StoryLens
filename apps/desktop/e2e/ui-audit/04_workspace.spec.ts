import { test, expect } from "@playwright/test";
import { installUiAuditMocks } from "./helpers/mockApi";
import { shot, prepareAuditSession, gotoReady } from "./helpers/shot";

test.describe.configure({ mode: "serial" });
test.setTimeout(180_000);

const BOOK = "/books/1?chapter=1";

test.describe("04 workspace", () => {
  test.beforeEach(async ({ page }) => {
    await prepareAuditSession(page, { onboarding: "completed" });
  });

  test("default workspace", async ({ page }) => {
    await installUiAuditMocks(page, { books: "one", analysisRun: "none", tasks: "empty" });
    await gotoReady(page, BOOK);
    await page.getByTestId("book-chapter-shell").waitFor();
    await shot(page, { id: "04-01", file: "04_workspace_default.png", route: BOOK, theme: "light" });
  });

  test("catalog open and closed", async ({ page }) => {
    await installUiAuditMocks(page, { analysisRun: "succeeded" });
    await gotoReady(page, `${BOOK}&analysisRun=55&view=result`);
    await page.getByTestId("book-chapter-catalog").click({ timeout: 10_000 });
    await page.getByTestId("chapter-catalog-drawer").waitFor({ timeout: 10_000 });
    await shot(page, { id: "04-02", file: "04_catalog_open.png", route: BOOK, theme: "light" });
    await page.getByRole("button", { name: "关闭" }).click({ timeout: 5_000 });
    await page.waitForTimeout(200);
    await shot(page, { id: "04-03", file: "04_catalog_closed.png", route: BOOK, theme: "light" });
  });

  test("reading body", async ({ page }) => {
    await installUiAuditMocks(page, { chapterMode: "default" });
    await gotoReady(page, BOOK);
    await page.getByTestId("book-view-reading").waitFor({ timeout: 8_000 }).catch(() => undefined);
    await shot(page, { id: "04-04", file: "04_reading_body.png", route: BOOK, theme: "light" });
    await shot(page, { id: "04-05", file: "04_analysis_rail.png", route: BOOK, theme: "light" });
  });

  test("no chapter selected", async ({ page }) => {
    await installUiAuditMocks(page);
    await gotoReady(page, "/books/1");
    await shot(page, { id: "04-06", file: "04_no_chapter.png", route: "/books/1", theme: "light" });
  });

  test("chapter loading", async ({ page }) => {
    await installUiAuditMocks(page, { chapterMode: "loading", paragraphsDelayMs: 8000 });
    await gotoReady(page, BOOK);
    await shot(page, {
      id: "04-07",
      file: "04_chapter_loading.png",
      route: BOOK,
      theme: "light",
      notes: "Paragraphs mock delayed",
    });
  });

  test("long short empty chapters", async ({ page }) => {
    await installUiAuditMocks(page, { chapterMode: "long" });
    await gotoReady(page, BOOK);
    await page.waitForTimeout(500);
    await shot(page, { id: "04-08", file: "04_long_chapter.png", route: BOOK, theme: "light", fullPage: true });

    await installUiAuditMocks(page, { chapterMode: "short" });
    await gotoReady(page, BOOK);
    await shot(page, { id: "04-09", file: "04_short_chapter.png", route: BOOK, theme: "light" });

    await installUiAuditMocks(page, { chapterMode: "empty" });
    await gotoReady(page, BOOK);
    await shot(page, { id: "04-10", file: "04_empty_body.png", route: BOOK, theme: "light" });
  });

  test("more menu", async ({ page }) => {
    await installUiAuditMocks(page);
    await gotoReady(page, BOOK);
    await page.getByTestId("book-more-menu-trigger").click();
    await page.getByTestId("book-more-menu-panel").waitFor();
    await shot(page, { id: "04-11", file: "04_more_menu.png", route: BOOK, theme: "light" });
  });

  test("narrow viewport and reading settings", async ({ page }) => {
    await installUiAuditMocks(page);
    await page.setViewportSize({ width: 1024, height: 768 });
    await gotoReady(page, BOOK);
    await shot(page, { id: "04-12", file: "04_narrow_1024.png", route: BOOK, theme: "light" });
    await page.getByTestId("reading-settings-trigger").click();
    await page.getByTestId("reading-settings-panel").waitFor();
    await shot(page, { id: "04-13", file: "04_reading_settings.png", route: BOOK, theme: "light" });
    await page.setViewportSize({ width: 1440, height: 900 });
  });

  test("long titles", async ({ page }) => {
    await installUiAuditMocks(page, { books: "long_titles", chapterMode: "long_title" });
    await gotoReady(page, BOOK);
    await shot(page, {
      id: "04-14",
      file: "04_inspector_collapsed.png",
      route: BOOK,
      theme: "light",
      notes: "Long book/chapter titles; inspector collapse depends on journey tab",
    });
  });
});
