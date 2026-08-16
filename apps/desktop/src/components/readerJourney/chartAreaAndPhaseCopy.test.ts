/**
 * 两处在真实页面上才现形的问题.
 *
 * 1. Carrying the curve out to the chapter's edges (CHG-20260815-102) left the composite
 *    lens's area fill closing its baseline at the first and last *scene midpoints*. Those
 *    used to be the same points as the line's ends; once they were not, the polygon closed
 *    through two diagonals — a wedge under the opening and another over the ending.
 * 2. Real payloads carry `summary: "开端"` beside `title: "开端"`. The card rendered
 *    「开端 · 节奏速度 65 · 开端」: the same word twice with a number between them.
 */

import { describe, expect, it } from "vitest";
import { buildLinePathD, buildProportionalXScale } from "./journeyChartScales";
import { resolvePhaseSummaryDisplay } from "./journeyUiLabels";
import { HOOK_PAYOFF_LENS_LEGEND } from "./readerJourneyLensExplanation";

describe("面积填充跟着曲线的真实两端走", () => {
  const WIDTH = 720;
  const PLOT_LEFT = 44;
  const PLOT_RIGHT = 700;
  // 《再也不见》第一章: 3 scenes over 5 / 29 / 11 paragraphs.
  const SPANS = [
    { scene_ordinal: 1, weight: 5 },
    { scene_ordinal: 2, weight: 29 },
    { scene_ordinal: 3, weight: 11 },
  ];

  function areaPath(edges: { left: number; right: number } | null) {
    const x = buildProportionalXScale(SPANS, WIDTH);
    const series = SPANS.map((s, i) => ({ scene_ordinal: s.scene_ordinal, value: 60 + i }));
    const line = buildLinePathD(series, x, (v) => v, edges);
    const baseline = 380;
    const first = edges?.left ?? x(1);
    const last = edges?.right ?? x(3);
    return `${line} L ${last} ${baseline} L ${first} ${baseline} Z`;
  }

  it("closes the baseline where the line actually ends", () => {
    const d = areaPath({ left: PLOT_LEFT, right: PLOT_RIGHT });
    expect(d).toContain(`M ${PLOT_LEFT} 60`);
    expect(d).toContain(`L ${PLOT_RIGHT} 380 L ${PLOT_LEFT} 380 Z`);
  });

  it("has no diagonal between the line's end and the baseline's end", () => {
    // The bug in one assertion: the x the line ends at must equal the x the baseline
    // returns from. Anything else is a wedge.
    const d = areaPath({ left: PLOT_LEFT, right: PLOT_RIGHT });
    const points = [...d.matchAll(/[ML] (\d+(?:\.\d+)?) (\d+(?:\.\d+)?)/g)].map((m) => ({
      x: Number(m[1]),
      y: Number(m[2]),
    }));
    const lastOnLine = points[points.length - 3];
    const firstOnBaseline = points[points.length - 2];
    expect(firstOnBaseline.x).toBeCloseTo(lastOnLine.x, 6);
    expect(points[0].x).toBeCloseTo(points[points.length - 1].x, 6);
  });
});

describe("阶段卡的描述不是它自己的标题", () => {
  it("rejects a summary that merely echoes the title", () => {
    expect(resolvePhaseSummaryDisplay("开端", "开端")).toBe("建立背景、人物与阅读期待");
    expect(resolvePhaseSummaryDisplay("发展", "发展")).toBe("推动事件发展与核心冲突");
    expect(resolvePhaseSummaryDisplay("收束", "收束")).toBe("形成阶段结果并留下后续期待");
  });

  it("covers the phase names the pipeline actually emits", () => {
    // 收束 was covered only because it is spelled the same in both vocabularies; 开端 and
    // 发展 fell through to 「选择阶段或节点查看详细分析」, an instruction, not a description.
    for (const title of ["开端", "发展", "收束"]) {
      expect(resolvePhaseSummaryDisplay(null, title)).not.toMatch(/选择阶段/);
    }
  });

  it("keeps a real summary", () => {
    expect(resolvePhaseSummaryDisplay("进入较慢，主要依靠氛围建立", "开端")).toBe(
      "进入较慢，主要依靠氛围建立",
    );
  });
});

describe("图例与轨迹用同一套词", () => {
  it("keys the legend on the four actions, not on the suspense wording", () => {
    // This is what makes the legend translatable at all: if the rows were identified by
    // their Chinese text there would be nothing to map. Renaming a label without renaming
    // its key here silently drops that row back to the suspense word.
    expect(HOOK_PAYOFF_LENS_LEGEND.map((i) => i.key)).toEqual([
      "raise",
      "deepen",
      "answer",
      "carry",
    ]);
  });
});
