import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const globalCss = readFileSync(
  resolve(__dirname, "../../styles/global.css"),
  "utf8",
);
const chapterResultCss = readFileSync(
  resolve(__dirname, "../chapterResult/chapterResult.css"),
  "utf8",
);

describe("Reader Journey width root-cause guards", () => {
  it("excludes journey sync workspace from book-shell 240px first-track rule", () => {
    expect(globalCss).toMatch(
      /\.book-shell-simplified\s+\.workspace:not\(:has\(\.artifact\)\):not\(\.results-page-journey-sync\)/,
    );
    expect(globalCss).not.toMatch(
      /\.book-shell-simplified\s+\.workspace:not\(:has\(\.artifact\)\)\s*\{[^}]*grid-template-columns:\s*240px/s,
    );
  });

  it("forces journey sync page to a single fluid column", () => {
    expect(globalCss).toMatch(
      /\.results-page-journey-sync\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s*!important/s,
    );
    expect(chapterResultCss).toMatch(
      /\.analysis-result-route-adapter\s+\.results-page-journey-sync\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s*!important/s,
    );
  });

  it("does not let ≤1280 workspace media override crush journey sync", () => {
    expect(globalCss).toMatch(
      /@media\s*\(max-width:\s*1280px\)\s*\{[\s\S]*?\.workspace:not\(\.results-page-journey-sync\)\s*\{/,
    );
  });
});
