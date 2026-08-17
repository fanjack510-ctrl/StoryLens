/** The page budget is the format's one hard promise, so it is the one thing pinned by a test.
 *
 * Twenty pages is not a style preference. A professional reader's first complaint about the
 * screen report was that it holds too much, and a printed report that grows with the book is
 * one nobody reads to the end. The per-chapter table is what gives way — it takes the pages
 * left over and says how many rows it dropped — so the check that matters is that a very long
 * book still fits.
 *
 * This writes the HTML to disk when STORYLENS_PRINT_OUT is set, which is how the rendered PDF
 * gets checked against a real Chromium.
 */
import { describe, expect, it } from "vitest";
import { buildPrintHtml, PAGE_BUDGET } from "./printExport";
import type { WholeBookAnalysisV2 } from "./contracts";

function book(chapters: number): WholeBookAnalysisV2 {
  const ev = Object.fromEntries(
    Array.from({ length: 40 }, (_, i) => [
      `EVD-${i}`,
      {
        evidence_id: `EVD-${i}`,
        snapshot_id: 1,
        revision_hash: "r",
        chapter_id: i + 1,
        chapter_index: i + 1,
        chapter_title: "",
        start_offset: 0,
        end_offset: 20,
        quote_or_excerpt: `第${i + 1}章里被引用的那一句话，长度大致是真实引文的样子。`,
        reason: "",
      },
    ]),
  );
  return {
    schema_version: "whole-book-analysis-v2.0",
    book_metadata: {
      book_id: 1,
      snapshot_id: 1,
      revision_hash: "revision-hash",
      title: "很长的一本书",
      chapter_count: chapters,
      character_count: chapters * 3000,
    },
    type_profile: {
      version: "2.0",
      primary_genre: "男频升级流",
      secondary_genres: [],
      narrative_drivers: [],
      narrative_traits: [],
      genre_confidence: 1,
      analysis_focus: [],
      genre_expectations: [],
      evidence: [],
    },
    overview: {
      version: "2.0",
      one_sentence_story: "一个人从最低处一路走到最高处的故事。",
      full_summary: "",
      protagonist: "主角",
      initial_state: "",
      final_state: "",
      core_goal: "",
      goal_evolution: [],
      core_conflict: "",
      conflict_evolution: [],
      core_question: "",
      major_storylines: [],
      major_turning_points: [],
      major_suspense: [],
      final_climax: "",
      ending_resolution: [],
      ending_open_questions: [],
      story_skeleton: [],
      evidence: [],
    },
    story: {
      availability: "available",
      structure_stages: Array.from({ length: 8 }, (_, i) => ({
        chapter_start: i * 10 + 1,
        chapter_end: i * 10 + 10,
        evidence: [],
        stage_id: `S${i}`,
        title: `第 ${i + 1} 阶段的标题写得比较长一点`,
        summary: "这一阶段的经过，写足一百来字的样子，用来占版面。".repeat(3),
        protagonist_state: "",
        stage_goal: "",
        core_conflict: "",
        major_characters: [],
        key_events: [],
        major_choice: "",
        cost_paid: [],
        gain_received: [],
        turning_point: "这一阶段结束时发生的那个转折。",
        ending_state: "",
        next_question: "",
      })),
      storylines: Array.from({ length: 20 }, (_, i) => ({
        chapter_start: i + 1,
        chapter_end: i + 20,
        evidence: [],
        storyline_id: `SL${i}`,
        name: `第 ${i + 1} 条线的名字`,
        type: "subplot",
        importance: 0.2,
        participants: [],
        nodes: [],
        turning_points: [],
        relationship_to_mainline: "",
        status: "open",
        resolution: "",
      })),
      causal_chain: [],
      chronology: [],
    },
    characters: {
      version: "2.0",
      availability: "available",
      protagonist: {
        initial_identity: "主角",
        initial_goal: "活下去",
        final_goal: "把整件事做完",
        final_identity: "主角",
        stages: Array.from({ length: 8 }, (_, i) => ({
          chapter: i * 10 + 1,
          chapter_end: i * 10 + 10,
          stage_name: `第 ${i + 1} 程`,
          entry_state: "从这里到那里",
          goal: "",
          major_events: [],
          conflict: "",
          choice: "",
          cost_paid: [],
          gain_received: [],
          evidence: [],
        })),
        external_status_track: [],
        ability_track: [],
        internal_belief_track: [],
        relationship_track: [],
        overall_cost: [],
        overall_gain: [],
        core_transformation: "",
        arc_summary: "",
      },
      major_characters: Array.from({ length: 24 }, (_, i) => ({
        character_id: `C${i}`,
        name: `配角${i}`,
        aliases: [],
        importance: 0.1,
        identity: "",
        role: i === 0 ? "protagonist" : "supporting",
        initial_goal: "",
        final_goal: "",
        character_arc: "",
        key_events: [],
        relationship_to_protagonist: "跟主角之间的关系写一句话",
        relationship_changes: [],
        major_choice: "",
        cost_paid: [],
        gain_received: [],
        ending: "",
        evidence: [],
      })),
      relationships: [],
    },
    suspense: {
      version: "2.0",
      availability: "available",
      lifecycles: Array.from({ length: 40 }, (_, i) => ({
        chapter_start: i + 1,
        chapter_end: i + 10,
        evidence: [],
        suspense_id: `SUS${i}`,
        question: `第 ${i + 1} 个被抛出来的问题是什么？`,
        importance: 0.5,
        reader_initial_knowledge: "",
        truth: "",
        events: [],
        clues: [],
        misdirections: [],
        partial_reveals: [],
        twist: "",
        payoff: "",
        storyline_effect: "",
        status: i % 3 === 0 ? "resolved" : "unresolved",
      })),
    },
    pacing: {
      version: "2.0",
      availability: "available",
      points: Array.from({ length: Math.min(96, chapters) }, (_, i) => ({
        chapter_start: i + 1,
        chapter_end: i + 1,
        plot_progress: 40 + ((i * 7) % 55),
        emotion: 30 + ((i * 11) % 60),
        hook_density: i % 2 ? 67 : 17,
        dominant_events: [],
        reason: "",
        story_consequence: "",
      })),
      event_markers: [],
      pacing_regions: [
        {
          chapter_start: 43,
          chapter_end: 45,
          evidence: [],
          type: "fatigue",
          reason: "连续 3 个区间的阅读驱动力处于平缓区",
          diagnosis: "读者推进力持续偏低，可考虑压缩或加入转折",
          related_events: [],
        },
      ],
    },
    chapters: {
      version: "2.0",
      availability: "available",
      aggregation_size: 10,
      functions: Array.from({ length: chapters }, (_, i) => ({
        chapter_id: i + 1,
        chapter_index: i + 1,
        title: `第 ${i + 1} 章`,
        primary_function: "推进+悬念",
        secondary_functions: [],
        summary: `第 ${i + 1} 章发生的事情，一句话概括，长度接近真实摘要。`,
        importance: 0.5,
        evidence: [],
      })),
      heatmap: [],
    },
    assessment: {
      version: "2.0",
      overall_summary: "总体判断写在这里，两三句话。".repeat(3),
      dimensions: [
        "story_structure",
        "protagonist_growth",
        "character_relationships",
        "suspense_payoff",
        "pacing",
        "chapter_efficiency",
      ].map((d) => ({
        dimension: d as never,
        rating: "B+" as never,
        conclusion: "这一维度的结论，写足一行半的长度用来占版面测试。",
        supporting_metrics: [],
        evidence: [],
        dimension_label: "",
      })),
      strengths: Array.from({ length: 4 }, (_, i) => ({
        chapter_start: i * 20 + 1,
        chapter_end: i * 20 + 20,
        evidence: [`EVD-${i}`, `EVD-${i + 1}`],
        title: `已经做对的第 ${i + 1} 处`,
        why_good: "为什么这一处是对的，写一段话。".repeat(2),
      })),
      issues: Array.from({ length: 3 }, (_, i) => ({
        chapter_start: i * 20 + 1,
        chapter_end: i * 20 + 20,
        evidence: [`EVD-${i}`, `EVD-${i + 1}`, `EVD-${i + 2}`],
        issue_id: `${i}`,
        priority: "P1" as never,
        category: "pacing",
        symptom: "症状写在这里，一句到两句话的长度。",
        root_cause: "根因写在这里，一句到两句话的长度。",
        reader_impact: "读者会怎样，一句话。",
        supporting_metrics: [],
        possible_direction: "",
        dimension: "",
        problem: "",
        cause: "",
        recommended_direction: "",
      })),
      issue_map: [],
      revision_priorities: Array.from({ length: 3 }, (_, i) => ({
        priority: (["first", "second", "third"] as const)[i],
        chapter_ranges: [[i * 20 + 1, i * 20 + 20]],
        direction: "该怎么改，写一段具体的话，不是泛泛而谈。".repeat(2),
        preserve: ["改动时必须保住的第一件事", "第二件事"],
      })),
      preserve_list: ["保留清单第一条", "第二条", "第三条"],
      overall_assessment: "",
    },
    evidence_index: ev as never,
    analysis_metadata: {
      run_id: 1,
      provider_name: "deepseek",
      model_name: "deepseek-v4-flash",
      real_provider_calls: 24,
      result_origin: "real_provider",
      generated_at: "2026-08-17T00:00:00Z",
      pipeline_version: "long-novel-engine-1.0",
      schema_version: "whole-book-analysis-v2.0",
    } as never,
    journey: { availability: "unavailable", axis: "none" } as never,
    story_breakdown: { availability: "unavailable" } as never,
  } as unknown as WholeBookAnalysisV2;
}

