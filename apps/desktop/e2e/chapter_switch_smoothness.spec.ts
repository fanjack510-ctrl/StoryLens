/**
 * Minimal browser proof for smooth chapter switch + single-line chapter rows.
 * Mocks APIs — does not call models or create analysis runs.
 */
import { expect, test, type Page } from "@playwright/test";

const ROUTE = "/books/3?chapter=10&view=reading";

function buildChapters() {
  const body = Array.from({ length: 120 }, (_, i) => {
    const n = i + 1;
    const long =
      n === 6
        ? `第6章｜《陈氏编导法则》额外很长很长很长标题用于省略`
        : `第${n}章 条目${n}`;
    return {
      id: n,
      book_id: 3,
      chapter_index: n,
      title: long,
      display_title: long,
      word_count: 800,
      section_type: "chapter",
      chapter_number_normalized: n,
    };
  });
  return body;
}

function buildParagraphs(chapterId: number) {
  const items = Array.from({ length: 40 }, (_, i) => ({
    id: `B0003-C${String(chapterId).padStart(4, "0")}-P${String(i + 1).padStart(4, "0")}`,
    chapter_id: chapterId,
    paragraph_index: i + 1,
    raw_text: `第${chapterId}章段落${i + 1}。`.repeat(10),
  }));
  return { items, offset: 0, limit: 200, total: items.length, has_more: false };
}

async function mockApis(page: Page) {
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
          title: "长篇切章测试书",
          source_file_name: "long.txt",
          source_file_hash: "x",
          created_at: "2026-01-01T00:00:00Z",
          revision_number: 1,
        },
      });
    }
    if (url.includes("/books/3/chapters") && method === "GET") {
      return route.fulfill({ json: chapters });
    }
    const para = url.match(/\/chapters\/(\d+)\/paragraphs/);
    if (para && method === "GET") {
      return route.fulfill({ json: buildParagraphs(Number(para[1])) });
    }
    if (url.includes("/scenes") && method === "GET") {
      return route.fulfill({ json: [] });
    }
    if (url.includes("/runs") || url.includes("/analysis")) {
      return route.fulfill({ status: 404, json: { detail: "not used" } });
    }
    return route.fulfill({ status: 200, json: {} });
  });
}

test.describe("CHG-20260723-004 chapter switch smoothness", () => {
  test("workspace identity stable; list scroll kept; long title no overlap", async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem("storylens.onboarding.v1", "completed");
      localStorage.setItem("storylens.developerMode", "1");
      sessionStorage.setItem("storylens.uiAudit", "1");
    });
    await mockApis(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(ROUTE, { waitUntil: "domcontentloaded" });
    await page.getByTestId("reading-content-scroll-region").waitFor({ timeout: 20000 });
    await expect(page.getByTestId("book-workspace-page")).toBeVisible();

    const workspaceBefore = await page.getByTestId("book-workspace-page").evaluate((el) => el);
    const navBefore = await page.getByTestId("workspace-book-nav").evaluate((el) => el);

    await page.getByTestId("chapter-list-scroll-region").evaluate((el) => {
      (el as HTMLElement).scrollTop = 220;
    });
    const listTopBefore = await page
      .getByTestId("chapter-list-scroll-region")
      .evaluate((el) => (el as HTMLElement).scrollTop);

    await page.getByTestId("reading-content-scroll-region").evaluate((el) => {
      (el as HTMLElement).scrollTop = 180;
    });

    // Chapter 11 is nearby in 1-100 range — should not remount workspace.
    await page.locator('.workspace-chapter-item[data-chapter-id="11"]').click();
    await expect(page.locator(".workspace-chapter-heading")).toContainText("第11章");
    await expect(page.getByTestId("workspace-chapter-item-selected")).toHaveAttribute(
      "data-chapter-id",
      "11",
    );

    const workspaceAfter = await page.getByTestId("book-workspace-page").evaluate((el) => el);
    const navAfter = await page.getByTestId("workspace-book-nav").evaluate((el) => el);
    expect(workspaceAfter).toBe(workspaceBefore);
    expect(navAfter).toBe(navBefore);

    const listTopAfter = await page
      .getByTestId("chapter-list-scroll-region")
      .evaluate((el) => (el as HTMLElement).scrollTop);
    // nearest-if-needed should not yank list back to 0 for nearby selection
    expect(listTopAfter).toBeGreaterThan(100);
    expect(Math.abs(listTopAfter - listTopBefore)).toBeLessThan(80);

    await page.waitForTimeout(120);
    const readingTop = await page
      .getByTestId("reading-content-scroll-region")
      .evaluate((el) => (el as HTMLElement).scrollTop);
    expect(readingTop).toBe(0);

    // Long title row metrics — single line, no overlap with next row.
    await page.locator('[data-testid="workspace-sidebar-range-select"]').selectOption("1-100");
    const geom = await page.evaluate(() => {
      const a = document.querySelector(
        '.workspace-chapter-item[data-chapter-id="6"]',
      ) as HTMLElement | null;
      const b = document.querySelector(
        '.workspace-chapter-item[data-chapter-id="7"]',
      ) as HTMLElement | null;
      if (!a || !b) return null;
      const ar = a.getBoundingClientRect();
      const br = b.getBoundingClientRect();
      const title = a.querySelector(".workspace-chapter-title") as HTMLElement;
      const cs = getComputedStyle(title);
      return {
        heightA: ar.height,
        heightB: br.height,
        gap: br.top - ar.bottom,
        whiteSpace: cs.whiteSpace,
        overflow: cs.overflow,
        textOverflow: cs.textOverflow,
      };
    });
    expect(geom).toBeTruthy();
    expect(geom!.heightA).toBeGreaterThanOrEqual(34);
    expect(geom!.heightA).toBeLessThanOrEqual(40);
    expect(geom!.heightB).toBeGreaterThanOrEqual(34);
    expect(geom!.heightB).toBeLessThanOrEqual(40);
    expect(geom!.gap).toBeGreaterThanOrEqual(0);
    expect(geom!.whiteSpace).toBe("nowrap");
    expect(geom!.overflow).toBe("hidden");
    expect(geom!.textOverflow).toBe("ellipsis");
  });
});
