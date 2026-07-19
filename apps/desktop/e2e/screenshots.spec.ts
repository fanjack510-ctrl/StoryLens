import { test } from "@playwright/test";
import { mkdirSync } from "node:fs";
const out = "../../docs/screenshots/phase2a";
test("phase2a screenshots", async ({ page }) => {
  mkdirSync(out, { recursive: true });
  const shots: [string, string][] = [
    ["/", "01_home_light.png"],
    ["/library", "02_library.png"],
    ["/books/1", "03_book_workspace.png"],
    ["/books/1", "04_scene_evidence.png"],
    ["/tasks", "05_tasks.png"],
    ["/providers", "06_providers_overview.png"],
    ["/providers", "07_aliyun_configuration.png"],
    ["/providers", "08_cloud_disconnected.png"],
    ["/settings", "09_settings_diagnostics.png"],
  ];
  for (const [path, name] of shots) {
    await page.goto(path);
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${out}/${name}`, fullPage: true });
  }
  await page.goto("/");
  await page.getByText("深色").click();
  await page.screenshot({ path: `${out}/10_home_dark.png`, fullPage: true });
});
