import path from "node:path";
import { test } from "@playwright/test";
import { installUiAuditMocks } from "./helpers/mockApi";
import { shot, prepareAuditSession, gotoReady } from "./helpers/shot";
import { FICTION_TXT } from "./fixtures/fictionTexts";
import fs from "node:fs";
import os from "node:os";

test.describe.configure({ mode: "serial" });
test.setTimeout(120_000);

const BOOK = "/books/1?chapter=1";

test.describe("03 reparse", () => {
  test.beforeEach(async ({ page }) => {
    await prepareAuditSession(page, { onboarding: "completed", developerMode: true });
  });

  test("reparse dialog modes", async ({ page }) => {
    await installUiAuditMocks(page, { importPreview: "ok" });
    await gotoReady(page, BOOK);
    await page.getByTestId("book-more-menu-trigger").click({ timeout: 10_000 });
    await page.getByTestId("book-more-reparse").click({ timeout: 10_000 });
    await page.getByTestId("reparse-dialog").waitFor({ timeout: 10_000 });
    await shot(page, { id: "03-12", file: "03_reparse_dialog.png", route: BOOK, theme: "light" });

    const tmp = path.join(os.tmpdir(), "fiction_reparse_audit.txt");
    fs.writeFileSync(tmp, FICTION_TXT, "utf8");
    await page.getByTestId("reparse-file-input").setInputFiles(tmp);
    await page.getByTestId("reparse-preview").waitFor({ timeout: 10_000 });
    await shot(page, { id: "03-13", file: "03_reparse_replace.png", route: BOOK, theme: "light" });
    await page.getByTestId("reparse-create-revision").scrollIntoViewIfNeeded();
    await shot(page, { id: "03-14", file: "03_reparse_revision.png", route: BOOK, theme: "light" });
  });
});
