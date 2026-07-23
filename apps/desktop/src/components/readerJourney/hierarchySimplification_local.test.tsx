import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { buildFixture13Scenes } from "./mockVisualizationFixtures";
import { OBSERVATION_LENSES } from "./observationLenses";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

afterEach(() => {
  cleanup();
  document.getElementById("journey-overlay-root")?.remove();
});

const css = readFileSync(resolve(__dirname, "./readerJourney.css"), "utf8");

describe("Reader Journey hierarchy simplification", () => {
  it("uses a unified topbar: lenses left, 收起详情 + 对比分析 right", () => {
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
    expect(screen.queryByTestId("journey-summary-cards")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-curve-legend")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-lens-how-to-trigger")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-more-chart-settings")).not.toBeInTheDocument();
    expect(screen.queryByText("更多操作")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-lens-active-hint")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-chart-analysis-tools")).not.toBeInTheDocument();

    const toolbar = screen.getByTestId("journey-curve-toolbar");
    const lenses = screen.getByTestId("journey-lens-selector-list");
    const actions = screen.getByTestId("journey-toolbar-right");
    expect(within(lenses).getAllByRole("radio")).toHaveLength(OBSERVATION_LENSES.length);
    expect(screen.getByTestId("journey-lens-composite")).toHaveAttribute("aria-current", "true");
    expect(within(toolbar).getByTestId("journey-inspector-toggle")).toHaveTextContent(
      /收起详情|展开详情/,
    );
    expect(within(toolbar).getByTestId("journey-overlay-composite")).toHaveTextContent("对比分析");
    expect(within(lenses).queryByText("对比分析")).not.toBeInTheDocument();
    expect(actions.contains(screen.getByTestId("journey-overlay-composite"))).toBe(true);
    expect(actions.contains(screen.getByTestId("journey-inspector-toggle"))).toBe(true);

    const region = screen.getByTestId("journey-toolbar-region");
    expect(region).toHaveAttribute("data-topbar", "unified");
    expect(css).toMatch(/\.journey-topbar__row[\s\S]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+auto/);

    const inspector = screen.getByTestId("journey-inspector-toggle");
    const compare = screen.getByTestId("journey-overlay-composite");
    const lensBtn = screen.getByTestId("journey-lens-composite");
    expect(inspector.className).toContain("journey-lens-segment");
    expect(compare.className).toContain("journey-lens-segment");
    expect(lensBtn.className).toContain("journey-lens-segment");

    expect(screen.getByTestId("journey-unified-legend")).toHaveAttribute(
      "data-legend-placement",
      "above-chart",
    );
    const oneLiner = screen.getByTestId("journey-lens-one-liner");
    expect(oneLiner.textContent).toMatch(/^综合阅读：/);
    expect(oneLiner.textContent).toContain("不代表一定写得差");
    // Only one explanation paragraph — no duplicate bare summary
    expect(screen.queryAllByTestId("journey-lens-one-liner")).toHaveLength(1);
  });

  it("toggles inspector label and exits compare from the same topbar slot", () => {
    render(
      <MemoryRouter initialEntries={["/?overview=curve"]}>
        <ReaderJourneyWorkspace
          visualization={buildFixture13Scenes()}
          onLocateEvidence={vi.fn()}
        />
      </MemoryRouter>,
    );
    const toggle = screen.getByTestId("journey-inspector-toggle");
    const first = toggle.textContent || "";
    fireEvent.click(toggle);
    const second = toggle.textContent || "";
    expect(first).not.toBe(second);
    expect(second).toMatch(/收起详情|展开详情/);
    fireEvent.click(toggle);
    expect(toggle).toHaveTextContent(first);

    fireEvent.click(screen.getByTestId("journey-overlay-composite"));
    fireEvent.click(screen.getByTestId("journey-compare-arousal"));
    fireEvent.click(screen.getByTestId("journey-compare-confirm"));
    expect(screen.getByTestId("journey-comparison-toolbar")).toBeInTheDocument();
    const exit = within(screen.getByTestId("journey-toolbar-right")).getByTestId(
      "journey-comparison-exit",
    );
    expect(exit).toHaveTextContent("退出对比");
    expect(exit.className).toMatch(/active/);
    fireEvent.click(exit);
    expect(screen.queryByTestId("journey-comparison-toolbar")).not.toBeInTheDocument();
    expect(screen.getByTestId("journey-overlay-composite")).toHaveTextContent("对比分析");
  });

  it("hides empty phase cards and compare on 钩子回收 lens", () => {
    render(
      <MemoryRouter initialEntries={["/?overview=curve&lens=hook_payoff"]}>
        <ReaderJourneyWorkspace
          visualization={buildFixture13Scenes()}
          onLocateEvidence={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("journey-lens-hook_payoff")).toHaveAttribute("aria-current", "true");
    expect(screen.queryByTestId("journey-phase-strip-wrap")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-overlay-composite")).not.toBeInTheDocument();
    expect(screen.getByTestId("journey-inspector-toggle")).toBeInTheDocument();
    expect(screen.getByTestId("journey-lens-one-liner").textContent).toMatch(/^钩子回收：/);
  });

  it("keeps right actions visible at 1024px while lenses may scroll", () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 1024 });
    render(
      <MemoryRouter initialEntries={["/?overview=curve"]}>
        <ReaderJourneyWorkspace
          visualization={buildFixture13Scenes()}
          onLocateEvidence={vi.fn()}
        />
      </MemoryRouter>,
    );
    const actions = screen.getByTestId("journey-toolbar-right");
    expect(actions).toBeVisible();
    expect(within(actions).getByTestId("journey-overlay-composite")).toBeVisible();
    expect(css).toMatch(/\.journey-topbar\s+\.journey-lens-selector-list[\s\S]*overflow-x:\s*auto/);
  });

  it("keeps topbar single-row contract under zoom-like narrow action budgets", () => {
    // Approximate 150% / 200% usable width shrinkage without full browser zoom.
    for (const width of [1024 / 1.5, 1024 / 2] as const) {
      Object.defineProperty(window, "innerWidth", {
        configurable: true,
        value: Math.floor(width),
      });
      cleanup();
      render(
        <MemoryRouter initialEntries={["/?overview=curve"]}>
          <ReaderJourneyWorkspace
            visualization={buildFixture13Scenes()}
            onLocateEvidence={vi.fn()}
          />
        </MemoryRouter>,
      );
      const region = screen.getByTestId("journey-toolbar-region");
      const actions = screen.getByTestId("journey-toolbar-right");
      expect(region).toHaveAttribute("data-topbar", "unified");
      expect(within(actions).getByTestId("journey-inspector-toggle")).toBeInTheDocument();
      expect(within(actions).getByTestId("journey-overlay-composite")).toBeInTheDocument();
      expect(css).toMatch(/flex-wrap:\s*nowrap/);
    }
  });
});
