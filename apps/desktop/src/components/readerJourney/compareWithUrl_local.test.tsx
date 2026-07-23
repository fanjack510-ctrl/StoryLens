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

describe("对比分析 mode + tools separation", () => {
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
  });

  it("keeps analysis tools out of the Lens list", () => {
    render(
      <MemoryRouter initialEntries={["/?overview=curve"]}>
        <ReaderJourneyWorkspace
          visualization={buildFixture13Scenes()}
          onLocateEvidence={vi.fn()}
        />
      </MemoryRouter>,
    );
    const lenses = screen.getByTestId("journey-lens-selector-list");
    expect(within(lenses).queryByText("对比分析")).not.toBeInTheDocument();
    expect(within(lenses).queryByText("对比指标")).not.toBeInTheDocument();
    expect(within(lenses).queryByText("重置视图")).not.toBeInTheDocument();
    expect(within(lenses).queryByText("适配全图")).not.toBeInTheDocument();
    expect(screen.getByTestId("journey-chart-tools")).toHaveAttribute(
      "data-tools-relocated",
      "true",
    );
    expect(screen.getByTestId("journey-chart-analysis-tools").textContent).toMatch(/对比分析/);
  });

  it("requires confirm before entering compare mode", () => {
    render(
      <MemoryRouter initialEntries={["/?overview=curve&lens=emotion"]}>
        <ReaderJourneyWorkspace
          visualization={buildFixture13Scenes()}
          onLocateEvidence={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId("journey-comparison-toolbar")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("journey-overlay-composite"));
    expect(screen.getByTestId("journey-compare-primary-label").textContent).toMatch(/情绪强度/);
    fireEvent.click(screen.getByTestId("journey-compare-reading_momentum"));
    // Pending only — not active yet
    expect(screen.queryByTestId("journey-comparison-toolbar")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("journey-compare-confirm"));
    expect(screen.getByTestId("journey-comparison-toolbar")).toBeInTheDocument();
    expect(screen.getByTestId("journey-comparison-active").textContent).toMatch(
      /情绪强度.*综合阅读动力/,
    );
    expect(screen.getByTestId("journey-comparison-exit")).toBeInTheDocument();
    expect(screen.getAllByTestId("journey-curve-path-secondary").length).toBeGreaterThan(0);
  });

  it("cancel does not activate compare", () => {
    render(
      <MemoryRouter initialEntries={["/?overview=curve&lens=emotion"]}>
        <ReaderJourneyWorkspace
          visualization={buildFixture13Scenes()}
          onLocateEvidence={vi.fn()}
        />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId("journey-overlay-composite"));
    fireEvent.click(screen.getByTestId("journey-compare-reading_momentum"));
    fireEvent.click(screen.getByTestId("journey-compare-cancel"));
    expect(screen.queryByTestId("journey-comparison-toolbar")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-curve-path-secondary")).not.toBeInTheDocument();
  });

  it("restores compare from URL and exits via fixed exit control", () => {
    render(
      <MemoryRouter initialEntries={["/?overview=curve&lens=composite&compareWith=arousal"]}>
        <ReaderJourneyWorkspace
          visualization={buildFixture13Scenes()}
          onLocateEvidence={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("journey-comparison-toolbar")).toHaveAttribute(
      "data-compare-with",
      "arousal",
    );
    expect(screen.getByTestId("journey-overlay-composite")).toHaveAttribute(
      "data-compare-with",
      "arousal",
    );
    fireEvent.click(screen.getByTestId("journey-comparison-exit"));
    expect(screen.queryByTestId("journey-comparison-toolbar")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-curve-path-secondary")).not.toBeInTheDocument();
  });

  it("hides compare tools on hook_payoff and clears compare", () => {
    render(
      <MemoryRouter initialEntries={["/?overview=curve&lens=composite&compareWith=arousal"]}>
        <ReaderJourneyWorkspace
          visualization={buildFixture13Scenes()}
          onLocateEvidence={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("journey-comparison-toolbar")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("journey-lens-hook_payoff"));
    expect(screen.queryByTestId("journey-comparison-toolbar")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-overlay-composite")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-chart-analysis-tools")).not.toBeInTheDocument();
  });

  it("auto-exits when switching to the same primary as compare", () => {
    render(
      <MemoryRouter initialEntries={["/?overview=curve&lens=emotion&compareWith=reading_momentum"]}>
        <ReaderJourneyWorkspace
          visualization={buildFixture13Scenes()}
          onLocateEvidence={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("journey-comparison-toolbar")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("journey-lens-composite"));
    expect(screen.queryByTestId("journey-comparison-toolbar")).not.toBeInTheDocument();
    expect(screen.getByTestId("journey-compare-live").textContent).toMatch(/对比模式已结束/);
  });

  it("shows phase primary-only hint while comparing", () => {
    render(
      <MemoryRouter initialEntries={["/?overview=curve&lens=emotion&compareWith=reading_momentum"]}>
        <ReaderJourneyWorkspace
          visualization={buildFixture13Scenes()}
          onLocateEvidence={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("journey-phase-primary-only-hint").textContent).toMatch(
      /阶段摘要仅显示主指标：情绪强度/,
    );
  });

  it("hides reset view when viewport is already full", () => {
    render(
      <MemoryRouter initialEntries={["/?overview=curve&lens=emotion"]}>
        <ReaderJourneyWorkspace
          visualization={buildFixture13Scenes()}
          onLocateEvidence={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId("journey-zoom-fit-all")).not.toBeInTheDocument();
  });
});
