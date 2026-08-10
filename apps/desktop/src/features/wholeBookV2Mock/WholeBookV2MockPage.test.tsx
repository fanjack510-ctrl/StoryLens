import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { WholeBookV2MockPage } from "./WholeBookV2MockPage";
import { WholeBookV2ProgressMockPage } from "./WholeBookV2ProgressMockPage";
import { buildMockWholeBookAnalysisV2 } from "../wholeBookV2/mockAdapter";
import { MODULES } from "../wholeBookV2/presentation/modules";

afterEach(cleanup);

describe("Whole-Book V2 static mock", () => {
  it("buildMockWholeBookAnalysisV2 passes parseWholeBookV2", () => {
    const data = buildMockWholeBookAnalysisV2();
    expect(data.schema_version).toBe("whole-book-analysis-v2.0");
    expect(data.story.structure_stages.length).toBeGreaterThan(0);
    expect(data.characters.protagonist.stages.length).toBeGreaterThan(0);
    expect(data.pacing.event_markers.length).toBeGreaterThan(0);
  });

  it("uses shared ReportView with seven approved modules", () => {
    render(
      <MemoryRouter>
        <WholeBookV2MockPage />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("whole-book-v2-mock")).toBeInTheDocument();
    expect(screen.getByTestId("whole-book-v2-report")).toBeInTheDocument();
    expect(screen.getAllByText("作品画像").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("navigation", { name: "全书分析模块" }).querySelectorAll("button")).toHaveLength(7);
    for (const mod of MODULES) {
      expect(screen.getByRole("button", { name: new RegExp(mod.label) })).toBeInTheDocument();
    }
    expect(screen.queryByRole("button", { name: /类型专项/ })).not.toBeInTheDocument();
    expect(screen.getByText("故事骨架 Timeline")).toBeInTheDocument();
  });

  it("renders pacing and chapters via shared ReportView", () => {
    render(
      <MemoryRouter>
        <WholeBookV2MockPage />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: /节奏/ }));
    expect(screen.getByRole("img", { name: "全书节奏曲线" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /章节/ }));
    expect(screen.getByText(/聚合展示热力图/)).toBeInTheDocument();
  });

  it("renders comprehensive assessment module", () => {
    render(
      <MemoryRouter>
        <WholeBookV2MockPage />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: /综合诊断/ }));
    expect(screen.getByText("六维评估")).toBeInTheDocument();
    expect(screen.getByText("修改优先级")).toBeInTheDocument();
  });

  it("reveals protagonist cost and gain in characters module", () => {
    render(
      <MemoryRouter>
        <WholeBookV2MockPage />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: /^3人物$|^3 人物$/ }));
    fireEvent.click(screen.getByRole("button", { name: "主角历程" }));
    expect(screen.getByText("付出 COST")).toBeInTheDocument();
    expect(screen.getByText("获得 GAIN")).toBeInTheDocument();
  });

  it("renders the complete progress surface", () => {
    render(
      <MemoryRouter>
        <WholeBookV2ProgressMockPage />
      </MemoryRouter>,
    );
    expect(screen.getByText("63%")).toBeInTheDocument();
    expect(screen.getByText("最终报告")).toBeInTheDocument();
    expect(screen.getByText("当前累计费用")).toBeInTheDocument();
  });
});
