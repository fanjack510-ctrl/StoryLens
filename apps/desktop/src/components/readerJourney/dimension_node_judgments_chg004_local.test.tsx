/**
 * CHG-20260729-004 — dimension-specific curve node judgments.
 */
import { describe, expect, it, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type {
  JourneySceneNode,
  ReaderJourneyVisualization,
} from "../../types/readerJourneyVisualization";
import {
  buildDimensionJudgmentsForVisualization,
  deriveDimensionNodeJudgmentV1,
  resolveDimensionFitLabel,
  resolveDimensionNodeLabelVisibility,
  type DimensionJudgmentLens,
} from "./dimensionNodeJudgments";
import { CanonicalJourneyChart } from "./CanonicalJourneyChart";
import { buildMockReaderJourneyVisualization } from "./mockVisualization";
import { JOURNEY_STAGE_VISUAL_TOKENS } from "./journeyVisualTokens";

function node(partial: Partial<JourneySceneNode> & { scene_ordinal: number }): JourneySceneNode {
  const base = buildMockReaderJourneyVisualization().scene_nodes[0];
  return {
    ...base,
    ...partial,
    scene_ordinal: partial.scene_ordinal,
    scores: {
      ...base.scores,
      ...(partial.scores || {}),
    },
    dimension_insights: {
      overall_reading: null,
      plot_progression: null,
      reading_tension: null,
      emotional_intensity: null,
      hook_payoff: null,
      pacing_speed: null,
      ...(partial.dimension_insights || {}),
    },
  } as JourneySceneNode;
}

/** Isolated 6-scene fixture — four score series diverge; labels must diverge. */
export function chg004DimensionFixtureViz(): ReaderJourneyVisualization {
  const roles = ["setup", "transition", "escalation", "escalation", "reveal", "aftermath"] as const;
  const plots = [42, 40, 64, 78, 88, 48];
  const tensions = [45, 48, 62, 80, 68, 42];
  const emotions = [38, 52, 82, 58, 72, 44];
  const pacings = [48, 38, 72, 70, 86, 40];
  const hooks = [55, 50, 60, 70, 45, 30];
  const payoffs = [20, 22, 30, 35, 60, 75];
  const plotInsights = [
    "开场信息铺垫",
    "推进幅度有限",
    "目标明确，开始追查",
    "冲突升级，对抗加剧",
    "局势反转，真相揭晓",
    "完成收束",
  ];
  const tensionInsights = [
    "疑问建立",
    "期待维持",
    "风险上升",
    "悬念强化",
    "部分回应",
    "张力回落",
  ];
  const emotionInsights = [
    "情绪铺垫",
    "紧张上升",
    "情绪爆发",
    "情绪回落",
    "再次抬升",
    "情绪释放",
  ];
  const pacingInsights = [
    "平稳进入",
    "适度放缓",
    "明显加速",
    "保持平稳",
    "再次加速",
    "收束减速",
  ];

  const scene_nodes = roles.map((role, i) =>
    node({
      scene_ordinal: i + 1,
      scene_id: i + 1,
      role: "core",
      scene_role: role,
      phase_ordinal: i < 2 ? 1 : i < 5 ? 2 : 3,
      scores: {
        reading_momentum: 50 + i * 3,
        plot_progress: plots[i],
        reading_tension: tensions[i],
        hook: hooks[i],
        payoff: payoffs[i],
        pacing_speed: pacings[i],
        pacing_fit: i === 2 ? 40 : 75,
        arousal_start: emotions[i],
        arousal_end: emotions[i],
        emotional_investment: emotions[i],
        valence_start: 0.1,
        valence_end: 0.1,
      },
      dimension_insights: {
        plot_progression: plotInsights[i],
        reading_tension: tensionInsights[i],
        emotional_intensity: emotionInsights[i],
        pacing_speed: pacingInsights[i],
      },
    }),
  );

  const viz = buildMockReaderJourneyVisualization();
  return {
    ...viz,
    scene_nodes,
    phases: [
      {
        ...viz.phases[0],
        ordinal: 1,
        title: "开端",
        start_scene_ordinal: 1,
        end_scene_ordinal: 2,
      },
      {
        ...viz.phases[1],
        ordinal: 2,
        title: "发展",
        start_scene_ordinal: 3,
        end_scene_ordinal: 5,
      },
      {
        ...viz.phases[2],
        ordinal: 3,
        title: "收束",
        start_scene_ordinal: 6,
        end_scene_ordinal: 6,
      },
    ],
  };
}

const EXPECTED: Record<DimensionJudgmentLens, string[]> = {
  plot_progress: ["信息铺垫", "推进有限", "目标明确", "冲突升级", "局势反转", "完成收束"],
  reading_tension: ["疑问建立", "期待维持", "风险上升", "悬念强化", "部分回应", "张力回落"],
  emotion: ["情绪铺垫", "紧张上升", "情绪爆发", "情绪回落", "再次抬升", "情绪释放"],
  pacing: ["平稳进入", "适度放缓", "明显加速", "保持平稳", "再次加速", "收束减速"],
};

function zhLen(s: string): number {
  return Array.from(s).length;
}

function chartProps(
  viz: ReaderJourneyVisualization,
  lens: DimensionJudgmentLens | "composite" | "hook_payoff",
  selected: number | null = 3,
) {
  return {
    visualization: viz,
    metric: "reading_momentum" as const,
    observationLens: lens,
    chartHeight: 280,
    yDomainMode: "fixed_0_100" as const,
    viewStart: 1,
    viewEnd: viz.scene_nodes.length,
    onViewChange: () => undefined,
    selectedSceneOrdinal: selected,
    selectedPhaseOrdinal: null,
    markerMode: "full" as const,
    onSelectScene: () => undefined,
    onSelectRisk: () => undefined,
    onSelectHook: () => undefined,
    onSelectPayoff: () => undefined,
  };
}

describe("CHG-20260729-004 dimension node judgments", () => {
  afterEach(() => {
    cleanup();
  });

  it("plot progression labels cover required cases and exclude cross-dimension terms", () => {
    const viz = chg004DimensionFixtureViz();
    const map = buildDimensionJudgmentsForVisualization(viz.scene_nodes, "plot_progress", 3);
    const labels = [1, 2, 3, 4, 5, 6].map((o) => map.get(o)?.short_label);
    expect(labels).toEqual(EXPECTED.plot_progress);
    for (const label of labels) {
      expect(label).not.toMatch(/风险上升|情绪爆发|明显加速|钩子/);
    }
    const j4 = map.get(4)!;
    expect(j4.fit_label).toBeTruthy();
    expect(j4.short_label).not.toBe(j4.fit_label);
  });

  it("reading tension labels cover required cases", () => {
    const viz = chg004DimensionFixtureViz();
    const map = buildDimensionJudgmentsForVisualization(viz.scene_nodes, "reading_tension", 3);
    expect([1, 2, 3, 4, 5, 6].map((o) => map.get(o)?.short_label)).toEqual(
      EXPECTED.reading_tension,
    );
    for (const o of [1, 2, 3, 4, 5, 6]) {
      expect(map.get(o)?.short_label).not.toMatch(/目标明确|情绪爆发|明显加速|冲突升级/);
    }
  });

  it("emotional intensity labels cover rise/peak/drop/turn cases and avoid 强/中/弱 only", () => {
    const viz = chg004DimensionFixtureViz();
    const map = buildDimensionJudgmentsForVisualization(viz.scene_nodes, "emotion", 3);
    expect([1, 2, 3, 4, 5, 6].map((o) => map.get(o)?.short_label)).toEqual(EXPECTED.emotion);
    for (const o of [1, 2, 3, 4, 5, 6]) {
      const lab = map.get(o)?.short_label || "";
      expect(["强", "中", "弱"]).not.toContain(lab);
      expect(lab).not.toMatch(/冲突升级|明显加速/);
    }
  });

  it("pacing labels and fit mapping 偏强→偏快 / 偏弱→偏慢", () => {
    const viz = chg004DimensionFixtureViz();
    const map = buildDimensionJudgmentsForVisualization(viz.scene_nodes, "pacing", 3);
    expect([1, 2, 3, 4, 5, 6].map((o) => map.get(o)?.short_label)).toEqual(EXPECTED.pacing);
    const fastNode = node({
      scene_ordinal: 1,
      scene_role: "aftermath",
      scores: { pacing_speed: 95, pacing_fit: null },
    });
    expect(resolveDimensionFitLabel("pacing", fastNode)).toBe("偏快");
    const slowNode = node({
      scene_ordinal: 1,
      scene_role: "climax",
      scores: { pacing_speed: 15, pacing_fit: null },
    });
    expect(resolveDimensionFitLabel("pacing", slowNode)).toBe("偏慢");
  });

  it("label density rules are shared across dimensions", () => {
    expect(
      resolveDimensionNodeLabelVisibility({
        sceneCount: 6,
        importance: "low",
        isSelected: false,
        judgmentSource: "derived",
      }).showAboveNode,
    ).toBe(true);
    expect(
      resolveDimensionNodeLabelVisibility({
        sceneCount: 15,
        importance: "low",
        isSelected: false,
        judgmentSource: "derived",
      }).showAboveNode,
    ).toBe(false);
    expect(
      resolveDimensionNodeLabelVisibility({
        sceneCount: 15,
        importance: "high",
        isSelected: false,
        judgmentSource: "derived",
      }).showAboveNode,
    ).toBe(true);
    expect(
      resolveDimensionNodeLabelVisibility({
        sceneCount: 30,
        importance: "medium",
        isSelected: false,
        judgmentSource: "derived",
      }).showAboveNode,
    ).toBe(false);
    expect(
      resolveDimensionNodeLabelVisibility({
        sceneCount: 30,
        importance: "low",
        isSelected: true,
        judgmentSource: "derived",
      }).showAboveNode,
    ).toBe(true);
  });

  it("labels stay within 10 Chinese chars and avoid internal fields", () => {
    const viz = chg004DimensionFixtureViz();
    for (const lens of Object.keys(EXPECTED) as DimensionJudgmentLens[]) {
      const map = buildDimensionJudgmentsForVisualization(viz.scene_nodes, lens, 1);
      for (const j of map.values()) {
        if (j.short_label) {
          expect(zhLen(j.short_label)).toBeLessThanOrEqual(10);
          expect(j.short_label).not.toMatch(/plot_progress|reading_tension|formula|score_/i);
        }
        expect(j.judgment_source).toMatch(/derived|unavailable/);
      }
    }
  });

  it("four dimensions produce distinct label sets (not renamed copies)", () => {
    const sets = (Object.keys(EXPECTED) as DimensionJudgmentLens[]).map((lens) =>
      EXPECTED[lens].join("|"),
    );
    expect(new Set(sets).size).toBe(4);
  });

  it("deterministic for same inputs; unavailable fallback when score missing", () => {
    const viz = chg004DimensionFixtureViz();
    const a = deriveDimensionNodeJudgmentV1({
      dimension: "plot_progress",
      currentScene: viz.scene_nodes[2],
      previousScene: viz.scene_nodes[1],
      sceneCount: 6,
    });
    const b = deriveDimensionNodeJudgmentV1({
      dimension: "plot_progress",
      currentScene: viz.scene_nodes[2],
      previousScene: viz.scene_nodes[1],
      sceneCount: 6,
    });
    expect(a).toEqual(b);

    const empty = node({
      scene_ordinal: 1,
      scene_role: "setup",
      scores: {
        plot_progress: null,
        reading_tension: null,
        pacing_speed: null,
        emotional_investment: null,
        arousal_start: null,
        arousal_end: null,
      },
    });
    const miss = deriveDimensionNodeJudgmentV1({
      dimension: "plot_progress",
      currentScene: empty,
      sceneCount: 1,
    });
    expect(miss.judgment_source).toBe("unavailable");
    expect(miss.full_reason).toContain("暂无可靠判断");
  });

  it("chart shows dimension judgments above nodes and fit below; switches cleanly", () => {
    const viz = chg004DimensionFixtureViz();
    const { rerender } = render(
      <MemoryRouter>
        <CanonicalJourneyChart {...chartProps(viz, "plot_progress", 3)} />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("journey-dimension-judgment-3")).toHaveTextContent("目标明确");
    expect(screen.getByTestId("journey-dimension-fit-3")).toBeInTheDocument();
    expect(screen.queryByTestId("journey-composite-fit-3")).not.toBeInTheDocument();

    rerender(
      <MemoryRouter>
        <CanonicalJourneyChart {...chartProps(viz, "reading_tension", 3)} />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("journey-dimension-judgment-3")).toHaveTextContent("风险上升");
    expect(screen.queryByText("目标明确")).not.toBeInTheDocument();

    rerender(
      <MemoryRouter>
        <CanonicalJourneyChart {...chartProps(viz, "emotion", 3)} />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("journey-dimension-judgment-3")).toHaveTextContent("情绪爆发");

    rerender(
      <MemoryRouter>
        <CanonicalJourneyChart {...chartProps(viz, "pacing", 3)} />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("journey-dimension-judgment-3")).toHaveTextContent("明显加速");
    expect(screen.getByTestId("journey-pacing-fit-3")).toBeInTheDocument();
  });

  it("composite and hook_payoff remain free of dimension judgment markers", () => {
    const viz = chg004DimensionFixtureViz();
    const { rerender, unmount } = render(
      <MemoryRouter>
        <CanonicalJourneyChart {...chartProps(viz, "composite", 3)} />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId("journey-dimension-judgment-3")).not.toBeInTheDocument();

    rerender(
      <MemoryRouter>
        <CanonicalJourneyChart {...chartProps(viz, "hook_payoff", 3)} />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId("journey-dimension-judgment-3")).not.toBeInTheDocument();
    unmount();
  });

  it("tooltip shows judgment + fit + reason for dimension lenses", () => {
    const viz = chg004DimensionFixtureViz();
    const { container, unmount } = render(
      <MemoryRouter>
        <CanonicalJourneyChart {...chartProps(viz, "plot_progress", 3)} />
      </MemoryRouter>,
    );
    const nodeEl = within(container).getByTestId("journey-curve-node-3");
    fireEvent.mouseEnter(nodeEl);
    const tip = within(container).getByTestId("journey-node-tooltip");
    expect(within(tip).getByTestId("journey-tooltip-dimension-judgment")).toHaveTextContent(
      "目标明确",
    );
    expect(within(tip).getByTestId("journey-tooltip-dimension-fit").textContent).toMatch(/适配/);
    expect(within(tip).getByTestId("journey-tooltip-dimension-reason")).toBeInTheDocument();
    unmount();
  });

  it("stage band tokens remain CHG-002 palette", () => {
    expect(JOURNEY_STAGE_VISUAL_TOKENS.opening.cardBackground).toBe("#E4F1E8");
    expect(JOURNEY_STAGE_VISUAL_TOKENS.development.cardBackground).toBe("#F7EDD8");
    expect(JOURNEY_STAGE_VISUAL_TOKENS.closing.cardBackground).toBe("#E7EDF6");
    expect(JOURNEY_STAGE_VISUAL_TOKENS.opening.chartBand).toBe("#E4F1E8");
    expect(JOURNEY_STAGE_VISUAL_TOKENS.development.chartBand).toBe("#F7EDD8");
    expect(JOURNEY_STAGE_VISUAL_TOKENS.closing.chartBand).toBe("#E7EDF6");
  });

  it("bottom axis short labels sync with active dimension", () => {
    const viz = chg004DimensionFixtureViz();
    const { rerender, container, unmount } = render(
      <MemoryRouter>
        <CanonicalJourneyChart {...chartProps(viz, "plot_progress", 3)} />
      </MemoryRouter>,
    );
    expect(within(container).getByTestId("journey-dimension-axis-short-3")).toHaveTextContent(
      "目标明确",
    );

    rerender(
      <MemoryRouter>
        <CanonicalJourneyChart {...chartProps(viz, "reading_tension", 3)} />
      </MemoryRouter>,
    );
    expect(within(container).getByTestId("journey-dimension-axis-short-3")).toHaveTextContent(
      "风险上升",
    );
    unmount();
  });
});
