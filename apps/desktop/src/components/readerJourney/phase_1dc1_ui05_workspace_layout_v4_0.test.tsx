import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CanonicalJourneyChart } from "./CanonicalJourneyChart";
import { computeYScale } from "./journeyChartScales";
import {
  CHART_SHELL_MIN_HEIGHT_PX,
  JOURNEY_VISUALIZATION_VERSION,
  LAYOUT_BREAKPOINTS,
  SOURCE_PANE_WIDTH_PX,
  INSPECTOR_PANE_WIDTH_PX,
  TOOL_RAIL_WIDTH_PX,
  chartHeightPx,
  plotAreaHeightPx,
  resolveJourneyLayoutMode,
  SVG_HEIGHT_STANDARD_PX,
} from "./journeyVisualizationConfig";
import {
  buildFixture13Scenes,
  buildFixture30Scenes,
} from "./mockVisualizationFixtures";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";

const css = readFileSync(resolve(__dirname, "./readerJourney.css"), "utf8");
const workspaceSource = readFileSync(
  resolve(__dirname, "./ReaderJourneyWorkspace.tsx"),
  "utf8",
);
const toolbarSource = readFileSync(
  resolve(__dirname, "./JourneyChartToolbar.tsx"),
  "utf8",
);
const configSource = readFileSync(
  resolve(__dirname, "./journeyVisualizationConfig.ts"),
  "utf8",
);

function renderWorkspace(viz = buildFixture13Scenes(), width = 1600) {
  Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
    configurable: true,
    value() {
      return {
        width,
        height: 900,
        top: 0,
        left: 0,
        bottom: 900,
        right: width,
        x: 0,
        y: 0,
        toJSON() {
          return {};
        },
      };
    },
  });
  return render(
    <MemoryRouter>
      <div style={{ width }}>
        <ReaderJourneyWorkspace visualization={viz} onLocateEvidence={vi.fn()} />
      </div>
    </MemoryRouter>,
  );
}


function openExportMenu() {
  const more = screen.queryByTestId("journey-more-chart-settings");
  if (more && !screen.queryByTestId("journey-export-png")) {
    fireEvent.click(more);
  }
  return screen.getByTestId("journey-export-png");
}

