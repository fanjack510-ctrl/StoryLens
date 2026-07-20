import { test, expect } from "@playwright/test";
import { installUiAuditMocks } from "./helpers/mockApi";
import {
  shot,
  prepareAuditSession,
  gotoReady,
  assertNoDirtyVisibleText,
} from "./helpers/shot";

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
    return rect.width < 40 && rect.height > text.length * 14;
  });
  expect(bad, "chapter title must not stack as single characters").toBe(false);
}

async function assertWorkspaceHealthy(page: import("@playwright/test").Page) {
  const bodyText = await page.locator("body").innerText();
  expect(bodyText).not.toContain("Unexpected Application Error");
  await assertNoDirtyVisibleText(page);
  await assertNoHorizontalPageScroll(page);
  await assertNoVerticalTitleStack(page);
}

async function readerContentWidth(page: import("@playwright/test").Page) {
  return page.evaluate(() => {
    const reader = document.querySelector(
      ".book-shell-simplified article.reader, .book-shell-simplified .workspace-reader",
    ) as HTMLElement | null;
    return reader ? reader.getBoundingClientRect().width : 0;
  });
}

async function assertSceneCatalogClean(page: import("@playwright/test").Page) {
  const sceneList = page.locator(".workspace-scene-list");
  if ((await sceneList.count()) === 0) return;
  const text = await sceneList.innerText();
  expect(text).not.toMatch(/Sundefined|Snull|SNaN|undefined|null|NaN/i);
  const ordinals = page.locator(".workspace-scene-ordinal");
  const n = await ordinals.count();
  for (let i = 0; i < n; i += 1) {
    const label = (await ordinals.nth(i).innerText()).trim();
    expect(label).not.toMatch(/undefined|null|NaN/i);
    expect(label.length).toBeGreaterThan(0);
  }
}

async function shot04(
  page: import("@playwright/test").Page,
  meta: Parameters<typeof shot>[1],
) {
  await shot(page, { ...meta, checkDirtyVisible: true });
}

