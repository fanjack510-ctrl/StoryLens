import { describe, expect, it } from "vitest";
import {
  buildBookHomeChapterRows,
  chapterAnalysisBadge,
  isBookHomePath,
} from "./bookHomeCatalog";
import type { Chapter, Run } from "../types";

describe("bookHomeCatalog", () => {
  it("treats missing chapter= as book home", () => {
    expect(isBookHomePath(new URLSearchParams())).toBe(true);
    expect(isBookHomePath(new URLSearchParams("chapter=12"))).toBe(false);
  });

  it("never invents badges from other chapters", () => {
    const runs = [
      { id: 8, subject_id: "1220", status: "succeeded", chapter_complete: true },
    ] as Run[];
    expect(chapterAnalysisBadge(1224, runs)).toBe("unanalyzed");
    expect(chapterAnalysisBadge(1220, runs)).toBe("journey_ready");
  });

  it("builds rows for catalog without selecting a chapter", () => {
    const chapters = [
      {
        id: 1,
        book_id: 9,
        chapter_index: 1,
        title: "一",
        display_title: "第1章",
        word_count: 10,
        section_type: "chapter",
      },
    ] as Chapter[];
    const rows = buildBookHomeChapterRows(chapters, []);
    expect(rows).toHaveLength(1);
    expect(rows[0].badge).toBe("unanalyzed");
  });
});
