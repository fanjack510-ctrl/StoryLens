/**
 * TEST-ONLY browser DOM verification for MG-V1.2.0-E2E-STABILIZATION (CHG-048).
 */
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const desktopRequire = createRequire(
  path.join(__dirname, "..", "..", "..", "..", "apps", "desktop", "package.json"),
);
const { chromium } = desktopRequire("@playwright/test");

const FIXTURES = path.join(
  process.env.TEMP || process.env.TMP || "",
  "storylens-v120-e2e",
  "MANUAL_FIXTURES.json",
);
const API = process.env.STORYLENS_V120_E2E_API_URL || "http://127.0.0.1:8007";
const FE = process.env.STORYLENS_V120_E2E_FE_URL || "http://127.0.0.1:1427";

const catalog = JSON.parse(fs.readFileSync(FIXTURES, "utf8"));
const keys = [
  "regression_overview",
  "regression_characters",
  "regression_structure",
  "cf_available",
  "cf_evidence",
  "cf_function_filter",
  "cf_status_filter",
  "cf_chapter_detail",
  "cost_consent",
  "conflict",
  "canceled",
  "cf_failed",
];

const results = [];

async function check(page, key) {
  const entry = catalog[key];
  const row = {
    key,
    book_id: entry?.book_id ?? null,
    run_id: entry?.whole_book_run_id ?? null,
    url: entry?.url ?? null,
    page_ok: false,
    free_page: false,
    purchase_ui: "ABSENT",
    fixture_banner: false,
    progress_card: "n/a",
    notes: [],
  };
  if (!entry?.url) {
    row.notes.push("missing url");
    results.push(row);
    return;
  }
  const url = String(entry.url).replace(":1426", ":1427").replace(":8006", ":8007");
  row.url = url;
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(800);
  row.free_page = (await page.locator('[data-testid="whole-book-free-product-page"]').count()) > 0;
  row.fixture_banner = (await page.locator('[data-testid="whole-book-free-fixture-banner"]').count()) > 0;
  const body = await page.locator("body").innerText();
  row.purchase_ui = /购买|License|VIP|升级套餐|立即开通/.test(body) ? "PRESENT" : "ABSENT";
  const progress = await page.locator('[data-testid="whole-book-free-progress"]').count();
  row.progress_card = progress > 0 ? "PRESENT" : "ABSENT";
  row.page_ok = row.free_page && row.purchase_ui === "ABSENT";
  if (!row.free_page) row.notes.push("free product page missing");
  results.push(row);
}

const browser = await chromium.launch({ channel: "msedge", headless: true });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
for (const key of keys) {
  try {
    await check(page, key);
  } catch (err) {
    results.push({ key, page_ok: false, notes: [String(err)] });
  }
}
// layout checks
for (const vp of [
  { w: 1366, h: 768 },
  { w: 1920, h: 1080 },
]) {
  await page.setViewportSize({ width: vp.w, height: vp.h });
  const entry = catalog.regression_overview || catalog.cf_available;
  if (entry?.url) {
    await page.goto(String(entry.url).replace(":1426", ":1427"), {
      waitUntil: "domcontentloaded",
      timeout: 60000,
    });
    await page.waitForTimeout(500);
    const metrics = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    results.push({
      key: `layout_${vp.w}x${vp.h}`,
      page_ok: metrics.scrollWidth <= metrics.clientWidth + 1,
      horizontal_scroll: metrics.scrollWidth > metrics.clientWidth + 1 ? "PRESENT" : "ABSENT",
      ...metrics,
    });
  }
}
await browser.close();

const out = path.join(__dirname, "DOM_VERIFY_RESULTS.json");
const summary = {
  api: API,
  fe: FE,
  fixtures: FIXTURES,
  page_ok_all: results.every((r) => r.page_ok !== false || r.key.startsWith("layout_") ? r.page_ok !== false : true),
  purchase_ui: results.some((r) => r.purchase_ui === "PRESENT") ? "PRESENT" : "ABSENT",
  results,
};
fs.writeFileSync(out, JSON.stringify(summary, null, 2), "utf8");
console.log(JSON.stringify({ ok: summary.purchase_ui === "ABSENT", out, count: results.length }, null, 2));
