import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  DEFAULT_OVERVIEW_RATIO,
  JourneyResizableSplit,
  MIN_DETAIL_PX,
  MIN_OVERVIEW_PX,
  OVERVIEW_HEIGHT_STORAGE_KEY,
  clampOverviewRatio,
  defaultOverviewRatioForHeight,
} from "./JourneyResizableSplit";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { buildMockReaderJourneyVisualization } from "./mockVisualization";

vi.mock("./exportJourneyPng", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./exportJourneyPng")>();
  return {
    ...actual,
    exportJourneyPng: vi.fn().mockResolvedValue({
      filename: "StoryLens_Chapter_ReaderJourney_v1.1.png",
    }),
  };
});

afterEach(cleanup);

beforeEach(() => {
  localStorage.clear();
});

describe("Phase 1C-C.2.5B resizable overview", () => {
  it("clamps overview/detail minima and picks height-based defaults", () => {
    expect(defaultOverviewRatioForHeight(1000)).toBe(0.72);
    expect(defaultOverviewRatioForHeight(800)).toBe(0.7);
    expect(MIN_OVERVIEW_PX).toBe(440);
    expect(MIN_DETAIL_PX).toBe(200);
    const clamped = clampOverviewRatio(0.9, 1000);
    expect(clamped).toBeLessThanOrEqual(1 - MIN_DETAIL_PX / 1000);
    expect(clampOverviewRatio(0.1, 1000)).toBeGreaterThanOrEqual(MIN_OVERVIEW_PX / 1000);
  });

  it("renders resize handle and persists preference on reset", () => {
    render(
      <JourneyResizableSplit
        overview={<div data-testid="ov">overview</div>}
        detail={<div data-testid="dt">detail</div>}
      />,
    );
    expect(screen.getByTestId("journey-resize-handle")).toBeInTheDocument();
    fireEvent.doubleClick(screen.getByTestId("journey-resize-handle"));
    const stored = JSON.parse(localStorage.getItem(OVERVIEW_HEIGHT_STORAGE_KEY) ?? "{}");
    expect(stored.ratio).toBeGreaterThan(0);
    expect(stored.updatedAt).toBeTruthy();
    expect(DEFAULT_OVERVIEW_RATIO).toBe(0.72);
  });

  it("wires resizable split into ReaderJourneyWorkspace", () => {
    const visualization = buildMockReaderJourneyVisualization();
    render(
      <MemoryRouter>
        <ReaderJourneyWorkspace
          visualization={visualization}
          onLocateEvidence={vi.fn()}
          activeSceneOrdinal={12}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("journey-resizable-split")).toBeInTheDocument();
    expect(screen.getByTestId("journey-overview-pane")).toBeInTheDocument();
    expect(screen.getByTestId("journey-detail-pane")).toBeInTheDocument();
    expect(screen.getByTestId("journey-collapse-inspector")).toBeInTheDocument();
  });

  it("supports keyboard nudge on separator", () => {
    render(
      <div style={{ height: 900 }}>
        <JourneyResizableSplit
          overview={<div>overview</div>}
          detail={<div>detail</div>}
          contentHeight={900}
        />
      </div>,
    );
    const handle = screen.getByTestId("journey-resize-handle");
    fireEvent.keyDown(handle, { key: "ArrowDown" });
    const stored = JSON.parse(localStorage.getItem(OVERVIEW_HEIGHT_STORAGE_KEY) ?? "{}");
    expect(Number(stored.ratio)).toBeGreaterThan(DEFAULT_OVERVIEW_RATIO - 0.001);
  });
});
