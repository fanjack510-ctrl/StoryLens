import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";
import { HookPayoffTimeline } from "./HookPayoffTimeline";
import { useDeveloperModeStore } from "../../stores/developerModeStore";
import { chg005CompleteFixtureViz } from "./chg005CompleteFixture";

function vizWithLoops(): ReaderJourneyVisualization {
  return chg005CompleteFixtureViz();
}

afterEach(() => {
  cleanup();
  useDeveloperModeStore.setState({ developerMode: false });
});

describe("Hook resolution result page (CHG-005 ordinary UI)", () => {
  it("shows simplified overview without technical conflict table", () => {
    const onSelect = vi.fn();
    render(
      <HookPayoffTimeline
        visualization={vizWithLoops()}
        selectedLoopId="ID-identity"
        onSelectLoop={onSelect}
      />,
    );
    expect(screen.getByTestId("hook-resolution-overview")).toBeInTheDocument();
    expect(screen.queryByTestId("hook-resolution-conflicts")).not.toBeInTheDocument();
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

  it("empty state keeps scene track with blank labels when no loops", () => {
    const empty = vizWithLoops();
    (empty as { narrative_loops: unknown[] }).narrative_loops = [];
    render(<HookPayoffTimeline visualization={empty} />);
    expect(screen.getByTestId("hook-resolution-empty")).toBeInTheDocument();
    expect(screen.getByTestId("hook-chapter-scene-row")).toBeInTheDocument();
    expect(screen.getByTestId("hook-chapter-scene-label-1").textContent).toBe("—");
    expect(screen.getByTestId("hook-stat-answered").textContent).toMatch(/本章回应：0/);
    expect(screen.getByTestId("hook-stat-chapter-pull").textContent).toMatch(/暂无/);
  });
});
