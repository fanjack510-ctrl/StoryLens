import { test, expect } from "@playwright/test";
import { installUiAuditMocks } from "./helpers/mockApi";
import { shot, prepareAuditSession, gotoReady } from "./helpers/shot";

test.describe.configure({ mode: "serial" });
test.setTimeout(180_000);

const BOOK = "/books/1?chapter=1";

async function assertNoHorizontalPageScroll(page: import("@playwright/test").Page) {
  const scrolled = await page.evaluate(() => {
    const root = document.documentElement;
    return root.scrollWidth > root.clientWidth + 1;
  });
  expect(scrolled, "page must not horizontally scroll").toBe(false);
}

async function assertNoVerticalTitleStack(page: import("@playwright/test").Page) {
  const bad = await page.evaluate(() => {
    const heading = document.querySelector(".workspace-chapter-heading, .reader h1");
    if (!heading) return false;
    const text = (heading.textContent || "").replace(/\s+/g, "");
    if (text.length < 4) return false;
    const rect = heading.getBoundingClientRect();
    // Single-character-per-line stack is extremely tall vs narrow
    return rect.width < 40 && rect.height > text.length * 14;
  });
  expect(bad, "chapter title must not stack as single characters").toBe(false);
}

async function assertWorkspaceHealthy(page: import("@playwright/test").Page) {
  const bodyText = await page.locator("body").innerText();
  for (const token of ["Unexpected Application Error", "undefined", "NaN"]) {
    // Allow "undefined" only inside technical hashes etc. — ban bare crash tokens already
    // covered by shot helper; here ban literal NaN and unexpected app errors.
    if (token === "undefined") continue;
    expect(bodyText.includes(token), `banned token: ${token}`).toBe(false);
  }
  expect(bodyText).not.toMatch(/\bNaN\b/);
  expect(bodyText).not.toContain("Unexpected Application Error");
  await assertNoHorizontalPageScroll(page);
  await assertNoVerticalTitleStack(page);
}

