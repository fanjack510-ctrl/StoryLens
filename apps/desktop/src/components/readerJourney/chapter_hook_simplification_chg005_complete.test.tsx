/**
 * CHG-20260729-005 complete — sections 11–19 coverage + 6-scene fixture.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";
import { HookPayoffTimeline } from "./HookPayoffTimeline";
import {
  buildChapterHookSimplificationModel,
  deriveChapterEndingPullV1,
  deriveChapterHookSceneInsightV1,
  selectImportantChapterHooks,
} from "./chapterHookSimplification";
import { getNarrativeLoops, type NarrativeLoopView } from "./narrativeLoopView";
import { JOURNEY_STAGE_VISUAL_TOKENS } from "./journeyVisualTokens";
import { JourneySceneDetailPanel } from "./JourneySceneDetailPanel";
import { chg005CompleteFixtureViz } from "./chg005CompleteFixture";

afterEach(() => {
  cleanup();
});

describe("CHG-20260729-005 complete sections 11–19", () => {
  it("fixture overview and scene labels match expected pattern", () => {
    const model = buildChapterHookSimplificationModel(chg005CompleteFixtureViz());
    expect(model.overview.raised).toBe(2);
    expect(model.overview.answered).toBe(1);
    expect(model.overview.chapter_pull).toBe("明确");
    const labels = model.scene_rows.map((r) => r.short_label);
    expect(labels).toEqual([
      "提出疑问",
      "加深悬念",
      "给出回应",
      "提出疑问",
      "加深悬念",
      "留到下章",
    ]);
    expect(model.summary_line).not.toMatch(/本章提出 \d+ 个/);
  });

  it("important hooks: max 3, reader questions, result labels, no smoke-fake/ids in copy", () => {
    const viz = chg005CompleteFixtureViz();
    const loops = getNarrativeLoops(viz);
    const important = selectImportantChapterHooks(loops, 6, 3);
    expect(important.length).toBeGreaterThan(0);
    expect(important.length).toBeLessThanOrEqual(3);
    const a = selectImportantChapterHooks(loops, 6, 3);
    const b = selectImportantChapterHooks(loops, 6, 3);
    expect(a.map((h) => h.loop_id)).toEqual(b.map((h) => h.loop_id));
    for (const h of important) {
      expect(h.reader_question).not.toMatch(/smoke-fake|hook_0/i);
      expect(["已回应", "部分回应", "继续保留", "暂无可靠判断"]).toContain(h.result_label);
      expect(h.last_change_scene).toBeGreaterThanOrEqual(h.open_scene);
    }
    // Protagonist / conflict preference: identity or danger near top
    expect(important[0].reader_question).toMatch(/主角|门外|谁|为什么/);
  });

  it("ending pull derives status and stays within 120 chars without provider", () => {
    const loops = getNarrativeLoops(chg005CompleteFixtureViz());
    const pull = deriveChapterEndingPullV1(loops, 6);
    expect(pull.status).toBe("明确");
    expect(pull.judgment).toBeTruthy();
    const blob = `${pull.left_behind || ""}${pull.reader_wants || ""}${pull.judgment || ""}`;
    expect(Array.from(blob).length).toBeLessThanOrEqual(120);

    const closed = deriveChapterEndingPullV1(
      loops.map((l) => ({
        ...l,
        status: "resolved",
        display_status: "resolved",
        payoffs: [
          ...(l.payoffs || []),
          { scene_ordinal: 6, type: "full", summary: "收束" },
        ],
        primary_relation: {
          grade: "confirmed",
          payoff_ref: { scene_ordinal: 6, type: "full" },
        },
      })) as unknown as NarrativeLoopView[],
      6,
    );
    expect(["暂无", "无法判断", "较弱"]).toContain(closed.status);

    expect(deriveChapterEndingPullV1([], 6).status).toBe("无法判断");

    // Mid-chapter unresolved only — must not become 章末牵引.
    const midOnly = deriveChapterEndingPullV1(
      [
        {
          loop_id: "mid-only",
          question: "信封里写了什么？",
          open_from_scene: 1,
          hook: [{ scene_ordinal: 1, type: "new", summary: "信封", strength: 70 }],
          developments: [],
          payoffs: [],
          status: "open",
          display_status: "open",
          consistency_status: "consistent",
          conflicts: [],
        },
      ] as unknown as NarrativeLoopView[],
      6,
    );
    expect(midOnly.status).toBe("暂无");
  });

  it("right panel scene insight covers four node kinds without tech fields", () => {
    const viz = chg005CompleteFixtureViz();
    for (const ordinal of [1, 2, 3, 6]) {
      const insight = deriveChapterHookSceneInsightV1({
        visualization: viz,
        sceneOrdinal: ordinal,
        node: viz.scene_nodes[ordinal - 1],
      });
      expect(insight.title).toMatch(/钩子洞察/);
      expect(insight.body).not.toMatch(/hook_id|smoke-fake|formula|L\d+/i);
      expect(Array.from(insight.body).length).toBeLessThanOrEqual(160);
      expect(insight.node_label).toBeTruthy();
    }
    const node = viz.scene_nodes[3];
    render(
      <JourneySceneDetailPanel
        node={node}
        visualization={viz}
        observationLens="hook_payoff"
        onLocateEvidence={vi.fn()}
      />,
    );
    expect(screen.getByTestId("scene-hook-insight-text")).toBeInTheDocument();
    expect(screen.queryByTestId("hook-resolution-evidence")).not.toBeInTheDocument();
    expect(screen.getByTestId("scene-detail-insight-panel").textContent).not.toMatch(
      /ID-identity|回收率|smoke-fake/,
    );
  });

  // 「normal UI hides tech table; developer mode shows collapsed tech details」删除：「技术详情」是开发者模式独有的折叠，已随该模式删除。


  it("empty and low-confidence states avoid negative quality copy", () => {
    const empty = chg005CompleteFixtureViz();
    (empty as { narrative_loops: unknown[] }).narrative_loops = [];
    render(<HookPayoffTimeline visualization={empty} />);
    expect(screen.getByTestId("hook-resolution-verdict").textContent).toContain(
      "本章未形成明确的阅读悬念",
    );
    expect(screen.getByTestId("hook-resolution-empty").textContent).not.toMatch(
      /分析失败|质量较差|回收率 0|缺少吸引力/,
    );

    cleanup();
    const weak = chg005CompleteFixtureViz();
    (weak as { narrative_loops: Array<Record<string, unknown>> }).narrative_loops = [
      {
        loop_id: "smoke-fake-1",
        question: "smoke-fake",
        open_from_scene: 1,
        hook: [{ scene_ordinal: 1, strength: 10 }],
        payoffs: [],
        status: "open",
        display_status: "open",
      },
    ];
    render(<HookPayoffTimeline visualization={weak} />);
    expect(screen.getByTestId("hook-resolution-verdict").textContent).toMatch(
      /较弱的阅读期待|未形成明确/,
    );
  });

  it("renders reader question cards and compact trajectory; stage bands preserved", () => {
    const onSelect = vi.fn();
    render(
      <HookPayoffTimeline
        visualization={chg005CompleteFixtureViz()}
        selectedSceneOrdinal={4}
        onSelectLoop={onSelect}
        onSelectScene={vi.fn()}
      />,
    );
    const card = screen.getAllByTestId("hook-chapter-question-card")[0];
    expect(card.textContent).toMatch(/S\d{2} 提出/);
    expect(card.textContent).toMatch(/部分回应|已回应|继续保留|新提出/);
    expect(screen.queryByTestId("hook-chapter-ending-pull")).not.toBeInTheDocument();
    expect(JOURNEY_STAGE_VISUAL_TOKENS.opening.chartBand).toBe("#E4F1E8");
    fireEvent.click(screen.getByTestId("hook-chapter-scene-3"));
    expect(onSelect).toHaveBeenCalled();
  });
});
