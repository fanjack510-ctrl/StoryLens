import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { applyJourneySelectionIntent } from "./journeySelectionTransaction";
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

function LocationProbe({ onChange }: { onChange: (search: string) => void }) {
  const location = useLocation();
  onChange(location.search);
  return null;
}

function renderBooksLike(initial: string, onSelectionChange = vi.fn()) {
  const searches: string[] = [];
  const initialParams = new URLSearchParams(initial.includes("?") ? initial.split("?")[1] : "");
  const initialScene = Number(initialParams.get("scene")) || 12;

  function Harness() {
    const [scene, setScene] = React.useState<number | null>(initialScene);
    const [phase, setPhase] = React.useState<number | null>(4);
    return (
      <>
        <LocationProbe onChange={(s) => searches.push(s)} />
        <ReaderJourneyWorkspace
          visualization={visualization}
          onLocateEvidence={vi.fn()}
          activeSceneOrdinal={scene}
          activePhaseOrdinal={phase}
          selectedMetric="engagement"
          onSelectionChange={(patch) => {
            onSelectionChange(patch);
            if (patch.activeSceneOrdinal !== undefined) {
              setScene(patch.activeSceneOrdinal);
            }
            if (patch.activePhaseOrdinal !== undefined) {
              setPhase(patch.activePhaseOrdinal);
            }
          }}
        />
      </>
    );
  }

  render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route path="*" element={<Harness />} />
      </Routes>
    </MemoryRouter>,
  );
  return { searches, onSelectionChange };
}

