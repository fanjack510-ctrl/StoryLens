import { describe, expect, it } from "vitest";
import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";
import {
  assertMainStatusPartition,
  buildChapterVerdict,
  buildHookResolutionModel,
  conflictDivergencePlain,
  resolveHookMainStatus,
} from "./hookResolutionModel";

function baseViz(loops: unknown[]): ReaderJourneyVisualization {
  return {
    visualization_version: "test",
    chapter_summary: {
      chapter_id: 1,
      chapter_title: "t",
      diagnosis: "d",
      primary_traction: "p",
      strongest_payoff: null,
      strongest_hook: null,
      weak_interval: "",
      counts: {
        scene_count: 5,
        phase_count: 1,
        question_chain_count: 0,
        canonical_chain_count: 0,
        core: 5,
        secondary: 0,
        beat: 0,
      },
      peaks: {
        engagement_peak: { scene_ordinal: 1, value: 90 },
        engagement_valley: { scene_ordinal: 2, value: 10 },
        curiosity_peak: { scene_ordinal: 1, value: 80 },
        tension_peak: { scene_ordinal: 1, value: 70 },
        emotional_peak: { scene_ordinal: 1, value: 60 },
      },
    },
    scene_nodes: Array.from({ length: 5 }, (_, i) => ({
      scene_id: i + 1,
      scene_ordinal: i + 1,
      role: "core",
      scores: {},
    })),
    curve_series: {},
    phases: [],
    question_chains: [],
    canonical_chains: [],
    hook_markers: [],
    payoff_markers: [],
    risk_intervals: [],
    narrative_loops: loops,
    reading_resistance: [],
  } as unknown as ReaderJourneyVisualization;
}

describe("hookResolutionModel main status + stats", () => {
  it("keeps A+B+C=N and treats conflict as additive", () => {
    const model = buildHookResolutionModel(
      baseViz([
        {
          loop_id: "L1",
          question: "他是谁",
          open_from_scene: 1,
          hook: [{ scene_ordinal: 1, type: "new" }],
          payoffs: [{ scene_ordinal: 3, type: "full", summary: "揭晓" }],
          status: "resolved",
          display_status: "resolved",
          consistency_status: "consistent",
          conflicts: [],
          primary_relation: {
            grade: "confirmed",
            payoff_ref: { scene_ordinal: 3, type: "full" },
          },
        },
        {
          loop_id: "L2",
          question: "父母异常",
          open_from_scene: 2,
          hook: [{ scene_ordinal: 2, type: "new" }],
          payoffs: [{ scene_ordinal: 4, type: "partial", summary: "部分" }],
          status: "partially_resolved",
          display_status: "partially_resolved",
          consistency_status: "soft_conflict",
          soft_conflict: true,
          conflicts: [{ code: "payoff_score_without_entity", message: "分数与实体不一致" }],
          primary_relation: {
            grade: "probable",
            payoff_ref: { scene_ordinal: 4, type: "partial" },
          },
        },
        {
          loop_id: "L3",
          question: "危险来源",
          open_from_scene: 1,
          hook: [{ scene_ordinal: 1, type: "new" }],
          payoffs: [],
          status: "open",
          display_status: "open",
          consistency_status: "consistent",
          conflicts: [],
        },
      ]),
    );
    expect(assertMainStatusPartition(model.stats)).toBe(true);
    expect(model.stats).toEqual({
      established: 3,
      resolved: 1,
      partial: 1,
      unresolved: 1,
      conflict: 1,
    });
    expect(model.stats.resolved + model.stats.partial + model.stats.unresolved).toBe(
      model.stats.established,
    );
    expect(model.conflicts).toHaveLength(1);
    expect(model.rows.every((r) => Boolean(r.main_status))).toBe(true);
    expect(model.verdict).toMatch(
      /本章建立 3 个钩子，已回收 1 个，部分回收 1 个，未回收 1 个，其中 1 个存在判定冲突/,
    );
    const conflictRow = model.rows.find((r) => r.loop_id === "L2");
    expect(conflictRow?.has_conflict).toBe(true);
    expect(conflictRow?.conflict_divergence_plain).toBeTruthy();
    expect(conflictRow?.why_judgment_plain).toMatch(/部分回应/);
  });

  it("maps payoff_score empty payoffs[] to ordinary Chinese", () => {
    const plain = conflictDivergencePlain({
      loop_id: "q5",
      question: "冲突",
      open_from_scene: 1,
      hook: [{ scene_ordinal: 1 }],
      payoffs: [],
      status: "open",
      display_status: "open",
      soft_conflict: true,
      consistency_status: "soft_conflict",
      conflicts: [
        {
          code: "payoff_score_without_entity",
          message: "Scene 5: payoff_score=80 but payoffs[] is empty",
        },
      ],
      primary_relation: {
        grade: "candidate",
        payoff_ref: { scene_ordinal: 5, type: "score_inferred", source_type: "score_inferred" },
      },
    } as never);
    expect(plain).toMatch(/分数提示可能存在回报/);
    expect(plain).not.toMatch(/payoff_score/);
  });

  it("buildChapterVerdict hides conflict clause when zero", () => {
    expect(
      buildChapterVerdict({
        established: 2,
        resolved: 1,
        partial: 0,
        unresolved: 1,
        conflict: 0,
      }),
    ).toBe("本章建立 2 个钩子，已回收 1 个，部分回收 0 个，未回收 1 个。");
  });

  it("gives one main status even under hard conflict", () => {
    const loop = {
      loop_id: "Lx",
      question: "冲突钩子",
      open_from_scene: 1,
      hook: [{ scene_ordinal: 1 }],
      payoffs: [{ scene_ordinal: 2, type: "partial" }],
      status: "inconsistent",
      display_status: "inconsistent",
      hard_blocked: true,
      consistency_status: "inconsistent",
      conflicts: [{ code: "no_text_evidence", message: "缺少文本证据" }],
      primary_relation: {
        grade: "probable",
        payoff_ref: { scene_ordinal: 2, type: "partial" },
      },
    };
    const result = resolveHookMainStatus(loop as never);
    expect(result.main_status).toBe("partial");
    expect(result.has_conflict).toBe(true);
    const model = buildHookResolutionModel(baseViz([loop]));
    expect(model.rows).toHaveLength(1);
    expect(model.rows[0].main_status).toBe("partial");
    expect(model.rows[0].has_conflict).toBe(true);
    expect(model.conflicts[0].main_label).toBe("部分回收");
  });

  it("does not treat score_inferred alone as resolved", () => {
    const result = resolveHookMainStatus({
      loop_id: "Ls",
      question: "弱候选",
      open_from_scene: 1,
      hook: [{ scene_ordinal: 1 }],
      payoffs: [],
      status: "open",
      display_status: "open",
      consistency_status: "soft_conflict",
      soft_conflict: true,
      conflicts: [],
      primary_relation: {
        grade: "candidate",
        payoff_ref: {
          scene_ordinal: 3,
          type: "score_inferred",
          source_type: "score_inferred",
        },
      },
    } as never);
    expect(result.main_status).toBe("unresolved");
  });

  it("returns empty model without fake chart rows", () => {
    const model = buildHookResolutionModel(baseViz([]));
    expect(model.empty).toBe(true);
    expect(model.stats.established).toBe(0);
    expect(model.rows).toHaveLength(0);
  });
});
