/** Not a permanent test — a build harness: when RENDER_INPUT/RENDER_OUTPUT are set, render
 *  that analysis JSON through the real exporter and write the HTML to disk. Skipped in
 *  normal runs. Kept as a test file so it runs through the exact vitest/TS toolchain the
 *  product uses, with zero extra build setup. */
import { readFileSync, writeFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { parseWholeBookV2 } from "./adapter";
import { buildReportHtml } from "./reportExport";

describe("render report from file", () => {
  const src = process.env.RENDER_INPUT;
  const dst = process.env.RENDER_OUTPUT;
  it.skipIf(!src || !dst)("renders", () => {
    const data = parseWholeBookV2(JSON.parse(readFileSync(src!, "utf-8")));
    const html = buildReportHtml(data);
    writeFileSync(dst!, html, "utf-8");
    expect(html.length).toBeGreaterThan(10000);
  });
});
