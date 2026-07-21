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
  CHART_SHELL_MIN_HEIGHT_PX,
  JOURNEY_VISUALIZATION_VERSION,
  PLOT_AREA_HEIGHT_PRESETS,
  SVG_HEIGHT_STANDARD_PX,
  TOOL_RAIL_WIDTH_PX,
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
const configSource = readFileSync(
  resolve(__dirname, "./journeyVisualizationConfig.ts"),
  "utf8",
);
const workspaceSource = readFileSync(
  resolve(__dirname, "./ReaderJourneyWorkspace.tsx"),
  "utf8",
);
const chartSource = readFileSync(resolve(__dirname, "./CanonicalJourneyChart.tsx"), "utf8");

function renderWorkspace(viz = buildFixture13Scenes()) {
  return render(
    <MemoryRouter>
      <ReaderJourneyWorkspace visualization={viz} onLocateEvidence={vi.fn()} />
    </MemoryRouter>,
  );
}

function scoreFixture(scores: number[]) {
  const viz = buildFixture13Scenes();
  const nodes = viz.scene_nodes.slice(0, scores.length);
  const series = scores.map((value, i) => ({
    scene_ordinal: i + 1,
    value,
  }));
  return {
    ...viz,
    scene_nodes: nodes.map((n, i) => ({ ...n, scene_ordinal: i + 1 })),
    curve_series: Object.fromEntries(
      Object.keys(viz.curve_series).map((key) => [key, series]),
    ) as typeof viz.curve_series,
  };
}

