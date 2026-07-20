import { expect, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { AUDIT_DIRTY_VISIBLE_PATTERNS } from "../../../src/services/auditDirtyVisibleText";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** Repo root: apps/desktop/e2e/ui-audit/helpers -> ../../../../.. */
export const REPO_ROOT = path.resolve(__dirname, "../../../../..");
export const AUDIT_WORK = path.join(REPO_ROOT, "artifacts", "ui-audit-work");
export const SCREENSHOT_DIR = path.join(AUDIT_WORK, "screenshots");
export const MANIFEST_PATH = path.join(AUDIT_WORK, "screenshot-manifest.jsonl");

export type ShotMeta = {
  id: string;
  file: string;
  route?: string;
  theme?: "light" | "dark";
  notes?: string;
  fullPage?: boolean;
  /** Strict visible dirty-token scan (undefined/null/NaN/…). Used by 04 workspace shots. */
  checkDirtyVisible?: boolean;
};

function ensureDirs() {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  fs.mkdirSync(AUDIT_WORK, { recursive: true });
}

/** Strip any accidental plaintext secrets from DOM before capture. */
export async function maskSecretsInDom(page: Page) {
  try {
    if (page.isClosed()) return;
    await page.evaluate(() => {
      const SECRET = /sk-[A-Za-z0-9]{8,}|Bearer\s+[A-Za-z0-9._-]{8,}|api[_-]?key["'\s:=]+[A-Za-z0-9_-]{8,}/gi;
      const walk = (node: Node) => {
        if (node.nodeType === Node.TEXT_NODE && node.textContent && SECRET.test(node.textContent)) {
          node.textContent = node.textContent.replace(SECRET, "****MASKED****");
        }
        node.childNodes.forEach(walk);
      };
      walk(document.body);
      document.querySelectorAll<HTMLInputElement>('input[type="password"], input[name*="key" i]').forEach((el) => {
        if (el.value && el.value.length > 0 && !/^\*+$/.test(el.value)) {
          el.setAttribute("data-audit-masked", "1");
        }
      });
    });
  } catch {
    /* page closed or navigate mid-shot */
  }
}

export async function assertAuditPageHealthy(page: Page) {
  if (page.isClosed()) {
    throw new Error("Audit page closed before screenshot");
  }
  const bodyText = await page.locator("body").innerText();
  const banned = [
    "Unexpected Application Error",
    "TypeError",
    "Cannot read properties of undefined",
    "is not a function",
  ];
  for (const token of banned) {
    if (bodyText.includes(token)) {
      throw new Error(`Audit page shows crash text: ${token}`);
    }
  }
  // Literal "undefined/undefined" progress or labels
  if (/\bundefined\b\/\bundefined\b/i.test(bodyText) || bodyText.includes("undefined/undefined")) {
    throw new Error("Audit page shows undefined/undefined");
  }
  // Scene catalog bug class — must never appear in any audit shot
  if (/Sundefined|Snull|SNaN/i.test(bodyText)) {
    throw new Error("Audit page shows dirty scene ordinal label");
  }
}

/** Visible text / control values only — not raw HTML / JS source. */
export async function assertNoDirtyVisibleText(page: Page) {
  const patternSources = AUDIT_DIRTY_VISIBLE_PATTERNS.map((re) => ({
    source: re.source,
    flags: re.flags,
  }));
  const hits = await page.evaluate((patterns) => {
    const dirty = patterns.map((p) => new RegExp(p.source, p.flags));
    const found: string[] = [];
    const pushIf = (raw: string | null | undefined) => {
      const text = (raw || "").trim();
      if (!text) return;
      for (const re of dirty) {
        if (re.test(text)) {
          found.push(text.slice(0, 120));
          return;
        }
      }
    };
    const walk = (node: Node) => {
      if (node.nodeType === Node.TEXT_NODE) {
        const parent = node.parentElement;
        if (!parent) return;
        const tag = parent.tagName;
        if (tag === "SCRIPT" || tag === "STYLE" || tag === "NOSCRIPT") return;
        const style = getComputedStyle(parent);
        if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") {
          return;
        }
        pushIf(node.textContent);
        return;
      }
      if (node.nodeType === Node.ELEMENT_NODE) {
        const el = node as HTMLElement;
        if (el.tagName === "SCRIPT" || el.tagName === "STYLE" || el.tagName === "NOSCRIPT") return;
        if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
          pushIf(el.value);
        }
        if (el instanceof HTMLSelectElement) {
          pushIf(el.value);
          const opt = el.selectedOptions?.[0];
          pushIf(opt?.textContent);
        }
        el.childNodes.forEach(walk);
      }
    };
    walk(document.body);
    return found;
  }, patternSources);
  if (hits.length) {
    throw new Error(`Audit page shows dirty visible text: ${hits[0]}`);
  }
}

export async function shot(page: Page, meta: ShotMeta) {
  ensureDirs();
  await assertAuditPageHealthy(page);
  if (meta.checkDirtyVisible) {
    await assertNoDirtyVisibleText(page);
  }
  await maskSecretsInDom(page);
  const file = meta.file.endsWith(".png") ? meta.file : `${meta.file}.png`;
  const target = path.join(SCREENSHOT_DIR, file);
  await page.screenshot({
    path: target,
    fullPage: meta.fullPage ?? true,
    animations: "disabled",
  });
  expect(fs.existsSync(target)).toBeTruthy();
  const record = {
    ...meta,
    file,
    captured_at: new Date().toISOString(),
    bytes: fs.statSync(target).size,
  };
  fs.appendFileSync(MANIFEST_PATH, `${JSON.stringify(record)}\n`, "utf8");
  return target;
}

