/**
 * 单章可测的三件事 + 类型词表.
 *
 * Measured on three real books before this change: 0 of 10 hooks were ever answered inside
 * the chapter, because `v2_profile_to_v1_compat_payload` hardcoded `payoffs: []`. The lens
 * led with three cards that therefore always read 新提出 · 留到下章. First-scene hook strength,
 * by contrast, separates the same three books 95 / 50 / 50.
 */

import { describe, expect, it } from "vitest";
import { buildChapterHookVitals, firstHookPosition } from "./chapterHookVitals";
import { hookLabelZh } from "./chapterHookSimplification";
import { firstHookMarkLabelZh, hookLensLabelZh } from "./lensMetricBinding";
import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";

function viz(
  scenes: Array<{
    ordinal: number;
    hook?: number;
    paragraphs: number;
    hookParagraph?: string;
    ledger?: { opened: number; closed: number; balance: number };
  }>,
): ReaderJourneyVisualization {
  return {
    scene_nodes: scenes.map((s) => ({
      scene_ordinal: s.ordinal,
      paragraph_count: s.paragraphs,
      scores: s.hook == null ? {} : { hook: s.hook },
      hooks: s.hookParagraph
        ? [{ type: "information", summary: "", strength: s.hook ?? 0, evidence_paragraph_ids: [s.hookParagraph] }]
        : [],
      open_questions: s.ledger,
    })),
  } as unknown as ReaderJourneyVisualization;
}

// 《我不是戏神》第一章, as measured: 6 scenes spanning 28/2/11/18/3/6 paragraphs.
const XISHEN = viz([
  { ordinal: 1, hook: 95, paragraphs: 28, hookParagraph: "B0010-C0002-P0001" },
  { ordinal: 2, hook: 60, paragraphs: 2 },
  { ordinal: 3, hook: 80, paragraphs: 11 },
  { ordinal: 4, hook: 70, paragraphs: 18 },
  { ordinal: 5, hook: 45, paragraphs: 3 },
  { ordinal: 6, hook: 80, paragraphs: 6, ledger: { opened: 4, closed: 3, balance: 7 } },
]);

// 《再也不见》's confirmed profile resolves to this table.
const ROMANCE = {
  open: "起了心结",
  deepen: "越陷越深",
  answer: "挑明",
  carry: "悬而未说",
  lens: "心结与挑明",
  first_mark: "第一处牵挂",
};

describe("单章钩子体检", () => {
  it("leads with opening pull, ending pull and where the first hook lands", () => {
    const vitals = buildChapterHookVitals(XISHEN);
    expect(vitals.map((v) => v.key)).toEqual(["opening", "ending", "first_hook"]);
    expect(vitals[0].score).toBe(95);
    expect(vitals[0].band).toBe("strong");
    expect(vitals[0].display).toBe("95");
    expect(vitals[1].score).toBe(80);
    expect(vitals[1].basis).toContain("开 4 收 3");
    expect(vitals[1].basis).toContain("仍欠 7");
  });

  it("separates books the four-label vocabulary could not", () => {
    // The same measurement on 《再也不见》: first scene 50, not 95. The four labels read
    // 提出疑问 on both.
    const romance = viz([
      { ordinal: 1, hook: 50, paragraphs: 20 },
      { ordinal: 2, hook: 50, paragraphs: 15 },
      { ordinal: 3, hook: 65, paragraphs: 10, ledger: { opened: 3, closed: 3, balance: 0 } },
    ]);
    expect(buildChapterHookVitals(XISHEN)[0].score).toBe(95);
    expect(buildChapterHookVitals(romance)[0].score).toBe(50);
    expect(buildChapterHookVitals(XISHEN)[0].band).toBe("strong");
    expect(buildChapterHookVitals(romance)[0].band).toBe("weak");
  });

  it("reports the first hook's paragraph and its share of the chapter", () => {
    const position = firstHookPosition(XISHEN);
    expect(position.paragraph).toBe(1);
    expect(position.totalParagraphs).toBe(68);
    expect(position.sharePercent).toBeCloseTo((1 / 68) * 100, 6);
    expect(buildChapterHookVitals(XISHEN)[2].reading).toBe("第一段就下钩");
    // The position is what this row reports; it must be printed, not tucked into a tooltip.
    expect(buildChapterHookVitals(XISHEN)[2].display).toBe("P1");
  });

  it("says the position is unknown rather than guessing one", () => {
    // Pre-v2.2 artifacts have no first_hook_paragraph_id, and the field the shim used
    // pointed at the scene's own first paragraph on all three books — a number that
    // disagreed with the model's own prose. Absent beats wrong.
    const legacy = viz([
      { ordinal: 1, hook: 70, paragraphs: 10 },
      { ordinal: 2, hook: 60, paragraphs: 10 },
    ]);
    const vitals = buildChapterHookVitals(legacy);
    expect(firstHookPosition(legacy).paragraph).toBeNull();
    expect(vitals[2].band).toBe("unknown");
    expect(vitals[2].score).toBeNull();
    expect(vitals[2].reading).toContain("未记录");
    expect(vitals[2].display).toBe("—");
  });

  it("keeps a missing score visibly missing", () => {
    const noScores = viz([{ ordinal: 1, paragraphs: 5 }]);
    const vitals = buildChapterHookVitals(noScores);
    expect(vitals[0].score).toBeNull();
    expect(vitals[0].display).toBe("—");
    expect(vitals[0].band).toBe("unknown");
  });

  it("returns nothing when there is nothing to measure", () => {
    expect(buildChapterHookVitals(viz([]))).toEqual([]);
  });
});

