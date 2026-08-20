import { describe, expect, it } from "vitest";
import { buildMockWholeBookAnalysisV2 } from "./mockAdapter";
import { buildReportHtml, reportFileName } from "./reportExport";

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
