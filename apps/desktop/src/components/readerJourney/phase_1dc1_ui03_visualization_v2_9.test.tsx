import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CanonicalJourneyChart } from "./CanonicalJourneyChart";
import {
  buildLinePathD,
  collectDataWarnings,
  computeYScale,
  resolveMetricValue,
} from "./journeyChartScales";
import {
  CHART_HEIGHT_PRESETS,
  CHART_PAD,
  JOURNEY_VISUALIZATION_VERSION,
  PLOT_AREA_HEIGHT_PRESETS,
  allowsHorizontalPanZoom,
  chartHeightPx,
  plotAreaHeightPx,
  requiresBrush,
  showsZoomControls,
} from "./journeyVisualizationConfig";
import {
  buildFixture13Scenes,
  buildFixture30Scenes,
  buildFixture3Scenes,
  buildFixture60Scenes,
} from "./mockVisualizationFixtures";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";

const css = readFileSync(resolve(__dirname, "./readerJourney.css"), "utf8");

function renderWorkspace(viz = buildFixture13Scenes()) {
  return render(
    <MemoryRouter>
      <ReaderJourneyWorkspace visualization={viz} onLocateEvidence={vi.fn()} />
    </MemoryRouter>,
  );
}

describe("Reader Journey Visualization v2.9 (superseded by v3.0)", () => {
  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it("exposes global visualization version 4.0", () => {
    expect(JOURNEY_VISUALIZATION_VERSION).toBe("4.2");
  });

  it("uses plot_area_height>=340 as desktop default (SVG standard=420)", () => {
    expect(PLOT_AREA_HEIGHT_PRESETS.standard).toBeGreaterThanOrEqual(340);
    expect(PLOT_AREA_HEIGHT_PRESETS.expanded).toBe(480);
    expect(plotAreaHeightPx("standard")).toBeGreaterThanOrEqual(340);
    expect(chartHeightPx("standard")).toBe(420);
    expect(CHART_HEIGHT_PRESETS.standard).toBe(420);
    expect(CHART_HEIGHT_PRESETS.expanded).toBe(480 + CHART_PAD.top + CHART_PAD.bottom);
  });

  it("keeps Y domain fixed 0鈥?00 by default with ticks 0/25/50/75/100", () => {
    const viz = buildFixture13Scenes();
    const scale = computeYScale(viz.curve_series.curiosity, chartHeightPx("standard"), "fixed_0_100");
    expect(scale.domainMin).toBe(0);
    expect(scale.domainMax).toBe(100);
    expect(scale.ticks).toEqual([0, 25, 50, 75, 100]);
    renderWorkspace(viz);
    for (const tick of [0, 25, 50, 75, 100]) {
      expect(screen.getByTestId(`journey-y-tick-${tick}`)).toBeInTheDocument();
    }
  });

  it("defaults Inspector collapsed and curve SVG at real plot height", () => {
    renderWorkspace();
    expect(screen.getByTestId("journey-resizable-split")).toHaveAttribute(
      "data-inspector-collapsed",
      "true",
    );
    expect(screen.getByTestId("journey-inspector-summary-bar")).toBeInTheDocument();
    expect(screen.getByTestId("journey-curve-svg").getAttribute("height")).toBe("420");
    expect(screen.getByTestId("journey-curve-section")).toHaveAttribute(
      "data-plot-area-height",
      String(plotAreaHeightPx("standard")),
    );
    expect(screen.getByTestId("journey-curve-container")).toHaveAttribute(
      "data-visualization-version",
      "4.2",
    );
  });

  it("hides zoom in/out for 鈮?5 scenes; shows for 30", () => {
    expect(showsZoomControls(13)).toBe(false);
    expect(showsZoomControls(30)).toBe(true);
    renderWorkspace(buildFixture13Scenes());
    fireEvent.click(screen.getByTestId("journey-more-chart-settings"));
    expect(screen.queryByTestId("journey-zoom-in")).not.toBeInTheDocument();
    cleanup();
    renderWorkspace(buildFixture30Scenes());
    fireEvent.click(screen.getByTestId("journey-more-chart-settings"));
    expect(screen.getByTestId("journey-zoom-in")).toBeEnabled();
  });

  it("moves height / focus-data into more settings (not primary toolbar)", () => {
    renderWorkspace();
    expect(screen.queryByTestId("journey-chart-height-expanded")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-y-domain-focus")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("journey-more-chart-settings"));
    expect(screen.getByTestId("journey-chart-height-expanded")).toBeInTheDocument();
    expect(screen.getByTestId("journey-y-domain-focus")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("journey-chart-height-expanded"));
    expect(screen.getByTestId("journey-curve-svg").getAttribute("height")).toBe("548");
    expect(screen.getByTestId("journey-curve-section")).toHaveAttribute(
      "data-plot-area-height",
      "480",
    );
  });

  it("renders all 13 scene nodes with full Y ticks and no chart overflow-y scroll", () => {
    renderWorkspace(buildFixture13Scenes());
    for (let i = 1; i <= 13; i += 1) {
      expect(screen.getByTestId(`journey-curve-node-${i}`)).toBeInTheDocument();
    }
    expect(css).toMatch(
      /\.journey-overview-curve \.journey-curve-container[\s\S]*overflow-y:\s*hidden/,
    );
    expect(css).not.toMatch(
      /\.journey-overview-curve \.journey-curve-container[\s\S]*overflow-y:\s*(auto|scroll)/,
    );
  });

  it("expands and collapses inspector via summary / toolbar", () => {
    renderWorkspace();
    expect(screen.getByTestId("journey-resizable-split")).toHaveAttribute(
      "data-inspector-collapsed",
      "true",
    );
    fireEvent.click(screen.getByTestId("journey-inspector-summary-expand"));
    expect(screen.getByTestId("journey-resizable-split")).toHaveAttribute(
      "data-inspector-collapsed",
      "false",
    );
    expect(screen.getByTestId("journey-detail-pane")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("journey-collapse-inspector"));
    expect(screen.getByTestId("journey-resizable-split")).toHaveAttribute(
      "data-inspector-collapsed",
      "true",
    );
  });

  it("keeps metric switch on fixed 0鈥?00 and syncs node click to inspector", () => {
    renderWorkspace(buildFixture13Scenes());
    fireEvent.click(screen.getByTestId("journey-metric-select"));
    fireEvent.click(screen.getByTestId("journey-metric-curiosity"));
    expect(screen.getByTestId("journey-y-tick-0")).toBeInTheDocument();
    expect(screen.getByTestId("journey-y-tick-100")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("journey-curve-node-5"));
    expect(screen.getByTestId("journey-detail-pane")).toHaveAttribute("data-inspector", "scene");
    expect(screen.getByTestId("journey-resizable-split")).toHaveAttribute(
      "data-inspector-collapsed",
      "false",
    );
  });

  it("enables pan for 30 scenes and brush for 60 scenes", () => {
    expect(allowsHorizontalPanZoom(30)).toBe(true);
    expect(requiresBrush(30)).toBe(false);
    expect(requiresBrush(60)).toBe(true);
    const { unmount } = renderWorkspace(buildFixture60Scenes());
    expect(screen.getByTestId("journey-chart-brush")).toBeInTheDocument();
    unmount();
  });

  it("shows scores 0/100 without coercing null to 0", () => {
    expect(resolveMetricValue({ scene_ordinal: 1, value: 0 })).toBe(0);
    expect(resolveMetricValue({ scene_ordinal: 4 })).toBeNull();
    const path = buildLinePathD(
      [
        { scene_ordinal: 1, value: 0 },
        { scene_ordinal: 2 },
        { scene_ordinal: 3, value: 100 },
      ],
      (o) => o * 10,
      (v) => 100 - v,
    );
    expect(path.split("M ").length - 1).toBe(2);
    expect(collectDataWarnings([{ scene_ordinal: 1, value: -5 }])).toHaveLength(1);
  });

  it("uses a single canonical chart for all fixtures", () => {
    for (const factory of [
      buildFixture3Scenes,
      buildFixture13Scenes,
      buildFixture30Scenes,
      buildFixture60Scenes,
    ]) {
      const viz = factory();
      const { unmount } = render(
        <CanonicalJourneyChart
          visualization={viz}
          metric="curiosity"
          chartHeight={chartHeightPx("standard")}
          yDomainMode="fixed_0_100"
          viewStart={1}
          viewEnd={viz.scene_nodes.length}
          onViewChange={() => undefined}
          selectedSceneOrdinal={null}
          selectedPhaseOrdinal={null}
          markerMode="compact"
          onSelectScene={() => undefined}
          onSelectRisk={() => undefined}
          onSelectHook={() => undefined}
          onSelectPayoff={() => undefined}
        />,
      );
      expect(screen.getByTestId("journey-curve-container")).toHaveAttribute(
        "data-canonical-chart",
        "true",
      );
      expect(screen.getByTestId("journey-curve-container")).toHaveAttribute(
        "data-visualization-version",
        "4.2",
      );
      unmount();
    }
  });

  it("keeps full-journey PNG export root independent of inspector", () => {
    renderWorkspace(buildFixture13Scenes());
    const fullRoot = screen.getByTestId("journey-export-full-root");
    expect(
      within(fullRoot).getByTestId("journey-curve-container-full-export").getAttribute("data-export-full"),
    ).toBe("true");
    expect(within(fullRoot).getByTestId("journey-curve-svg-full-export").getAttribute("height")).toBe(
      "420",
    );
  });

  it("contains no book/chapter/run hardcoding in visualization config", async () => {
    const mod = await import("./journeyVisualizationConfig");
    const source = JSON.stringify(mod);
    expect(source).not.toMatch(/book_id|chapter_id|run_id|Book #1|Run #5/i);
  });
});