export async function setTheme(page: Page, theme: "light" | "dark") {
  await applyProductTheme(page, theme);
}

/** Switch theme through the real product shell toggle (Zustand → `.app[data-theme]`). */
export async function applyProductTheme(page: Page, theme: "light" | "dark") {
  const shell = page.getByTestId("app-shell");
  await shell.waitFor({ timeout: 10_000 });
  const current = await shell.getAttribute("data-theme");
  if (current === theme) return;
  const toggle = page.locator(".theme-toggle-btn");
  await expect(toggle).toBeVisible();
  // Prefer DOM click so modal/backdrops cannot block the real product toggle handler.
  await toggle.evaluate((el: HTMLButtonElement) => el.click());
  await expect(shell).toHaveAttribute("data-theme", theme, { timeout: 5_000 });
}

export async function assertRealDarkTheme(page: Page) {
  const shell = page.getByTestId("app-shell");
  await expect(shell).toHaveAttribute("data-theme", "dark");
  const darkBg = await shell.evaluate((el) => getComputedStyle(el).backgroundColor);
  // Flip to light briefly to compare, then restore dark.
  await applyProductTheme(page, "light");
  const lightBg = await shell.evaluate((el) => getComputedStyle(el).backgroundColor);
  await applyProductTheme(page, "dark");
  expect(darkBg).not.toBe(lightBg);
  const journey = page.getByTestId("journey-workspace");
  if (await journey.count()) {
    const surface = await journey.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(surface).not.toMatch(/^rgb\(\s*255,\s*255,\s*255\s*\)$/);
  }
}

/** Assert analysis surfaces (dialog / progress inspector / boundary card) are truly dark. */
export async function assertAnalysisDarkSurfaces(page: Page, opts: { flipCompare?: boolean } = {}) {
  const flipCompare = opts.flipCompare ?? true;
  if (flipCompare) {
    await assertRealDarkTheme(page);
  } else {
    const shell = page.getByTestId("app-shell");
    await expect(shell).toHaveAttribute("data-theme", "dark");
    const bg = await shell.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(bg).not.toMatch(/^rgb\(\s*255,\s*255,\s*255\s*\)$/);
  }
  const candidates = [
    page.getByTestId("start-analysis-dialog"),
    page.getByTestId("chapter-analysis-progress"),
    page.locator(".review-candidate").first(),
    page.getByTestId("shell-boundary-review"),
  ];
  for (const loc of candidates) {
    if (!(await loc.count())) continue;
    const bg = await loc.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(bg, "analysis dark surface must not be pure white").not.toMatch(
      /^rgb\(\s*255,\s*255,\s*255\s*\)$/,
    );
  }
}

export async function prepareAuditSession(
  page: Page,
  opts: {
    onboarding?: "pending" | "completed" | "skipped";
    developerMode?: boolean;
    showAdvanced?: boolean;
    telemetry?: "UNKNOWN" | "ENABLED" | "DISABLED";
    clearLicense?: boolean;
  } = {},
) {
  const onboarding = opts.onboarding ?? "completed";
  const developerMode = opts.developerMode ?? true;
  const showAdvanced = opts.showAdvanced ?? false;
  const telemetry = opts.telemetry ?? "UNKNOWN";
  const clearLicense = opts.clearLicense ?? true;

  await page.addInitScript(
    ({ onboarding, developerMode, showAdvanced, telemetry, clearLicense }) => {
      // onboardingStore persists plain status string: "completed" | "skipped"
      if (onboarding === "pending") {
        localStorage.removeItem("storylens.onboarding.v1");
      } else {
        localStorage.setItem("storylens.onboarding.v1", onboarding);
      }
      localStorage.setItem("storylens.developerMode", developerMode ? "1" : "0");
      if (showAdvanced) {
        localStorage.setItem("storylens.showAdvancedSettings", "1");
      } else {
        localStorage.removeItem("storylens.showAdvancedSettings");
      }
      if (telemetry === "UNKNOWN") {
        localStorage.removeItem("storylens.telemetry.consent");
      } else {
        localStorage.setItem("storylens.telemetry.consent", telemetry);
      }
      if (clearLicense) {
        localStorage.removeItem("storylens.license.dev.mock");
      }
      // Reset Reader Journey UI prefs so layout audits start from defaults.
      try {
        for (const key of Object.keys(localStorage)) {
          if (key.startsWith("storylens.readerJourney.")) localStorage.removeItem(key);
        }
      } catch {
        /* ignore */
      }
      sessionStorage.setItem("storylens.screenshotInit", "1");
      sessionStorage.setItem("storylens.uiAudit", "1");
    },
    { onboarding, developerMode, showAdvanced, telemetry, clearLicense },
  );
}

export async function gotoReady(page: Page, route: string) {
  await page.goto(route, { waitUntil: "domcontentloaded" });
  // Wait past bootstrap starting screen
  await page.getByTestId("desktop-bootstrap-starting").waitFor({ state: "hidden", timeout: 15000 }).catch(() => undefined);
  await page.waitForTimeout(300);
}