describe("Phase 1C-C.2.5.3 books route selection transaction", () => {
  it("applyJourneySelectionIntent atomically sets scene/paragraph/inspector", () => {
    const prev = new URLSearchParams(
      "tab=reader-journey&mode=sync&scene=12&inspector=phase&overview=curve&metric=engagement",
    );
    const next = applyJourneySelectionIntent(prev, {
      source: "curve",
      inspector: "scene",
      sceneOrdinal: 14,
      paragraphId: "B0001-C0002-P0064",
      clearCluster: true,
    });
    expect(next.get("scene")).toBe("14");
    expect(next.get("inspector")).toBe("scene");
    expect(next.get("paragraph")).toBe("B0001-C0002-P0064");
    expect(next.get("overview")).toBe("curve");
    expect(next.get("metric")).toBe("engagement");
    expect(next.get("mode")).toBe("sync");
  });

  it("Phase intent preserves scene and paragraph", () => {
    const prev = new URLSearchParams(
      "tab=reader-journey&scene=9&paragraph=B0001-C0002-P0090&inspector=scene",
    );
    const next = applyJourneySelectionIntent(prev, {
      source: "phase-strip",
      inspector: "phase",
      phaseId: 4,
      preserveScene: true,
    });
    expect(next.get("scene")).toBe("9");
    expect(next.get("paragraph")).toBe("B0001-C0002-P0090");
    expect(next.get("inspector")).toBe("phase");
  });

  it("same-event-loop merge does not leave stale scene with new inspector", () => {
    let params = new URLSearchParams("scene=12&inspector=phase&tab=reader-journey");
    // Simulate stale syncUrl snapshot write then authoritative commit.
    const stale = new URLSearchParams(params);
    stale.set("scene", "14");
    stale.set("paragraph", "B0001-C0002-P0064");
    // inspector still missing (old syncUrl behavior)
    params = stale;
    params = applyJourneySelectionIntent(params, {
      source: "rhythm",
      inspector: "scene",
      sceneOrdinal: 14,
      paragraphId: "B0001-C0002-P0064",
    });
    expect(params.get("scene")).toBe("14");
    expect(params.get("inspector")).toBe("scene");
  });

  it("Curve click commits scene+inspector without reverting to prior scene", async () => {
    const { searches, onSelectionChange } = renderBooksLike(
      "/?overview=curve&mode=sync&scene=12&inspector=phase&metric=engagement",
    );
    fireEvent.click(screen.getByTestId("journey-curve-node-14"));
    expect(onSelectionChange).toHaveBeenCalledWith(
      expect.objectContaining({ activeSceneOrdinal: 14, source: "journey_scene" }),
    );
    await waitFor(() => {
      const last = searches[searches.length - 1] ?? "";
      expect(last).toMatch(/scene=14/);
      expect(last).toMatch(/inspector=scene/);
      expect(last).not.toMatch(/inspector=phase/);
    });
    expect(screen.getByTestId("scene-detail-title")).toHaveTextContent(/场景14/);
  });

  it("Rhythm click commits scene URL atomically", async () => {
    const { searches } = renderBooksLike(
      "/?overview=curve&mode=sync&scene=14&inspector=scene",
    );
    fireEvent.click(screen.getByTestId("journey-rhythm-dot-9"));
    await waitFor(() => {
      const last = searches[searches.length - 1] ?? "";
      expect(last).toMatch(/scene=9/);
      expect(last).toMatch(/inspector=scene/);
    });
  });

  it("Phase click updates inspector without changing scene", async () => {
    const { searches, onSelectionChange } = renderBooksLike(
      "/?overview=curve&mode=sync&scene=9&paragraph=B0001-C0002-P0090&inspector=scene",
    );
    fireEvent.click(screen.getByTestId("journey-phase-4"));
    expect(onSelectionChange).toHaveBeenCalledWith(
      expect.objectContaining({
        activePhaseOrdinal: 4,
        source: "journey_phase",
      }),
    );
    const phaseCall = onSelectionChange.mock.calls.find(
      (call) => call[0]?.source === "journey_phase",
    );
    expect(phaseCall?.[0]?.activeSceneOrdinal).toBeUndefined();
    await waitFor(() => {
      const last = searches[searches.length - 1] ?? "";
      expect(last).toMatch(/inspector=phase/);
      expect(last).toMatch(/scene=9/);
      expect(last).toMatch(/paragraph=B0001-C0002-P0090/);
    });
    expect(screen.getByTestId("journey-phase-detail-panel")).toBeInTheDocument();
  });

  it("rapid Scene clicks end on the last ordinal", async () => {
    const { searches } = renderBooksLike("/?overview=curve&mode=sync&scene=12&inspector=scene");
    fireEvent.click(screen.getByTestId("journey-curve-node-12"));
    fireEvent.click(screen.getByTestId("journey-curve-node-14"));
    fireEvent.click(screen.getByTestId("journey-curve-node-9"));
    await waitFor(() => {
      const last = searches[searches.length - 1] ?? "";
      expect(last).toMatch(/scene=9/);
      expect(last).toMatch(/inspector=scene/);
    });
  });

  it("preserves metric and normalizes overview across Scene click", async () => {
    const { searches } = renderBooksLike(
      "/?overview=questions&mode=sync&scene=12&inspector=scene&metric=tension",
    );
    fireEvent.click(screen.getByTestId("journey-rhythm-dot-14"));
    await waitFor(() => {
      const last = searches[searches.length - 1] ?? "";
      expect(last).toMatch(/scene=14/);
      expect(last).toMatch(/overview=curve/);
      expect(last).toMatch(/metric=tension/);
    });
  });

  it("curve commit stays on Scene N after short delay (no stale N-1 URL echo)", async () => {
    const { searches } = renderBooksLike(
      "/?overview=curve&mode=sync&scene=12&inspector=scene",
    );
    fireEvent.click(screen.getByTestId("journey-curve-node-14"));
    await waitFor(() => {
      const last = searches[searches.length - 1] ?? "";
      expect(last).toMatch(/scene=14/);
    });
    await new Promise((r) => setTimeout(r, 50));
    const last = searches[searches.length - 1] ?? "";
    expect(last).toMatch(/scene=14/);
    expect(last).not.toMatch(/scene=12(?!\d)/);
  });
});
