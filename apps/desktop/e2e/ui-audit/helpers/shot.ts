import { expect, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

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
}

export async function shot(page: Page, meta: ShotMeta) {
  ensureDirs();
  await assertAuditPageHealthy(page);
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
  await page.evaluate((t) => {
    localStorage.setItem("storylens.theme", t);
    document.documentElement.dataset.theme = t;
    document.documentElement.classList.toggle("dark", t === "dark");
  }, theme);
  // Prefer clicking the theme toggle if present for real CSS application
  const darkBtn = page.getByText("深色", { exact: true });
  const lightBtn = page.getByText("浅色", { exact: true });
  if (theme === "dark" && (await darkBtn.count())) {
    await darkBtn.click().catch(() => undefined);
  }
  if (theme === "light" && (await lightBtn.count())) {
    await lightBtn.click().catch(() => undefined);
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