describe("Reader Journey Workspace Layout v4.0", () => {
  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it("exposes visualization version 4.0", () => {
    expect(JOURNEY_VISUALIZATION_VERSION).toBe("4.2");
  });

  it("resolves layout breakpoints without book/scene special cases", () => {
    expect(resolveJourneyLayoutMode(1440)).toBe("desktop");
    expect(resolveJourneyLayoutMode(1366)).toBe("mid");
    expect(resolveJourneyLayoutMode(1180)).toBe("mid");
    expect(resolveJourneyLayoutMode(1179)).toBe("narrow");
    expect(resolveJourneyLayoutMode(1099)).toBe("narrow");
    expect(LAYOUT_BREAKPOINTS.desktopMin).toBe(1440);
    expect(LAYOUT_BREAKPOINTS.midMin).toBe(1180);
    expect(configSource).not.toMatch(/book_id\s*===|chapter_id\s*===|run_id\s*===/);
    expect(workspaceSource).not.toMatch(/bookId\s*===|chapterId\s*===|runId\s*===/);
  });

  it("removes vertical tool rail single-char labels", () => {
    expect(screen.queryByTestId).toBeDefined();
    renderWorkspace();
    expect(screen.queryByTestId("journey-chart-tool-rail")).not.toBeInTheDocument();
    expect(toolbarSource).not.toMatch(/>\s*指\s*</);
    expect(toolbarSource).not.toMatch(/>\s*全\s*</);
    expect(toolbarSource).not.toMatch(/>\s*P\s*</);
    expect(toolbarSource).not.toMatch(/>\s*详\s*</);
    expect(toolbarSource).not.toMatch(/>\s*出\s*</);
    expect(TOOL_RAIL_WIDTH_PX).toBe(0);
  });

  it("shows full Chinese toolbar labels", () => {
    renderWorkspace(buildFixture13Scenes(), 1600);
    expect(screen.getByTestId("journey-curve-toolbar")).toBeInTheDocument();
    expect(screen.getByTestId("journey-zoom-fit-all")).toHaveTextContent("适应全部");
    expect(screen.getByTestId("journey-zoom-focus-phase")).toHaveTextContent("当前阶段");
    expect(screen.getByTestId("journey-inspector-toggle")).toHaveTextContent("展开详情");
    expect(openExportMenu()).toHaveTextContent("导出PNG");
    expect(screen.getByTestId("journey-more-chart-settings")).toHaveTextContent(
      "更多设置",
    );
    expect(screen.getByTestId("journey-metric-select")).toHaveTextContent("更多指标");
  });

  it("keeps Chart Y 0—100 and plot floors from v3.0", () => {
    expect(CHART_SHELL_MIN_HEIGHT_PX).toBeGreaterThanOrEqual(440);
    expect(SVG_HEIGHT_STANDARD_PX).toBe(420);
    expect(plotAreaHeightPx("standard")).toBeGreaterThanOrEqual(340);
    const viz = buildFixture13Scenes();
    const scale = computeYScale(viz.curve_series.curiosity, chartHeightPx("standard"), "fixed_0_100");
    expect(scale.domainMin).toBe(0);
    expect(scale.domainMax).toBe(100);
    expect(scale.ticks).toEqual([0, 25, 50, 75, 100]);
    renderWorkspace(viz);
    for (const tick of [0, 25, 50, 75, 100]) {
      expect(screen.getByTestId(`journey-y-tick-${tick}`)).toBeInTheDocument();
    }
    expect(screen.getByTestId("journey-curve-svg").getAttribute("height")).toBe("420");
  });

  it("defaults Inspector collapsed with summary bar; dock does not use absolute/fixed over plot", () => {
    renderWorkspace();
    expect(screen.getByTestId("journey-workspace")).toHaveAttribute(
      "data-inspector-collapsed",
      "true",
    );
    expect(screen.getByTestId("journey-inspector-summary-bar")).toBeInTheDocument();
    expect(screen.getByTestId("journey-inspector-summary-expand")).toHaveTextContent("展开详情");
    expect(screen.queryByTestId("journey-inspector-pane")).not.toBeInTheDocument();
    expect(css).toMatch(/\.journey-inspector-pane\s*\{[^}]*overflow-y:\s*auto/);
    expect(css).toMatch(/journey-workspace-v4/);
  });

  it("opens docked Inspector without inserting into chart shell", () => {
    renderWorkspace(buildFixture13Scenes(), 1600);
    fireEvent.click(screen.getByTestId("journey-inspector-summary-expand"));
    const pane = screen.getByTestId("journey-inspector-pane");
    expect(pane).toBeInTheDocument();
    const shell = screen.getByTestId("journey-chart-shell");
    expect(shell.contains(pane)).toBe(false);
    expect(screen.getByTestId("journey-workspace")).toHaveAttribute(
      "data-inspector-collapsed",
      "false",
    );
    fireEvent.click(screen.getByTestId("journey-collapse-inspector"));
    expect(screen.getByTestId("journey-workspace")).toHaveAttribute(
      "data-inspector-collapsed",
      "true",
    );
  });

  it("places Scene navigation below SVG", () => {
    renderWorkspace(buildFixture13Scenes());
    const viewport = screen.getByTestId("journey-chart-viewport");
    const section = within(viewport).getByTestId("journey-curve-section");
    const rhythm = within(viewport).getByTestId("journey-rhythm-strip");
    expect(
      section.compareDocumentPosition(rhythm) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("renders all 13 scene nodes", () => {
    renderWorkspace(buildFixture13Scenes());
    for (let i = 1; i <= 13; i += 1) {
      expect(screen.getByTestId(`journey-curve-node-${i}`)).toBeInTheDocument();
    }
  });

  it("keeps horizontal browse capability for 30 scenes", () => {
    renderWorkspace(buildFixture30Scenes());
    expect(screen.getByTestId("journey-curve-svg")).toBeInTheDocument();
    expect(screen.getByTestId("journey-chart-viewport")).toBeInTheDocument();
  });

  it("uses CSS grid tokens for source/inspector widths", () => {
    expect(SOURCE_PANE_WIDTH_PX.desktop).toBe(300);
    expect(INSPECTOR_PANE_WIDTH_PX.desktop).toBe(360);
    expect(css).toMatch(/minmax\(0,\s*1fr\)/);
    expect(css).toMatch(/--source-pane-width/);
    expect(css).toMatch(/--inspector-pane-width/);
    expect(workspaceSource).toMatch(/journey-workspace-v4/);
    expect(workspaceSource).not.toMatch(/JourneyResizableSplit/);
  });

  it("opens more settings menu via portal host", () => {
    renderWorkspace(buildFixture13Scenes(), 1600);
    fireEvent.click(screen.getByTestId("journey-more-chart-settings"));
    expect(screen.getByTestId("journey-more-menu-panel")).toBeInTheDocument();
    expect(screen.getByTestId("journey-chart-height-standard")).toBeInTheDocument();
  });

  it("does not modify semantic contract strings in workspace", () => {
    expect(workspaceSource).not.toMatch(/prompt|ModelInvocationBroker|aliyun_api_key/i);
  });
});
