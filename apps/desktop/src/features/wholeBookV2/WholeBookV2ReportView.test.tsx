import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { buildMockWholeBookAnalysisV2 } from "./mockAdapter";
import { modulesForDocument } from "./presentation/modules";
import { WholeBookV2ReportView } from "./presentation/WholeBookV2ReportView";

afterEach(cleanup);

describe("WholeBookV2ReportView", () => {
  const data = buildMockWholeBookAnalysisV2();

  // 评测文档没有拆文，拆文文档没有总览和综合诊断——导航按文档实际有什么来排。
  const assessmentModules = modulesForDocument(data);

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
    for (const mod of assessmentModules) {
      expect(within(nav).getByRole("button", { name: new RegExp(mod.label) })).toBeInTheDocument();
    }

    for (const mod of assessmentModules) {
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

  // 拆文报告曾经把「拆文」的九段内容整个丢掉，只留下总览和综合诊断两张空白页——
  // 空白页正是这次要修的东西，所以这里同时断言「有拆文」和「没有那两页」。
  it("swaps overview and assessment for 拆文 when the document is a breakdown", () => {
    const breakdown = {
      ...data,
      // A real 拆文 run leaves these two nearly empty; that emptiness — not the mode — is
      // what removes their tabs.
      overview: { ...data.overview, one_sentence_story: "", full_summary: "" },
      assessment: { ...data.assessment, overall_summary: "", issues: [] },
      story_breakdown: {
        four_beats: [
          {
            beat: "起",
            title: "两人第一次同处一室",
            summary: "把气味写成距离。",
            chapter_start: 1,
            chapter_end: 8,
            evidence: [],
          },
        ],
        standout_moments: [
          {
            rank: 1,
            title: "他闻到了",
            quote: "空气忽然变甜",
            why_it_lands: "第一次把设定用在情绪上。",
            chapter: 12,
            evidence: [],
          },
        ],
        moment_count_rationale: "只有十处真正推动了关系。",
        chapter_hooks: [{ chapter: 1, question: "他为什么不躲", evidence: [] }],
        reusable_techniques: [
          {
            name: "气味代替独白",
            what_it_is: "用嗅觉写心理",
            why_it_works: "省掉解释",
            transfers_to: "任何有身体感官的设定",
          },
        ],
        supporting_cast: [
          { name: "室友", function: "把秘密说破", stays_in_lane: "是", evidence: [] },
        ],
        cast_note: "配角都只服务一条线。",
      },
    } as never;

    render(
      <WholeBookV2ReportView
        data={breakdown}
        activeModule="beats"
        onModuleChange={() => {}}
        mode="formal"
      />,
    );
    const nav = screen.getByRole("navigation", { name: "全书分析模块" });
    // 拆文现在是顶层四页，不再是一个页签折着五个小标签——同一份内容在 PDF 里是三个正章，
    // 屏幕上却要点两层才看得到。
    for (const label of ["起承转合", "打动人的瞬间", "每章问题", "手法与配角"]) {
      expect(within(nav).getByRole("button", { name: new RegExp(label) })).toBeInTheDocument();
    }
    expect(within(nav).queryByRole("button", { name: /全书总览/ })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("button", { name: /综合诊断/ })).not.toBeInTheDocument();
    expect(screen.getByText("两人第一次同处一室")).toBeInTheDocument();
  });

  // A 拆文 run that also wrote a 全书总览 keeps it. Keying the nav off the mode instead of the
  // content would throw that away.
  it("keeps 全书总览 when a breakdown document also filled it", () => {
    const both = {
      ...data,
      story_breakdown: { four_beats: [{ beat: "起", title: "开场", summary: "", chapter_start: 1, chapter_end: 2, evidence: [] }] },
    } as never;
    render(
      <WholeBookV2ReportView data={both} activeModule="overview" onModuleChange={() => {}} mode="formal" />,
    );
    const nav = screen.getByRole("navigation", { name: "全书分析模块" });
    expect(within(nav).getByRole("button", { name: /全书总览/ })).toBeInTheDocument();
    // 拆文现在是顶层四页，不再是一个页签折着五个小标签——同一份内容在 PDF 里是三个正章，
    // 屏幕上却要点两层才看得到。
    for (const label of ["起承转合", "打动人的瞬间", "每章问题", "手法与配角"]) {
      expect(within(nav).getByRole("button", { name: new RegExp(label) })).toBeInTheDocument();
    }
  });

  // An empty `story_breakdown` block is what a 评测 run writes; it must not earn a tab.
  it("hides 拆文 when the breakdown block is present but empty", () => {
    const empty = { ...data, story_breakdown: { four_beats: [], standout_moments: [] } } as never;
    render(
      <WholeBookV2ReportView data={empty} activeModule="overview" onModuleChange={() => {}} mode="formal" />,
    );
    const nav = screen.getByRole("navigation", { name: "全书分析模块" });
    expect(within(nav).queryByRole("button", { name: /起承转合/ })).not.toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: /综合诊断/ })).toBeInTheDocument();
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
