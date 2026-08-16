/**
 * 章节骨架 (CHG-20260816-102).
 *
 * The first 拆书 mode was 我在写 with the annotation moved and the heading reworded — the
 * user called it correctly: "基本就是相反的一点". A second reading has to carry different
 * content, so these pin that the skeleton names *moves* and *shares* rather than restating
 * scores, and that the one place raw scores misread the chapter is handled.
 */

import { describe, expect, it } from "vitest";
import { buildChapterSkeleton, skeletonLedgerNote } from "./chapterSkeleton";
import type { JourneySceneNode } from "../../types/readerJourneyVisualization";

function scene(
  ordinal: number,
  paragraphs: number,
  scores: Record<string, number>,
  openQuestions?: { opened: number; closed: number; balance: number },
): JourneySceneNode {
  return {
    scene_ordinal: ordinal,
    paragraph_count: paragraphs,
    paragraph_range: {
      start_paragraph_id: `B0001-C0001-P${String(ordinal * 10).padStart(4, "0")}`,
      end_paragraph_id: `B0001-C0001-P${String(ordinal * 10 + paragraphs - 1).padStart(4, "0")}`,
    },
    scores,
    open_questions: openQuestions,
    include_in_main_curve: true,
  } as unknown as JourneySceneNode;
}

const OPENS = { hook: 90, payoff: 30, information_gain: 80, tension: 60, reading_momentum: 70 };
const EMPTY = { hook: 30, payoff: 30, information_gain: 30, tension: 30, reading_momentum: 20 };
const PEAK = { hook: 80, payoff: 65, information_gain: 65, tension: 95, reading_momentum: 85 };

describe("章节骨架", () => {
  it("names the move each scene makes, not its score", () => {
    const rows = buildChapterSkeleton([
      scene(1, 28, OPENS),
      scene(2, 18, PEAK),
      scene(3, 6, { ...OPENS, reading_momentum: 78 }, { opened: 4, closed: 3, balance: 7 }),
    ]);
    expect(rows.map((r) => r.function)).toEqual(["异常开场", "压力峰值", "悬置收尾"]);
    // The share is the transferable part — 54% on one opening move is what a reader copies.
    expect(Math.round(rows[0].sharePercent)).toBe(54);
  });

  it("judges the ending by the ledger, not by the payoff score", () => {
    // A payoff of 65 is level 3 — 「有兑现但强度弱」. On a real chapter ending on an
    // unanswered question the raw score read as a close while the ledger went 6 → 7.
    const closingScore = { hook: 80, payoff: 65, information_gain: 65, tension: 80, reading_momentum: 78 };
    const stillOwing = buildChapterSkeleton([
      scene(1, 10, OPENS),
      scene(2, 10, closingScore, { opened: 4, closed: 3, balance: 7 }),
    ]);
    expect(stillOwing[1].function).toBe("悬置收尾");

    const paidOff = buildChapterSkeleton([
      scene(1, 10, OPENS),
      scene(2, 10, closingScore, { opened: 1, closed: 4, balance: 0 }),
    ]);
    expect(paidOff[1].function).toBe("闭合收尾");
  });

  it("separates a short breath from a long stall — the same emptiness, different verdict", () => {
    const short = buildChapterSkeleton([
      scene(1, 40, OPENS),
      scene(2, 3, EMPTY),
      scene(3, 10, PEAK, { opened: 1, closed: 1, balance: 0 }),
    ]);
    expect(short[1].function).toBe("换气");

    const long = buildChapterSkeleton([
      scene(1, 5, OPENS),
      scene(2, 29, EMPTY),
      scene(3, 11, PEAK, { opened: 1, closed: 1, balance: 0 }),
    ]);
    expect(long[1].function).toBe("空转");
    expect(long[1].skippable).toBe(true);
    expect(Math.round(long[1].sharePercent)).toBe(64);
  });

  it("reads paragraph numbers out of the ids so the rows locate in the text", () => {
    const rows = buildChapterSkeleton([scene(1, 5, OPENS), scene(2, 5, PEAK)]);
    expect(rows[0].paragraphFrom).toBe(10);
    expect(rows[0].paragraphTo).toBe(14);
  });

  it("says nothing at all when there is not enough chapter to have a shape", () => {
    expect(buildChapterSkeleton([scene(1, 10, OPENS)])).toEqual([]);
  });

  it("summarises what the sequence adds up to", () => {
    const owing = skeletonLedgerNote([
      scene(1, 10, OPENS, { opened: 5, closed: 3, balance: 2 }),
      scene(2, 10, PEAK, { opened: 4, closed: 3, balance: 3 }),
    ]);
    expect(owing).toContain("章末仍欠 3");

    const even = skeletonLedgerNote([
      scene(1, 10, OPENS, { opened: 2, closed: 2, balance: 0 }),
      scene(2, 10, PEAK, { opened: 3, closed: 3, balance: 0 }),
    ]);
    expect(even).toContain("一分不欠");
  });

  it("returns no ledger note for a run from before the ledger existed", () => {
    expect(skeletonLedgerNote([scene(1, 10, OPENS), scene(2, 10, PEAK)])).toBeNull();
  });
});
