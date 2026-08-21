/** 单章评测报告：这份文件必须真的有内容，而且必须只是评测。 */
import { describe, expect, it } from "vitest";
import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";
import { buildChapterPrintHtml, chapterReportFileName } from "./chapterReportExport";

function scene(ordinal: number, over: Record<string, unknown> = {}) {
  return {
    scene_id: ordinal,
    scene_ordinal: ordinal,
    paragraph_range: {
      start_paragraph_id: `B0001-C0001-P${String(ordinal * 5).padStart(4, "0")}`,
      end_paragraph_id: `B0001-C0001-P${String(ordinal * 5 + 4).padStart(4, "0")}`,
    },
    paragraph_count: 5,
    phase_ordinal: 1,
    role: "core",
    final_level: "core",
    importance_score: 50,
    importance_formula_version: "1.0",
    deterministic_reasons: [],
    scene_value_summary: `第 ${ordinal} 场把故事推到下一步`,
    dominant_emotion: "紧张",
    engagement: { engagement_score: 60 + ordinal },
    scores: { hook: 80 - ordinal * 5 },
    reader_question_in: [],
    reader_question_created: [{ question: `疑问 ${ordinal}`, strength: 90 }],
    reader_question_answered: [],
    reader_question_out: [{ question: `疑问 ${ordinal}` }],
    payoffs: [],
    hooks: [{ evidence_paragraph_ids: [`B0001-C0001-P${String(ordinal * 5).padStart(4, "0")}`] }],
    techniques: [],
    risk_points: [],
    character_effects: [],
    writing_takeaways: [],
    evidence_paragraph_ids: [],
    evidence_count: 0,
    confidence: 0.9,
    primary_payoff: null,
    primary_hook: null,
    primary_risk: null,
    ...over,
  };
}

function viz(over: Partial<ReaderJourneyVisualization> = {}): ReaderJourneyVisualization {
  const nodes = [scene(1), scene(2), scene(3)];
  return {
    visualization_version: "4.2",
    main_curve: { label: "追读意愿", why: "免费流读者随时可划走。" },
    hook_vocabulary: {
      open: "提出疑问",
      deepen: "加深悬念",
      answer: "给出回应",
      carry: "留到下章",
      lens: "钩子回收",
      first_mark: "首钩位置",
    },
    chapter_summary: {
      chapter_title: "第1章 戏鬼回家",
      diagnosis: "开篇抓得住，中段掉了一次。",
      primary_traction: "他为什么穿着戏袍出现在雷雨里？",
      peaks: { engagement_average: "63.0" },
    },
    phases: [
      {
        ordinal: 1,
        title: "开端",
        start_scene_ordinal: 1,
        end_scene_ordinal: 3,
        primary_reader_question: "他是谁？",
        dominant_emotion: "紧张",
        reading_payoff: "",
        continuation_motivation: "想知道他到底是不是阿伶",
        summary: "少年在雷雨里醒来。",
        confidence: 0.9,
        average_engagement: 62,
        core_scene_count: 3,
      },
    ],
    curve_series: {
      engagement: nodes.map((n) => ({ scene_ordinal: n.scene_ordinal, value: n.engagement.engagement_score })),
    },
    scene_nodes: nodes,
    role_counts: { core: 3, secondary: 0, beat: 0 },
    primary_question_chain: null,
    phase_question_chains: [],
    secondary_question_chains: [],
    payoff_markers: [],
    hook_markers: [],
    risk_intervals: [],
    formula_versions: {
      visualization_version: "4.2",
      chain_rank_formula_version: "1.0",
      importance_formula_version: "1.0",
      chain_merge_formula_version: "1.0",
      engagement_formula_version: "1.0",
    },
    calibration_status: { scene_contract_version: "2.0", semantic_source: "v2_native" },
    ...over,
  } as unknown as ReaderJourneyVisualization;
}

const input = { visualization: viz(), chapterTitle: "第1章 戏鬼回家", bookTitle: "我不是戏神" };

