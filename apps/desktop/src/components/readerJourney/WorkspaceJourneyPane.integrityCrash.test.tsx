import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WorkspaceJourneyPane } from "./WorkspaceJourneyPane";

/**
 * Reproduce production crash: integrity-redacted nodes have no scores/engagement
 * but coarse hasUsableJourneyVisualization still passes → invalid_artifact still
 * mounted ReaderJourneyWorkspace → node.scores.reading_momentum threw.
 */
describe("WorkspaceJourneyPane integrity-redacted Run#8", () => {
  it("does not throw when nodes are integrity_blocked without scores", () => {
    const journey = {
      status: "succeeded",
      journey_run_id: 7,
      trusted: false,
      integrity_status: "data_integrity_failed",
      visualization: {
        scene_nodes: [
          { scene_ordinal: 1, integrity_blocked: true },
          { scene_ordinal: 2, integrity_blocked: true },
        ],
        phases: [{ ordinal: 1 }],
        curve_series: { curiosity: [{ scene_ordinal: 1, value: 0.5 }] },
      },
    } as any;

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    expect(() =>
      render(
        <QueryClientProvider client={qc}>
          <MemoryRouter>
            <WorkspaceJourneyPane
              bookId={9}
              chapterId={1220}
              analysisRunId={8}
              journey={journey}
              mainContentState="invalid_artifact"
              onRetry={() => undefined}
              onReading={() => undefined}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      ),
    ).not.toThrow();

    expect(screen.getByTestId("workspace-journey-pane")).toHaveAttribute(
      "data-state",
      "invalid_artifact",
    );
    expect(screen.getByTestId("workspace-journey-integrity-banner")).toBeInTheDocument();
    expect(screen.queryByTestId("journey-sync-workspace")).not.toBeInTheDocument();
  });
});
