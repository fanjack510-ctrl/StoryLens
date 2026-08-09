import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { WholeBookV2MockPage } from "./WholeBookV2MockPage";
import { WholeBookV2ProgressMockPage } from "./WholeBookV2ProgressMockPage";
import { chapterHeatmap, characters, diagnoses, hookLifecycles, relationships, storyStages, storylines } from "./wholeBookV2MockData";
import { assessmentIssues, assessmentStrengths, characterDetails, dimensionAssessments, growthTracks, hookDetails, pacingMarkers, protagonistArcDetails, revisionPriorities, richDiagnoses, richOverview, storyStageDetails, workProfile } from "./wholeBookV2MockEnrichment";

afterEach(cleanup);

describe("Whole-Book V2 static mock", () => {
  it("provides the required long-book dataset", () => {
    expect(storyStages.length).toBeGreaterThanOrEqual(8);
    expect(storylines.length).toBeGreaterThanOrEqual(6);
    expect(characters.length).toBeGreaterThanOrEqual(12);
    expect(relationships.length).toBeGreaterThanOrEqual(15);
    expect(hookLifecycles.length).toBeGreaterThanOrEqual(10);
    expect(chapterHeatmap).toHaveLength(26);
    expect(diagnoses.length).toBeGreaterThanOrEqual(12);
    expect(richOverview.synopsis.length).toBeGreaterThanOrEqual(300);
    expect(storyStageDetails).toHaveLength(9);
    expect(storyStageDetails.every((stage) => stage.summary.length >= 200 && stage.evidence.length >= 3)).toBe(true);
    expect(protagonistArcDetails).toHaveLength(10);
    expect(protagonistArcDetails.every((stage) => stage.cost_paid && stage.gain_received && stage.evidence.length)).toBe(true);
    expect(growthTracks).toHaveLength(4);
    expect(characterDetails.every((character) => character.key_events.length >= 5)).toBe(true);
    expect(hookDetails.every((hook) => hook.clues.length && hook.payoff && hook.evidence.length)).toBe(true);
    expect(pacingMarkers.length).toBeGreaterThanOrEqual(12);
    expect(richDiagnoses.every((item) => item.supporting_metrics.length && item.possible_direction)).toBe(true);
    expect(dimensionAssessments).toHaveLength(6);
    expect(assessmentStrengths.length).toBeGreaterThanOrEqual(6);
    expect(assessmentIssues.length).toBeGreaterThanOrEqual(12);
    expect(revisionPriorities).toHaveLength(3);
  });
  it("keeps seven approved modules and removes the fixed type tab", () => {
    render(<MemoryRouter><WholeBookV2MockPage /></MemoryRouter>);
    expect(screen.getAllByText("作品画像").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(workProfile.plainSummary)).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "全书分析模块" }).querySelectorAll("button")).toHaveLength(7);
    expect(screen.queryByRole("button", { name: /类型专项/ })).not.toBeInTheDocument();
    expect(screen.getByText("故事骨架 Timeline")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /节奏/ }));
    expect(screen.getByRole("img", { name: "第 1 至 1299 章节奏曲线" })).toBeInTheDocument();
    expect(screen.getByText("CURVE HOVER DETAIL")).toBeInTheDocument();
    expect(screen.getByText("Chapter Range Detail")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /章节/ }));
    expect(screen.getByText(/仅展示选中区间内 5 个代表章节/)).toBeInTheDocument();
  });
  it("renders the comprehensive assessment with strengths, issue map and priorities", () => {
    render(<MemoryRouter><WholeBookV2MockPage /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: /综合评估/ }));
    expect(screen.getByText("六维评估")).toBeInTheDocument();
    expect(screen.getByText("全书问题地图")).toBeInTheDocument();
    expect(screen.getByText("修改优先级")).toBeInTheDocument();
    expect(screen.getByText("建议保留、不应轻易修改的设计")).toBeInTheDocument();
  });
  it("reveals full protagonist cost, gain and four-track growth", () => {
    render(<MemoryRouter><WholeBookV2MockPage /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: /^3人物$|^3 人物$/ }));
    fireEvent.click(screen.getByRole("button", { name: "主角历程" }));
    expect(screen.getByText("付出 COST")).toBeInTheDocument();
    expect(screen.getByText("获得 GAIN")).toBeInTheDocument();
    expect(screen.getByText("四轨成长 · 与主时间线对齐")).toBeInTheDocument();
    expect(screen.getByText("外在身份 / 社会位置")).toBeInTheDocument();
  });
  it("renders the complete progress surface", () => {
    render(<MemoryRouter><WholeBookV2ProgressMockPage /></MemoryRouter>);
    expect(screen.getByText("63%")).toBeInTheDocument();
    expect(screen.getByText("最终报告")).toBeInTheDocument();
    expect(screen.getByText("当前累计费用")).toBeInTheDocument();
    expect(screen.getByText("模型等待秒数")).toBeInTheDocument();
  });
});
