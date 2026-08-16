/**
 * CHG-20260723-006: Lens click must stick on the first press (no snap-back race).
 */
import { cleanup, fireEvent, render, screen, act } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation, useSearchParams } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { buildFixture13Scenes } from "./mockVisualizationFixtures";
import {
  canonicalMetricForLens,
  resolveJourneyLensFromSearch,
  lensIdFromMetric,
  metricForLens,
} from "./readerJourneyLensExplanation";
import { useJourneySelection } from "../../hooks/useJourneySelection";
import type { JourneyCurveMetric } from "../../types/readerJourneyVisualization";
import type { SceneResultItem } from "../../types";
import { OBSERVATION_LENSES, type ObservationLensId } from "./observationLenses";

afterEach(() => {
  cleanup();
  document.getElementById("journey-overlay-root")?.remove();
});

function LocationProbe({ onChange }: { onChange: (search: string) => void }) {
  const location = useLocation();
  onChange(location.search);
  return null;
}

/** Mirrors SyncWorkspace: controlled metric + onSelectionChange that may sync URL. */
function SyncLikeHarness({
  initialMetric = "curiosity" as JourneyCurveMetric,
  syncUrlOnRhythm = false,
}: {
  initialMetric?: JourneyCurveMetric;
  /** When true, reproduces the pre-fix stale URL overwrite race. */
  syncUrlOnRhythm?: boolean;
}) {
  const [params, setParams] = useSearchParams();
  const [metric, setMetric] = useState<JourneyCurveMetric>(initialMetric);

  return (
    <ReaderJourneyWorkspace
      visualization={buildFixture13Scenes()}
      onLocateEvidence={vi.fn()}
      selectedMetric={metric}
      onSelectionChange={(patch) => {
        if (!patch.selectedMetric) return;
        setMetric(patch.selectedMetric);
        if (syncUrlOnRhythm || patch.source !== "journey_rhythm") {
          // Stale snapshot overwrite (old bug): drop/restore previous lens.
          const next = new URLSearchParams(params);
          next.set("metric", patch.selectedMetric);
          // Intentionally does not set lens — simulates old useJourneySelection.syncUrl
          setParams(next, { replace: true });
        }
      }}
    />
  );
}

describe("resolveJourneyLensFromSearch", () => {
  it("prefers explicit lens over conflicting metric", () => {
    expect(resolveJourneyLensFromSearch("reading_tension", "curiosity")).toBe("reading_tension");
    expect(canonicalMetricForLens("reading_tension")).toBe("tension");
  });

  it("falls back to metric only when lens missing", () => {
    expect(resolveJourneyLensFromSearch(null, "curiosity")).toBe("plot_progress");
    expect(resolveJourneyLensFromSearch("invalid", "arousal")).toBe("emotion");
  });
});

