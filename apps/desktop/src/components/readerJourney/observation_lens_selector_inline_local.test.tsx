/**
 * Local Vitest: Reader Journey lens selector is inline (no overlay dropdown).
 * Covers selection, selected state, and non-overlap layout at key widths.
 */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { buildFixture13Scenes } from "./mockVisualizationFixtures";
import { OBSERVATION_LENSES, getObservationLensHint } from "./observationLenses";

const toolbarSource = readFileSync(resolve(__dirname, "./JourneyChartToolbar.tsx"), "utf8");
const css = readFileSync(resolve(__dirname, "./readerJourney.css"), "utf8");

function rect(top: number, left: number, width: number, height: number) {
  return {
    top,
    left,
    width,
    height,
    bottom: top + height,
    right: left + width,
    x: left,
    y: top,
    toJSON() {
      return {};
    },
  };
}

function overlaps(
  a: { top: number; left: number; bottom: number; right: number },
  b: { top: number; left: number; bottom: number; right: number },
) {
  return !(a.bottom <= b.top || a.top >= b.bottom || a.right <= b.left || a.left >= b.right);
}

function renderAtWidth(width: number) {
  Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
    configurable: true,
    value(this: HTMLElement) {
      const testId = this.getAttribute("data-testid") || "";
      if (testId === "journey-lens-select-menu" || testId === "journey-lens-selector-list") {
        return rect(40, 8, Math.min(width - 200, 720), 40);
      }
      if (testId === "journey-toolbar-region" || testId === "journey-curve-toolbar") {
        return rect(8, 8, width - 16, 48);
      }
      if (testId === "journey-toolbar-right") {
        return rect(12, width - 220, 200, 40);
      }
      if (testId === "journey-phase-strip" || testId === "journey-phase-strip-wrap") {
        return rect(130, 8, width - 16, 110);
      }
      if (testId === "journey-chart-shell" || testId === "journey-curve-svg") {
        return rect(260, 8, width - 16, 360);
      }
      if (testId?.startsWith("journey-phase-") && /journey-phase-\d+$/.test(testId)) {
        return rect(140, 20, 180, 90);
      }
      return rect(0, 0, width, 900);
    },
  });
  return render(
    <MemoryRouter initialEntries={["/?overview=curve&scene=3"]}>
      <div style={{ width, height: 900 }} data-testid="viewport-shell">
        <ReaderJourneyWorkspace
          visualization={buildFixture13Scenes()}
          onLocateEvidence={vi.fn()}
          sourcePane={<div data-testid="fixture-source">正文</div>}
        />
      </div>
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  document.getElementById("journey-overlay-root")?.remove();
});

describe("Reader Journey inline lens selector (no overlay)", () => {
  it("source uses inline segmented control, not JourneyPopover for lenses", () => {
    expect(toolbarSource).toMatch(/data-lens-layout="inline-segmented"/);
    expect(toolbarSource).toMatch(/journey-lens-segmented/);
    expect(toolbarSource).not.toMatch(/journey-lens-select-menu[\s\S]{0,80}JourneyPopover/);
    expect(toolbarSource).not.toMatch(/更多操作/);
    expect(toolbarSource).not.toMatch(/journey-lens-active-hint/);
    expect(css).toMatch(/\.journey-topbar\s+\.journey-lens-selector-list[\s\S]*overflow-x:\s*auto/);
    expect(css).toMatch(/\.journey-topbar__row[\s\S]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+auto/);
  });

  it("renders all six lenses inline with clear selected state and one named explanation", () => {
    renderAtWidth(1440);
    const group = screen.getByTestId("journey-lens-select");
    expect(group).toHaveAttribute("role", "radiogroup");
    expect(group).toHaveAttribute("data-current-lens", "composite");
    expect(screen.getByTestId("journey-lens-selector-list")).toHaveAttribute(
      "data-lens-panel",
      "inline",
    );
    for (const lens of OBSERVATION_LENSES) {
      const btn = screen.getByTestId(`journey-lens-${lens.id}`);
      expect(btn).toBeInTheDocument();
      expect(btn).toHaveTextContent(lens.labelZh);
      expect(btn.textContent).not.toMatch(/^镜头/);
    }
    expect(screen.getByTestId("journey-lens-composite")).toHaveClass("active");
    expect(screen.getByTestId("journey-lens-composite")).toHaveAttribute("aria-checked", "true");
    expect(screen.queryByTestId("journey-lens-active-hint")).not.toBeInTheDocument();
    expect(screen.getByTestId("journey-lens-one-liner").textContent).toBe(
      `综合阅读：${getObservationLensHint("composite")}`,
    );
  });

  it("switches lenses without opening an overlay panel", () => {
    renderAtWidth(1180);
    fireEvent.click(screen.getByTestId("journey-lens-plot_progress"));
    expect(screen.getByTestId("journey-lens-select")).toHaveAttribute(
      "data-current-lens",
      "plot_progress",
    );
    expect(screen.getByTestId("journey-lens-plot_progress")).toHaveClass("active");
    expect(screen.getByTestId("journey-lens-composite")).not.toHaveClass("active");
    expect(screen.getByTestId("journey-lens-one-liner").textContent).toBe(
      `剧情推进：${getObservationLensHint("plot_progress")}`,
    );
    expect(screen.queryByTestId("journey-lens-select-menu-panel")).not.toBeInTheDocument();
    const overlay = document.getElementById("journey-overlay-root");
    if (overlay) {
      expect(overlay.querySelector('[data-testid="journey-lens-select-menu-panel"]')).toBeNull();
      expect(overlay.querySelector('[data-testid="journey-lens-selector-list"]')).toBeNull();
    }
    expect(
      screen.getByTestId("journey-toolbar-region").contains(
        screen.getByTestId("journey-lens-selector-list"),
      ),
    ).toBe(true);
  });

  it.each([1024, 1180, 1440, 1920] as const)(
    "at %spx lens control does not overlap phase strip or chart shell",
    (width) => {
      renderAtWidth(width);
      const lens = screen.getByTestId("journey-lens-select-menu").getBoundingClientRect();
      const phases = screen.getByTestId("journey-phase-strip-wrap").getBoundingClientRect();
      const chart = screen.getByTestId("journey-chart-shell").getBoundingClientRect();
      const actions = screen.getByTestId("journey-toolbar-right").getBoundingClientRect();
      expect(overlaps(lens, phases)).toBe(false);
      expect(overlaps(lens, chart)).toBe(false);
      expect(lens.bottom).toBeLessThanOrEqual(phases.top);
      expect(phases.bottom).toBeLessThanOrEqual(chart.top);
      expect(actions.right).toBeLessThanOrEqual(width);
      const toolbar = screen.getByTestId("journey-toolbar-region");
      for (const lensDef of OBSERVATION_LENSES) {
        expect(within(toolbar).getByTestId(`journey-lens-${lensDef.id}`)).toBeEnabled();
      }
      expect(within(toolbar).getByTestId("journey-overlay-composite")).toBeInTheDocument();
      expect(within(toolbar).getByTestId("journey-inspector-toggle")).toBeInTheDocument();
      expect(screen.queryByTestId("journey-zoom-fit-all")).not.toBeInTheDocument();
      expect(within(toolbar).getByTestId("journey-zoom-focus-phase")).not.toBeVisible();
      expect(within(toolbar).getByTestId("journey-all-metrics")).not.toBeVisible();
    },
  );
});
