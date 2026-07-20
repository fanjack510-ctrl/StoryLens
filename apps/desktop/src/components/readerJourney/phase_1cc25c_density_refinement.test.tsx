import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { buildMockReaderJourneyVisualization } from "./mockVisualization";
import { ALL_METRIC_KEYS, MORE_METRIC_KEYS, QUICK_METRIC_KEYS } from "./journeyUiLabels";
import * as exportModule from "./exportJourneyPng";

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


const css = readFileSync(resolve(__dirname, "./readerJourney.css"), "utf8");
const visualization = buildMockReaderJourneyVisualization();

describe("Phase 1C-C.2.5C density refinement (updated for 2.6)", () => {
  it("uses compact metric strip and single metric selector", () => {
    render(
      <MemoryRouter initialEntries={["/?overview=curve&scene=12"]}>
        <ReaderJourneyWorkspace
          visualization={visualization}
          onLocateEvidence={vi.fn()}
          activeSceneOrdinal={12}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("journey-summary-cards").className).toMatch(/journey-(insight|metric|summary)-strip/);
    expect(css).toMatch(/\.journey-metric-strip/);
    expect(screen.getByTestId("journey-curve-legend")).toHaveTextContent("当前场景");
    expect(screen.getByTestId("journey-curve-legend")).toHaveTextContent("钩子");
    expect(screen.getByTestId("journey-curve-legend").textContent).not.toMatch(/已回答问题/);

    fireEvent.click(screen.getByTestId("journey-marker-full"));
    expect(screen.getByTestId("journey-curve-legend")).toHaveTextContent("已回答问题");

    expect(QUICK_METRIC_KEYS).toEqual(["engagement", "curiosity", "tension"]);
    expect(MORE_METRIC_KEYS).toContain("valence");
    expect(ALL_METRIC_KEYS).toContain("valence");
    fireEvent.click(screen.getByTestId("journey-metric-select"));
    expect(screen.getByTestId("journey-metric-select-menu")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("journey-metric-valence"));
    expect(screen.getByTestId("journey-metric-select")).toHaveTextContent("情绪正负");
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
    expect(screen.getByTestId("scene-detail-title")).toHaveTextContent("Scene 12");
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
    fireEvent.click(screen.getByTestId("journey-export-png"));
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
