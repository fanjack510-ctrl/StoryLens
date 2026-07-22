import { describe, expect, it } from "vitest";
import type { Chapter } from "../types";
import {
  adjacentBodyChapters,
  bodyChapters,
  bodyOrdinalOf,
  buildChapterRanges,
  buildChapterReadingSearchParams,
  chapterByBodyOrdinal,
  filterChaptersByTitle,
  resolveOrdinalJump,
} from "./chapterNavigation";

function ch(
  id: number,
  opts: Partial<Chapter> & { section_type?: string } = {},
): Chapter {
  return {
    id,
    book_id: 1,
    chapter_index: id,
    title: opts.title || `第${id}章`,
    display_title: opts.display_title || opts.title || `第${id}章`,
    word_count: 10,
    section_type: opts.section_type || "chapter",
    chapter_number_normalized: opts.chapter_number_normalized ?? id,
  };
}

describe("chapterNavigation", () => {
  const chapters = [
    ch(10, { section_type: "front_matter", title: "前言", display_title: "前言" }),
    ch(101, { title: "戏鬼回家", chapter_number_normalized: 1 }),
    ch(205, { title: "灾厄", chapter_number_normalized: 2 }),
    ch(999, { title: "终章", chapter_number_normalized: 3 }),
  ];

  it("excludes front_matter from body ordinals", () => {
    expect(bodyChapters(chapters)).toHaveLength(3);
    expect(bodyOrdinalOf(chapters, 101)).toBe(1);
    expect(bodyOrdinalOf(chapters, 999)).toBe(3);
    expect(bodyOrdinalOf(chapters, 10)).toBeNull();
  });

  it("resolves ordinal jump by reading order, not database id", () => {
    const hit = resolveOrdinalJump(chapters, "2");
    expect(hit.ok).toBe(true);
    if (hit.ok) {
      expect(hit.chapter.id).toBe(205);
      expect(hit.ordinal).toBe(2);
    }
    expect(chapterByBodyOrdinal(chapters, 800)).toBeNull();
  });

  it("rejects invalid and out-of-range ordinals", () => {
    expect(resolveOrdinalJump(chapters, "0").ok).toBe(false);
    expect(resolveOrdinalJump(chapters, "abc")).toEqual({
      ok: false,
      reason: "invalid",
      total: 3,
    });
    expect(resolveOrdinalJump(chapters, "4")).toEqual({
      ok: false,
      reason: "out_of_range",
      total: 3,
    });
  });

  it("builds 100-chapter ranges including a short final bucket", () => {
    const ranges = buildChapterRanges(1299);
    expect(ranges[0]).toEqual({ startOrdinal: 1, endOrdinal: 100, label: "1—100" });
    expect(ranges[ranges.length - 1]).toEqual({
      startOrdinal: 1201,
      endOrdinal: 1299,
      label: "1201—1299",
    });
    expect(ranges).toHaveLength(13);
  });

  it("filters titles locally", () => {
    expect(filterChaptersByTitle(chapters, " 灾 ").map((c) => c.id)).toEqual([205]);
    expect(filterChaptersByTitle(chapters, "   ")).toEqual([]);
  });

  it("adjacent chapters disable at ends", () => {
    expect(adjacentBodyChapters(chapters, 101).prev).toBeNull();
    expect(adjacentBodyChapters(chapters, 101).next?.id).toBe(205);
    expect(adjacentBodyChapters(chapters, 999).next).toBeNull();
  });

  it("reading params clear analysis bindings", () => {
    const params = buildChapterReadingSearchParams(205);
    expect(params.get("chapter")).toBe("205");
    expect(params.get("view")).toBe("reading");
    expect(params.get("analysisRun")).toBeNull();
    expect(params.get("tab")).toBeNull();
    expect(params.get("journeyView")).toBeNull();
  });
});
