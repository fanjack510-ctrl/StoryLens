import { describe, expect, it } from "vitest";
import { PRO_CAPABILITY_LABELS } from "./productEdition";

describe("Whole-book product semantics (WB-0.6)", () => {
  it("maps native whole-book capability label", () => {
    expect(PRO_CAPABILITY_LABELS.whole_book_native).toBe("原生全书分析");
  });

  it("maps enhanced whole-book capability label", () => {
    expect(PRO_CAPABILITY_LABELS.whole_book_enhanced).toBe("精细增强分析");
  });

  it("maps chapter aggregate insights label without legacy 全书洞察 wording", () => {
    expect(PRO_CAPABILITY_LABELS.chapter_aggregate_insights).toBe("章节精细分析覆盖");
    expect(PRO_CAPABILITY_LABELS.chapter_aggregate_insights).not.toContain("全书洞察");
  });

  it("keeps legacy pro_whole_book_insights distinct from chapter aggregate label", () => {
    expect(PRO_CAPABILITY_LABELS.pro_whole_book_insights).toContain("章节精细分析覆盖");
    expect(PRO_CAPABILITY_LABELS.pro_whole_book_insights).toContain("Legacy");
  });
});