describe("Reader Journey Visualization v3.0", () => {
  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it("exposes global visualization version 4.0 (supersedes v3.0 layout)", () => {
    expect(JOURNEY_VISUALIZATION_VERSION).toBe("4.2");
  });

  it("enforces desktop hard floors: shell>=440 svg=420 plot>=340", () => {
    expect(CHART_SHELL_MIN_HEIGHT_PX).toBeGreaterThanOrEqual(440);
    expect(SVG_HEIGHT_STANDARD_PX).toBe(420);
    expect(plotAreaHeightPx("standard")).toBeGreaterThanOrEqual(340);
    expect(chartHeightPx("standard")).toBe(420);
    expect(PLOT_AREA_HEIGHT_PRESETS.standard).toBe(352);
    expect(CHART_HEIGHT_PRESETS.standard).toBe(420);
    expect(TOOL_RAIL_WIDTH_PX).toBe(0);
  });

  it("keeps Y domain fixed 0鈥?00 with five ticks", () => {
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

  it.each([0, 10, 25, 50, 100])("renders score=%s node fully in DOM", (score) => {
    const viz = scoreFixture([score, 60, 80]);
    render(
      <CanonicalJourneyChart
        visualization={viz}
        metric="engagement"
        chartHeight={chartHeightPx("standard")}
        yDomainMode="fixed_0_100"
        viewStart={1}
        viewEnd={3}
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
    const node = screen.getByTestId("journey-curve-node-1");
    expect(node).toHaveAttribute("data-score", String(score));
    const cy = Number(node.querySelector("circle")?.getAttribute("cy"));
    const scale = computeYScale(viz.curve_series.engagement, chartHeightPx("standard"), "fixed_0_100");
    expect(cy).toBeCloseTo(scale.yForValue(score), 1);
    expect(cy).toBeGreaterThanOrEqual(CHART_PAD.top - 8);
    expect(cy).toBeLessThanOrEqual(chartHeightPx("standard") - CHART_PAD.bottom + 8);
  });

  it("defaults Inspector collapsed; chart shell and horizontal toolbar present", () => {
    renderWorkspace();
    expect(screen.getByTestId("journey-resizable-split")).toHaveAttribute(
      "data-inspector-collapsed",
      "true",
    );
    expect(screen.getByTestId("journey-inspector-summary-bar")).toBeInTheDocument();
    expect(screen.getByTestId("journey-chart-shell")).toBeInTheDocument();
    expect(screen.getByTestId("journey-chart-viewport")).toBeInTheDocument();
    expect(screen.getByTestId("journey-curve-toolbar")).toBeInTheDocument();
    expect(screen.queryByTestId("journey-chart-tool-rail")).not.toBeInTheDocument();
    expect(screen.getByTestId("journey-curve-svg").getAttribute("height")).toBe("420");
    expect(screen.getByTestId("journey-curve-section")).toHaveAttribute(
      "data-plot-area-height",
      String(plotAreaHeightPx("standard")),
    );
    expect(screen.getByTestId("journey-curve-container")).toHaveAttribute(
      "data-visualization-version",
      "4.2",
    );
    expect(screen.getByTestId("journey-curve-container")).toHaveAttribute(
      "data-clip-height",
      String(plotAreaHeightPx("standard")),
    );
  });

  it("places Scene navigation below SVG (not covering plot)", () => {
    renderWorkspace(buildFixture13Scenes());
    const viewport = screen.getByTestId("journey-chart-viewport");
    const section = within(viewport).getByTestId("journey-curve-section");
    const rhythm = within(viewport).getByTestId("journey-rhythm-strip");
    expect(
      section.compareDocumentPosition(rhythm) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("uses horizontal toolbar instead of vertical tool rail", () => {
    renderWorkspace();
    expect(screen.queryByTestId("journey-chart-tool-rail")).not.toBeInTheDocument();
    expect(screen.getByTestId("journey-curve-toolbar")).toBeInTheDocument();
    expect(screen.getByTestId("journey-zoom-fit-all")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("journey-more-chart-settings"));
    expect(screen.getByTestId("journey-export-png")).toBeInTheDocument();
    expect(css).toMatch(/\.journey-chart-tool-rail\s*\{[^}]*display:\s*none/);
  });

  it("hides zoom in/out for 鈮?5 scenes; shows for 30 under more settings", () => {
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

  it("keeps height / focus-data only in more settings", () => {
    renderWorkspace();
    expect(screen.queryByTestId("journey-chart-height-expanded")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("journey-more-chart-settings"));
    expect(screen.getByTestId("journey-chart-height-expanded")).toBeInTheDocument();
    expect(screen.getByTestId("journey-y-domain-focus")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("journey-chart-height-expanded"));
    expect(screen.getByTestId("journey-curve-svg").getAttribute("height")).toBe(
      String(chartHeightPx("expanded")),
    );
  });

  it("renders all 13 scene nodes; chart overflow-y is not scroll/auto", () => {
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
    expect(css).toMatch(/\.journey-chart-viewport[\s\S]*overflow-y:\s*hidden/);
  });

  it("clipPath height equals plotHeight in markup", () => {
    expect(chartSource).toMatch(/data-clip-height=\{plotHeight\}/);
    expect(chartSource).toMatch(/height=\{plotHeight\}/);
    renderWorkspace();
    const clip = document.querySelector("#journey-plot-clip rect");
    expect(clip).not.toBeNull();
    expect(clip?.getAttribute("height")).toBe(String(plotAreaHeightPx("standard")));
    expect(screen.getByTestId("journey-curve-container").getAttribute("data-clip-height")).toBe(
      String(plotAreaHeightPx("standard")),
    );
  });

  it("expands inspector without removing chart shell / plot height attrs", () => {
    renderWorkspace();
    const before = screen.getByTestId("journey-curve-svg").getAttribute("height");
    fireEvent.click(screen.getByTestId("journey-inspector-summary-expand"));
    expect(screen.getByTestId("journey-resizable-split")).toHaveAttribute(
      "data-inspector-collapsed",
      "false",
    );
    expect(screen.getByTestId("journey-curve-svg").getAttribute("height")).toBe(before);
    expect(screen.getByTestId("journey-chart-shell")).toBeInTheDocument();
    const collapse = screen.getAllByTestId("journey-collapse-inspector")[0];
    fireEvent.click(collapse);
    expect(screen.getByTestId("journey-resizable-split")).toHaveAttribute(
      "data-inspector-collapsed",
      "true",
    );
    expect(screen.getByTestId("journey-inspector-summary-bar")).toBeInTheDocument();
  });

  it("keeps metric switch on fixed 0鈥?00 and syncs node click to inspector", () => {
    renderWorkspace(buildFixture13Scenes());
    fireEvent.click(screen.getByTestId("journey-metric-select"));
    fireEvent.click(screen.getByTestId("journey-metric-curiosity"));
    expect(screen.getByTestId("journey-y-tick-0")).toBeInTheDocument();
    expect(screen.getByTestId("journey-y-tick-100")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("journey-curve-node-5"));
    expect(screen.getByTestId("journey-detail-pane")).toHaveAttribute("data-inspector", "scene");
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
      within(fullRoot)
        .getByTestId("journey-curve-container-full-export")
        .getAttribute("data-export-full"),
    ).toBe("true");
    expect(
      within(fullRoot).getByTestId("journey-curve-svg-full-export").getAttribute("height"),
    ).toBe("420");
  });

  it("contains no book/chapter/run hardcoding in visualization config or workspace", () => {
    expect(configSource).not.toMatch(/book_id|chapter_id|run_id|Book #1|Run #5|Chapter #2/i);
    expect(workspaceSource).not.toMatch(/Book #1|Chapter #2|Run #5|13 Scene鐗瑰垽/);
  });

  it("CSS does not force legacy short SVG height that crushed the plot", () => {
    expect(css).not.toMatch(/\.journey-curve-svg\s*\{[^}]*height:\s*260px\s*;/);
  });
});
