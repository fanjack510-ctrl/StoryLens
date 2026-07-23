import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { buildFixture13Scenes } from "./mockVisualizationFixtures";
import { OBSERVATION_LENSES } from "./observationLenses";

afterEach(() => {
  cleanup();
  document.getElementById("journey-overlay-root")?.remove();
});

describe("Reader Journey hierarchy simplification", () => {
  it("removes invalid top controls and duplicate summary/legend surfaces", () => {
    render(
      <MemoryRouter initialEntries={["/?overview=curve"]}>
        <ReaderJourneyWorkspace
          visualization={buildFixture13Scenes()}
          onLocateEvidence={vi.fn()}
        />
      </MemoryRouter>,
    );

    expect(screen.queryByText("精简标记")).not.toBeInTheDocument();
    expect(screen.queryByText("完整标记")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-analysis-info-popover")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-v2-native-real-banner")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-chapter-summary-bullets")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-analysis-title")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-summary-cards")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-curve-legend")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-lens-how-to-trigger")).not.toBeInTheDocument();

    const lenses = screen.getByTestId("journey-lens-selector-list");
    expect(within(lenses).getAllByRole("radio")).toHaveLength(OBSERVATION_LENSES.length);
    expect(screen.getByTestId("journey-lens-composite")).toHaveAttribute("aria-current", "true");
    expect(screen.getByTestId("journey-unified-legend")).toBeInTheDocument();
    expect(screen.getByTestId("journey-lens-one-liner")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("journey-more-chart-settings"));
    expect(screen.getByTestId("journey-analysis-info")).toBeInTheDocument();
  });
});
