/**
 * Real-browser geometry tests for pure reading workspace scroll
 * (view=reading, no analysisRun). Must not fake scrollHeight in JSDOM.
 */
import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SHOT_DIR = path.resolve(
  __dirname,
  "../../../audits/chg-20260722-008-reading-scroll",
);

const ROUTE = "/books/3?chapter=4&view=reading";
const CHAPTER_COUNT = 80;
const PARAGRAPH_COUNT = 60;

function buildChapters() {
  const front = [
    {
      id: 9001,
      book_id: 3,
      chapter_index: 0,
      title: "资料 序",
      display_title: "资料 序",
      word_count: 10,
      section_type: "front_matter",
      chapter_number_normalized: null,
    },
  ];
  const body = Array.from({ length: CHAPTER_COUNT }, (_, i) => {
    const n = i + 1;
    return {
      id: n,
      book_id: 3,
      chapter_index: n,
      title: `第${n}章 长卷条目${n}`,
      display_title: `第${n}章 长卷条目${n}`,
      word_count: 1200,
      section_type: "chapter",
      chapter_number_normalized: n,
    };
  });
  return [...front, ...body];
}

function buildParagraphs(chapterId: number) {
  const items = Array.from({ length: PARAGRAPH_COUNT }, (_, i) => ({
    id: `B0003-C${String(chapterId).padStart(4, "0")}-P${String(i + 1).padStart(4, "0")}`,
    chapter_id: chapterId,
    paragraph_index: i + 1,
    raw_text: `第${chapterId}章第${i + 1}段。`.repeat(8) + "正文足够长以超过视口高度。".repeat(6),
  }));
  return {
    items,
    offset: 0,
    limit: 200,
    total: items.length,
    has_more: false,
  };
}

async function prepareSession(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("storylens.onboarding.v1", "completed");
    localStorage.setItem("storylens.developerMode", "1");
    localStorage.removeItem("storylens.license.dev.mock");
    sessionStorage.setItem("storylens.uiAudit", "1");
  });
}

async function mockReadingApis(page: Page) {
  const chapters = buildChapters();
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    if (url.includes("/health")) {
      return route.fulfill({ json: { status: "ok", database: "ok", default_provider: "fake" } });
    }
    if (url.match(/\/books\/3$/) && method === "GET") {
      return route.fulfill({
        json: {
          id: 3,
          title: "长卷滚动验收书",
          source_file_name: "long.txt",
          source_file_hash: "scrollfix",
          created_at: "2026-01-01T00:00:00Z",
          revision_number: 1,
        },
      });
    }
    if (url.includes("/books/3/chapters") && method === "GET") {
      return route.fulfill({ json: chapters });
    }
    if (url.includes("/paragraphs") && method === "GET") {
      const m = url.match(/\/chapters\/(\d+)\/paragraphs/);
      const chapterId = m ? Number(m[1]) : 4;
      return route.fulfill({ json: buildParagraphs(chapterId) });
    }
    if (url.includes("/scenes") && method === "GET") {
      return route.fulfill({ json: [] });
    }
    if (url.includes("/providers") || url.includes("/ai-")) {
      return route.fulfill({ json: [] });
    }
    if (url.includes("/analysis-runs")) {
      return route.fulfill({ json: [] });
    }
    if (url.includes("/desktop/")) {
      return route.fulfill({ json: { status: "ready" } });
    }
    return route.fulfill({ status: 200, json: {} });
  });
}

type BoxMetrics = {
  clientHeight: number;
  scrollHeight: number;
  scrollTop: number;
  overflowY: string;
  scrollbarWidth: string;
  webkitScrollbarDisplay: string;
};

