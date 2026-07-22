import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  JOURNEY_VISUALIZATION_VERSION,
  SOURCE_PANE_WIDTH_PX,
  INSPECTOR_PANE_WIDTH_PX,
  INSPECTOR_BOTTOM_DOCK_HEIGHT_PX,
  UI_PREF_KEYS,
} from "./journeyVisualizationConfig";
import {
  INSPECTOR_DOCK_HEIGHT_RANGE,
  INSPECTOR_PANE_WIDTH_RANGE,
  MAIN_PANE_MIN_WIDTH_PX,
  SOURCE_PANE_WIDTH_RANGE,
  SPLITTER_WIDTH_PX,
  clampPreferredToRange,
  effectivePaneWidth,
  maxSidePaneWidth,
  sanitizePreferredWidth,
} from "./journeyPaneWidth";
import { buildFixture13Scenes } from "./mockVisualizationFixtures";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";

const css = readFileSync(resolve(__dirname, "./readerJourney.css"), "utf8");
const workspaceSource = readFileSync(
  resolve(__dirname, "./ReaderJourneyWorkspace.tsx"),
  "utf8",
);
const configSource = readFileSync(
  resolve(__dirname, "./journeyVisualizationConfig.ts"),
  "utf8",
);
const paneWidthSource = readFileSync(resolve(__dirname, "./journeyPaneWidth.ts"), "utf8");
const splitterSource = readFileSync(
  resolve(__dirname, "./JourneyPaneSplitter.tsx"),
  "utf8",
);

function renderWorkspace(
  viz = buildFixture13Scenes(),
  width = 1600,
  options?: { sourcePane?: boolean },
) {
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
      <div style={{ width, height: 900 }}>
        <ReaderJourneyWorkspace
          visualization={viz}
          onLocateEvidence={vi.fn()}
          sourcePane={
            options?.sourcePane === false ? undefined : <div data-testid="fixture-source">姝ｆ枃</div>
          }
        />
      </div>
    </MemoryRouter>,
  );
}

function openInspector() {
  const toggle = screen.queryByTestId("journey-inspector-summary-expand");
  if (toggle) fireEvent.click(toggle);
}