describe("类型词表", () => {

  it("renames the four actions in the book's own terms", () => {
    expect(hookLabelZh("提出疑问", ROMANCE)).toBe("起了心结");
    expect(hookLabelZh("加深悬念", ROMANCE)).toBe("越陷越深");
    expect(hookLabelZh("给出回应", ROMANCE)).toBe("挑明");
    expect(hookLabelZh("留到下章", ROMANCE)).toBe("悬而未说");
  });

  it("keeps the suspense wording when the backend sends no vocabulary", () => {
    // No vocabulary means an unconfirmed profile or a legacy payload. Naming the reader's
    // experience off an inference is the substitution INV-P2 forbids.
    expect(hookLabelZh("提出疑问", null)).toBe("提出疑问");
    expect(hookLabelZh("提出疑问", undefined)).toBe("提出疑问");
  });

  it("passes through anything that is not one of the four actions", () => {
    expect(hookLabelZh("—", ROMANCE)).toBe("—");
    expect(hookLabelZh(null, ROMANCE)).toBe("");
  });
});

describe("镜头名与体检项也跟着类型走", () => {
  it("names the lens and its first-occurrence vital from the vocabulary", () => {
    // Renaming only the four actions left a romance chapter reading
    // 「钩子回收 · 首钩位置 P2 · 起了心结」: two vocabularies on one screen.
    expect(hookLensLabelZh({ hook_vocabulary: ROMANCE } as never)).toBe("心结与挑明");
    expect(firstHookMarkLabelZh({ hook_vocabulary: ROMANCE } as never)).toBe("第一处牵挂");
  });

  it("keeps the shipped names when the backend sends none", () => {
    expect(hookLensLabelZh(null)).toBe("钩子回收");
    expect(firstHookMarkLabelZh(undefined)).toBe("首钩位置");
    expect(hookLensLabelZh({ hook_vocabulary: { open: "起了心结" } } as never)).toBe("钩子回收");
  });

  it("labels the vital from the payload", () => {
    const romanceViz = {
      scene_nodes: [
        { scene_ordinal: 1, paragraph_count: 5, scores: { hook: 50 }, hooks: [] },
        { scene_ordinal: 2, paragraph_count: 9, scores: { hook: 65 }, hooks: [] },
      ],
      hook_vocabulary: ROMANCE,
    } as unknown as ReaderJourneyVisualization;
    expect(buildChapterHookVitals(romanceViz)[2].label).toBe("第一处牵挂");
    expect(buildChapterHookVitals(XISHEN)[2].label).toBe("首钩位置");
  });
});
