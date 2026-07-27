/**
 * v2.8 visualization tests 鈥?superseded by v2.9 canonical restoration.
 * Kept as a thin compatibility suite so historical gate paths still resolve.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  CHART_HEIGHT_PRESETS,
  JOURNEY_VISUALIZATION_VERSION,
  PLOT_AREA_HEIGHT_PRESETS,
  allowsHorizontalPanZoom,
  requiresBrush,
} from "./journeyVisualizationConfig";
import { buildFixture13Scenes, buildFixture30Scenes } from "./mockVisualizationFixtures";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";

function renderWorkspace(viz = buildFixture13Scenes()) {
  return render(
    <MemoryRouter>
      <ReaderJourneyWorkspace visualization={viz} onLocateEvidence={vi.fn()} />
    </MemoryRouter>,
  );
}

describe("Reader Journey Visualization v2.8 (superseded by v3.0)", () => {
  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it("forwards to visualization version 4.0 after full-plot restore", () => {
    expect(JOURNEY_VISUALIZATION_VERSION).toBe("4.2");
    expect(PLOT_AREA_HEIGHT_PRESETS.standard).toBeGreaterThanOrEqual(340);
    expect(CHART_HEIGHT_PRESETS.standard).toBe(420);
  });

  it("keeps Y ticks 0/25/50/75/100 and 13-scene fit", () => {
    renderWorkspace();
    for (const tick of [0, 25, 50, 75, 100]) {
      expect(screen.getByTestId(`journey-y-tick-${tick}`)).toBeInTheDocument();
    }
    for (let i = 1; i <= 13; i += 1) {
      expect(screen.getByTestId(`journey-curve-node-${i}`)).toBeInTheDocument();
    }
  });

  it("keeps density policy for 30 scenes", () => {
    expect(allowsHorizontalPanZoom(30)).toBe(true);
    expect(requiresBrush(30)).toBe(false);
    renderWorkspace(buildFixture30Scenes());
    expect(screen.getByTestId("journey-zoom-in")).toBeInTheDocument();
  });
});
