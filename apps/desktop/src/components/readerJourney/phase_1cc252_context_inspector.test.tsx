import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { buildMockReaderJourneyVisualization } from "./mockVisualization";
import { MORE_METRIC_KEYS, QUICK_METRIC_KEYS } from "./journeyUiLabels";
import * as exportModule from "./exportJourneyPng";

vi.mock("./exportJourneyPng", async (importOriginal) => {
  const actual = await importOriginal<typeof exportModule>();
  return {
    ...actual,
    exportJourneyPng: vi.fn().mockResolvedValue({
      filename: "StoryLens_Chapter_ReaderJourney_v1.1.png",
    }),
  };
});

afterEach(cleanup);

const css = readFileSync(resolve(__dirname, "./readerJourney.css"), "utf8");
const visualization = buildMockReaderJourneyVisualization();

function renderAt(path: string, props: Record<string, unknown> = {}) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ReaderJourneyWorkspace
        visualization={visualization}
        onLocateEvidence={vi.fn()}
        {...props}
      />
    </MemoryRouter>,
  );
}

describe("Phase 1C-C.2.5.2 Context Inspector", () => {
  it("does not render Phase detail above the curve", () => {
    renderAt("/?overview=curve&scene=12&inspector=phase", {
      activeSceneOrdinal: 12,
      activePhaseOrdinal: 3,
    });
    expect(screen.queryByTestId("journey-phase-popover")).not.toBeInTheDocument();
    const overview = screen.getByTestId("journey-overview-curve");
    expect(overview.querySelector('[data-testid="journey-phase-detail-panel"]')).toBeNull();
    expect(screen.getByTestId("journey-curve-svg")).toBeInTheDocument();
  });

  it("shows Phase detail in the lower Context Inspector after Phase click", () => {
    const onSelectionChange = vi.fn();
    renderAt("/?overview=curve&scene=12", {
      activeSceneOrdinal: 12,
      activePhaseOrdinal: 4,
      onSelectionChange,
    });
    fireEvent.click(screen.getByTestId("journey-phase-2"));
    expect(screen.getByTestId("journey-phase-detail-panel")).toBeInTheDocument();
    expect(screen.queryByTestId("scene-detail-title")).not.toBeInTheDocument();
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
  });

  it("switches to Scene detail when a Scene is selected", () => {
    renderAt("/?overview=curve&inspector=phase", {
      activePhaseOrdinal: 4,
    });
    expect(screen.getByTestId("journey-phase-detail-panel")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("journey-curve-node-10"));
    expect(screen.getByTestId("scene-detail-title")).toHaveTextContent("Scene 10");
    expect(screen.queryByTestId("journey-phase-detail-panel")).not.toBeInTheDocument();
  });

  it("never shows Phase and Scene details at the same time", () => {
    renderAt("/?overview=curve&scene=12&inspector=phase", {
      activeSceneOrdinal: 12,
      activePhaseOrdinal: 3,
    });
    expect(screen.getByTestId("journey-phase-detail-panel")).toBeInTheDocument();
    expect(screen.queryByTestId("scene-detail-title")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("journey-curve-node-12"));
    expect(screen.getByTestId("scene-detail-title")).toBeInTheDocument();
    expect(screen.queryByTestId("journey-phase-detail-panel")).not.toBeInTheDocument();
  });

  it("exposes four Phase detail tabs", () => {
    renderAt("/?overview=curve&inspector=phase", {
      activeSceneOrdinal: 12,
      activePhaseOrdinal: 3,
    });
    expect(screen.getByTestId("phase-detail-tab-overview")).toBeInTheDocument();
    expect(screen.getByTestId("phase-detail-tab-questions")).toBeInTheDocument();
    expect(screen.getByTestId("phase-detail-tab-risks")).toBeInTheDocument();
    expect(screen.getByTestId("phase-detail-tab-scenes")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("phase-detail-tab-questions"));
    expect(screen.getByTestId("phase-detail-panel-questions")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("phase-detail-tab-risks"));
    expect(screen.getByTestId("phase-detail-panel-risks")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("phase-detail-tab-scenes"));
    expect(screen.getByTestId("phase-detail-panel-scenes")).toBeInTheDocument();
  });

  it("related Scene click enters Scene detail and notifies selection", () => {
    const onSelectionChange = vi.fn();
    renderAt("/?overview=curve&inspector=phase", {
      activePhaseOrdinal: 1,
      onSelectionChange,
    });
    fireEvent.click(screen.getByTestId("phase-detail-tab-scenes"));
    fireEvent.click(screen.getByTestId("phase-related-scene-2"));
    expect(screen.getByTestId("scene-detail-title")).toHaveTextContent("Scene 2");
    expect(onSelectionChange).toHaveBeenCalledWith(
      expect.objectContaining({ activeSceneOrdinal: 2, source: "journey_scene" }),
    );
  });

  it("keeps single metric selector with all metrics available", () => {
    const onSelectionChange = vi.fn();
    renderAt("/?overview=curve&metric=engagement", {
      activeSceneOrdinal: 12,
      selectedMetric: "engagement",
      onSelectionChange,
    });
    expect(QUICK_METRIC_KEYS).toEqual(["engagement", "curiosity", "tension"]);
    expect(MORE_METRIC_KEYS).toEqual([
      "payoff",
      "hook",
      "dropoff_risk",
      "valence",
      "arousal",
    ]);
    expect(screen.getByTestId("journey-metric-select")).toHaveTextContent("阅读牵引");
    fireEvent.click(screen.getByTestId("journey-metric-select"));
    expect(screen.getByTestId("journey-metric-select-menu")).toBeInTheDocument();
    expect(screen.getByTestId("journey-metric-engagement")).toBeInTheDocument();
    expect(screen.getByTestId("journey-metric-curiosity")).toBeInTheDocument();
    expect(screen.getByTestId("journey-metric-payoff")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("journey-metric-valence"));
    expect(onSelectionChange).toHaveBeenCalledWith(
      expect.objectContaining({ selectedMetric: "valence", source: "journey_rhythm" }),
    );
  });

  it("uses compact legend by default and expands in full marker mode", () => {
    renderAt("/?overview=curve");
    const legend = screen.getByTestId("journey-curve-legend");
    expect(legend).toHaveTextContent("当前场景");
    expect(legend).toHaveTextContent("钩子");
    expect(legend).toHaveTextContent("回报");
    expect(legend).toHaveTextContent("风险");
    expect(legend.textContent).not.toMatch(/次级节点/);
    expect(legend.textContent).not.toMatch(/已回答问题/);

    fireEvent.click(screen.getByTestId("journey-marker-full"));
    expect(legend).toHaveTextContent("已回答问题");
    expect(legend).toHaveTextContent("问题升级");
    expect(legend).toHaveTextContent("次级节点");
    expect(legend).toHaveTextContent("节拍节点");
    expect(legend).toHaveTextContent("派生标记");
  });

  it("keeps thin rhythm strip scene locate capability", () => {
    const onSelectionChange = vi.fn();
    renderAt("/?overview=curve&scene=5", {
      activeSceneOrdinal: 5,
      onSelectionChange,
    });
    const strip = screen.getByTestId("journey-rhythm-strip");
    expect(strip.className).toContain("journey-rhythm-strip-thin");
    expect(screen.getByTestId("journey-rhythm-dot-8")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("journey-rhythm-dot-8"));
    expect(onSelectionChange).toHaveBeenCalledWith(
      expect.objectContaining({ activeSceneOrdinal: 8, source: "journey_rhythm" }),
    );
  });

  it("keeps curve height independent of Context Inspector content", () => {
    renderAt("/?overview=curve&scene=12&inspector=phase", {
      activeSceneOrdinal: 12,
      activePhaseOrdinal: 3,
    });
    expect(screen.getByTestId("journey-curve-svg").getAttribute("height")).toBe("420");
    expect(css).toMatch(/\.journey-overview-pane[\s\S]*overflow:\s*hidden/);
    expect(css).not.toMatch(/journey-phase-popover/);
  });

  it("PNG export still targets Overview only", async () => {
    renderAt("/?overview=curve&scene=12&inspector=phase", {
      activeSceneOrdinal: 12,
      activePhaseOrdinal: 3,
    });
    fireEvent.click(screen.getByTestId("journey-export-png"));
    await vi.waitFor(() => {
      expect(exportModule.exportJourneyPng).toHaveBeenCalled();
    });
    const exportRoot = screen.getByTestId("journey-export-root");
    expect(exportRoot.contains(screen.getByTestId("journey-curve-svg"))).toBe(true);
    expect(exportRoot.contains(screen.getByTestId("journey-phase-detail-panel"))).toBe(false);
  });
});

