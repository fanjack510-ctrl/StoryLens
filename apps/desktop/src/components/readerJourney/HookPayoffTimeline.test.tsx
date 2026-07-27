import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
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
        open_from_scene: 1,
        hook: [{ scene_ordinal: 1, type: "new", summary: "身份疑问" }],
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
        hook: [{ scene_ordinal: 2, type: "new" }],
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
        hook: [{ scene_ordinal: 3, type: "new" }],
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

describe("Hook resolution result page", () => {
  it("shows overview + list only; no standalone conflict block or ID column", () => {
    const onSelect = vi.fn();
    render(
      <HookPayoffTimeline
        visualization={vizWithLoops()}
        selectedLoopId="L1"
        onSelectLoop={onSelect}
      />,
    );
    expect(screen.getByTestId("hook-resolution-overview")).toBeInTheDocument();
    expect(screen.queryByTestId("hook-resolution-conclusion")).not.toBeInTheDocument();
    expect(screen.queryByTestId("hook-resolution-conflicts")).not.toBeInTheDocument();
    expect(screen.queryByText("冲突提醒")).not.toBeInTheDocument();

    expect(screen.getByTestId("hook-resolution-verdict").textContent).toMatch(
      /本章建立 3 个钩子，已回收 1 个，部分回收 1 个，未回收 1 个，其中 1 个存在判定冲突/,
    );
    expect(screen.getByTestId("hook-payoff-stats").textContent).toMatch(/建立钩子 3/);
    expect(screen.getByTestId("hook-payoff-stats").textContent).toMatch(/已回收 1/);
    expect(screen.getByTestId("hook-payoff-stats").textContent).toMatch(/部分回收 1/);
    expect(screen.getByTestId("hook-payoff-stats").textContent).toMatch(/未回收 1/);
    expect(screen.getByTestId("hook-payoff-stats").textContent).toMatch(/有冲突 1/);

    const lanes = screen.getAllByTestId("hook-payoff-loop-row");
    expect(lanes).toHaveLength(3);
    expect(lanes[0]).toHaveAttribute("data-main-status", "partial");
    expect(lanes[0]).toHaveAttribute("data-line-style", "dashed");
    expect(lanes[0]).toHaveAttribute("data-has-conflict", "true");
    expect(within(lanes[0]).getByTestId("hook-resolution-lane-status").textContent).toMatch(
      /部分回收｜有冲突/,
    );
    expect(lanes[1]).toHaveAttribute("data-line-style", "solid");
    expect(lanes[2]).toHaveAttribute("data-line-style", "gray");
    expect(within(lanes[2]).getByTestId("hook-resolution-node-unresolved")).toBeInTheDocument();

    const table = screen.getByTestId("hook-resolution-table");
    expect(table.textContent).not.toMatch(/\bID\b/);
    expect(within(table).queryByText("L1")).not.toBeInTheDocument();
    expect(within(table).queryByText("L2")).not.toBeInTheDocument();
    expect(within(table).getByText("提出位置")).toBeInTheDocument();
    expect(within(table).getByText("回收结果")).toBeInTheDocument();

    const listRows = screen.getAllByTestId("hook-resolution-list-row");
    expect(listRows).toHaveLength(3);
    expect(listRows[0].textContent).toMatch(/有/);
    expect(listRows[2].textContent).toMatch(/本章未回收/);
    fireEvent.click(within(listRows[0]).getByTestId("hook-resolution-locate"));
    expect(onSelect).toHaveBeenCalled();
  });

  it("hides conflict stat when conflict count is zero", () => {
    const viz = vizWithLoops();
    (viz as { narrative_loops: Array<{ soft_conflict?: boolean; consistency_status?: string; conflicts?: unknown[] }> }).narrative_loops =
      (viz as { narrative_loops: Array<Record<string, unknown>> }).narrative_loops.map((loop) => ({
        ...loop,
        soft_conflict: false,
        consistency_status: "consistent",
        conflicts: [],
      }));
    render(<HookPayoffTimeline visualization={viz} />);
    expect(screen.queryByTestId("hook-stat-conflict")).not.toBeInTheDocument();
    expect(screen.getByTestId("hook-resolution-verdict").textContent).not.toMatch(/判定冲突/);
  });

  it("shows empty state without bus lanes", () => {
    const empty = vizWithLoops();
    (empty as { narrative_loops: unknown[] }).narrative_loops = [];
    render(<HookPayoffTimeline visualization={empty} />);
    expect(screen.getByTestId("hook-resolution-empty")).toBeInTheDocument();
    expect(screen.queryAllByTestId("hook-payoff-loop-row")).toHaveLength(0);
    expect(screen.queryByTestId("hook-resolution-conflicts")).not.toBeInTheDocument();
  });
});
