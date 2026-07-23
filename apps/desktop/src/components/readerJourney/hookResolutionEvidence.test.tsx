import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { JourneySceneNode, ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";
import { JourneySceneDetailPanel } from "./JourneySceneDetailPanel";

afterEach(() => cleanup());

function vizAndNode(): { viz: ReaderJourneyVisualization; node: JourneySceneNode } {
  const node = {
    scene_id: 1,
    scene_ordinal: 1,
    role: "core",
    scores: { reading_momentum: 50, curiosity: 40, tension: 30 },
    engagement: { engagement_score: 50 },
    techniques: [],
    scene_value_summary: "场景摘要",
  } as unknown as JourneySceneNode;
  const viz = {
    visualization_version: "test",
    chapter_summary: {
      chapter_id: 1,
      chapter_title: "t",
      diagnosis: "d",
      primary_traction: "p",
      strongest_payoff: null,
      strongest_hook: null,
      weak_interval: "",
      counts: {
        scene_count: 5,
        phase_count: 1,
        question_chain_count: 0,
        canonical_chain_count: 0,
        core: 5,
        secondary: 0,
        beat: 0,
      },
      peaks: {
        engagement_peak: { scene_ordinal: 1, value: 90 },
        engagement_valley: { scene_ordinal: 2, value: 10 },
        curiosity_peak: { scene_ordinal: 1, value: 80 },
        tension_peak: { scene_ordinal: 1, value: 70 },
        emotional_peak: { scene_ordinal: 1, value: 60 },
      },
    },
    scene_nodes: [node],
    curve_series: {},
    phases: [],
    question_chains: [],
    canonical_chains: [],
    hook_markers: [],
    payoff_markers: [],
    risk_intervals: [],
    narrative_loops: [
      {
        loop_id: "nl-conflict",
        question: "他是谁",
        open_from_scene: 1,
        hook: [{ scene_ordinal: 1, type: "new" }],
        payoffs: [],
        status: "open",
        display_status: "open",
        soft_conflict: true,
        consistency_status: "soft_conflict",
        conflicts: [
          {
            code: "payoff_score_without_entity",
            message: "Scene 5: payoff_score=80 but payoffs[] is empty",
          },
        ],
        primary_relation: {
          grade: "candidate",
          payoff_ref: {
            scene_ordinal: 5,
            type: "score_inferred",
            source_type: "score_inferred",
          },
        },
      },
    ],
    reading_resistance: [],
  } as unknown as ReaderJourneyVisualization;
  return { viz, node };
}

describe("hook resolution evidence in inspector", () => {
  it("shows ordinary conflict language; tech text only under folded 分析信息", () => {
    const { viz, node } = vizAndNode();
    render(
      <JourneySceneDetailPanel
        node={node}
        visualization={viz}
        observationLens="hook_payoff"
        selectedLoopId="nl-conflict"
        onLocateEvidence={vi.fn()}
      />,
    );
    expect(screen.getByTestId("hook-resolution-evidence")).toBeInTheDocument();
    expect(screen.getByTestId("hook-resolution-evidence-conclusion").textContent).toMatch(/未回收/);
    expect(screen.getByTestId("hook-resolution-evidence-why").textContent).toMatch(
      /没有足够的实体回报证据/,
    );
    expect(screen.getByTestId("hook-resolution-evidence-divergence").textContent).toMatch(
      /分数提示可能存在回报/,
    );
    expect(screen.getByTestId("hook-resolution-evidence-divergence").textContent).not.toMatch(
      /payoff_score/,
    );
    const tech = screen.getByTestId("hook-resolution-evidence-tech");
    expect(tech).toBeInTheDocument();
    expect(tech.textContent).toMatch(/payoff_score=80/);
    expect(screen.queryByText("冲突提醒")).not.toBeInTheDocument();
  });
});
