import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
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

const visualization = buildMockReaderJourneyVisualization();

describe("Phase 1C-C.2.5.2-Hygiene phase selection thaw v2-2", () => {
  it("Phase click updates activePhase and does not change activeScene", () => {
    const onSelectionChange = vi.fn();
    render(
      <MemoryRouter initialEntries={["/?overview=curve&scene=12"]}>
        <ReaderJourneyWorkspace
          visualization={visualization}
          onLocateEvidence={vi.fn()}
          activeSceneOrdinal={12}
          activePhaseOrdinal={4}
          onSelectionChange={onSelectionChange}
        />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId("journey-phase-2"));
    expect(onSelectionChange).toHaveBeenCalledWith(
      expect.objectContaining({
        activePhaseOrdinal: 2,
        source: "journey_phase",
      }),
    );
    const phaseCall = onSelectionChange.mock.calls.find(
      (call) => call[0]?.source === "journey_phase",
    );
    expect(phaseCall?.[0]?.activeSceneOrdinal).toBeUndefined();
    expect(screen.getByTestId("journey-phase-detail-panel")).toBeInTheDocument();
  });

  it("Scene click still updates activeScene", () => {
    const onSelectionChange = vi.fn();
    render(
      <MemoryRouter initialEntries={["/?overview=curve"]}>
        <ReaderJourneyWorkspace
          visualization={visualization}
          onLocateEvidence={vi.fn()}
          onSelectionChange={onSelectionChange}
        />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId("journey-curve-node-10"));
    expect(onSelectionChange).toHaveBeenCalledWith(
      expect.objectContaining({
        activeSceneOrdinal: 10,
        source: "journey_scene",
      }),
    );
    expect(screen.getByTestId("scene-detail-title")).toHaveTextContent("Scene 10");
  });
});