describe("印刷版全书报告", () => {
  it("章节表按剩余页数截断，并说明砍掉了多少", () => {
    const html = buildPrintHtml(book(800));
    expect(html).toContain("章未列出");
    // The elastic section must not silently swallow the whole book.
    const rows = (html.match(/<tr><th>\d+<\/th>/g) ?? []).length;
    expect(rows).toBeGreaterThan(0);
    expect(rows).toBeLessThan(800);
  });

  it("短书不触发截断提示", () => {
    const html = buildPrintHtml(book(12));
    expect(html).not.toContain("章未列出");
  });

  it("每一页都声明了分页，且页数不超过预算", () => {
    const html = buildPrintHtml(book(800));
    const pages = (html.match(/class="page"/g) ?? []).length;
    expect(pages).toBeLessThanOrEqual(PAGE_BUDGET);
    expect(pages).toBeGreaterThanOrEqual(8);
  });

  it("空板块不占页：没有悬念就不印悬念页", () => {
    const d = book(20);
    d.suspense.lifecycles = [];
    const html = buildPrintHtml(d);
    expect(html).not.toContain("六</span>悬念分析");
  });

  it("声明了编码，不靠浏览器猜", () => {
    // The file is opened as file:/// by a headless Chromium; with no charset it is decoded
    // with the system default, which on a Chinese Windows is GBK and prints as mojibake.
    const html = buildPrintHtml(book(20));
    expect(html.startsWith("<!doctype html>")).toBe(true);
    expect(html).toContain('<meta charset="utf-8">');
    expect(html).toContain('lang="zh-CN"');
  });

  it("模型名取自契约里真实存在的字段", () => {
    // The old code read `provider` / `model`; the document carries `provider_name` /
    // `model_name`, so the source table printed a lone separator where the model should be.
    const html = buildPrintHtml(book(20));
    expect(html).toContain("deepseek / deepseek-v4-flash");
  });

  it("模型答不上来的字段不印：unknown 不是一个值", () => {
    const d = book(20);
    d.characters.major_characters = [
      { name: "甲", role: "supporting", relationship_to_protagonist: "从对立到合作", character_arc: "", evidence: [] },
      { name: "乙", role: "supporting", relationship_to_protagonist: "unknown", character_arc: "", evidence: [] },
    ] as never;
    const html = buildPrintHtml(d);
    expect(html).not.toContain("unknown");
    // The one we cannot describe is still counted and named, just not given a table row.
    expect(html).toContain("另有 1 人登场");
  });

  it("每一个分析章都落在一个判断上", () => {
    // This is the report's spine: a chapter that measures something must end by saying what the
    // measurement means, otherwise the reader is left holding data.
    const html = buildPrintHtml(book(40));
    expect((html.match(/本章判断/g) ?? []).length).toBeGreaterThanOrEqual(4);
  });

  it("问题与建议合成一章，不重复列两遍", () => {
    const html = buildPrintHtml(book(40));
    expect(html).toContain("七</span>问题与修订建议");
    expect(html).not.toContain("问题清单");
  });

  it("引文解析到真实的证据条目", () => {
    const html = buildPrintHtml(book(20));
    expect(html).toContain("被引用的那一句话");
  });

  it("写出 HTML 供人工渲染核对", () => {
    const out = process.env.STORYLENS_PRINT_OUT;
    if (!out) return;
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    require("node:fs").writeFileSync(out, buildPrintHtml(book(800)), "utf-8");
    expect(require("node:fs").existsSync(out)).toBe(true);
  });
});

/** Renders a real stored document when one is pointed at, which is the only way to check the
 *  thing the synthetic fixture cannot: whether the pages read as something an author would use. */
it("真实文档也在预算内", () => {
  const src = process.env.STORYLENS_PRINT_DOC;
  const out = process.env.STORYLENS_PRINT_REAL_OUT;
  if (!src || !out) return;
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const fs = require("node:fs");
  const doc = JSON.parse(fs.readFileSync(src, "utf-8")) as WholeBookAnalysisV2;
  const html = buildPrintHtml(doc);
  fs.writeFileSync(out, html, "utf-8");
  expect((html.match(/class="page"/g) ?? []).length).toBeLessThanOrEqual(PAGE_BUDGET);
});
