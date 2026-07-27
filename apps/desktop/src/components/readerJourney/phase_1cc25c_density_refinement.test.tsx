import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { buildMockReaderJourneyVisualization } from "./mockVisualization";
import { ALL_METRIC_KEYS, MORE_METRIC_KEYS, QUICK_METRIC_KEYS } from "./journeyUiLabels";
import * as exportModule from "./exportJourneyPng";
import { expectRemovedHierarchyChrome, openExportMenu } from "./journeyTestHelpers";

vi.mock("./exportJourneyPng", async (importOriginal) => {
  const actual = await importOriginal<typeof exportModule>();
  return {
    ...actual,
    exportJourneyPng: vi.fn().mockResolvedValue({
      filename: "StoryLens_Chapter_旅程分析_v1.1.png",
    }),
  };
});

afterEach(() => {
  cleanup();
  localStorage.clear();
});

const visualization = buildMockReaderJourneyVisualization();

describe("Phase 1C-C.2.5C density refinement (updated for 2.6)", () => {
  it("uses unified topbar and above-chart legend instead of summary strip", () => {
    render(
      <MemoryRouter initialEntries={["/?overview=curve&scene=12"]}>
        <ReaderJourneyWorkspace
          visualization={visualization}
          onLocateEvidence={vi.fn()}
          activeSceneOrdinal={12}
        />
      </MemoryRouter>,
    );
    expectRemovedHierarchyChrome();
    expect(screen.getByTestId("journey-toolbar-region")).toHaveAttribute("data-topbar", "unified");
    expect(screen.getByTestId("journey-unified-legend")).toHaveAttribute(
      "data-legend-placement",
      "above-chart",
    );
    expect(screen.getByTestId("journey-minimal-legend")).toBeInTheDocument();

    expect(QUICK_METRIC_KEYS).toEqual(["engagement", "curiosity", "tension"]);
    expect(MORE_METRIC_KEYS).toContain("valence");
    expect(ALL_METRIC_KEYS).toContain("valence");
    fireEvent.click(screen.getByTestId("journey-lens-emotion"));
    expect(screen.getByTestId("journey-lens-emotion")).toHaveAttribute("aria-current", "true");
  });

  it("opens Phase Context Inspector and keeps Scene selection on single view", () => {
    render(
      <MemoryRouter initialEntries={["/?overview=curve&scene=12"]}>
        <ReaderJourneyWorkspace
          visualization={visualization}
          onLocateEvidence={vi.fn()}
          activeSceneOrdinal={12}
          activePhaseOrdinal={4}
        />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId("journey-phase-3"));
    expect(screen.getByTestId("journey-phase-detail-panel")).toBeInTheDocument();
    expect(screen.queryByTestId("journey-phase-popover")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("journey-curve-node-12"));
    fireEvent.click(screen.getByTestId("scene-detail-tab-questions"));
    expect(screen.getByTestId("scene-detail-panel-questions")).toBeInTheDocument();
    expect(screen.getByTestId("scene-detail-title")).toHaveTextContent(/场景12/);
  });

  it("exports PNG from legacy overview=questions without leaving journey analysis", async () => {
    render(
      <MemoryRouter initialEntries={["/?overview=questions&scene=12"]}>
        <ReaderJourneyWorkspace
          visualization={visualization}
          onLocateEvidence={vi.fn()}
          activeSceneOrdinal={12}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("journey-overview-curve")).toBeInTheDocument();
    fireEvent.click(openExportMenu());
    await vi.waitFor(() => {
      expect(exportModule.exportJourneyPng).toHaveBeenCalled();
    });
    expect(screen.getByTestId("journey-overview-curve")).toBeInTheDocument();
  });

  it("keeps inspector dock controls keyboard accessible", () => {
    render(
      <MemoryRouter>
        <ReaderJourneyWorkspace visualization={visualization} onLocateEvidence={vi.fn()} />
      </MemoryRouter>,
    );
    const expand = screen.getByTestId("journey-inspector-summary-expand");
    expect(expand.tagName).toBe("BUTTON");
    expect(expand).toHaveAttribute("type", "button");
    fireEvent.click(expand);
    const collapse = screen.getAllByTestId("journey-collapse-inspector")[0];
    expect(collapse.tagName).toBe("BUTTON");
    expect(collapse).toHaveAttribute("type", "button");
  });
});
