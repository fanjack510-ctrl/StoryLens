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

describe("Hook resolution result page (CHG-011 ordinary UI)", () => {
  it("shows verdict and reader questions without legacy stats blocks", () => {
    const onSelect = vi.fn();
    render(
      <HookPayoffTimeline
        visualization={vizWithLoops()}
        selectedLoopId="ID-identity"
        selectedSceneOrdinal={3}
        onSelectLoop={onSelect}
      />,
    );
    expect(screen.getByTestId("hook-resolution-overview")).toBeInTheDocument();
    expect(screen.queryByTestId("hook-resolution-conflicts")).not.toBeInTheDocument();
    expect(screen.queryByTestId("hook-payoff-stats")).not.toBeInTheDocument();
    expect(screen.queryByTestId("hook-chapter-ending-pull")).not.toBeInTheDocument();
    expect(screen.getByTestId("hook-chapter-reader-questions")).toBeInTheDocument();
    expect(screen.queryByTestId("hook-resolution-table")).not.toBeInTheDocument();
    expect(screen.queryAllByTestId("hook-payoff-loop-row")).toHaveLength(0);
    fireEvent.click(screen.getAllByTestId("hook-chapter-question-btn")[0]);
    expect(onSelect).toHaveBeenCalled();
  });

  it("does not show unresolved-as-failure conflict stat chrome", () => {
    render(<HookPayoffTimeline visualization={vizWithLoops()} />);
    expect(screen.queryByTestId("hook-stat-conflict")).not.toBeInTheDocument();
    expect(screen.getByTestId("hook-resolution-verdict").textContent).not.toMatch(/判定冲突/);
  });

  it("empty state shows title and note without trajectory", () => {
    const empty = vizWithLoops();
    (empty as { narrative_loops: unknown[] }).narrative_loops = [];
    render(<HookPayoffTimeline visualization={empty} />);
    expect(screen.getByTestId("hook-resolution-verdict").textContent).toContain(
      "本章未形成明确的阅读悬念",
    );
    expect(screen.getByTestId("hook-resolution-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("hook-chapter-scene-row")).not.toBeInTheDocument();
    expect(screen.queryByTestId("hook-chapter-reader-questions")).not.toBeInTheDocument();
  });
});
