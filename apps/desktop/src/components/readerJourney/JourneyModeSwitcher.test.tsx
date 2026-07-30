import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { JourneyModeSwitcher } from "./JourneyModeSwitcher";
import {
  parseJourneyViewMode,
  resolveJourneyPageModeFromSearch,
  journeyViewToPageMode,
  pageModeToJourneyView,
} from "./journeyViewMode";
import { WorkspaceViewSwitcher } from "../layout/WorkspaceViewSwitcher";

afterEach(cleanup);

describe("journeyViewMode", () => {
  it("defaults and maps illegal values to compare", () => {
    expect(parseJourneyViewMode(null)).toBe("compare");
    expect(parseJourneyViewMode("nope")).toBe("compare");
    expect(parseJourneyViewMode("compare")).toBe("compare");
    expect(parseJourneyViewMode("journey")).toBe("journey");
    expect(parseJourneyViewMode("text")).toBe("text");
  });

  it("maps pageMode aliases", () => {
    expect(journeyViewToPageMode("compare")).toBe("sync");
    expect(journeyViewToPageMode("text")).toBe("reading");
    expect(pageModeToJourneyView("sync")).toBe("compare");
    expect(pageModeToJourneyView("reading")).toBe("text");
  });

  it("prefers journeyView over legacy mode", () => {
    const params = new URLSearchParams("mode=journey&journeyView=text");
    expect(resolveJourneyPageModeFromSearch(params)).toBe("reading");
  });

  it("falls back to legacy mode when journeyView absent", () => {
    expect(resolveJourneyPageModeFromSearch(new URLSearchParams("mode=journey"))).toBe(
      "journey",
    );
    expect(resolveJourneyPageModeFromSearch(new URLSearchParams())).toBe("sync");
  });
});

describe("JourneyModeSwitcher", () => {
  it("renders 正文对照 / 旅程视图 / 仅看正文 — never 正文阅读", () => {
    const onChange = vi.fn();
    render(<JourneyModeSwitcher pageMode="sync" onChange={onChange} />);
    expect(screen.getByTestId("journey-mode-sync")).toHaveTextContent("正文对照");
    expect(screen.getByTestId("journey-mode-journey")).toHaveTextContent("旅程视图");
    expect(screen.getByTestId("journey-mode-reading")).toHaveTextContent("仅看正文");
    expect(screen.queryByText("正文阅读")).not.toBeInTheDocument();
    screen.getByTestId("journey-mode-journey").click();
    expect(onChange).toHaveBeenCalledWith("journey");
  });
});

describe("WorkspaceViewSwitcher primary nav", () => {
  it("shows 正文阅读 and 阅读旅程 without 场景分析 by default (CHG-011)", () => {
    render(
      <WorkspaceViewSwitcher
        active="journey"
        onChange={() => undefined}
        journeyAvailable
      />,
    );
    expect(screen.getAllByText("正文阅读")).toHaveLength(1);
    expect(screen.queryByTestId("workspace-tab-analysis")).not.toBeInTheDocument();
    expect(screen.getByTestId("workspace-tab-journey")).toHaveTextContent("阅读旅程");
  });

  it("shows 场景分析 only when showAnalysisTab is true", () => {
    render(
      <WorkspaceViewSwitcher
        active="analysis"
        onChange={() => undefined}
        showAnalysisTab
        journeyAvailable
      />,
    );
    expect(screen.getByTestId("workspace-tab-analysis")).toHaveTextContent("场景分析");
  });

  it("CHG-017: journeyPrimary marks 阅读旅程 as green primary, not dual with progress", () => {
    render(
      <WorkspaceViewSwitcher
        active="journey"
        onChange={() => undefined}
        journeyAvailable
        journeyPrimary
      />,
    );
    const journey = screen.getByTestId("workspace-tab-journey");
    expect(journey.className).toContain("primary");
    expect(journey).toHaveAttribute("data-nav-primary", "true");
  });

  it("CHG-017: running journey tab stays secondary (no primary class)", () => {
    render(
      <WorkspaceViewSwitcher
        active="reading"
        onChange={() => undefined}
        journeyInProgress
        showJourneyTab
      />,
    );
    const journey = screen.getByTestId("workspace-tab-journey");
    expect(journey.className).not.toContain("primary");
    expect(journey).toHaveAttribute("data-nav-primary", "false");
  });
});
