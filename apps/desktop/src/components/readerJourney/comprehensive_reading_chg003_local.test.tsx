/**
 * CHG-20260729-003 — comprehensive reading presentation (factors, fit, key nodes, stage judgment).
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type {
  JourneySceneNode,
  ReaderJourneyVisualization,
} from "../../types/readerJourneyVisualization";
import {
  COMPREHENSIVE_READING_COPY,
  buildComprehensiveShortLabel,
  deriveComprehensiveKeyNodes,
  deriveComprehensiveReadingFactors,
  deriveStageJudgmentSummary,
  enrichVisualizationComprehensivePresentation,
  resolveCompositeRoleFit,
  resolveOverallReadingScore,
} from "./comprehensiveReadingPresentation";
import { compositeRoleFitLabel } from "./observationLenses";
import { getLensExplanation } from "./readerJourneyLensExplanation";
import { JourneyLensExplanationChrome } from "./JourneyLensExplanationChrome";
import { JOURNEY_STAGE_VISUAL_TOKENS } from "./journeyVisualTokens";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { buildMockReaderJourneyVisualization } from "./mockVisualization";

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
  } as JourneySceneNode;
}

function chg003FixtureViz(): ReaderJourneyVisualization {
  const roles = ["setup", "transition", "escalation", "reveal", "climax", "aftermath"] as const;
  const momentums = [58, 48, 72, 68, 86, 62];
  const plots = [42, 35, 78, 70, 88, 40];
  const tensions = [38, 40, 70, 62, 90, 35];
  const hooks = [40, 35, 60, 55, 80, 45];
  const payoffs = [25, 20, 45, 70, 85, 72];
  const emotions = [40, 38, 55, 48, 75, 50];
  const pacings = [45, 82, 60, 58, 78, 35];

  const scene_nodes = momentums.map((m, i) =>
    node({
      scene_ordinal: i + 1,
      scene_id: i + 1,
      role: i === 1 ? "secondary" : "core",
      scene_role: roles[i],
      phase_ordinal: i < 2 ? 1 : i < 5 ? 2 : 3,
      scores: {
        reading_momentum: m,
        plot_progress: plots[i],
        reading_tension: tensions[i],
        hook: hooks[i],
        payoff: payoffs[i],
        pacing_speed: pacings[i],
        pacing_fit: roles[i] === "transition" && pacings[i] > 75 ? 40 : 75,
        arousal_start: emotions[i],
        arousal_end: emotions[i] + 2,
        emotional_investment: emotions[i],
      },
      overall_reading_score: m,
      composite_role_fit: compositeRoleFitLabel(m, roles[i]),
      dimension_insights: {
        overall_reading: `场景${i + 1}综合阅读洞察`,
        plot_progression: null,
        reading_tension: null,
        emotional_intensity: null,
        hook_payoff: null,
        pacing_speed: null,
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
        average_engagement: 53,
        summary: "",
      },
      {
        ...viz.phases[1],
        ordinal: 2,
        title: "发展",
        start_scene_ordinal: 3,
        end_scene_ordinal: 5,
        average_engagement: 75,
        summary: "",
      },
      {
        ...(viz.phases[2] || viz.phases[0]),
        ordinal: 3,
        title: "收束",
        start_scene_ordinal: 6,
        end_scene_ordinal: 6,
        average_engagement: 62,
        summary: "",
      },
    ].slice(0, 3),
    risk_intervals: [
      {
        risk_type: "consecutive_no_payoff",
        start_scene_ordinal: 1,
        end_scene_ordinal: 2,
        severity: "medium",
        label: "阅读阻力",
      } as never,
    ],
  };
}

describe("CHG-20260729-003 score and fit", () => {
  it("uses reading_momentum / overall_reading_score alias", () => {
    const n = node({
      scene_ordinal: 1,
      scores: { reading_momentum: 58 } as never,
      overall_reading_score: 58,
    });
    expect(resolveOverallReadingScore(n)).toBe(58);
  });

  it("setup mid score can be 合适 while climax same score can be 偏弱", () => {
    expect(compositeRoleFitLabel(58, "setup")).toBe("合适");
    expect(compositeRoleFitLabel(58, "climax")).toBe("偏弱");
  });

  it("transition high score can be 偏强 while climax same score 合适", () => {
    expect(compositeRoleFitLabel(82, "transition")).toBe("偏强");
    expect(compositeRoleFitLabel(82, "climax")).toBe("合适");
  });

  it("null momentum → 无法判断", () => {
    expect(compositeRoleFitLabel(null, "setup")).toBe("无法判断");
    const blank = {
      scene_ordinal: 1,
      scores: {},
      overall_reading_score: null,
      composite_role_fit: null,
      engagement: { engagement_score: Number.NaN },
    } as unknown as JourneySceneNode;
    expect(resolveOverallReadingScore(blank)).toBeNull();
    expect(resolveCompositeRoleFit(blank)).toBe("无法判断");
  });

  it("does not use fixed global thresholds alone (same score different fit)", () => {
    const a = compositeRoleFitLabel(58, "setup");
    const b = compositeRoleFitLabel(58, "climax");
    expect(a).not.toBe(b);
  });
});

describe("CHG-20260729-003 driver / drag", () => {
  it("limits to one driver and one drag; stable; no internal fields", () => {
    const n = node({
      scene_ordinal: 3,
      scene_role: "escalation",
      scores: {
        reading_momentum: 72,
        plot_progress: 78,
        reading_tension: 70,
        hook: 60,
        payoff: 45,
        pacing_speed: 60,
        emotional_investment: 55,
      } as never,
      composite_role_fit: "合适",
    });
    const a = deriveComprehensiveReadingFactors(n);
    const b = deriveComprehensiveReadingFactors(n);
    expect(a).toEqual(b);
    expect(a.explanation_source).toBe("derived");
    expect(a.primary_driver).toBeTruthy();
    expect(a.primary_driver).not.toEqual(a.primary_drag);
    expect(JSON.stringify(a)).not.toMatch(/reading_momentum|plot_progress|formula/i);
  });

  it("payoff response can be driver; weak tension can be drag", () => {
    const n = node({
      scene_ordinal: 4,
      scene_role: "reveal",
      scores: {
        reading_momentum: 68,
        plot_progress: 70,
        reading_tension: 30,
        hook: 50,
        payoff: 75,
        pacing_speed: 55,
      } as never,
      composite_role_fit: "合适",
    });
    const f = deriveComprehensiveReadingFactors(n);
    expect(f.primary_driver).toMatch(/回应|推进|揭示/);
  });

  it("pace too fast with 偏强 prefers drag 节奏偏快", () => {
    const n = node({
      scene_ordinal: 2,
      scene_role: "transition",
      scores: {
        reading_momentum: 82,
        plot_progress: 40,
        pacing_speed: 88,
        pacing_fit: 35,
        hook: 30,
        payoff: 20,
      } as never,
      composite_role_fit: "偏强",
    });
    const f = deriveComprehensiveReadingFactors(n);
    expect(f.primary_drag).toBe("节奏偏快");
  });

  it("short label respects 12 char limit", () => {
    const label = buildComprehensiveShortLabel({
      primary_driver: "剧情产生实质推进",
      primary_drag: "情绪铺垫不足",
      explanation_source: "derived",
    });
    expect(label).toBeTruthy();
    expect(Array.from(label!).length).toBeLessThanOrEqual(12);
  });
});

describe("CHG-20260729-003 key nodes and stage summaries", () => {
  it("marks rise/drop/turn with limits; first scene not auto rise/drop", () => {
    const enriched = enrichVisualizationComprehensivePresentation(chg003FixtureViz());
    const keys = enriched.comprehensive_key_nodes || [];
    expect(keys.every((k) => k.scene_ordinal !== 1 || k.kind === "composite_turn")).toBe(true);
    expect(keys.length).toBeGreaterThan(0);
    expect(keys.length).toBeLessThanOrEqual(5);
    const kinds = new Set(keys.map((k) => k.kind));
    expect(kinds.size).toBeGreaterThan(0);
    const ordinals = keys.map((k) => k.scene_ordinal);
    expect(new Set(ordinals).size).toBe(ordinals.length);
  });

  it("deriveComprehensiveKeyNodes is deterministic", () => {
    const viz = enrichVisualizationComprehensivePresentation(chg003FixtureViz());
    expect(deriveComprehensiveKeyNodes(viz)).toEqual(deriveComprehensiveKeyNodes(viz));
  });

  it("stage judgments differ and stay within length", () => {
    const enriched = enrichVisualizationComprehensivePresentation(chg003FixtureViz());
    const texts = enriched.phases.map((p) => p.stage_judgment_summary || "");
    expect(texts.every((t) => t.length > 0)).toBe(true);
    expect(new Set(texts).size).toBeGreaterThanOrEqual(2);
    for (const t of texts) {
      expect(Array.from(t).length).toBeLessThanOrEqual(32);
      expect(t).not.toMatch(/reading_momentum|formula|plot_progress/);
    }
  });
});

describe("CHG-20260729-003 copy and chrome", () => {
  it("definition matches freeze and chrome has no double prefix", () => {
    const expl = getLensExplanation("composite");
    expect(expl.one_line_summary).toBe(COMPREHENSIVE_READING_COPY.definition);
    expect(expl.one_line_summary.startsWith("综合阅读：")).toBe(false);
    render(<JourneyLensExplanationChrome lensId="composite" />);
    const line = screen.getByTestId("journey-lens-one-liner").textContent || "";
    expect(line.match(/综合阅读：/g)?.length).toBe(1);
  });

  it("keeps CHG-002 stage colors", () => {
    expect(JOURNEY_STAGE_VISUAL_TOKENS.opening.chartBand).toBe("#E4F1E8");
    expect(JOURNEY_STAGE_VISUAL_TOKENS.development.chartBand).toBe("#F7EDD8");
    expect(JOURNEY_STAGE_VISUAL_TOKENS.closing.chartBand).toBe("#E7EDF6");
  });
});

describe("CHG-20260729-003 workspace UI", () => {
  it("shows stage judgments on composite phase cards", () => {
    const viz = chg003FixtureViz();
    render(
      <MemoryRouter initialEntries={["/?overview=curve&lens=composite"]}>
        <ReaderJourneyWorkspace visualization={viz} onLocateEvidence={() => undefined} />
      </MemoryRouter>,
    );
    const card = screen.getByTestId("journey-phase-1");
    expect(card.textContent).toMatch(/综合阅读/);
    expect(card.querySelector(".journey-phase-card-desc")?.textContent?.length).toBeGreaterThan(4);
    expect(screen.getAllByTestId("journey-lens-one-liner")[0].textContent).toContain("故事理解");
  });
});
