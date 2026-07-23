import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";
import { HookPayoffTimeline } from "./HookPayoffTimeline";

function vizWithLoops(): ReaderJourneyVisualization {
  return {
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
        scene_count: 6,
        phase_count: 1,
        question_chain_count: 0,
        canonical_chain_count: 0,
        core: 6,
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
    scene_nodes: Array.from({ length: 6 }, (_, i) => ({
      scene_id: i + 1,
      scene_ordinal: i + 1,
      role: "core",
      scores: {},
    })),
    curve_series: {},
    phases: [],
    question_chains: [],
    canonical_chains: [],
    hook_markers: [],
    payoff_markers: [],
    risk_intervals: [],
    narrative_loops: [
      {
        loop_id: "L1",
        question: "他的真实身份究竟是什么人",
        information_gap: "身份疑问",
        open_from_scene: 1,
        hook: [{ scene_ordinal: 1, type: "new", summary: "身份疑问" }],
        developments: [],
        payoffs: [{ scene_ordinal: 4, type: "partial", summary: "部分揭晓" }],
        status: "partially_resolved",
        display_status: "partially_resolved",
        consistency_status: "ok",
        primary_relation: {
          grade: "explicit",
          blocked: false,
          payoff_ref: { scene_ordinal: 4, type: "partial" },
        },
      },
      {
        loop_id: "L2",
        question: "父母为何异常",
        information_gap: "父母异常",
        open_from_scene: 2,
        hook: [{ scene_ordinal: 2, type: "new", summary: "父母异常" }],
        developments: [],
        payoffs: [{ scene_ordinal: 5, type: "full", summary: "真相" }],
        status: "resolved",
        display_status: "resolved",
        consistency_status: "ok",
        primary_relation: {
          grade: "probable",
          blocked: false,
          payoff_ref: { scene_ordinal: 5, type: "full" },
        },
      },
      {
        loop_id: "L3",
        question: "背后声音从何而来",
        open_from_scene: 3,
        hook: [{ scene_ordinal: 3, type: "new", summary: "背后声音" }],
        developments: [],
        payoffs: [],
        status: "open",
        display_status: "open",
        consistency_status: "ok",
      },
      {
        loop_id: "L4",
        question: "危险来源是谁",
        open_from_scene: 1,
        hook: [{ scene_ordinal: 1, type: "new", summary: "危险来源" }],
        developments: [],
        payoffs: [],
        status: "open",
        display_status: "open",
        consistency_status: "ok",
      },
      {
        loop_id: "L5",
        question: "第五条过长问题用于截断测试ABCDEF",
        open_from_scene: 2,
        hook: [{ scene_ordinal: 2, type: "new", summary: "超长标签测试文本" }],
        developments: [],
        payoffs: [],
        status: "open",
        display_status: "open",
        consistency_status: "ok",
      },
    ],
    reading_resistance: [],
  } as unknown as ReaderJourneyVisualization;
}

afterEach(() => cleanup());

describe("HookPayoffTimeline one-loop-per-row", () => {
  it("renders one row per loop with truncation and horizontal min-width", () => {
    render(
      <HookPayoffTimeline visualization={vizWithLoops()} selectedLoopId="L1" />,
    );
    const root = screen.getByTestId("hook-payoff-timeline");
    expect(root).toHaveAttribute("data-layout", "one-loop-per-row");
    const rows = screen.getAllByTestId("hook-payoff-loop-row");
    expect(rows.length).toBe(5);
    expect(rows[0]).toHaveClass("is-active");
    expect(rows[1]).toHaveClass("is-muted");
    const track = screen.getByTestId("hook-payoff-rows-track");
    expect(Number.parseInt(track.style.minWidth, 10)).toBeGreaterThanOrEqual(480);
    const questions = within(rows[4]).getAllByText(/…/);
    expect(questions[0].textContent!.length).toBeLessThanOrEqual(12);
    expect(screen.getByTestId("hook-payoff-stats").textContent).toMatch(/建立钩子/);
  });
});