async function metricsOf(page: Page, testId: string): Promise<BoxMetrics | null> {
  return page.evaluate((id) => {
    const el = document.querySelector(`[data-testid="${id}"]`) as HTMLElement | null;
    if (!el) return null;
    const cs = getComputedStyle(el);
    let webkitScrollbarDisplay = "";
    try {
      const pseudo = getComputedStyle(el, "::-webkit-scrollbar");
      webkitScrollbarDisplay = pseudo.display || "";
    } catch {
      webkitScrollbarDisplay = "n/a";
    }
    return {
      clientHeight: el.clientHeight,
      scrollHeight: el.scrollHeight,
      scrollTop: el.scrollTop,
      overflowY: cs.overflowY,
      scrollbarWidth: cs.scrollbarWidth,
      webkitScrollbarDisplay,
    };
  }, testId);
}

async function setScrollTop(page: Page, testId: string, top: number) {
  return page.evaluate(
    ({ id, top }) => {
      const el = document.querySelector(`[data-testid="${id}"]`) as HTMLElement | null;
      if (!el) return null;
      el.scrollTop = top;
      return el.scrollTop;
    },
    { id: testId, top },
  );
}

async function chainAudit(page: Page) {
  return page.evaluate(() => {
    const pick = (sel: string) => document.querySelector(sel) as HTMLElement | null;
    const nodes: { name: string; sel: string; el: HTMLElement | null }[] = [
      { name: "html", sel: "html", el: document.documentElement },
      { name: "body", sel: "body", el: document.body },
      { name: "#root", sel: "#root", el: pick("#root") },
      { name: "app-shell", sel: ".app-shell-simplified", el: pick(".app-shell-simplified") },
      { name: "main", sel: ".app-shell-simplified > main", el: pick(".app-shell-simplified > main") },
      { name: "book-shell", sel: ".book-shell-simplified", el: pick(".book-shell-simplified") },
      { name: "book-shell-body", sel: '[data-testid="book-shell-body"]', el: pick('[data-testid="book-shell-body"]') },
      { name: "book-shell-main", sel: '[data-testid="main-content-pane"]', el: pick('[data-testid="main-content-pane"]') },
      {
        name: "reading-workspace-body",
        sel: '[data-testid="reading-workspace-body"]',
        el: pick('[data-testid="reading-workspace-body"]'),
      },
      { name: "workspace", sel: ".workspace.workspace-content", el: pick(".workspace.workspace-content") },
      { name: "left-sidebar", sel: ".workspace-book-nav", el: pick(".workspace-book-nav") },
      {
        name: "chapter-list",
        sel: '[data-testid="chapter-list-scroll-region"]',
        el: pick('[data-testid="chapter-list-scroll-region"]'),
      },
      { name: "reader", sel: ".workspace-reader", el: pick(".workspace-reader") },
      {
        name: "reading-content",
        sel: '[data-testid="reading-content-scroll-region"]',
        el: pick('[data-testid="reading-content-scroll-region"]'),
      },
    ];
    return nodes.map(({ name, sel, el }) => {
      if (!el) return { name, sel, missing: true };
      const cs = getComputedStyle(el);
      return {
        name,
        sel,
        missing: false,
        clientHeight: el.clientHeight,
        scrollHeight: el.scrollHeight,
        overflowY: cs.overflowY,
        overflowX: cs.overflowX,
        minHeight: cs.minHeight,
        height: cs.height,
        maxHeight: cs.maxHeight,
        display: cs.display,
        flex: cs.flex,
        gridTemplateRows: cs.gridTemplateRows,
      };
    });
  });
}

async function shot(page: Page, name: string) {
  fs.mkdirSync(SHOT_DIR, { recursive: true });
  await page.screenshot({
    path: path.join(SHOT_DIR, name),
    fullPage: false,
  });
}