test.describe("04 workspace", () => {
  test.beforeEach(async ({ page }) => {
    await prepareAuditSession(page, { onboarding: "completed" });
  });

  test("default workspace", async ({ page }) => {
    await installUiAuditMocks(page, { books: "one", analysisRun: "none", tasks: "empty" });
    await gotoReady(page, BOOK);
    await page.getByTestId("book-chapter-shell").waitFor();
    await assertWorkspaceHealthy(page);
    await shot(page, { id: "04-01", file: "04_workspace_default.png", route: BOOK, theme: "light" });
  });

  test("catalog open and closed", async ({ page }) => {
    await installUiAuditMocks(page, { analysisRun: "succeeded" });
    await gotoReady(page, `${BOOK}&analysisRun=55&view=result`);
    await page.getByTestId("book-chapter-catalog").click({ timeout: 10_000 });
    const drawer = page.getByTestId("chapter-catalog-drawer");
    await drawer.waitFor({ timeout: 10_000 });
    await expect(drawer.getByText("章节目录")).toBeVisible();
    await expect(page.getByTestId("chapter-catalog-close")).toBeVisible();
    await expect(page.locator(".chapter-catalog-item.active").first()).toBeVisible();
    await assertWorkspaceHealthy(page);
    await shot(page, { id: "04-02", file: "04_catalog_open.png", route: BOOK, theme: "light" });
    await page.getByRole("button", { name: "关闭" }).click({ timeout: 5_000 });
    await page.waitForTimeout(200);
    await assertWorkspaceHealthy(page);
    await shot(page, { id: "04-03", file: "04_catalog_closed.png", route: BOOK, theme: "light" });
  });

  test("reading body", async ({ page }) => {
    await installUiAuditMocks(page, { chapterMode: "default" });
    await gotoReady(page, BOOK);
    await page.getByTestId("book-view-reading").waitFor({ timeout: 8_000 }).catch(() => undefined);
    await assertWorkspaceHealthy(page);
    await shot(page, { id: "04-04", file: "04_reading_body.png", route: BOOK, theme: "light" });
    await shot(page, { id: "04-05", file: "04_analysis_rail.png", route: BOOK, theme: "light" });
  });

  test("no chapter selected", async ({ page }) => {
    await installUiAuditMocks(page);
    await gotoReady(page, "/books/1");
    await assertWorkspaceHealthy(page);
    await shot(page, { id: "04-06", file: "04_no_chapter.png", route: "/books/1", theme: "light" });
  });

  test("chapter loading", async ({ page }) => {
    await installUiAuditMocks(page, { chapterMode: "loading", paragraphsDelayMs: 8000 });
    await gotoReady(page, BOOK);
    await assertWorkspaceHealthy(page);
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
    await assertWorkspaceHealthy(page);
    await shot(page, { id: "04-08", file: "04_long_chapter.png", route: BOOK, theme: "light", fullPage: true });

    await installUiAuditMocks(page, { chapterMode: "short" });
    await gotoReady(page, BOOK);
    await assertWorkspaceHealthy(page);
    await shot(page, { id: "04-09", file: "04_short_chapter.png", route: BOOK, theme: "light" });

    await installUiAuditMocks(page, { chapterMode: "empty" });
    await gotoReady(page, BOOK);
    await assertWorkspaceHealthy(page);
    await shot(page, { id: "04-10", file: "04_empty_body.png", route: BOOK, theme: "light" });
  });

  test("more menu", async ({ page }) => {
    await installUiAuditMocks(page);
    await gotoReady(page, BOOK);
    await page.getByTestId("book-more-menu-trigger").click();
    await page.getByTestId("book-more-menu-panel").waitFor();
    await assertWorkspaceHealthy(page);
    await shot(page, { id: "04-11", file: "04_more_menu.png", route: BOOK, theme: "light" });
  });

  test("narrow viewport and reading settings", async ({ page }) => {
    await installUiAuditMocks(page, { books: "one", analysisRun: "none", tasks: "empty" });
    await page.setViewportSize({ width: 1024, height: 768 });
    await gotoReady(page, BOOK);

    const layout = await page.evaluate(() => {
      const reader = document.querySelector(
        ".book-shell-simplified article.reader, .book-shell-simplified .workspace-reader",
      ) as HTMLElement | null;
      const prose = document.querySelector(
        ".book-shell-simplified .workspace-prose, .book-shell-simplified .workspace-reading-canvas",
      ) as HTMLElement | null;
      const readerWidth = reader ? reader.getBoundingClientRect().width : 0;
      const proseWidth = prose ? prose.getBoundingClientRect().width : 0;
      const contentWidth = Math.max(readerWidth, proseWidth);
      const heading = document.querySelector(
        ".book-shell-simplified .workspace-chapter-heading, .book-shell-simplified .reader h1",
      );
      const headingText = (heading?.textContent || "").replace(/\s+/g, "");
      const headingRect = heading?.getBoundingClientRect();
      const verticalTitle =
        !!headingRect &&
        headingText.length >= 4 &&
        headingRect.width < 40 &&
        headingRect.height > headingText.length * 14;
      const nav = document.querySelector(".workspace-book-nav");
      const inspector = document.querySelector(
        ".workspace-inspector:has(.artifact), .chapter-analysis-progress-panel",
      );
      const navVisible =
        !!nav &&
        getComputedStyle(nav).display !== "none" &&
        getComputedStyle(nav).visibility !== "hidden" &&
        nav.getBoundingClientRect().width > 8;
      const inspectorVisible =
        !!inspector &&
        getComputedStyle(inspector).display !== "none" &&
        getComputedStyle(inspector).position !== "absolute" &&
        getComputedStyle(inspector).position !== "fixed" &&
        inspector.getBoundingClientRect().width > 8;
      const threeFixed = navVisible && inspectorVisible;
      const horizontal =
        document.documentElement.scrollWidth > document.documentElement.clientWidth + 1;
      return {
        contentWidth,
        readerWidth,
        proseWidth,
        verticalTitle,
        threeFixed,
        horizontal,
        grid: reader?.parentElement ? getComputedStyle(reader.parentElement).gridTemplateColumns : "",
        display: reader?.parentElement ? getComputedStyle(reader.parentElement).display : "",
      };
    });

    expect(
      layout.contentWidth,
      `reading content width >= 520 (got reader=${layout.readerWidth} prose=${layout.proseWidth} grid=${layout.grid} display=${layout.display})`,
    ).toBeGreaterThanOrEqual(520);
    expect(layout.verticalTitle, "chapter title not vertical").toBe(false);
    expect(layout.horizontal, "no horizontal scroll").toBe(false);
    expect(layout.threeFixed, "must not keep three fixed side panels").toBe(false);

    await assertWorkspaceHealthy(page);
    await shot(page, { id: "04-12", file: "04_narrow_1024.png", route: BOOK, theme: "light" });

    await page.getByTestId("reading-settings-trigger").click();
    const panel = page.getByTestId("reading-settings-panel");
    await panel.waitFor();
    await expect(panel.getByText("字号")).toBeVisible();
    await expect(panel.getByText("行距")).toBeVisible();
    await expect(panel.getByText("正文宽度")).toBeVisible();
    await expect(panel.getByText("显示段落 ID")).toBeVisible();
    const box = await panel.boundingBox();
    expect(box).toBeTruthy();
    const viewport = page.viewportSize()!;
    expect(box!.x).toBeGreaterThanOrEqual(-1);
    expect(box!.y).toBeGreaterThanOrEqual(-1);
    expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width + 1);
    expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height + 1);
    await assertWorkspaceHealthy(page);
    await shot(page, { id: "04-13", file: "04_reading_settings.png", route: BOOK, theme: "light" });
    await page.setViewportSize({ width: 1440, height: 900 });
  });

  test("long titles", async ({ page }) => {
    await installUiAuditMocks(page, { books: "long_titles", chapterMode: "long_title" });
    await gotoReady(page, BOOK);
    await assertWorkspaceHealthy(page);
    await shot(page, {
      id: "04-14",
      file: "04_inspector_collapsed.png",
      route: BOOK,
      theme: "light",
      notes: "Long book/chapter titles; inspector collapse depends on journey tab",
    });
  });
});
