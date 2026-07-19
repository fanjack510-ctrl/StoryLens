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
const panelSource = readFileSync(resolve(__dirname, "./MetricSelectorPanel.tsx"), "utf8");
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

  it("opens MetricSelectorPanel in document flow below toolbar", () => {
    renderWorkspace();
    expect(screen.queryByTestId("journey-metric-select-menu")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("journey-metric-select"));
    const panel = screen.getByTestId("journey-metric-select-menu");
    expect(panel).toHaveAttribute("data-metric-panel", "in-flow");
    expect(panel).toHaveAttribute("role", "listbox");
    expect(panel).toHaveAttribute("aria-label", "选择当前指标");
    const region = screen.getByTestId("journey-toolbar-region");
    expect(region.contains(panel)).toBe(true);
    expect(screen.getByTestId("journey-metric-select")).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByTestId("journey-metric-select")).toHaveAttribute(
      "aria-haspopup",
      "listbox",
    );
    // Not a fixed/absolute overlay in CSS or panel styles
    const style = window.getComputedStyle(panel);
    expect(style.position === "static" || style.position === "" || style.position === "relative").toBe(
      true,
    );
    expect(css).toMatch(/\.journey-metric-selector-panel\s*\{[^}]*position:\s*static/s);
    expect(panelSource).toMatch(/role="listbox"/);
    expect(panelSource).toMatch(/data-metric-panel="in-flow"/);
  });

  it("pushes Phase and Chart below the open panel in DOM order", () => {
    renderWorkspace();
    fireEvent.click(screen.getByTestId("journey-metric-select"));
    const region = screen.getByTestId("journey-toolbar-region");
    const phase = screen.getByTestId("journey-phase-strip-wrap");
    const chart = screen.getByTestId("journey-chart-shell");
    const panel = screen.getByTestId("journey-metric-select-menu");
    expect(
      region.compareDocumentPosition(phase) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      panel.compareDocumentPosition(phase) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      phase.compareDocumentPosition(chart) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("does not use absolute overlay for metric options", () => {
    expect(toolbarSource).toMatch(/MetricSelectorPanel/);
    expect(toolbarSource).not.toMatch(/JourneyAnchoredMenu[\s\S]*journey-metric/);
    expect(css).toMatch(/\.journey-metric-selector-panel\s*\{[^}]*position:\s*static/s);
    expect(css).not.toMatch(/\.journey-metric-selector-panel\s*\{[^}]*position:\s*(absolute|fixed)/s);
  });

  it("selects metric, closes panel, keeps scene, and shows full Chinese labels", async () => {
    renderWorkspace();
    const sceneBefore = screen.getByTestId("journey-metric-select").getAttribute("data-current-metric");
    expect(sceneBefore).toBe("engagement");
    fireEvent.click(screen.getByTestId("journey-metric-select"));
    const menu = screen.getByTestId("journey-metric-select-menu");
    for (const key of ALL_METRIC_KEYS) {
      const opt = within(menu).getByTestId(`journey-metric-${key}`);
      expect(opt).toHaveAttribute("role", "option");
      expect(opt).toHaveTextContent(METRIC_LABELS_ZH[key]);
    }
    fireEvent.click(within(menu).getByTestId("journey-metric-hook"));
    expect(screen.queryByTestId("journey-metric-select-menu")).not.toBeInTheDocument();
    expect(screen.getByTestId("journey-metric-select")).toHaveAttribute(
      "data-current-metric",
      "hook",
    );
    expect(screen.getByTestId("journey-metric-select")).toHaveTextContent("钩子");
    expect(screen.getByTestId("journey-metric-select")).toHaveAttribute("aria-expanded", "false");
    // Scene URL param preserved; chart nodes still present
    expect(screen.getByTestId("journey-curve-node-3")).toBeInTheDocument();
    expect(screen.getByTestId("journey-rhythm-dot-3")).toBeInTheDocument();
  });

  it("closes on Escape and outside click", () => {
    renderWorkspace();
    fireEvent.click(screen.getByTestId("journey-metric-select"));
    expect(screen.getByTestId("journey-metric-select-menu")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByTestId("journey-metric-select-menu")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("journey-metric-select"));
    expect(screen.getByTestId("journey-metric-select-menu")).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByTestId("journey-phase-strip"));
    expect(screen.queryByTestId("journey-metric-select-menu")).not.toBeInTheDocument();
  });

  it("supports keyboard listbox selection", () => {
    renderWorkspace();
    fireEvent.click(screen.getByTestId("journey-metric-select"));
    const selected = screen.getByTestId("journey-metric-engagement");
    expect(selected).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(selected, { key: "ArrowRight" });
    const curiosity = screen.getByTestId("journey-metric-curiosity");
    fireEvent.keyDown(curiosity, { key: "Enter" });
    expect(screen.queryByTestId("journey-metric-select-menu")).not.toBeInTheDocument();
    expect(screen.getByTestId("journey-metric-select")).toHaveAttribute(
      "data-current-metric",
      "curiosity",
    );
  });

  it("keeps splitter widths and inspector state when opening metric panel", () => {
    renderWorkspace(buildFixture13Scenes(), 1600);
    const expand = screen.queryByTestId("journey-inspector-summary-expand");
    if (expand) fireEvent.click(expand);
    const grid = screen.getByTestId("journey-workspace-grid");
    const sourceW = grid.getAttribute("data-source-width");
    const inspectorW = grid.getAttribute("data-inspector-width");
    fireEvent.click(screen.getByTestId("journey-metric-select"));
    expect(screen.getByTestId("journey-metric-select-menu")).toBeInTheDocument();
    expect(grid.getAttribute("data-source-width")).toBe(sourceW);
    expect(grid.getAttribute("data-inspector-width")).toBe(inspectorW);
    expect(screen.getByTestId("journey-workspace")).toHaveAttribute(
      "data-inspector-collapsed",
      "false",
    );
  });

  it("uses SharedPopover via overlay-root for 更多设置 with z-index token 40", () => {
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
    expect(panelSource).not.toMatch(/book_id|chapter_id|run_id|bookId|chapterId|runId/);
    expect(toolbarSource).not.toMatch(/book_id\s*===|chapter_id\s*===|run_id\s*===/);
    expect(workspaceSource).not.toMatch(/MetricSelector[\s\S]{0,80}bookId\s*===/);
  });

  it("shows current metric on trigger as 当前指标 · label", () => {
    renderWorkspace();
    const trigger = screen.getByTestId("journey-metric-select");
    expect(trigger).toHaveTextContent("当前指标");
    expect(trigger).toHaveTextContent("阅读牵引");
    expect(trigger.textContent).toMatch(/当前指标\s*·\s*阅读牵引/);
  });

  it("uses full-width narrow panel styles without floating mini-menu", () => {
    expect(css).toMatch(/\.journey-metric-selector-panel\.is-narrow/);
    expect(css).toMatch(/grid-template-columns:\s*1fr/);
    expect(panelSource).toMatch(/narrow/);
  });
});
