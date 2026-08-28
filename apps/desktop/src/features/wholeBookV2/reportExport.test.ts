import { describe, expect, it } from "vitest";
import { buildMockWholeBookAnalysisV2 } from "./mockAdapter";
import { buildBasicReportHtml, buildReportHtml, reportFileName } from "./reportExport";

describe("结构化报告导出", () => {
  const data = buildMockWholeBookAnalysisV2();
  const html = buildReportHtml(data, new Date("2026-08-15T12:00:00"));
  // The visible report is everything before the embedded raw-data block; the block itself
  // legitimately contains wire enums, so assertions about reader-facing text stop there.
  const visible = html.slice(0, html.indexOf('<script id="raw-data"'));

  it("七个模块和证据附录都在", () => {
    for (const h of [
      ">1　全书总览<", ">2　故事<", ">3　人物<", ">4　悬念<",
      ">5　节奏<", ">6　章节<", ">7　综合诊断<", "附录A　证据索引",
    ]) {
      expect(html).toContain(h);
    }
  });

  it("正文不出现裸的机器枚举", () => {
    // Everything the screen translates, the export must translate too — same label maps.
    for (const raw of [">protagonist<", ">supporting<", ">clue<", ">unresolved<", ">resolved<", ">pacing<", ">suspense_payoff<"]) {
      expect(visible).not.toContain(raw);
    }
  });

  // 模型答不上来时写下的 `unknown`，在 PDF 那一侧早就挡住了，屏幕和这份 HTML 没有。
  // 一份真实报告里有 13 处。
  it("模型没答上来的字段不印占位词", () => {
    const d = structuredClone(buildMockWholeBookAnalysisV2());
    d.characters.major_characters = [
      { ...d.characters.major_characters[0], relationship_to_protagonist: "unknown" },
      { ...d.characters.major_characters[0], name: "乙", relationship_to_protagonist: "未知" },
    ] as never;
    const out = buildReportHtml(d, new Date("2026-08-15T12:00:00"));
    const body = out.slice(0, out.indexOf('<script id="raw-data"'));
    expect(body).not.toContain("unknown");
    expect(body).not.toContain("未知");
    expect(body).not.toContain("与主角的关系");
  });

  const breakdownDoc = () => {
    const d = structuredClone(buildMockWholeBookAnalysisV2()) as never as Record<string, unknown>;
    // 拆文文档里这两块本来就是空的——空，正是它们不该出现在文件里的理由。
    d.overview = { ...(d.overview as object), one_sentence_story: "", full_summary: "" };
    d.assessment = { ...(d.assessment as object), overall_summary: "", issues: [] };
    d.story_breakdown = {
      version: "1.0",
      availability: "available",
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
    };
    return d as never;
  };

  // 导出器原先根本不认识 story_breakdown：导出一份拆文报告，会得到一个没有拆文内容、
  // 却带着两节空白总览与综合诊断的文件——屏幕上修掉的缺陷，在人们真正会保存和转发的
  // 那个文件里活了下来。
  it("拆文报告导出来要有拆文，而且没有那两节空的", () => {
    const out = buildReportHtml(breakdownDoc(), new Date("2026-08-15T12:00:00"));
    const body = out.slice(0, out.indexOf('<script id="raw-data"'));
    for (const heading of ["拆文", "四个部分", "打动人的瞬间", "每章留下的问题", "可复用的手法", "配角功能"]) {
      expect(body).toContain(heading);
    }
    expect(body).toContain("两人第一次同处一室");
    expect(body).toContain("空气忽然变甜");
    expect(body).toContain("气味代替独白");
    expect(body).not.toContain("全书总览");
    expect(body).not.toContain("综合诊断");
  });

  // 评测文档里 story_breakdown 是个空壳，不该因此多出一节空的拆文。
  it("评测报告不因为空的拆文块多出一节", () => {
    const d = structuredClone(buildMockWholeBookAnalysisV2()) as never as Record<string, unknown>;
    d.story_breakdown = { four_beats: [], standout_moments: [] };
    const out = buildReportHtml(d as never, new Date("2026-08-15T12:00:00"));
    const body = out.slice(0, out.indexOf('<script id="raw-data"'));
    expect(body).toContain("全书总览");
    expect(body).toContain("综合诊断");
    expect(body).not.toContain('id="sb"');
  });

  it("内嵌 JSON 能取回并等于原始数据", () => {
    const m = /<script id="raw-data" type="application\/json">([\s\S]*?)<\/script>/.exec(html);
    expect(m).not.toBeNull();
    expect(JSON.parse(m![1])).toEqual(JSON.parse(JSON.stringify(data)));
  });

  it("数据量级正确：每章功能一行，每条证据一行", () => {
    expect(html.match(/<tr><td>第 \d+ 章<\/td><td>[^<]*<\/td><td>\d\.\d<\/td>/g)?.length).toBe(
      data.chapters.functions.length,
    );
    const evidenceCount = Object.keys(data.evidence_index ?? {}).length;
    if (evidenceCount > 0) {
      expect(html).toContain(`附录A　证据索引（${evidenceCount}）`);
    }
  });

  it("文件名带书名并以 .html 结尾", () => {
    const name = reportFileName(data);
    expect(name.endsWith("-全书分析报告.html")).toBe(true);
    expect(name.includes("/")).toBe(false);
  });

  it("HTML 元素配平（表格与章节标题）", () => {
    for (const tag of ["table", "tr", "td", "th", "h2", "h3", "ul", "li"]) {
      const open = (html.match(new RegExp(`<${tag}[ >]`, "g")) ?? []).length;
      const close = (html.match(new RegExp(`</${tag}>`, "g")) ?? []).length;
      expect(`${tag}:${open}`).toBe(`${tag}:${close}`);
    }
  });
});

describe("免费基础 HTML 与 Pro 报告边界", () => {
  it("只保留核心摘要，不携带原始 JSON、证据附录和打印版式", () => {
    const html = buildBasicReportHtml(buildMockWholeBookAnalysisV2());
    expect(html).toContain("免费基础阅读版");
    expect(html).toContain("这本书讲什么");
    expect(html).not.toContain('id="raw-data"');
    expect(html).not.toContain("附录A");
    expect(html).not.toContain("@media print");
  });
});
