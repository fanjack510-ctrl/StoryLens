/**
 * CHG-20260803-047 — Evidence deep-link / restore / production route isolation.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  EvidenceChapterIdMissingError,
  buildWholeBookEvidenceSearchParams,
  openEvidenceInReader,
  openEvidenceInReaderFromSource,
  readEvidenceRestoreState,
  resolveEvidenceChapterId,
  wholeBookFreeModuleHref,
} from "../services/wholeBookFreeEvidenceDeepLink";
import type { EvidenceSourceDetail } from "../services/wholeBookFreeProductApi";

function source(overrides: Partial<EvidenceSourceDetail> = {}): EvidenceSourceDetail {
  return {
    evidence_id: 501,
    chapter_id: 42,
    chapter_index: 1,
    chapter_title: "第1章",
    paragraph_index: 3,
    global_paragraph_index: 3,
    paragraph_text: "林凡踏入山门，心中忐忑。",
    quote_text: "踏入山门",
    start_offset: 2,
    end_offset: 6,
    paragraph_text_hash: "ph",
    snapshot_id: 11,
    state: "valid",
    ...overrides,
  };
}

describe("Evidence chapter_id vs chapter_index", () => {
  it("uses real chapter_id and keeps chapter_index as display-only", () => {
    const params = buildWholeBookEvidenceSearchParams(source(), 42, {
      returnModule: "overview",
    });
    expect(params.get("chapter")).toBe("42");
    expect(params.get("chapterId")).toBe("42");
    expect(params.get("chapterIndex")).toBe("1");
    expect(params.get("paragraphIndex")).toBe("3");
    expect(params.get("startOffset")).toBe("2");
    expect(params.get("endOffset")).toBe("6");
    expect(params.get("snapshotId")).toBe("11");
    expect(params.get("returnModule")).toBe("overview");
    expect(params.toString()).not.toContain("evidence_map");
  });

  it("throws when chapter_id is missing — does not fall back to chapter_index", () => {
    expect(() => resolveEvidenceChapterId(source({ chapter_id: null }))).toThrow(
      EvidenceChapterIdMissingError,
    );
    expect(() =>
      openEvidenceInReaderFromSource(1, source({ chapter_id: null }), {
        returnModule: "characters_events",
      }),
    ).toThrow("EVIDENCE_CHAPTER_ID_MISSING");
  });

  it("rejects using chapter_index as chapter id when source.chapter_id differs", () => {
    expect(() => openEvidenceInReader(1, source(), 1)).toThrow("EVIDENCE_CHAPTER_ID_MISSING");
  });

  it("rejects stale evidence without opening another revision silently", () => {
    expect(() => openEvidenceInReaderFromSource(1, source({ state: "stale" }))).toThrow(
      "EVIDENCE_STALE",
    );
  });
});

describe("Chapter Functions restore URL", () => {
  it("persists function/status/cursor/detail restore anchors", () => {
    const href = openEvidenceInReaderFromSource(8, source(), {
      returnModule: "chapter_functions",
      restore: {
        restoreFunction: "climax",
        restoreStatus: "observed",
        restoreCursor: "cur-9",
        restoreChapter: "12",
      },
    });
    expect(href).toContain("returnModule=chapter_functions");
    expect(href).toContain("restoreFunction=climax");
    expect(href).toContain("restoreStatus=observed");
    expect(href).toContain("restoreCursor=cur-9");
    expect(href).toContain("restoreChapter=12");
    expect(href).toContain("chapter=42");
  });

  it("rebuilds free module href with filters and detail for refresh/reentry", () => {
    const href = wholeBookFreeModuleHref(8, "chapter_functions", {
      restoreFunction: "setup",
      restoreStatus: "inferred",
      restoreCursor: "cur-1",
      restoreChapter: "3",
    });
    expect(href).toBe(
      "/books/8/whole-book?module=chapter_functions&restoreFunction=setup&restoreStatus=inferred&restoreCursor=cur-1&restoreChapter=3&cfFunction=setup&cfStatus=inferred&cfChapter=3",
    );
  });

  it("reads restore state from reader URL search params", () => {
    const params = new URLSearchParams(
      "returnTo=whole-book&returnModule=chapter_functions&restoreFunction=climax&restoreCursor=c1&cfChapter=9",
    );
    expect(readEvidenceRestoreState(params)).toEqual({
      restoreFunction: "climax",
      restoreStatus: null,
      restoreCursor: "c1",
      restoreChapter: "9",
    });
  });
});

describe("Production route registration", () => {
  it("gates /dev/* routes behind import.meta.env.DEV only", () => {
    const routerSource = readFileSync(join(process.cwd(), "src/app/router.tsx"), "utf8");
    expect(routerSource).toContain("import.meta.env.DEV");
    expect(routerSource).toContain("/dev/whole-book-diagnostics");
    expect(routerSource).toContain("/dev/whole-book-free-chapter-functions-harness");
    expect(routerSource).toMatch(
      /const devOnlyChildren = import\.meta\.env\.DEV\s*\?\s*\[[\s\S]*\/dev\//,
    );
    expect(routerSource).toContain("...devOnlyChildren");
    // Mock lab must not be registered on the product router.
    expect(routerSource).not.toContain("whole-book-mock-run-lab");
    expect(routerSource).not.toContain("WholeBookMockRunLab");
    expect(routerSource).not.toContain("failure-injection");
    expect(routerSource).not.toContain("FakeProvider");
  });

  it("source tree has no fuzzy indexOf fallback in Free product drawer", () => {
    const pageSource = readFileSync(
      join(process.cwd(), "src/pages/WholeBookFreeProductPage.tsx"),
      "utf8",
    );
    expect(pageSource).toContain("highlightQuoteExact");
    expect(pageSource).not.toMatch(/paragraphText\.indexOf\(quoteText\)/);
    expect(pageSource).not.toContain("evidence_map");
  });
});
