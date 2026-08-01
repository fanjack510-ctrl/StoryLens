/**
 * TEST-ONLY Playwright layout verification for CHG-20260801-031.
 * Run from apps/desktop with live UI pointed at SMOKE_UI / SMOKE_API.
 */
import { chromium } from "playwright";
import fs from "fs";
import path from "path";

const UI = process.env.STORYLENS_CHG031_UI || "http://127.0.0.1:1424";
const OVERVIEW_PATH = process.env.STORYLENS_CHG031_OVERVIEW_PATH || "/books/8/whole-book";
const COST_PATH = process.env.STORYLENS_CHG031_COST_PATH || "/books/9/whole-book";
const OUT_DIR =
  process.env.STORYLENS_CHG031_OUT ||
  path.resolve("../../../release/evidence/whole-book/CHG-20260801-031");

fs.mkdirSync(OUT_DIR, { recursive: true });

function report(name, ok, detail = {}) {
  console.log(JSON.stringify({ check: name, ok, ...detail }));
  return ok;
}

async function measure(page) {
  return page.evaluate(() => {
    const root = document.querySelector('[data-testid="whole-book-free-product-page"]');
    const layout = document.querySelector('[data-testid="whole-book-free-layout"]');
    const nav = document.querySelector('[data-testid="whole-book-free-module-nav"]');
    const main = document.querySelector('[data-testid="whole-book-free-main-content"]');
    const shell = document.querySelector('[data-testid="app-shell"]');
    const shellMain = shell?.querySelector("main") || null;
    // Exclude evidence buttons (…-claim-evidence-*).
    const claims = [...document.querySelectorAll('[data-testid^="whole-book-free-claim-"]')].filter(
      (el) => !String(el.getAttribute("data-testid") || "").includes("-claim-evidence-"),
    );
    // Prefer layout CSS pixels (offsetWidth) — html zoom would shrink getBoundingClientRect.
    const box = (el) => {
      if (!el) return null;
      return {
        x: el.offsetLeft,
        y: el.offsetTop,
        width: el.offsetWidth,
        height: el.offsetHeight,
        top: el.offsetTop,
        left: el.offsetLeft,
      };
    };
    const claimRects = claims.map((c) => c.getBoundingClientRect());
    let claimColumns = 1;
    if (claimRects.length >= 2) {
      const firstTop = Math.round(claimRects[0].top / 8) * 8;
      claimColumns = claimRects.filter((r) => Math.round(r.top / 8) * 8 === firstTop).length;
    }
    const rootCs = root ? getComputedStyle(root) : null;
    const navBox = nav ? nav.getBoundingClientRect() : null;
    const mainBox = main ? main.getBoundingClientRect() : null;
    return {
      viewport: { w: window.innerWidth, h: window.innerHeight },
      zoom: getComputedStyle(document.documentElement).zoom || "1",
      rootCssMaxWidth: rootCs?.maxWidth || null,
      rootCssWidth: rootCs?.width || null,
      root: box(root),
      layout: box(layout),
      nav: box(nav),
      main: box(main),
      shellMain: box(shellMain),
      navScreenX: navBox?.x ?? null,
      mainScreenX: mainBox?.x ?? null,
      claimCount: claims.length,
      claimColumns,
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
      hasProPurchase: /购买|升级\s*Pro|立即开通/.test(document.body.innerText),
      hasFixture: document.body.innerText.includes("测试数据"),
      hasError404: document.body.innerText.includes("无法读取数据") || document.body.innerText.includes("HTTP 404"),
    };
  });
}

async function shot(page, name) {
  const p = path.join(OUT_DIR, name);
  await page.screenshot({ path: p, fullPage: false });
  return p;
}

const results = [];
const browser = await chromium.launch({ headless: true });

