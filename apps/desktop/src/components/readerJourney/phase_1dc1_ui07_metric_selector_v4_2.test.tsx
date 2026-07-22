import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  JOURNEY_VISUALIZATION_VERSION,
  SVG_HEIGHT_STANDARD_PX,
  plotAreaHeightPx,
  chartHeightPx,
} from "./journeyVisualizationConfig";
import { JOURNEY_Z_INDEX } from "./journeyOverlayTokens";
import { ALL_METRIC_KEYS, METRIC_LABELS_ZH } from "./journeyUiLabels";
import { buildFixture13Scenes } from "./mockVisualizationFixtures";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { computeYScale } from "./journeyChartScales";

const css = readFileSync(resolve(__dirname, "./readerJourney.css"), "utf8");
const toolbarSource = readFileSync(resolve(__dirname, "./JourneyChartToolbar.tsx"), "utf8");
const popoverSource = readFileSync(resolve(__dirname, "./JourneyPopover.tsx"), "utf8");
const workspaceSource = readFileSync(
  resolve(__dirname, "./ReaderJourneyWorkspace.tsx"),
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
    <MemoryRouter initialEntries={["/?overview=curve&scene=3&metric=engagement"]}>
      <div style={{ width, height: 900 }}>
        <ReaderJourneyWorkspace
          visualization={viz}
          onLocateEvidence={vi.fn()}
          sourcePane={<div data-testid="fixture-source">正文</div>}
        />
      </div>
    </MemoryRouter>,
  );
}