test.describe("04 workspace", () => {
  test.beforeEach(async ({ page }) => {
    await prepareAuditSession(page, { onboarding: "completed" });
  });

  test("default workspace", async ({ page }) => {
    await installUiAuditMocks(page, { books: "one", analysisRun: "none", tasks: "empty" });
    await gotoReady(page, BOOK);
    await page.getByTestId("book-chapter-shell").waitFor();
    await expect(page.getByText("\u865a\u6784\u661f\u6e2f\u7f16\u5e74\u53f2").first()).toBeVisible();
    await expect(page.getByText("\u7b2c\u4e00\u7ae0\u3000\u6f6e\u6c50\u949f").first()).toBeVisible();
    await expect(page.locator(".workspace-prose .paragraph").first()).toBeVisible();
    await assertSceneCatalogClean(page);
    await assertWorkspaceHealthy(page);
    await shot04(page, { id: "04-01", file: "04_workspace_default.png", route: BOOK, theme: "light" });
  });

  test("catalog open and closed", async ({ page }) => {
    await installUiAuditMocks(page, { analysisRun: "succeeded", tasks: "empty" });
    await gotoReady(page, `${BOOK}&analysisRun=55&view=result`);
    await page.getByTestId("book-chapter-catalog").click({ timeout: 10_000 });
    const drawer = page.getByTestId("chapter-catalog-drawer");
    await drawer.waitFor({ timeout: 10_000 });
    await expect(drawer.getByText("\u7ae0\u8282\u76ee\u5f55")).toBeVisible();
    await expect(page.getByTestId("chapter-catalog-close")).toBeVisible();
    await expect(page.locator(".chapter-catalog-item.active").first()).toBeVisible();
    await assertWorkspaceHealthy(page);
    await shot04(page, { id: "04-02", file: "04_catalog_open.png", route: BOOK, theme: "light" });
    await page.getByRole("button", { name: "\u5173\u95ed" }).click({ timeout: 5_000 });
    await page.waitForTimeout(200);
    await assertWorkspaceHealthy(page);
    await shot04(page, { id: "04-03", file: "04_catalog_closed.png", route: BOOK, theme: "light" });
  });

  test("reading body", async ({ page }) => {
    await installUiAuditMocks(page, {
      chapterMode: "default",
      analysisRun: "none",
      tasks: "empty",
    });
    await gotoReady(page, BOOK);
    await page.getByTestId("book-view-reading").waitFor({ timeout: 8_000 }).catch(() => undefined);
    await assertWorkspaceHealthy(page);
    await shot04(page, { id: "04-04", file: "04_reading_body.png", route: BOOK, theme: "light" });
  });

  test("analysis rail", async ({ page }) => {
    await installUiAuditMocks(page, { analysisRun: "running", tasks: "empty" });
    await gotoReady(page, `${BOOK}&analysisRun=55&view=progress`);
    const inspector = page.getByTestId("chapter-analysis-progress");
    await expect(inspector).toBeVisible({ timeout: 10_000 });
    await expect(inspector.getByText("\u5f53\u524d\u9636\u6bb5")).toBeVisible();
    const width = await readerContentWidth(page);
    expect(width, "reader remains usable with analysis rail").toBeGreaterThanOrEqual(420);
    await assertSceneCatalogClean(page);
    await assertWorkspaceHealthy(page);
    await shot04(page, { id: "04-05", file: "04_analysis_rail.png", route: BOOK, theme: "light" });
  });

  test("no chapter selected", async ({ page }) => {
    await installUiAuditMocks(page, {
      books: "one",
      chapters: "empty",
      analysisRun: "none",
      tasks: "empty",
    });
    await gotoReady(page, "/books/1");
    const empty = page.getByTestId("workspace-no-chapter");
    await expect(empty).toBeVisible({ timeout: 10_000 });
    await expect(empty.getByText("\u9009\u62e9\u4e00\u4e2a\u7ae0\u8282\u5f00\u59cb\u9605\u8bfb")).toBeVisible();
    await expect(page.locator(".workspace-chapter-heading")).toHaveCount(0);
    await expect(page.locator(".workspace-prose .paragraph")).toHaveCount(0);
    await expect(page.getByTestId("shell-start-analysis")).toBeDisabled();
    await expect(page.getByTestId("chapter-analysis-progress")).toHaveCount(0);
    await expect(page.locator(".workspace-inspector .artifact")).toHaveCount(0);
    await assertWorkspaceHealthy(page);
    await shot04(page, { id: "04-06", file: "04_no_chapter.png", route: "/books/1", theme: "light" });
  });

  test("chapter loading", async ({ page }) => {
    await installUiAuditMocks(page, {
      chapterMode: "loading",
      paragraphsDelayMs: 8000,
      analysisRun: "none",
      tasks: "empty",
    });
    await gotoReady(page, BOOK);
    await expect(page.getByTestId("workspace-chapter-loading")).toBeVisible({ timeout: 8_000 });
    await expect(page.getByText("\u6b63\u5728\u8f7d\u5165\u7ae0\u8282")).toBeVisible();
    await expect(page.locator(".workspace-prose .paragraph")).toHaveCount(0);
    await assertWorkspaceHealthy(page);
    await shot04(page, {
      id: "04-07",
      file: "04_chapter_loading.png",
      route: BOOK,
      theme: "light",
      notes: "Paragraphs mock delayed",
    });
  });

  test("long short empty chapters", async ({ page }) => {
    await installUiAuditMocks(page, {
      chapterMode: "long",
      analysisRun: "none",
      tasks: "empty",
    });
    await gotoReady(page, BOOK);
    await page.waitForTimeout(500);
    await assertWorkspaceHealthy(page);
    await shot04(page, {
      id: "04-08",
      file: "04_long_chapter.png",
      route: BOOK,
      theme: "light",
      fullPage: true,
    });

    await installUiAuditMocks(page, {
      chapterMode: "short",
      analysisRun: "none",
      tasks: "empty",
    });
    await gotoReady(page, BOOK);
    await assertWorkspaceHealthy(page);
    await shot04(page, { id: "04-09", file: "04_short_chapter.png", route: BOOK, theme: "light" });

    await installUiAuditMocks(page, {
      chapterMode: "empty",
      analysisRun: "none",
      tasks: "empty",
    });
    await gotoReady(page, BOOK);
    await expect(page.getByTestId("workspace-empty-body")).toBeVisible();
    await expect(page.getByText("\u8fd9\u4e2a\u7ae0\u8282\u6ca1\u6709\u53ef\u663e\u793a\u7684\u6b63\u6587")).toBeVisible();
    await expect(page.locator(".workspace-prose .paragraph")).toHaveCount(0);
    await assertWorkspaceHealthy(page);
    await shot04(page, { id: "04-10", file: "04_empty_body.png", route: BOOK, theme: "light" });
  });

  test("more menu", async ({ page }) => {
    await installUiAuditMocks(page, { analysisRun: "none", tasks: "empty" });
    await gotoReady(page, BOOK);
    await page.getByTestId("book-more-menu-trigger").click();
    await page.getByTestId("book-more-menu-panel").waitFor();
    await assertWorkspaceHealthy(page);
    await shot04(page, { id: "04-11", file: "04_more_menu.png", route: BOOK, theme: "light" });
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
    await shot04(page, { id: "04-12", file: "04_narrow_1024.png", route: BOOK, theme: "light" });

    await page.getByTestId("reading-settings-trigger").click();
    const panel = page.getByTestId("reading-settings-panel");
    await panel.waitFor();
    await expect(panel.getByText("\u5b57\u53f7")).toBeVisible();
    await expect(panel.getByText("\u884c\u8ddd")).toBeVisible();
    await expect(panel.getByText("\u6b63\u6587\u5bbd\u5ea6")).toBeVisible();
    await expect(panel.getByText("\u663e\u793a\u6bb5\u843d ID")).toBeVisible();
    const box = await panel.boundingBox();
    expect(box).toBeTruthy();
    const viewport = page.viewportSize()!;
    expect(box!.x).toBeGreaterThanOrEqual(-1);
    expect(box!.y).toBeGreaterThanOrEqual(-1);
    expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width + 1);
    expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height + 1);
    await assertWorkspaceHealthy(page);
    await shot04(page, { id: "04-13", file: "04_reading_settings.png", route: BOOK, theme: "light" });
    await page.setViewportSize({ width: 1440, height: 900 });
  });

  test("inspector collapsed via real dismiss", async ({ page }) => {
    await installUiAuditMocks(page, { analysisRun: "running", tasks: "empty" });
    await gotoReady(page, `${BOOK}&analysisRun=55&view=progress`);

    const inspector = page.getByTestId("chapter-analysis-progress");
    await expect(inspector).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("chapter-analysis-dismiss")).toBeVisible();

    const widthExpanded = await readerContentWidth(page);
    expect(widthExpanded).toBeGreaterThan(0);

    await page.getByTestId("chapter-analysis-dismiss").click();
    await expect(inspector).toHaveCount(0, { timeout: 5_000 });
    await expect(page.getByTestId("book-shell-body")).toHaveAttribute("data-has-progress", "false");

    const widthCollapsed = await readerContentWidth(page);
    expect(
      widthCollapsed,
      `reader must widen after collapse (expanded=${widthExpanded} collapsed=${widthCollapsed})`,
    ).toBeGreaterThan(widthExpanded + 40);

    const expand = page.getByTestId("chapter-analysis-expand");
    await expect(expand).toBeVisible();

    await expect(page.getByTestId("chapter-analysis-progress")).toHaveCount(0);
    await assertSceneCatalogClean(page);
    await assertWorkspaceHealthy(page);
    await shot04(page, {
      id: "04-14",
      file: "04_inspector_collapsed.png",
      route: `${BOOK}&analysisRun=55&view=progress`,
      theme: "light",
      notes: "Clicked dismiss; progress panel unmounted; reader widened",
    });

    await expand.click();
    await expect(page.getByTestId("chapter-analysis-progress")).toBeVisible({ timeout: 5_000 });
    await expect(page.getByTestId("book-shell-body")).toHaveAttribute("data-has-progress", "true");
    const widthRestored = await readerContentWidth(page);
    expect(widthRestored).toBeLessThan(widthCollapsed - 20);
  });
});