async function runViewport(label, w, h, { overviewShot, costShot }) {
  const page = await browser.newPage({ viewport: { width: w, height: h } });
  await page.goto(`${UI}${OVERVIEW_PATH}`, { waitUntil: "networkidle", timeout: 60000 });
  await page.waitForTimeout(1200);
  const m = await measure(page);
  if (overviewShot) await shot(page, overviewShot);

  const shellW = m.shellMain?.width || w - 200;
  const rootW = m.root?.width || 0;
  const navW = m.nav?.width || 0;
  const mainW = m.main?.width || 0;
  const noHScroll = m.scrollWidth <= m.clientWidth + 1;
  // Workbench must beat the old ~650–900 centered article column.
  const wideEnough = rootW >= Math.min(1200, shellW * 0.72) || rootW >= 1200;
  const notNarrowFixed = rootW > 1000 || w < 1280;
  const twoColOk = w >= 1440 ? m.claimColumns >= 2 : true;
  const mainWider = mainW > navW;
  const sideBySide =
    w > 1050
      ? m.navScreenX != null &&
        m.mainScreenX != null &&
        m.navScreenX < m.mainScreenX
      : true;

  results.push(
    report(`${label}/overview-width`, wideEnough && notNarrowFixed, {
      rootW,
      shellW,
      claimColumns: m.claimColumns,
      claimCount: m.claimCount,
    }),
  );
  results.push(report(`${label}/no-hscroll`, noHScroll, { scrollWidth: m.scrollWidth, clientWidth: m.clientWidth }));
  results.push(report(`${label}/nav-main`, mainWider && sideBySide && !m.hasError404, { navW, mainW, sideBySide }));
  results.push(report(`${label}/claims`, m.claimCount === 9 && twoColOk, { claimColumns: m.claimColumns }));
  results.push(report(`${label}/no-pro-purchase`, !m.hasProPurchase));

  await page.goto(`${UI}${COST_PATH}`, { waitUntil: "networkidle", timeout: 60000 });
  await page.waitForTimeout(1000);
  if (costShot) await shot(page, costShot);
  const costOk =
    (await page.locator('[data-testid="whole-book-free-prepare"]').count()) > 0 &&
    (await page.locator('[data-testid="whole-book-free-consent"]').count()) > 0 &&
    (await page.locator('[data-testid="whole-book-free-cost-estimate"]').count()) > 0;
  const limitsGrid = page.locator('[data-testid="whole-book-free-limits-grid"]');
  let limitsCols = 1;
  if ((await limitsGrid.count()) > 0) {
    limitsCols = await limitsGrid.evaluate((el) => {
      const style = getComputedStyle(el);
      const tpl = style.gridTemplateColumns || "";
      return tpl.split(" ").filter(Boolean).length || 1;
    });
  }
  const limitsOk = w >= 1440 ? limitsCols >= 3 : limitsCols >= 1;
  results.push(report(`${label}/cost-consent`, costOk && limitsOk, { limitsCols }));

  const hscrollCost = await page.evaluate(
    () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
  );
  results.push(report(`${label}/cost-no-hscroll`, hscrollCost));
  await page.close();
}

await runViewport("1920x1080", 1920, 1080, {
  overviewShot: "after-overview-1920x1080.png",
  costShot: "after-cost-consent-1920x1080.png",
});
await runViewport("1366x768", 1366, 768, {
  overviewShot: "after-overview-1366x768.png",
  costShot: "after-cost-consent-1366x768.png",
});
await runViewport("1280x720", 1280, 720, { overviewShot: null, costShot: null });
await runViewport("1440x900", 1440, 900, { overviewShot: null, costShot: null });
await runViewport("2560x1440", 2560, 1440, { overviewShot: null, costShot: null });

await browser.close();
const failed = results.filter((r) => !r);
const summary = { passed: results.filter(Boolean).length, failed: failed.length, outDir: OUT_DIR };
console.log("SUMMARY", JSON.stringify(summary));
process.exit(failed.length ? 1 : 0);
