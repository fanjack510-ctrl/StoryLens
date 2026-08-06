/**
 * Local structural audit for Reader Journey UI cleanup (this round only).
 * No Playwright / full screenshot pack — DOM + source contracts only.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { buildFixture13Scenes } from "./mockVisualizationFixtures";
import { formatMetricScoreLabel } from "./journeyUiLabels";
import { expectRemovedHierarchyChrome } from "./journeyTestHelpers";

const toolbarSource = readFileSync(resolve(__dirname, "./JourneyChartToolbar.tsx"), "utf8");
const modeSwitcherSource = readFileSync(resolve(__dirname, "./JourneyModeSwitcher.tsx"), "utf8");
const shellSource = readFileSync(
  resolve(__dirname, "../layout/AppShell.tsx"),
  "utf8",
);

afterEach(() => {
  cleanup();
  document.getElementById("journey-overlay-root")?.remove();
});

describe("Reader Journey UI cleanup local audit", () => {
  it("keeps top mode labels and removes source expand/collapse from toolbar", () => {
    expect(modeSwitcherSource).toMatch(/正文对照/);
    expect(modeSwitcherSource).toMatch(/旅程视图/);
    expect(modeSwitcherSource).toMatch(/仅看正文/);
    expect(toolbarSource).not.toMatch(/收起正文|展开正文/);
    expect(shellSource).toMatch(/小说叙事洞察与创作平台/);
    expect(shellSource).not.toMatch(/小说拆解工作台/);
  });

  it("unified topbar: lenses left, 收起详情 + 对比分析 right; no more menu", () => {
    render(
      <MemoryRouter initialEntries={["/?overview=curve&scene=3"]}>
        <ReaderJourneyWorkspace
          visualization={buildFixture13Scenes()}
          onLocateEvidence={vi.fn()}
          sourcePane={<div>正文</div>}
        />
      </MemoryRouter>,
    );
    expectRemovedHierarchyChrome();
    const toolbar = screen.getByTestId("journey-curve-toolbar");
    const actions = screen.getByTestId("journey-toolbar-right");
    expect(within(toolbar).getByTestId("journey-lens-select")).toBeInTheDocument();
    expect(within(toolbar).queryByTestId("journey-zoom-fit-all")).not.toBeInTheDocument();
    expect(within(actions).getByTestId("journey-overlay-composite")).toHaveTextContent("对比分析");
    expect(within(actions).getByTestId("journey-inspector-toggle")).toHaveTextContent(/详情/);
    expect(within(toolbar).getByTestId("journey-zoom-focus-phase")).not.toBeVisible();
    expect(within(toolbar).getByTestId("journey-all-metrics")).not.toBeVisible();
    expect(within(toolbar).queryByTestId("journey-source-toggle")).not.toBeInTheDocument();
    expect(screen.getByTestId("journey-toolbar-region")).toHaveAttribute("data-topbar", "unified");
  });

  it("keeps hidden export trigger off the removed more-actions menu", () => {
    render(
      <MemoryRouter initialEntries={["/?overview=curve"]}>
        <ReaderJourneyWorkspace
          visualization={buildFixture13Scenes()}
          onLocateEvidence={vi.fn()}
          sourcePane={<div>正文</div>}
        />
      </MemoryRouter>,
    );
    const exportBtn = screen.getByTestId("journey-export-png");
    expect(exportBtn).not.toBeVisible();
    expect(within(screen.getByTestId("journey-curve-toolbar")).queryByTestId("journey-export-png")).not.toBeInTheDocument();
  });

  it("phase cards use semantic scores and no 当前 badge", () => {
    expect(formatMetricScoreLabel("tension", 66)).toBe("张力 66");
    expect(formatMetricScoreLabel("hook", 48)).toBe("钩子 48");
    render(
      <MemoryRouter initialEntries={["/?overview=curve&phase=2"]}>
        <ReaderJourneyWorkspace
          visualization={buildFixture13Scenes()}
          activePhaseOrdinal={2}
          onLocateEvidence={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId("journey-phase-current-badge")).not.toBeInTheDocument();
    expect(screen.getByTestId("journey-phase-avg-2").textContent).toMatch(/综合阅读\s+\d+/);
    expect(screen.getByTestId("journey-phase-2")).toHaveClass("active-phase");
  });
});
