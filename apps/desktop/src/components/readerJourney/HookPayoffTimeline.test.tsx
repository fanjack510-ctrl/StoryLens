import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
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
    phases: [
      {
        ordinal: 1,
        title: "开端",
        start_scene_ordinal: 1,
        end_scene_ordinal: 2,
        average_engagement: 50,
        summary: "",
      },
      {
        ordinal: 2,
        title: "发展",
        start_scene_ordinal: 3,
        end_scene_ordinal: 5,
        average_engagement: 60,
        summary: "",
      },
      {
        ordinal: 3,
        title: "收束",
        start_scene_ordinal: 6,
        end_scene_ordinal: 6,
        average_engagement: 40,
        summary: "",
      },
    ],
    question_chains: [],
    canonical_chains: [],
    hook_markers: [],
    payoff_markers: [],
    risk_intervals: [],
    narrative_loops: [
      {
        loop_id: "L1",
        question: "他的真实身份究竟是什么人",
        open_from_scene: 1,
        hook: [{ scene_ordinal: 1, type: "new", summary: "身份疑问", strength: 75 }],
        developments: [{ scene_ordinal: 2 }],
        payoffs: [{ scene_ordinal: 4, type: "partial", summary: "部分揭晓" }],
        status: "partially_resolved",
        display_status: "partially_resolved",
        consistency_status: "soft_conflict",
        soft_conflict: true,
        conflicts: [{ code: "soft_conflict", message: "承接不稳定" }],
        primary_relation: {
          grade: "probable",
          payoff_ref: { scene_ordinal: 4, type: "partial" },
        },
      },
      {
        loop_id: "L2",
        question: "父母为何异常",
        open_from_scene: 2,
        hook: [{ scene_ordinal: 2, type: "new", strength: 60 }],
        payoffs: [{ scene_ordinal: 5, type: "full", summary: "真相" }],
        status: "resolved",
        display_status: "resolved",
        consistency_status: "consistent",
        conflicts: [],
        primary_relation: {
          grade: "confirmed",
          payoff_ref: { scene_ordinal: 5, type: "full" },
        },
      },
      {
        loop_id: "L3",
        question: "背后声音从何而来",
        open_from_scene: 3,
        hook: [{ scene_ordinal: 3, type: "new", strength: 70 }],
        payoffs: [],
        status: "open",
        display_status: "open",
        consistency_status: "consistent",
        conflicts: [],
      },
    ],
    reading_resistance: [],
  } as unknown as ReaderJourneyVisualization;
}

afterEach(() => cleanup());

describe("Hook resolution result page (CHG-005 ordinary UI)", () => {
  it("shows simplified overview without technical conflict table", () => {
    const onSelect = vi.fn();
    render(
      <HookPayoffTimeline
        visualization={vizWithLoops()}
        selectedLoopId="L1"
        onSelectLoop={onSelect}
      />,
    );
    expect(screen.getByTestId("hook-resolution-overview")).toBeInTheDocument();
    expect(screen.queryByTestId("hook-resolution-conflicts")).not.toBeInTheDocument();
    expect(screen.queryByText("冲突提醒")).not.toBeInTheDocument();
    expect(screen.getByTestId("hook-stat-raised").textContent).toMatch(/本章提出/);
    expect(screen.getByTestId("hook-stat-answered").textContent).toMatch(/本章回应/);
    expect(screen.getByTestId("hook-stat-carried").textContent).toMatch(/继续保留/);
    expect(screen.getByTestId("hook-stat-chapter-pull").textContent).toMatch(/章末牵引/);
    expect(screen.queryByTestId("hook-resolution-table")).not.toBeInTheDocument();
    expect(screen.queryAllByTestId("hook-payoff-loop-row")).toHaveLength(0);
    expect(screen.getByTestId("hook-chapter-important")).toBeInTheDocument();
    fireEvent.click(screen.getAllByTestId("hook-chapter-important-item")[0].querySelector("button")!);
    expect(onSelect).toHaveBeenCalled();
  });

  it("does not show unresolved-as-failure conflict stat chrome", () => {
    render(<HookPayoffTimeline visualization={vizWithLoops()} />);
    expect(screen.queryByTestId("hook-stat-conflict")).not.toBeInTheDocument();
    expect(screen.getByTestId("hook-resolution-verdict").textContent).not.toMatch(/判定冲突/);
  });

  it("shows empty state without scene row", () => {
    const empty = vizWithLoops();
    (empty as { narrative_loops: unknown[] }).narrative_loops = [];
    render(<HookPayoffTimeline visualization={empty} />);
    expect(screen.getByTestId("hook-resolution-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("hook-chapter-scene-row")).not.toBeInTheDocument();
  });
});