describe("单章评测报告", () => {
  it("三项判断、曲线、逐场景都在纸上——不是把屏幕截下来", () => {
    const html = buildChapterPrintHtml(input);
    expect(html).toContain("章节评测报告");
    expect(html).toContain("开篇抓力");
    expect(html).toContain("章末牵引");
    expect(html).toContain("首钩位置");
    // 曲线是真画出来的，不是一句「见屏幕」
    expect(html).toContain("<polyline");
    // 逐场景每一场都在
    expect(html).toContain("S1");
    expect(html).toContain("S3");
    expect(html).toContain("第 2 场把故事推到下一步");
  });

  it("说清楚它只做评测——用户问过「拆文的入口在哪」，纸上不能装作没这回事", () => {
    const html = buildChapterPrintHtml(input);
    expect(html).toContain("只做评测");
    expect(html).toMatch(/全书分析里选「拆文」/);
  });

  it("口径印在最后一页：换了模型或公式，分数就不可比", () => {
    const html = buildChapterPrintHtml({
      ...input,
      providerName: "deepseek",
      modelName: "deepseek-v4-flash",
      journeyRunId: 77,
    });
    expect(html).toContain("deepseek-v4-flash");
    expect(html).toContain("#77");
    expect(html).toContain("场景契约");
  });

  it("模型答 unknown 等于没答，不占一行", () => {
    const v = viz();
    v.scene_nodes[0].dominant_emotion = "unknown";
    v.scene_nodes[0].scene_value_summary = "未知";
    const html = buildChapterPrintHtml({ ...input, visualization: v });
    // data-band="unknown" 是给 CSS 用的挂钩，不是印在纸上的字；样式表和标签都去掉，
    // 剩下的才是读者在纸上看到的那些字。
    const printed = html.replace(/<style[\s\S]*?<\/style>/g, " ").replace(/<[^>]+>/g, " ");
    expect(printed).not.toContain("unknown");
    expect(printed).not.toContain("未知");
  });

  it("类型专项：分数旁边必须有刻度和依据段号，否则 0/5 只是一个数字", () => {
    const v = viz();
    v.scene_nodes[0].genre_axes = [
      {
        key: "clue_placement",
        label: "线索投放",
        level: 0,
        rationale: "本场没有放出任何可验证的线索。",
        evidence_paragraph_ids: ["B0001-C0001-P0005"],
        anchors: "0＝没有线索；3＝有线索但要回读；5＝线索当场可辨。",
      },
    ];
    const html = buildChapterPrintHtml({ ...input, visualization: v });
    expect(html).toContain("线索投放");
    expect(html).toContain("0 / 5");
    expect(html).toContain("0＝没有线索");
    expect(html).toContain("P5");
  });

  it("没有类型专项的书，不印一张空页", () => {
    expect(buildChapterPrintHtml(input)).not.toContain("类型专项");
  });

  it("场景为空时不抛错，也不画一条只有一个点的曲线", () => {
    const v = viz({ scene_nodes: [], curve_series: { engagement: [] } } as never);
    const html = buildChapterPrintHtml({ ...input, visualization: v });
    expect(html).toContain("章节评测报告");
    expect(html).not.toContain("<polyline");
  });

  it("文件名不带路径分隔符——章名里出现 / 会让保存失败", () => {
    expect(chapterReportFileName({ ...input, chapterTitle: "第1章 上/下" })).toBe(
      "StoryLens_第1章 上_下_章节评测报告.html",
    );
  });

  it("账本三个数必须对得上——开减收就是章末仍欠，不能开 5 收 3 却欠 12", () => {
    // opened / closed 是每一场的，balance 是累计。取末场那两个当本章合计，印出来的账
    // 自己就对不上；这条测的是「印在纸上的三个数彼此自洽」。
    const v = viz();
    const ledgers = [
      { opened: 5, closed: 3, balance: 2 },
      { opened: 3, closed: 1, balance: 4 },
      { opened: 5, closed: 3, balance: 6 },
    ];
    v.scene_nodes.forEach((n, i) => {
      (n as { open_questions?: unknown }).open_questions = ledgers[i];
    });
    const printed = buildChapterPrintHtml({ ...input, visualization: v }).replace(/<[^>]+>/g, " ");
    expect(printed).toMatch(/本章提出疑问\s*13\s*个/);
    expect(printed).toMatch(/本章给出回应\s*7\s*个/);
    expect(printed).toMatch(/章末仍欠\s*6\s*个/);
  });

  it("同名但不同刻度的轴，纸上要说破——否则读者以为其中一个印错了", () => {
    const v = viz();
    v.scene_nodes[0].genre_axes = [
      {
        key: "opening_grip",
        label: "开篇抓力",
        level: 5,
        rationale: "首句即抛出疑问。",
        evidence_paragraph_ids: ["B0001-C0001-P0005"],
        anchors: "0＝无异常；3＝有但被稀释；5＝首段就抛出。",
      },
    ];
    const html = buildChapterPrintHtml({ ...input, visualization: v });
    expect(html).toContain("与第一页那项同名，但不是同一个数");
  });

  it("阶段摘要就是阶段名时不重复印一遍", () => {
    const v = viz();
    v.phases[0].summary = v.phases[0].title;
    const printed = buildChapterPrintHtml({ ...input, visualization: v }).replace(/<[^>]+>/g, " ");
    expect(printed.match(/开端/g)?.length).toBe(1);
  });

  it("声明 UTF-8：这份文件由无头 Chromium 以 file:/// 打开，不声明就按 GBK 印成乱码", () => {
    expect(buildChapterPrintHtml(input)).toContain('<meta charset="utf-8">');
  });
});
