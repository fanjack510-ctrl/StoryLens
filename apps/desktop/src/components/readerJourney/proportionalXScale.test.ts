/**
 * 横轴按篇幅铺开 (CHG-20260815-101).
 *
 * Even spacing draws a 2-paragraph transition as wide as a 28-paragraph opening. On
 * 《我不是戏神》第一章 the six scenes span 28 / 2 / 11 / 18 / 3 / 6 paragraphs — 43% of the
 * chapter in the first one — and the shipped chart drew them as six evenly spaced dots. For
 * a chart that traces a reading experience that is not a simplification but a misstatement:
 * the horizontal distance between two points is how far the reader walked.
 */

import { describe, expect, it } from "vitest";
import {
  buildLinePathD,
  buildProportionalXScale,
  buildSceneExtents,
  xForSceneOrdinal,
} from "./journeyChartScales";
import { CHART_PAD } from "./journeyVisualizationConfig";

const WIDTH = 1000;
const PLOT = WIDTH - CHART_PAD.left - CHART_PAD.right;

// The real spans of 《我不是戏神》第一章.
const XISHEN = [28, 2, 11, 18, 3, 6].map((weight, i) => ({
  scene_ordinal: i + 1,
  weight,
}));

describe("按篇幅铺开的横轴", () => {
  it("gives each scene the share of the width it occupies in the chapter", () => {
    const x = buildProportionalXScale(XISHEN, WIDTH);
    const total = 68;
    // Scene 1 covers paragraphs 1–28, so its point sits at the middle of the first 41%.
    expect(x(1)).toBeCloseTo(CHART_PAD.left + (28 / total / 2) * PLOT, 1);
    // Scene 5 is 3 paragraphs starting after 59, so it sits far to the right and is narrow.
    const before5 = (28 + 2 + 11 + 18) / total;
    expect(x(5)).toBeCloseTo(CHART_PAD.left + (before5 + 3 / total / 2) * PLOT, 1);
  });

  it("separates a long slow stretch from a short crash, which even spacing cannot", () => {
    const x = buildProportionalXScale(XISHEN, WIDTH);
    const slowRun = x(2) - x(1); // 886 characters of opening, a gentle slope
    const crashRun = x(6) - x(5); // ~100 characters, a cliff
    expect(slowRun).toBeGreaterThan(crashRun * 2);

    // Under even spacing the two runs are identical, which is the bug.
    const even = (o: number) => xForSceneOrdinal(o, XISHEN.length, WIDTH);
    expect(even(2) - even(1)).toBeCloseTo(even(6) - even(5), 6);
  });

  it("keeps every point inside the plot area and in reading order", () => {
    const x = buildProportionalXScale(XISHEN, WIDTH);
    const xs = XISHEN.map((s) => x(s.scene_ordinal));
    expect(xs).toEqual([...xs].sort((a, b) => a - b));
    expect(Math.min(...xs)).toBeGreaterThanOrEqual(CHART_PAD.left);
    expect(Math.max(...xs)).toBeLessThanOrEqual(CHART_PAD.left + PLOT);
  });

  it("falls back to even spacing when the payload carries no paragraph counts", () => {
    // A legacy result keeps its old geometry rather than collapsing every point onto one.
    const missing = [1, 2, 3].map((n) => ({ scene_ordinal: n, weight: 0 }));
    const x = buildProportionalXScale(missing, WIDTH);
    expect(x(1)).toBeCloseTo(xForSceneOrdinal(1, 3, WIDTH), 6);
    expect(x(3)).toBeCloseTo(xForSceneOrdinal(3, 3, WIDTH), 6);
  });

  it("falls back to even spacing when every scene is the same length", () => {
    const same = [1, 2, 3, 4].map((n) => ({ scene_ordinal: n, weight: 5 }));
    const x = buildProportionalXScale(same, WIDTH);
    expect(x(2)).toBeCloseTo(xForSceneOrdinal(2, 4, WIDTH), 6);
  });

  it("centres a single scene instead of pinning it to the left edge", () => {
    const x = buildProportionalXScale([{ scene_ordinal: 1, weight: 40 }], WIDTH);
    expect(x(1)).toBeCloseTo(CHART_PAD.left + PLOT / 2, 6);
  });

  it("does not depend on the order the scenes arrive in", () => {
    const shuffled = [XISHEN[3], XISHEN[0], XISHEN[5], XISHEN[1], XISHEN[4], XISHEN[2]];
    const a = buildProportionalXScale(XISHEN, WIDTH);
    const b = buildProportionalXScale(shuffled, WIDTH);
    XISHEN.forEach((s) => expect(b(s.scene_ordinal)).toBeCloseTo(a(s.scene_ordinal), 6));
  });

  it("returns a usable x for an ordinal it has never seen", () => {
    // Defensive: a curve point whose scene was filtered out must not render at NaN.
    const x = buildProportionalXScale(XISHEN, WIDTH);
    expect(Number.isFinite(x(99))).toBe(true);
  });
});

