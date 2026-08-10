import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { buildMockWholeBookAnalysisV2 } from "./mockAdapter";
import { MODULES } from "./presentation/modules";
import { WholeBookV2ReportView } from "./presentation/WholeBookV2ReportView";

afterEach(cleanup);

describe("WholeBookV2ReportView", () => {
  const data = buildMockWholeBookAnalysisV2();

  it("renders all seven modules with formal nav labels", () => {
    const seen = new Set<string>();
    const { rerender } = render(
      <WholeBookV2ReportView
        data={data}
        activeModule="overview"
        onModuleChange={() => {}}
        mode="formal"
      />,
    );

    expect(screen.getByTestId("whole-book-v2-report")).toHaveAttribute("data-module", "overview");
    const nav = screen.getByRole("navigation", { name: "全书分析模块" });
    expect(within(nav).getAllByRole("button")).toHaveLength(7);
    for (const mod of MODULES) {
      expect(within(nav).getByRole("button", { name: new RegExp(mod.label) })).toBeInTheDocument();
    }

    for (const mod of MODULES) {
      rerender(
        <WholeBookV2ReportView
          data={data}
          activeModule={mod.key}
          onModuleChange={() => {}}
          mode="formal"
        />,
      );
      seen.add(mod.key);
      expect(screen.getByTestId("whole-book-v2-report")).toHaveAttribute("data-module", mod.key);
    }
    expect(seen.size).toBe(7);
  });

  it("does not show DEV badge or mock strings in formal mode", () => {
    render(
      <WholeBookV2ReportView
        data={data}
        activeModule="overview"
        onModuleChange={() => {}}
        mode="formal"
      />,
    );
    expect(screen.queryByText("DEV")).not.toBeInTheDocument();
    expect(screen.queryByText(/DEV Mock/i)).not.toBeInTheDocument();
    expect(screen.queryByText("CURVE HOVER DETAIL")).not.toBeInTheDocument();
  });

  it("shows protagonist arc cost/gain in characters module", () => {
    render(
      <WholeBookV2ReportView
        data={data}
        activeModule="characters"
        onModuleChange={() => {}}
        mode="formal"
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "主角历程" }));
    expect(screen.getByText("付出 COST")).toBeInTheDocument();
    expect(screen.getByText("获得 GAIN")).toBeInTheDocument();
    expect(data.characters.protagonist.stages.length).toBeGreaterThan(0);
  });

  it("renders pacing chart with event markers", () => {
    render(
      <WholeBookV2ReportView
        data={data}
        activeModule="pacing"
        onModuleChange={() => {}}
        mode="formal"
      />,
    );
    expect(screen.getByRole("img", { name: "全书节奏曲线" })).toBeInTheDocument();
    expect(data.pacing.event_markers.length).toBeGreaterThan(0);
  });

  it("uses shared report component from fixture via mockAdapter", () => {
    expect(data.schema_version).toBe("whole-book-analysis-v2.0");
    expect(data.book_metadata.title).toBeTruthy();
  });
});
