import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { buildFixture13Scenes } from "./mockVisualizationFixtures";
import { buildLensChartLines } from "./observationLenses";

afterEach(() => {
  cleanup();
  document.getElementById("journey-overlay-root")?.remove();
});

describe("对比指标 compareWith URL + chart lines", () => {
  it("does not draw secondary line without compareWith", () => {
    const viz = buildFixture13Scenes();
    expect(buildLensChartLines(viz, "composite")).toHaveLength(1);
    expect(buildLensChartLines(viz, "reading_tension", { compareWith: null })).toHaveLength(1);
  });

  it("adds named secondary line only when compareWith is set", () => {
    const viz = buildFixture13Scenes();
    const lines = buildLensChartLines(viz, "composite", { compareWith: "arousal" });
    expect(lines).toHaveLength(2);
    expect(lines[1].labelZh).toMatch(/情绪/);
    expect(lines.map((l) => l.id)[0]).not.toBe(lines.map((l) => l.id)[1]);
  });

  it("restores compareWith from URL and clears on 退出对比", () => {
    render(
      <MemoryRouter initialEntries={["/?overview=curve&lens=composite&compareWith=arousal"]}>
        <ReaderJourneyWorkspace
          visualization={buildFixture13Scenes()}
          onLocateEvidence={vi.fn()}
        />
      </MemoryRouter>,
    );
    const compareBtn = screen.getByTestId("journey-overlay-composite");
    expect(compareBtn).toHaveAttribute("data-compare-with", "arousal");
    fireEvent.click(compareBtn);
    fireEvent.click(screen.getByTestId("journey-compare-none"));
    expect(screen.getByTestId("journey-overlay-composite")).toHaveAttribute(
      "data-compare-with",
      "",
    );
  });

  it("keeps 对比指标 in tools, not as a main lens", () => {
    render(
      <MemoryRouter initialEntries={["/?overview=curve"]}>
        <ReaderJourneyWorkspace
          visualization={buildFixture13Scenes()}
          onLocateEvidence={vi.fn()}
        />
      </MemoryRouter>,
    );
    const lenses = screen.getByTestId("journey-lens-selector-list");
    expect(within(lenses).queryByText("对比指标")).not.toBeInTheDocument();
    expect(within(lenses).queryByText("全部指标")).not.toBeInTheDocument();
    expect(within(lenses).queryByText("当前阶段")).not.toBeInTheDocument();
    expect(screen.getByTestId("journey-chart-tools")).toHaveTextContent("对比指标");
    expect(screen.getByTestId("journey-chart-tools")).toHaveTextContent("适配全图");
  });
});
