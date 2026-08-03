/**
 * TEST-ONLY browser DOM verification for WB-2.2 MG-WB-2.2 smoke (CHG-042).
 * Uses catalog MANUAL_FIXTURES.json — never infers READY from DB alone.
 */
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const desktopRequire = createRequire(
  path.join(
    __dirname,
    "..",
    "..",
    "..",
    "..",
    "apps",
    "desktop",
    "package.json",
  ),
);
const { chromium } = desktopRequire("@playwright/test");

const FIXTURES = path.join(
  process.env.TEMP || process.env.TMP || "",
  "storylens-wb22-integration",
  "MANUAL_FIXTURES.json",
);
const API = process.env.STORYLENS_WB22_API_URL || "http://127.0.0.1:8006";
const FE = process.env.STORYLENS_WB22_FE_URL || "http://127.0.0.1:1426";

const catalog = JSON.parse(fs.readFileSync(FIXTURES, "utf8"));
const results = [];

async function apiChapterFunctions(runId) {
  if (runId == null) return { http: null };
  const url = `${API}/api/v1/whole-book/runs/${runId}/chapter-functions`;
  const resp = await fetch(url);
  let body = null;
  try {
    body = await resp.json();
  } catch {
    body = null;
  }
  return { http: resp.status, body };
}

async function checkEntry(page, key, entry) {
  const row = {
    key,
    book_id: entry.book_id,
    run_id: entry.whole_book_run_id,
    url: entry.url,
    seeded: entry.seeded !== false,
    expected: entry.expected_display || entry.expected_initial,
    page_ok: false,
    api_http: null,
    chapter_functions_visible: false,
    evidence_clickable: false,
    purchase_ui: "ABSENT",
    notes: [],
  };

  if (entry.seeded === false) {
    row.notes.push("seeded=false; skipped deep checks; expected manual fixture");
    row.page_ok = true;
    results.push(row);
    return row;
  }

  if (entry.whole_book_run_id != null) {
    const api = await apiChapterFunctions(entry.whole_book_run_id);
    row.api_http = api.http;
    if (![200, 404].includes(api.http) && !String(key).includes("absent")) {
      row.notes.push(`unexpected API status ${api.http}`);
    }
    if (api.body?.result_status) {
      row.notes.push(`api_result_status=${api.body.result_status}`);
    }
  } else {
    const prep = await fetch(`${API}/api/v1/books/${entry.book_id}/whole-book/prepare`);
    row.api_http = prep.status;
  }

  await page.goto(entry.url, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForTimeout(900);
  row.page_ok = true;

  const moduleKey = (() => {
    try {
      return new URL(entry.url).searchParams.get("module") || "";
    } catch {
      return "";
    }
  })();

  if (moduleKey === "chapter_functions" || !moduleKey) {
    const cfNav = page.getByRole("button", { name: /章节功能/ }).or(
      page.locator('[data-testid="whole-book-free-module-chapter_functions"]'),
    );
    if (await cfNav.count()) {
      await cfNav.first().click({ timeout: 5000 }).catch(() => {});
      await page.waitForTimeout(400);
    }
  } else if (moduleKey === "structure") {
    const structureNav = page.getByRole("button", { name: /故事结构/ }).or(
      page.locator('[data-testid="whole-book-free-module-structure"]'),
    );
    if (await structureNav.count()) {
      await structureNav.first().click({ timeout: 5000 }).catch(() => {});
    }
  }

  const disabledGate = await page.getByText("正式全书分析入口未启用").count();
  if (disabledGate) {
    row.notes.push("FREE_PRODUCT_FLAG_DISABLED");
  }

  const cfPanel = page.locator('[data-testid="whole-book-free-chapter-functions"]');
  if (await cfPanel.count()) {
    row.chapter_functions_visible = true;
    const state = await cfPanel.first().getAttribute("data-state");
    if (state) row.notes.push(`data-state=${state}`);
  } else {
    const structurePanel = page.locator('[data-testid="whole-book-free-structure"]');
    if (await structurePanel.count()) {
      row.chapter_functions_visible = true;
      const state = await structurePanel.first().getAttribute("data-state");
      if (state) row.notes.push(`structure_data-state=${state}`);
    } else {
      const bodyText = await page.locator("body").innerText();
      if (/章节功能|故事结构|全书分析|费用|确认|尚未|开发中|未分析|同意/.test(bodyText)) {
        row.chapter_functions_visible = true;
        row.notes.push("page text contains whole-book/chapter-functions cues");
      }
    }
  }

  const evidenceBtn = page.locator(
    '[data-testid*="evidence"], button:has-text("证据"), button:has-text("查看原文"), a:has-text("证据")',
  );
  if (await evidenceBtn.count()) {
    row.evidence_clickable = true;
  }

  const purchase = page.locator(
    "text=/购买|升级到 Pro|激活|付款|License|订阅 Pro/i",
  );
  if (await purchase.count()) {
    row.purchase_ui = "PRESENT";
  }

  results.push(row);
  return row;
}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });

const keys = [
  "cf_available",
  "cf_primary_secondary",
  "cf_primary_null",
  "cf_secondary_empty",
  "cf_partial",
  "cf_insufficient",
  "cf_failed",
  "canceled",
  "conflict",
  "cf_evidence",
  "cf_absent",
  "cf_long_book_pagination",
  "cf_function_filter",
  "cf_status_filter",
  "cf_chapter_detail",
  "wb21_context_available",
  "wb21_context_absent",
  "wb21_context_insufficient",
  "cost_consent",
  "regression_overview",
  "regression_characters",
  "regression_structure",
];

for (const key of keys) {
  const entry = catalog[key];
  if (!entry || typeof entry !== "object" || !entry.book_id) continue;
  try {
    await checkEntry(page, key, entry);
  } catch (err) {
    results.push({
      key,
      book_id: entry.book_id,
      run_id: entry.whole_book_run_id,
      url: entry.url,
      page_ok: false,
      error: String(err),
      purchase_ui: "UNKNOWN",
    });
  }
}

await browser.close();

const outDir = __dirname;
const outPath = path.join(outDir, "DOM_VERIFY_RESULTS.json");
const summary = {
  change_id: "CHG-20260803-042",
  verified_at: new Date().toISOString(),
  frontend: FE,
  api: API,
  fixtures: FIXTURES,
  results,
  purchase_ui_any: results.some((r) => r.purchase_ui === "PRESENT") ? "PRESENT" : "ABSENT",
  page_ok_all: results.length > 0 && results.every((r) => r.page_ok),
  catalog_keys_checked: results.map((r) => r.key),
};
fs.writeFileSync(outPath, JSON.stringify(summary, null, 2) + "\n", "utf8");
console.log(JSON.stringify(summary, null, 2));
process.exit(summary.page_ok_all && summary.purchase_ui_any === "ABSENT" ? 0 : 1);