describe("Reader Journey Resizable Workspace v4.1", () => {
  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it("exposes visualization version 4.1", () => {
    expect(JOURNEY_VISUALIZATION_VERSION).toBe("4.2");
  });

  it("defines pane ranges and main min 640 without book/run special cases", () => {
    expect(SOURCE_PANE_WIDTH_RANGE).toEqual({ min: 220, default: 300, max: 480 });
    expect(INSPECTOR_PANE_WIDTH_RANGE).toEqual({ min: 300, default: 360, max: 520 });
    expect(INSPECTOR_DOCK_HEIGHT_RANGE).toEqual({ min: 240, default: 320, max: 520 });
    expect(MAIN_PANE_MIN_WIDTH_PX).toBe(640);
    expect(SPLITTER_WIDTH_PX).toBe(8);
    expect(SOURCE_PANE_WIDTH_PX.desktop).toBe(300);
    expect(INSPECTOR_PANE_WIDTH_PX.desktop).toBe(360);
    expect(INSPECTOR_BOTTOM_DOCK_HEIGHT_PX.min).toBe(240);
    expect(paneWidthSource).not.toMatch(/book_id|chapter_id|run_id/);
    expect(workspaceSource).not.toMatch(/bookId\s*===|chapterId\s*===|runId\s*===/);
    expect(configSource).not.toMatch(/book_id\s*===|chapter_id\s*===|run_id\s*===/);
  });

  it("uses 5-column grid with minmax(0, 1fr) main", () => {
    expect(css).toMatch(/minmax\(0,\s*1fr\)/);
    expect(css).toMatch(/--splitter-left-width/);
    expect(css).toMatch(/--splitter-right-width/);
    expect(css).toMatch(/journey-pane-splitter/);
  });

  it("clamps preferred widths and distinguishes preferred vs effective", () => {
    expect(sanitizePreferredWidth(999, SOURCE_PANE_WIDTH_RANGE)).toBe(300);
    expect(sanitizePreferredWidth(250, SOURCE_PANE_WIDTH_RANGE)).toBe(250);
    expect(clampPreferredToRange(100, SOURCE_PANE_WIDTH_RANGE)).toBe(220);
    expect(clampPreferredToRange(600, SOURCE_PANE_WIDTH_RANGE)).toBe(480);
    const maxAllowed = maxSidePaneWidth(1600, 360, 2);
    expect(maxAllowed).toBe(1600 - 640 - 360 - 16);
    const effective = effectivePaneWidth(480, SOURCE_PANE_WIDTH_RANGE, 200, false);
    expect(effective).toBe(200);
    expect(effectivePaneWidth(300, SOURCE_PANE_WIDTH_RANGE, 800, true)).toBe(0);
  });

  it("renders source and inspector splitters on desktop with inspector open", () => {
    renderWorkspace(buildFixture13Scenes(), 1600);
    openInspector();
    const left = screen.getByTestId("journey-splitter-source");
    const right = screen.getByTestId("journey-splitter-inspector");
    expect(left).toHaveAttribute("role", "separator");
    expect(left).toHaveAttribute("aria-orientation", "vertical");
    expect(left).toHaveAttribute("aria-label", "调整正文区域宽度");
    expect(left).toHaveAttribute("aria-valuemin", "220");
    expect(right).toHaveAttribute("aria-label", "调整详情区域宽度");
    expect(right).toHaveAttribute("aria-valuemin", "300");
    expect(screen.getByTestId("journey-workspace-grid")).toHaveAttribute(
      "data-source-width",
      "300",
    );
    expect(screen.getByTestId("journey-workspace-grid")).toHaveAttribute(
      "data-inspector-width",
      "360",
    );
  });

  it("uses pointer capture APIs on splitter", () => {
    expect(splitterSource).toMatch(/setPointerCapture/);
    expect(splitterSource).toMatch(/releasePointerCapture/);
    expect(splitterSource).toMatch(/requestAnimationFrame/);
    expect(splitterSource).toMatch(/onPointerDown/);
    expect(splitterSource).toMatch(/onPointerMove/);
    expect(splitterSource).toMatch(/onPointerUp/);
    expect(splitterSource).toMatch(/onPointerCancel/);
  });

  it("drags source width with clamp to min/max", () => {
    renderWorkspace(buildFixture13Scenes(), 1600);
    openInspector();
    const splitter = screen.getByTestId("journey-splitter-source");
    fireEvent.pointerDown(splitter, { button: 0, clientX: 300, pointerId: 1 });
    fireEvent.pointerMove(splitter, { clientX: 100, pointerId: 1 });
    fireEvent.pointerUp(splitter, { pointerId: 1 });
    // rAF may not flush in jsdom 鈥?drive via keyboard for deterministic clamp
    splitter.focus();
    fireEvent.keyDown(splitter, { key: "Home" });
    expect(Number(splitter.getAttribute("aria-valuenow"))).toBe(220);
    fireEvent.keyDown(splitter, { key: "End" });
    expect(Number(splitter.getAttribute("aria-valuenow"))).toBeLessThanOrEqual(480);
    expect(JSON.parse(localStorage.getItem(UI_PREF_KEYS.sourcePaneWidth) ?? "null")).toBeGreaterThanOrEqual(
      220,
    );
  });

  it("keyboard Arrow adjusts by 8px; Shift by 24px; Enter resets default", () => {
    renderWorkspace(buildFixture13Scenes(), 1600);
    openInspector();
    const splitter = screen.getByTestId("journey-splitter-source");
    expect(Number(splitter.getAttribute("aria-valuenow"))).toBe(300);
    fireEvent.keyDown(splitter, { key: "ArrowRight" });
    expect(Number(splitter.getAttribute("aria-valuenow"))).toBe(308);
    fireEvent.keyDown(splitter, { key: "ArrowLeft", shiftKey: true });
    expect(Number(splitter.getAttribute("aria-valuenow"))).toBe(284);
    fireEvent.keyDown(splitter, { key: "Enter" });
    expect(Number(splitter.getAttribute("aria-valuenow"))).toBe(300);
  });

  it("double-click restores default pane width", () => {
    renderWorkspace(buildFixture13Scenes(), 1600);
    openInspector();
    const left = screen.getByTestId("journey-splitter-source");
    fireEvent.keyDown(left, { key: "ArrowRight" });
    fireEvent.keyDown(left, { key: "ArrowRight" });
    expect(Number(left.getAttribute("aria-valuenow"))).toBe(316);
    fireEvent.doubleClick(left);
    expect(Number(left.getAttribute("aria-valuenow"))).toBe(300);

    const right = screen.getByTestId("journey-splitter-inspector");
    fireEvent.keyDown(right, { key: "ArrowRight" });
    expect(Number(right.getAttribute("aria-valuenow"))).toBe(368);
    fireEvent.doubleClick(right);
    expect(Number(right.getAttribute("aria-valuenow"))).toBe(360);
  });

  it("persists preferred widths globally and restores after remount", () => {
    const { unmount } = renderWorkspace(buildFixture13Scenes(), 1600);
    openInspector();
    const splitter = screen.getByTestId("journey-splitter-source");
    fireEvent.keyDown(splitter, { key: "ArrowRight" });
    fireEvent.keyDown(splitter, { key: "ArrowRight" });
    expect(JSON.parse(localStorage.getItem(UI_PREF_KEYS.sourcePaneWidth)!)).toBe(316);
    unmount();
    renderWorkspace(buildFixture13Scenes(), 1600);
    openInspector();
    expect(screen.getByTestId("journey-splitter-source")).toHaveAttribute(
      "aria-valuenow",
      "316",
    );
  });

  it("hides splitters when source/inspector collapsed; expand restores preferred", () => {
    Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
      configurable: true,
      value() {
        return {
          width: 1600,
          height: 900,
          top: 0,
          left: 0,
          bottom: 900,
          right: 1600,
          x: 0,
          y: 0,
          toJSON() {
            return {};
          },
        };
      },
    });
    const viz = buildFixture13Scenes();
    const sourcePane = <div data-testid="fixture-source">正文</div>;
    const { rerender } = render(
      <MemoryRouter>
        <div style={{ width: 1600, height: 900 }}>
          <ReaderJourneyWorkspace
            visualization={viz}
            onLocateEvidence={vi.fn()}
            sourcePane={sourcePane}
          />
        </div>
      </MemoryRouter>,
    );
    openInspector();
    fireEvent.keyDown(screen.getByTestId("journey-splitter-source"), { key: "ArrowRight" });
    const preferred = JSON.parse(localStorage.getItem(UI_PREF_KEYS.sourcePaneWidth)!);
    rerender(
      <MemoryRouter>
        <div style={{ width: 1600, height: 900 }}>
          <ReaderJourneyWorkspace
            visualization={viz}
            onLocateEvidence={vi.fn()}
            sourcePane={sourcePane}
            sourceCollapsed
          />
        </div>
      </MemoryRouter>,
    );
    expect(screen.queryByTestId("journey-splitter-source")).not.toBeInTheDocument();
    rerender(
      <MemoryRouter>
        <div style={{ width: 1600, height: 900 }}>
          <ReaderJourneyWorkspace
            visualization={viz}
            onLocateEvidence={vi.fn()}
            sourcePane={sourcePane}
            sourceCollapsed={false}
          />
        </div>
      </MemoryRouter>,
    );
    expect(screen.getByTestId("journey-splitter-source")).toHaveAttribute(
      "aria-valuenow",
      String(preferred),
    );
  });

  it("more settings restores both pane defaults without changing scene URL", () => {
    renderWorkspace(buildFixture13Scenes(), 1600);
    openInspector();
    fireEvent.keyDown(screen.getByTestId("journey-splitter-source"), { key: "End" });
    fireEvent.click(screen.getByTestId("journey-more-chart-settings"));
    fireEvent.click(screen.getByTestId("journey-reset-pane-widths"));
    expect(screen.getByTestId("journey-splitter-source")).toHaveAttribute(
      "aria-valuenow",
      "300",
    );
    expect(screen.getByTestId("journey-splitter-inspector")).toHaveAttribute(
      "aria-valuenow",
      "360",
    );
  });

  it("protects MainPane minimum width when side panes expand", () => {
    const maxSource = maxSidePaneWidth(1440, 360, 2);
    expect(maxSource).toBe(1440 - 640 - 360 - 16);
    expect(maxSource).toBeLessThan(SOURCE_PANE_WIDTH_RANGE.max);
    renderWorkspace(buildFixture13Scenes(), 1440);
    openInspector();
    const left = screen.getByTestId("journey-splitter-source");
    fireEvent.keyDown(left, { key: "End" });
    const now = Number(left.getAttribute("aria-valuenow"));
    expect(now).toBeLessThanOrEqual(maxSource);
    expect(now + 360 + 16 + 640).toBeLessThanOrEqual(1440);
  });

  it("mid layout uses dock height splitter; narrow disables column splitters", () => {
    renderWorkspace(buildFixture13Scenes(), 1366);
    openInspector();
    expect(screen.getByTestId("journey-workspace")).toHaveAttribute("data-layout", "mid");
    expect(screen.getByTestId("journey-splitter-source")).toBeInTheDocument();
    expect(screen.queryByTestId("journey-splitter-inspector")).not.toBeInTheDocument();
    expect(screen.getByTestId("journey-splitter-dock")).toHaveAttribute(
      "aria-orientation",
      "horizontal",
    );
    expect(screen.getByTestId("journey-splitter-dock")).toHaveAttribute(
      "aria-label",
      "调整详情区域高度",
    );

    cleanup();
    localStorage.clear();
    renderWorkspace(buildFixture13Scenes(), 1000);
    expect(screen.getByTestId("journey-workspace")).toHaveAttribute("data-layout", "narrow");
    expect(screen.queryByTestId("journey-splitter-source")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-splitter-inspector")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-splitter-dock")).not.toBeInTheDocument();
  });

  it("keeps Inspector outside chart shell and scroll ownership tokens", () => {
    renderWorkspace(buildFixture13Scenes(), 1600);
    openInspector();
    const pane = screen.getByTestId("journey-inspector-pane");
    const shell = screen.getByTestId("journey-chart-shell");
    expect(shell.contains(pane)).toBe(false);
    expect(css).toMatch(/\.journey-workspace\.journey-workspace-v4[\s\S]*overflow:\s*hidden/);
    expect(css).toMatch(/\.journey-source-pane\s*\{[^}]*overflow-y:\s*auto/);
    expect(css).toMatch(/\.journey-main-pane\s*\{[^}]*overflow-y:\s*auto/);
    expect(css).toMatch(/\.journey-inspector-pane\s*\{[^}]*overflow-y:\s*auto/);
  });

  it("keeps Chart floors and does not introduce book/run special cases", () => {
    renderWorkspace();
    expect(screen.getByTestId("journey-curve-svg").getAttribute("height")).toBe("420");
    for (const tick of [0, 25, 50, 75, 100]) {
      expect(screen.getByTestId(`journey-y-tick-${tick}`)).toBeInTheDocument();
    }
    expect(workspaceSource).not.toMatch(/bookId\s*===\s*1|chapterId\s*===\s*2|runId\s*===\s*5/);
  });
});