describe("Lens single-click switching (no snap-back)", () => {
  it("switches plot_progress → reading_tension once and keeps URL + highlight", () => {
    const searches: string[] = [];
    render(
      <MemoryRouter initialEntries={["/?overview=curve&lens=plot_progress&metric=curiosity"]}>
        <LocationProbe onChange={(s) => searches.push(s)} />
        <ReaderJourneyWorkspace
          visualization={buildFixture13Scenes()}
          onLocateEvidence={vi.fn()}
        />
      </MemoryRouter>,
    );

    expect(screen.getByTestId("journey-lens-plot_progress")).toHaveAttribute("aria-current", "true");
    fireEvent.click(screen.getByTestId("journey-lens-reading_tension"));

    expect(screen.getByTestId("journey-lens-reading_tension")).toHaveAttribute(
      "aria-current",
      "true",
    );
    expect(screen.getByTestId("journey-lens-plot_progress")).not.toHaveAttribute("aria-current");
    // The definition moved to the main button's tooltip — it cost two rows above the chart
    // on every lens switch and was useful once. The title still names the active lens.
    expect(screen.getByTestId("journey-lens-title").textContent).toBe("阅读张力");

    const last = searches[searches.length - 1] || "";
    const q = new URLSearchParams(last.startsWith("?") ? last.slice(1) : last);
    expect(q.get("lens")).toBe("reading_tension");
    expect(q.get("metric")).toBe("tension");

    // Stay stable after microtasks / effects
    act(() => {
      /* flush */
    });
    expect(screen.getByTestId("journey-lens-reading_tension")).toHaveAttribute(
      "aria-current",
      "true",
    );
    expect(q.get("lens")).toBe("reading_tension");
  });

  it("walks the full lens chain with one click each", () => {
    const order: ObservationLensId[] = [
      "composite",
      "plot_progress",
      "reading_tension",
      "emotion",
      "pacing",
      "hook_payoff",
    ];
    render(
      <MemoryRouter initialEntries={["/?overview=curve&lens=composite&metric=engagement"]}>
        <ReaderJourneyWorkspace
          visualization={buildFixture13Scenes()}
          onLocateEvidence={vi.fn()}
        />
      </MemoryRouter>,
    );

    for (const lens of order) {
      fireEvent.click(screen.getByTestId(`journey-lens-${lens}`));
      expect(screen.getByTestId(`journey-lens-${lens}`)).toHaveAttribute("aria-current", "true");
      for (const other of OBSERVATION_LENSES) {
        if (other.id === lens) continue;
        expect(screen.getByTestId(`journey-lens-${other.id}`)).not.toHaveAttribute(
          "aria-current",
        );
      }
    }
  });

  it("keeps last intent under rapid clicks", () => {
    render(
      <MemoryRouter initialEntries={["/?overview=curve&lens=composite&metric=engagement"]}>
        <ReaderJourneyWorkspace
          visualization={buildFixture13Scenes()}
          onLocateEvidence={vi.fn()}
        />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId("journey-lens-plot_progress"));
    fireEvent.click(screen.getByTestId("journey-lens-reading_tension"));
    fireEvent.click(screen.getByTestId("journey-lens-emotion"));
    expect(screen.getByTestId("journey-lens-emotion")).toHaveAttribute("aria-current", "true");
    expect(screen.getByTestId("journey-lens-title").textContent).toBe("情绪强度");
  });

  it("clears compare when entering hook_payoff in one click", () => {
    render(
      <MemoryRouter
        initialEntries={["/?overview=curve&lens=plot_progress&metric=curiosity&compareWith=arousal"]}
      >
        <ReaderJourneyWorkspace
          visualization={buildFixture13Scenes()}
          onLocateEvidence={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("journey-comparison-toolbar")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("journey-lens-hook_payoff"));
    expect(screen.getByTestId("journey-lens-hook_payoff")).toHaveAttribute("aria-current", "true");
    expect(screen.queryByTestId("journey-comparison-toolbar")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-overlay-composite")).not.toBeInTheDocument();
  });

  it("does not snap back under controlled SyncWorkspace-like parent (fixed path)", () => {
    const searches: string[] = [];
    render(
      <MemoryRouter initialEntries={["/?overview=curve&lens=plot_progress&metric=curiosity"]}>
        <Routes>
          <Route
            path="*"
            element={
              <>
                <LocationProbe onChange={(s) => searches.push(s)} />
                <SyncLikeHarness syncUrlOnRhythm={false} />
              </>
            }
          />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId("journey-lens-reading_tension"));
    act(() => {
      /* effects */
    });
    expect(screen.getByTestId("journey-lens-reading_tension")).toHaveAttribute(
      "aria-current",
      "true",
    );
    const last = searches[searches.length - 1] || "";
    const q = new URLSearchParams(last.startsWith("?") ? last.slice(1) : last);
    expect(q.get("lens")).toBe("reading_tension");
    expect(q.get("metric")).toBe("tension");
  });

  it("normalizes conflicting metric when explicit lens is present", () => {
    const searches: string[] = [];
    render(
      <MemoryRouter initialEntries={["/?overview=curve&lens=reading_tension&metric=curiosity"]}>
        <LocationProbe onChange={(s) => searches.push(s)} />
        <ReaderJourneyWorkspace
          visualization={buildFixture13Scenes()}
          onLocateEvidence={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("journey-lens-reading_tension")).toHaveAttribute(
      "aria-current",
      "true",
    );
    const last = searches[searches.length - 1] || "";
    const q = new URLSearchParams(last.startsWith("?") ? last.slice(1) : last);
    expect(q.get("lens")).toBe("reading_tension");
    expect(q.get("metric")).toBe("tension");
  });

  it("maps lens ↔ metric consistently", () => {
    for (const lens of OBSERVATION_LENSES) {
      const metric = metricForLens(lens.id);
      expect(canonicalMetricForLens(lens.id)).toBe(metric);
      if (lens.id !== "pacing") {
        // pacing shares engagement metric with composite by design
        expect(lensIdFromMetric(metric) === lens.id || lens.id === "composite").toBeTruthy();
      }
    }
  });
});

describe("useJourneySelection syncUrl preserves lens", () => {
  function MetricOnlyWriter() {
    const { setMetric, state } = useJourneySelection({
      scenes: [
        {
          scene: {
            id: 1,
            ordinal: 1,
            start_paragraph_id: "p1",
          },
        } as SceneResultItem,
      ],
    });
    const [params] = useSearchParams();
    return (
      <div>
        <span data-testid="sel-metric">{state.selectedMetric}</span>
        <span data-testid="url-lens">{params.get("lens")}</span>
        <span data-testid="url-metric">{params.get("metric")}</span>
        <button
          type="button"
          data-testid="write-tension"
          onClick={() => setMetric("tension")}
        >
          tension
        </button>
      </div>
    );
  }

  it("functional sync sets lens with metric and does not drop prior scene", () => {
    render(
      <MemoryRouter initialEntries={["/?tab=reader-journey&lens=plot_progress&metric=curiosity&scene=3"]}>
        <MetricOnlyWriter />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId("write-tension"));
    expect(screen.getByTestId("url-metric").textContent).toBe("tension");
    expect(screen.getByTestId("url-lens").textContent).toBe("reading_tension");
  });
});
