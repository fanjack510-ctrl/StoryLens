/**
 * Local structural audit for Reader Journey UI cleanup (this round only).
 * No Playwright / full screenshot pack — DOM + source contracts only.
 */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { buildFixture13Scenes } from "./mockVisualizationFixtures";
import { formatMetricScoreLabel } from "./journeyUiLabels";

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

  it("toolbar primary row is compact: metric · fit · phase · details · more", () => {
    render(
      <MemoryRouter initialEntries={["/?overview=curve&scene=3"]}>
        <ReaderJourneyWorkspace
          visualization={buildFixture13Scenes()}
          onLocateEvidence={vi.fn()}
          sourcePane={<div>正文</div>}
        />
      </MemoryRouter>,
    );
    const toolbar = screen.getByTestId("journey-curve-toolbar");
    expect(within(toolbar).getByTestId("journey-metric-select")).toHaveTextContent(/指标/);
    expect(within(toolbar).getByTestId("journey-zoom-fit-all")).toBeInTheDocument();
    expect(within(toolbar).getByTestId("journey-zoom-focus-phase")).toHaveTextContent("当前阶段");
    expect(within(toolbar).getByTestId("journey-inspector-toggle")).toHaveTextContent(/详情/);
    expect(within(toolbar).getByTestId("journey-more-chart-settings")).toHaveTextContent("更多操作");
    expect(within(toolbar).queryByTestId("journey-export-png")).not.toBeInTheDocument();
    expect(within(toolbar).queryByTestId("journey-source-toggle")).not.toBeInTheDocument();
  });

  it("more actions popover holds export / height / Y / reset items", () => {
    render(
      <MemoryRouter initialEntries={["/?overview=curve"]}>
        <ReaderJourneyWorkspace
          visualization={buildFixture13Scenes()}
          onLocateEvidence={vi.fn()}
          sourcePane={<div>正文</div>}
        />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId("journey-more-chart-settings"));
    const panel = screen.getByTestId("journey-more-menu-panel");
    expect(within(panel).getByTestId("journey-export-png")).toHaveTextContent("导出 PNG");
    expect(within(panel).getByTestId("journey-chart-height-controls")).toBeInTheDocument();
    expect(within(panel).getByTestId("journey-y-domain-fixed")).toHaveTextContent("固定 0—100");
    expect(within(panel).getByTestId("journey-y-domain-focus")).toHaveTextContent("聚焦数据");
    expect(within(panel).getByTestId("journey-zoom-reset")).toHaveTextContent("恢复默认");
    expect(within(panel).getByTestId("journey-reset-pane-widths")).toHaveTextContent(
      "恢复默认栏宽",
    );
  });

  it("phase cards use semantic scores and no 当前 badge", () => {
    expect(formatMetricScoreLabel("tension", 66)).toBe("节奏 66");
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
    expect(screen.getByTestId("journey-phase-avg-2").textContent).toMatch(/阅读动力\s+\d+/);
    expect(screen.getByTestId("journey-phase-2")).toHaveClass("active-phase");
  });
});