describe("场景横向跨度与曲线两端 (CHG-20260815-102)", () => {
  const PLOT_LEFT = CHART_PAD.left;
  const PLOT_RIGHT = WIDTH - CHART_PAD.right;

  it("covers the chapter end to end with no gap between scenes", () => {
    const extents = buildSceneExtents(XISHEN, WIDTH);
    expect(extents).toHaveLength(XISHEN.length);
    expect(extents[0].x0).toBeCloseTo(PLOT_LEFT, 6);
    expect(extents[extents.length - 1].x1).toBeCloseTo(PLOT_RIGHT, 6);
    for (let i = 1; i < extents.length; i += 1) {
      expect(extents[i].x0).toBeCloseTo(extents[i - 1].x1, 6);
    }
  });

  it("makes each extent as wide as the scene's share of the chapter", () => {
    const extents = buildSceneExtents(XISHEN, WIDTH);
    const total = XISHEN.reduce((sum, s) => sum + s.weight, 0);
    extents.forEach((extent, i) => {
      expect(extent.x1 - extent.x0).toBeCloseTo((XISHEN[i].weight / total) * PLOT, 6);
    });
  });

  it("puts the dot at the middle of its own extent", () => {
    // This is the whole answer to 「为什么曲线不从最左边开始」: S1 occupies 41% of the
    // chapter, so its midpoint — and therefore its dot — sits a fifth of the way in.
    const x = buildProportionalXScale(XISHEN, WIDTH);
    buildSceneExtents(XISHEN, WIDTH).forEach((extent) => {
      expect(x(extent.scene_ordinal)).toBeCloseTo((extent.x0 + extent.x1) / 2, 6);
    });
  });

  it("carries the line flat out to both chapter edges", () => {
    const x = buildProportionalXScale(XISHEN, WIDTH);
    const series = XISHEN.map((s, i) => ({ scene_ordinal: s.scene_ordinal, value: 50 + i }));
    const d = buildLinePathD(series, x, (v) => v, { left: PLOT_LEFT, right: PLOT_RIGHT });
    expect(d.startsWith(`M ${PLOT_LEFT} 50`)).toBe(true);
    expect(d.endsWith(`L ${PLOT_RIGHT} 55`)).toBe(true);
    // The stub holds the end values — it must not invent a slope into the margin.
    expect(d).toContain(`M ${PLOT_LEFT} 50 L ${x(1)} 50`);
  });

  it("leaves the endpoints alone when no edges are given", () => {
    const x = buildProportionalXScale(XISHEN, WIDTH);
    const series = XISHEN.map((s) => ({ scene_ordinal: s.scene_ordinal, value: 50 }));
    expect(buildLinePathD(series, x, (v) => v).startsWith(`M ${x(1)} 50`)).toBe(true);
  });

  it("does not stub a segment that resumes after a gap", () => {
    // A null breaks the line. The segment after the break starts at a real measurement and
    // must not be dragged to the chart edge as though it were the chapter's first scene.
    const x = buildProportionalXScale(XISHEN, WIDTH);
    const series = [
      { scene_ordinal: 1, value: 50 },
      { scene_ordinal: 2, value: null },
      { scene_ordinal: 3, value: 70 },
    ];
    const d = buildLinePathD(series, x, (v) => v, { left: PLOT_LEFT, right: PLOT_RIGHT });
    expect(d).toContain(`M ${x(3)} 70`);
    expect(d.match(new RegExp(`M ${PLOT_LEFT} `, "g")) ?? []).toHaveLength(1);
  });

  it("draws no extents when spans are missing or uniform", () => {
    // Same fallback condition as the scale itself: a caller that gets [] must keep the old
    // fixed-width marks rather than invent a span.
    expect(buildSceneExtents([], WIDTH)).toEqual([]);
    expect(
      buildSceneExtents(
        XISHEN.map((s) => ({ ...s, weight: 10 })),
        WIDTH,
      ),
    ).toEqual([]);
    expect(buildSceneExtents(XISHEN.map((s) => ({ ...s, weight: 0 })), WIDTH)).toEqual([]);
  });
});