describe("Reader Journey Metric Selector Overlay System v4.2", () => {
  afterEach(() => {
    cleanup();
    document.getElementById("journey-overlay-root")?.remove();
  });

  it("exposes visualization version 4.2", () => {
    expect(JOURNEY_VISUALIZATION_VERSION).toBe("4.2");
  });

  it("opens metric options as a compact popover dropdown", () => {
    renderWorkspace();
    expect(screen.queryByTestId("journey-metric-select-menu-panel")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("journey-metric-select"));
    const panel = screen.getByTestId("journey-metric-select-menu-panel");
    expect(panel).toBeInTheDocument();
    expect(screen.getByTestId("journey-metric-selector-list")).toHaveAttribute(
      "data-metric-panel",
      "popover",
    );
    expect(screen.getByTestId("journey-metric-selector-list")).toHaveAttribute("role", "listbox");
    expect(screen.getByTestId("journey-metric-select")).toHaveAttribute("aria-expanded", "true");
    expect(document.getElementById("journey-overlay-root")?.contains(panel)).toBe(true);
    expect(toolbarSource).toMatch(/JourneyPopover/);
    expect(toolbarSource).not.toMatch(/MetricSelectorPanel/);
  });

  it("does not mount a wide in-flow metric grid under the toolbar", () => {
    renderWorkspace();
    fireEvent.click(screen.getByTestId("journey-metric-select"));
    expect(screen.queryByTestId("journey-metric-selector-grid")).not.toBeInTheDocument();
    expect(toolbarSource).not.toMatch(/阅读牵引[\s\S]{0,40}情绪/);
  });

  it("selects metric, closes menu, keeps scene, and shows full Chinese labels", async () => {
    renderWorkspace();
    expect(screen.getByTestId("journey-metric-select")).toHaveAttribute(
      "data-current-metric",
      "engagement",
    );
    fireEvent.click(screen.getByTestId("journey-metric-select"));
    const menu = screen.getByTestId("journey-metric-select-menu-panel");
    for (const key of ALL_METRIC_KEYS) {
      const opt = within(menu).getByTestId(`journey-metric-${key}`);
      expect(opt).toHaveAttribute("role", "option");
      expect(opt).toHaveTextContent(METRIC_LABELS_ZH[key]);
    }
    fireEvent.click(within(menu).getByTestId("journey-metric-hook"));
    expect(screen.queryByTestId("journey-metric-select-menu-panel")).not.toBeInTheDocument();
    expect(screen.getByTestId("journey-metric-select")).toHaveAttribute(
      "data-current-metric",
      "hook",
    );
    expect(screen.getByTestId("journey-metric-select")).toHaveTextContent("钩子强度");
    expect(screen.getByTestId("journey-metric-select")).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByTestId("journey-curve-node-3")).toBeInTheDocument();
    expect(screen.getByTestId("journey-rhythm-dot-3")).toBeInTheDocument();
  });

  it("closes on Escape and outside click", () => {
    renderWorkspace();
    fireEvent.click(screen.getByTestId("journey-metric-select"));
    expect(screen.getByTestId("journey-metric-select-menu-panel")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByTestId("journey-metric-select-menu-panel")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("journey-metric-select"));
    expect(screen.getByTestId("journey-metric-select-menu-panel")).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByTestId("journey-phase-strip"));
    expect(screen.queryByTestId("journey-metric-select-menu-panel")).not.toBeInTheDocument();
  });

  it("supports option click selection from popover list", () => {
    renderWorkspace();
    fireEvent.click(screen.getByTestId("journey-metric-select"));
    fireEvent.click(screen.getByTestId("journey-metric-curiosity"));
    expect(screen.queryByTestId("journey-metric-select-menu-panel")).not.toBeInTheDocument();
    expect(screen.getByTestId("journey-metric-select")).toHaveAttribute(
      "data-current-metric",
      "curiosity",
    );
  });

  it("keeps splitter widths and inspector state when opening metric menu", () => {
    renderWorkspace(buildFixture13Scenes(), 1600);
    const expand = screen.queryByTestId("journey-inspector-summary-expand");
    if (expand) fireEvent.click(expand);
    const grid = screen.getByTestId("journey-workspace-grid");
    const sourceW = grid.getAttribute("data-source-width");
    const inspectorW = grid.getAttribute("data-inspector-width");
    fireEvent.click(screen.getByTestId("journey-metric-select"));
    expect(screen.getByTestId("journey-metric-select-menu-panel")).toBeInTheDocument();
    expect(grid.getAttribute("data-source-width")).toBe(sourceW);
    expect(grid.getAttribute("data-inspector-width")).toBe(inspectorW);
    expect(screen.getByTestId("journey-workspace")).toHaveAttribute(
      "data-inspector-collapsed",
      "false",
    );
  });

  it("uses SharedPopover via overlay-root for 更多操作 with z-index token 40", () => {
    expect(JOURNEY_Z_INDEX.popoverMenu).toBe(40);
    expect(JOURNEY_Z_INDEX.chartTooltip).toBe(50);
    expect(JOURNEY_Z_INDEX.modalDialog).toBe(100);
    expect(popoverSource).toMatch(/getJourneyOverlayRoot/);
    expect(popoverSource).toMatch(/JOURNEY_Z_INDEX\.popoverMenu/);
    expect(css).toMatch(/--journey-z-popover:\s*40/);
    expect(css).not.toMatch(/z-index:\s*9999/);
    renderWorkspace();
    fireEvent.click(screen.getByTestId("journey-more-chart-settings"));
    expect(screen.getByTestId("journey-more-menu-panel")).toBeInTheDocument();
    expect(document.getElementById("journey-overlay-root")).toBeTruthy();
    const panel = screen.getByTestId("journey-more-menu-panel");
    expect(document.getElementById("journey-overlay-root")?.contains(panel)).toBe(true);
    expect(within(panel).getByTestId("journey-export-png")).toHaveTextContent("导出 PNG");
    expect(within(panel).getByTestId("journey-chart-height-controls")).toBeInTheDocument();
    expect(within(panel).getByTestId("journey-y-domain-fixed")).toHaveTextContent("固定 0—100");
    expect(within(panel).getByTestId("journey-y-domain-focus")).toHaveTextContent("聚焦数据");
    expect(within(panel).getByTestId("journey-zoom-reset")).toHaveTextContent("恢复默认");
    expect(within(panel).getByTestId("journey-reset-pane-widths")).toHaveTextContent(
      "恢复默认栏宽",
    );
  });

  it("preserves chart Y 0—100 and plot floors", () => {
    expect(SVG_HEIGHT_STANDARD_PX).toBe(420);
    expect(plotAreaHeightPx("standard")).toBe(352);
    const viz = buildFixture13Scenes();
    const scale = computeYScale(
      viz.curve_series.curiosity,
      chartHeightPx("standard"),
      "fixed_0_100",
    );
    expect(scale.domainMin).toBe(0);
    expect(scale.domainMax).toBe(100);
    renderWorkspace(viz);
    fireEvent.click(screen.getByTestId("journey-metric-select"));
    expect(screen.getByTestId("journey-curve-svg").getAttribute("height")).toBe("420");
    for (const tick of [0, 25, 50, 75, 100]) {
      expect(screen.getByTestId(`journey-y-tick-${tick}`)).toBeInTheDocument();
    }
  });

  it("hides metric panel during PNG export class", () => {
    expect(css).toMatch(
      /\.journey-workspace\.journey-exporting\s+\.journey-metric-selector-panel[\s\S]*display:\s*none/,
    );
  });

  it("has no book/chapter/run special cases in metric selector sources", () => {
    expect(toolbarSource).not.toMatch(/book_id\s*===|chapter_id\s*===|run_id\s*===/);
    expect(workspaceSource).not.toMatch(/MetricSelector[\s\S]{0,80}bookId\s*===/);
  });

  it("shows current metric on trigger as 指标 · label", () => {
    renderWorkspace();
    const trigger = screen.getByTestId("journey-metric-select");
    expect(trigger).toHaveTextContent("指标");
    expect(trigger).toHaveTextContent("阅读牵引");
    expect(trigger.textContent).toMatch(/指标\s*：\s*阅读牵引/);
  });

  it("does not show source expand/collapse on the journey toolbar", () => {
    renderWorkspace();
    expect(screen.queryByTestId("journey-source-toggle")).not.toBeInTheDocument();
    expect(toolbarSource).not.toMatch(/收起正文|展开正文/);
  });
});
