/**
 * CHG-20260729-005 hook consistency — chapter gate + respond hard gate + Fixture A/B.
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { HookPayoffTimeline } from "./HookPayoffTimeline";
import { JourneyDiagnosisBand } from "./JourneyDiagnosisBand";
import { JourneySceneDetailPanel } from "./JourneySceneDetailPanel";
import {
  buildChapterHookSimplificationModel,
  sceneHasReliableLinkedResponse,
} from "./chapterHookSimplification";
import {
  chg005FixtureAEmptyLoops,
  chg005FixtureANoReliableHooks,
  chg005FixtureBReliableHooks,
} from "./chg005HookConsistencyFixtures";
import { getNarrativeLoops, type NarrativeLoopView } from "./narrativeLoopView";
import { vi } from "vitest";

afterEach(() => {
  cleanup();
});

describe("CHG-005 hook consistency gates", () => {
  it("Fixture A (noise): uncertain mode, zeros, no respond, S05 not 明确回应", () => {
    const viz = chg005FixtureANoReliableHooks();
    const model = buildChapterHookSimplificationModel(viz);
    expect(model.chapter_hook_mode).toBe("uncertain");
    expect(model.overview.raised).toBe(0);
    expect(model.overview.answered).toBe(0);
    expect(model.overview.carried).toBe(0);
    expect(model.overview.chapter_pull).toBe("无法判断");
    expect(model.scene_actions.every((a) => a === "none")).toBe(true);
    expect(model.scene_rows.filter((r) => r.short_label).length).toBe(0);

    render(
      <>
        <HookPayoffTimeline visualization={viz} presentation={model} />
        <JourneyDiagnosisBand
          diagnoses={viz.scene_nodes.map((n) => ({
            scene_ordinal: n.scene_ordinal,
            primary_diagnosis: (n as { primary_diagnosis?: string }).primary_diagnosis,
            positive_mechanism: (n as { positive_mechanism?: string }).positive_mechanism,
            scores: n.scores,
          }))}
          selectedSceneOrdinal={5}
          observationLens="hook_payoff"
          hookPresentation={model}
          onSelectScene={() => undefined}
        />
      </>,
    );
    expect(screen.getByTestId("hook-resolution-verdict").textContent).toMatch(/较弱的阅读期待/);
    expect(screen.queryByTestId("hook-payoff-stats")).not.toBeInTheDocument();
    expect(screen.queryByTestId("hook-chapter-scene-row")).not.toBeInTheDocument();
    const s5 = screen.getByTestId("journey-diagnosis-band-s5");
    expect(s5.getAttribute("data-primary-label")).not.toMatch(/明确回应|给出回应/);
    expect(s5.getAttribute("data-primary-label")).toBe("—");
    expect(screen.getByTestId("hook-payoff-timeline").textContent).not.toMatch(
      /未发现明显异常|表现有效|回收率|smoke-fake/,
    );
  });

  it("Fixture A empty loops → none mode", () => {
    const model = buildChapterHookSimplificationModel(chg005FixtureAEmptyLoops());
    expect(model.chapter_hook_mode).toBe("none");
    expect(model.overview).toMatchObject({
      raised: 0,
      answered: 0,
      carried: 0,
      chapter_pull: "暂无",
    });
  });

  it("Fixture B: six labels + ending pull 明确 + linked respond", () => {
    const viz = chg005FixtureBReliableHooks();
    const model = buildChapterHookSimplificationModel(viz);
    expect(model.chapter_hook_mode).toBe("reliable");
    expect(model.scene_rows.map((r) => r.short_label)).toEqual([
      "提出疑问",
      "加深悬念",
      "给出回应",
      "提出疑问",
      "加深悬念",
      "留到下章",
    ]);
    expect(model.overview.chapter_pull).toBe("明确");
    expect(model.overview.answered).toBeGreaterThanOrEqual(1);
    expect(model.summary_line).not.toMatch(/本章提出 \d+ 个/);
    expect(model.reader_question_cards.length).toBeGreaterThan(0);
    expect(model.reader_question_cards[0].change_trail).toMatch(/S\d{2} 提出/);
    const identity = getNarrativeLoops(viz).find((l) => l.loop_id === "ID-identity")!;
    expect(sceneHasReliableLinkedResponse(identity, 3)).toBe(true);
  });

  it("respond hard gate: score-only / unlinked / no evidence → none", () => {
    const viz = chg005FixtureBReliableHooks();
    const loops = getNarrativeLoops(viz);
    const scoreOnly = {
      ...loops[0],
      loop_id: "score-only",
      question: "主角为什么会出现在这里？",
      payoffs: [],
      primary_relation: {
        grade: "candidate",
        payoff_ref: {
          scene_ordinal: 3,
          type: "score_inferred",
          source_type: "score_inferred",
          evidence_paragraph_ids: [],
        },
      },
    };
    expect(sceneHasReliableLinkedResponse(scoreOnly as unknown as NarrativeLoopView, 3)).toBe(false);

    const noEvidence = {
      ...loops[0],
      loop_id: "no-ev",
      payoffs: [{ scene_ordinal: 3, type: "partial", evidence_paragraph_ids: [] }],
      primary_relation: {
        grade: "probable",
        payoff_ref: {
          scene_ordinal: 3,
          type: "partial",
          evidence_paragraph_ids: [],
        },
      },
    };
    expect(sceneHasReliableLinkedResponse(noEvidence as unknown as NarrativeLoopView, 3)).toBe(false);

    const future = {
      ...loops[0],
      open_from_scene: 4,
      hook: [{ scene_ordinal: 4, type: "new", summary: "后提", strength: 80 }],
      payoffs: [
        {
          scene_ordinal: 3,
          type: "partial",
          evidence_paragraph_ids: ["B0001-C0001-P0001"],
        },
      ],
    };
    expect(sceneHasReliableLinkedResponse(future, 3)).toBe(false);
  });

  it("top response_count=0 ⇒ no scene respond; right insight matches mode", () => {
    const viz = chg005FixtureANoReliableHooks();
    const model = buildChapterHookSimplificationModel(viz);
    expect(model.overview.answered).toBe(0);
    expect(model.scene_actions.includes("respond")).toBe(false);
    render(
      <JourneySceneDetailPanel
        node={viz.scene_nodes[4]}
        visualization={viz}
        observationLens="hook_payoff"
        hookPresentation={model}
        onLocateEvidence={vi.fn()}
      />,
    );
    expect(screen.getByTestId("scene-hook-insight-text").textContent).toMatch(
      /较弱的阅读期待|暂无可靠钩子结论/,
    );
    expect(screen.getByTestId("scene-detail-insight-panel").textContent).not.toMatch(
      /明确回应/,
    );
  });

  it("reliable respond increases answered and band shows 给出回应 not 明确回应", () => {
    const viz = chg005FixtureBReliableHooks();
    const model = buildChapterHookSimplificationModel(viz);
    expect(model.overview.answered).toBeGreaterThanOrEqual(1);
    expect(model.scene_actions.includes("respond")).toBe(true);
    render(
      <JourneyDiagnosisBand
        diagnoses={viz.scene_nodes.map((n) => ({ scene_ordinal: n.scene_ordinal }))}
        selectedSceneOrdinal={3}
        observationLens="hook_payoff"
        hookPresentation={model}
        onSelectScene={() => undefined}
      />,
    );
    expect(screen.getByTestId("journey-diagnosis-band-s3").getAttribute("data-primary-label")).toBe(
      "给出回应",
    );
    expect(screen.getByTestId("journey-diagnosis-band").textContent).not.toMatch(/明确回应/);
  });
});