test.describe("pure reading workspace independent scroll", () => {
  test.setTimeout(120_000);

  test.beforeEach(async ({ page }) => {
    await prepareSession(page);
    await mockReadingApis(page);
  });

  test("chapter list and reading pane scroll independently @1440", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(ROUTE, { waitUntil: "domcontentloaded" });
    await page.getByTestId("desktop-bootstrap-starting").waitFor({ state: "hidden", timeout: 15000 }).catch(() => undefined);
    await page.getByTestId("reading-workspace-body").waitFor({ timeout: 15000 });
    await page.getByTestId("chapter-list-scroll-region").waitFor();
    await page.getByTestId("reading-content-scroll-region").waitFor();
    await expect(page.locator(".workspace-prose .paragraph").first()).toBeVisible();

    const chain = await chainAudit(page);
    const workspaceBody = chain.find((n) => n.name === "reading-workspace-body");
    expect(workspaceBody?.missing).toBeFalsy();
    expect((workspaceBody as { clientHeight?: number }).clientHeight || 0).toBeGreaterThan(200);

    const chapter = await metricsOf(page, "chapter-list-scroll-region");
    const reading = await metricsOf(page, "reading-content-scroll-region");
    expect(chapter).not.toBeNull();
    expect(reading).not.toBeNull();
    expect(chapter!.scrollHeight).toBeGreaterThan(chapter!.clientHeight);
    expect(reading!.scrollHeight).toBeGreaterThan(reading!.clientHeight);
    expect(chapter!.overflowY).toMatch(/auto|scroll/);
    expect(reading!.overflowY).toMatch(/auto|scroll/);
    expect(chapter!.scrollbarWidth).not.toBe("none");
    expect(reading!.scrollbarWidth).not.toBe("none");

    // Current chapter centered-ish in list after load (chapter=4)
    const activeVisible = await page.evaluate(() => {
      const list = document.querySelector('[data-testid="chapter-list-scroll-region"]') as HTMLElement;
      const item = list?.querySelector('[data-chapter-id="4"]') as HTMLElement | null;
      if (!list || !item) return false;
      const lr = list.getBoundingClientRect();
      const ir = item.getBoundingClientRect();
      return ir.top >= lr.top - 4 && ir.bottom <= lr.bottom + 4;
    });
    expect(activeVisible).toBe(true);

    await shot(page, "01_chapter_top_reading_top.png");

    const chapterBefore = chapter!.scrollTop;
    const readingBefore = reading!.scrollTop;
    const chapterMid = await setScrollTop(page, "chapter-list-scroll-region", 240);
    expect(chapterMid).toBeGreaterThan(chapterBefore);
    const readingUnchanged = await metricsOf(page, "reading-content-scroll-region");
    expect(readingUnchanged!.scrollTop).toBe(readingBefore);
    await shot(page, "02_chapter_mid_reading_top.png");

    const readingMid = await setScrollTop(page, "reading-content-scroll-region", 400);
    expect(readingMid).toBeGreaterThan(0);
    const chapterStill = await metricsOf(page, "chapter-list-scroll-region");
    expect(chapterStill!.scrollTop).toBe(chapterMid);
    await shot(page, "03_chapter_mid_reading_mid.png");

    const readingEnd = await setScrollTop(page, "reading-content-scroll-region", 50_000);
    expect(readingEnd).toBeGreaterThan(readingMid!);
    await shot(page, "04_reading_end.png");

    await setScrollTop(page, "reading-content-scroll-region", readingMid!);
    await setScrollTop(page, "chapter-list-scroll-region", 480);
    const independent = await page.evaluate(() => {
      const c = document.querySelector('[data-testid="chapter-list-scroll-region"]') as HTMLElement;
      const r = document.querySelector('[data-testid="reading-content-scroll-region"]') as HTMLElement;
      return {
        sameNode: c === r,
        chapterTop: c.scrollTop,
        readingTop: r.scrollTop,
        bodyScroll: document.documentElement.scrollTop + document.body.scrollTop,
        bodyOverflowY: getComputedStyle(document.body).overflowY,
        htmlClient: document.documentElement.clientHeight,
        bodyScrollHeight: document.body.scrollHeight,
      };
    });
    expect(independent.sameNode).toBe(false);
    expect(independent.chapterTop).toBeGreaterThan(200);
    expect(independent.readingTop).toBeGreaterThan(100);
    expect(independent.bodyScroll).toBeLessThan(2);
    await shot(page, "05_independent_scrolltops.png");

    // Switch chapter → reading scrollTop resets
    await setScrollTop(page, "reading-content-scroll-region", 300);
    await page.locator('.workspace-chapter-item[data-chapter-id="5"]').click();
    await expect(page.locator(".workspace-chapter-heading")).toContainText("第5章");
    await page.waitForTimeout(200);
    const afterNav = await metricsOf(page, "reading-content-scroll-region");
    expect(afterNav!.scrollTop).toBe(0);

    // Top app bar remains visible
    const headerVisible = await page.evaluate(() => {
      const header = document.querySelector(".app-shell-simplified header, .app-topbar, .workspace-toolbar");
      if (!header) return document.querySelector(".app-shell-simplified") != null;
      const r = (header as HTMLElement).getBoundingClientRect();
      return r.top >= 0 && r.bottom > 0 && r.height > 0;
    });
    expect(headerVisible).toBe(true);

    fs.mkdirSync(SHOT_DIR, { recursive: true });
    fs.writeFileSync(
      path.join(SHOT_DIR, "metrics-1440.json"),
      JSON.stringify({ chain, chapter, reading, independent }, null, 2),
      "utf8",
    );
  });

  test("1024 width keeps reading scroll; drawer chapters scroll", async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 800 });
    await page.goto(ROUTE, { waitUntil: "domcontentloaded" });
    await page.getByTestId("desktop-bootstrap-starting").waitFor({ state: "hidden", timeout: 15000 }).catch(() => undefined);
    await page.getByTestId("reading-content-scroll-region").waitFor({ timeout: 15000 });
    const reading = await metricsOf(page, "reading-content-scroll-region");
    expect(reading!.scrollHeight).toBeGreaterThan(reading!.clientHeight);
    expect(reading!.overflowY).toMatch(/auto|scroll/);
    const mid = await setScrollTop(page, "reading-content-scroll-region", 350);
    expect(mid).toBeGreaterThan(0);
    await shot(page, "06_w1024_reading_mid.png");

    const catalog = page.getByTestId("book-chapter-catalog");
    if (await catalog.isVisible().catch(() => false)) {
      await catalog.click();
      const drawerList = page.locator(".chapter-navigator-list, [data-testid='chapter-catalog-list']").first();
      await drawerList.waitFor({ timeout: 8000 });
      const drawerScrollable = await drawerList.evaluate((el) => {
        const cs = getComputedStyle(el as HTMLElement);
        return {
          clientHeight: (el as HTMLElement).clientHeight,
          scrollHeight: (el as HTMLElement).scrollHeight,
          overflowY: cs.overflowY,
        };
      });
      expect(drawerScrollable.scrollHeight).toBeGreaterThan(drawerScrollable.clientHeight - 1);
      expect(drawerScrollable.overflowY).toMatch(/auto|scroll/);
      await shot(page, "07_w1024_drawer_chapters.png");
      await page.getByTestId("chapter-catalog-close").click().catch(async () => {
        await page.keyboard.press("Escape");
      });
      const readingAfter = await metricsOf(page, "reading-content-scroll-region");
      expect(readingAfter!.scrollTop).toBe(mid);
    }
  });

  test("150% and 200% zoom reading still scrolls", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(ROUTE, { waitUntil: "domcontentloaded" });
    await page.getByTestId("desktop-bootstrap-starting").waitFor({ state: "hidden", timeout: 15000 }).catch(() => undefined);
    await page.getByTestId("reading-content-scroll-region").waitFor({ timeout: 15000 });

    for (const zoom of [1.5, 2.0] as const) {
      await page.evaluate((z) => {
        document.documentElement.style.zoom = String(z);
      }, zoom);
      await page.waitForTimeout(150);
      const reading = await metricsOf(page, "reading-content-scroll-region");
      expect(reading!.clientHeight).toBeGreaterThan(80);
      expect(reading!.scrollHeight).toBeGreaterThan(reading!.clientHeight);
      const top = await setScrollTop(page, "reading-content-scroll-region", 280);
      expect(top).toBeGreaterThan(0);
      await shot(page, zoom === 1.5 ? "08_zoom_150.png" : "09_zoom_200.png");
    }
    await page.evaluate(() => {
      document.documentElement.style.zoom = "1";
    });
  });
});
