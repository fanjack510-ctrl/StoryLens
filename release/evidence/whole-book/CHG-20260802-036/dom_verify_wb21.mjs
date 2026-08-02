/**
 * TEST-ONLY browser DOM verification for WB-2.1 MG-WB-2.1 smoke (CHG-036).
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
  "storylens-wb21-integration",
  "MANUAL_FIXTURES.json",
);
const API = process.env.STORYLENS_WB21_API_URL || "http://127.0.0.1:8005";
const FE = process.env.STORYLENS_WB21_FE_URL || "http://127.0.0.1:1425";

const catalog = JSON.parse(fs.readFileSync(FIXTURES, "utf8"));
const results = [];

async function apiStatus(runId) {
  if (runId == null) return { http: null };
  const url = `${API}/api/v1/whole-book/runs/${runId}/structure`;
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
    expected: entry.expected_display || entry.expected_initial,
    page_ok: false,
    api_http: null,
    structure_visible: false,
    evidence_clickable: false,
    purchase_ui: "ABSENT",
    notes: [],
  };

  if (entry.whole_book_run_id != null) {
    const api = await apiStatus(entry.whole_book_run_id);
    row.api_http = api.http;
    if (![200, 404].includes(api.http) && key !== "structure_absent") {
      row.notes.push(`unexpected API status ${api.http}`);
    }
  } else {
    const prep = await fetch(`${API}/api/v1/books/${entry.book_id}/whole-book/prepare`);
    row.api_http = prep.status;
  }

  await page.goto(entry.url, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForTimeout(800);
  row.page_ok = true;

  const structureNav = page.getByRole("button", { name: /故事结构/ }).or(
    page.locator('[data-testid="whole-book-free-module-structure"]'),
  );
  if (await structureNav.count()) {
    await structureNav.first().click({ timeout: 5000 }).catch(() => {});
  }

  const disabledGate = await page.getByText("正式全书分析入口未启用").count();
  if (disabledGate) {
    row.notes.push("FREE_PRODUCT_FLAG_DISABLED");
  }

  const panel = page.locator('[data-testid="whole-book-free-structure"]');
  if (await panel.count()) {
    row.structure_visible = true;
    const state = await panel.first().getAttribute("data-state");
    if (state) row.notes.push(`data-state=${state}`);
  } else {
    const bodyText = await page.locator("body").innerText();
    if (/故事结构|全书分析|费用|确认|尚未|开发中|未分析|同意/.test(bodyText)) {
      row.structure_visible = true;
      row.notes.push("page text contains whole-book/structure cues");
    }
  }

  const evidenceBtn = page.locator(
    '[data-testid*="evidence"], button:has-text("证据"), button:has-text("查看原文"), a:has-text("证据")',
  );
  if (await evidenceBtn.count()) {
    row.evidence_clickable = true;
  }

  const purchase = page.locator(
    'text=/购买|升级到 Pro|激活|付款|License|订阅 Pro/i',
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
  "structure_available",
  "non_three_act",
  "turning_points_empty",
  "insufficient",
  "failed",
  "canceled",
  "conflict",
  "evidence",
  "structure_absent",
  "cost_consent",
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
  change_id: "CHG-20260802-036",
  verified_at: new Date().toISOString(),
  frontend: FE,
  api: API,
  fixtures: FIXTURES,
  results,
  purchase_ui_any: results.some((r) => r.purchase_ui === "PRESENT") ? "PRESENT" : "ABSENT",
  page_ok_all: results.every((r) => r.page_ok),
};
fs.writeFileSync(outPath, JSON.stringify(summary, null, 2) + "\n", "utf8");
console.log(JSON.stringify(summary, null, 2));
process.exit(summary.page_ok_all && summary.purchase_ui_any === "ABSENT" ? 0 : 1);
