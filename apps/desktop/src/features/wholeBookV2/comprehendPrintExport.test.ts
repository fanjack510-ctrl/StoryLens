/** 「读懂」交出去的那份文件。
 *
 *  它回答的是「我不读原文能知道什么」，所以纸上第一位的是**可信度**而不是内容——纸比屏幕更
 *  容易被当成定稿，覆盖率藏进末尾小字，等于让读者在不知情的情况下信一份残缺的东西。
 */
import { describe, expect, it } from "vitest";
import type { ComprehendResult } from "../../services/wholeBookFreeProductApi";
import { buildComprehendPrintHtml, comprehendFileName } from "./comprehendPrintExport";

const base = (over: Partial<ComprehendResult> = {}): ComprehendResult =>
  ({
    schema_version: "comprehend/1.0",
    book: {
      one_paragraph: "这是一本手册。",
      argument: "各章互不隶属。",
      what_you_get: "知道怎么做审计。",
      who_should_read: "该读：工程师。不必读：纯后端。",
    },
    chapters: [
      {
        chapter: "第35章",
        title: "DATA VISUALIZATION",
        summary: "本章讲可视化。",
        through_line: "从感知到工具。",
        sections: [
          {
            label: "第35章 3.3 Principles of Color",
            claims: ["分类数据应当用色相区分，类别数不宜超过 12 种"],
            evidence: ["Palmer & Schloss (2010)"],
            actions: ["从 ColorBrewer 选不超过 12 种色相"],
            terms: ["Sequential mapping（顺序映射）"],
            open_questions: ["如何量化感知均匀带来的效率提升？"],
          },
        ],
      },
    ],
    sections_total: 76,
    sections_covered: 76,
    coverage: 1,
    trustworthy: true,
    provider_calls: 43,
    failures: [],
    rules: ["页眉页脚：按重复率剔除"],
    ...over,
  }) as ComprehendResult;

describe("读懂的印刷版式", () => {
  it("五类内容都在纸上，不是把屏幕截下来", () => {
    const html = buildComprehendPrintHtml(base(), "手册");
    for (const s of ["主张", "依据", "做法", "术语", "存疑"]) expect(html).toContain(s);
    expect(html).toContain("分类数据应当用色相区分");
    expect(html).toContain("第35章 3.3 Principles of Color");
  });

  it("覆盖不足时，第一页就说清缺了多少——不能藏进末尾小字", () => {
    const html = buildComprehendPrintHtml(
      base({ sections_covered: 60, coverage: 60 / 76, trustworthy: false }),
      "手册",
    );
    const head = html.slice(0, html.indexOf("第35章"));
    expect(head).toContain("有 16 节没读到");
    expect(head).toContain("请回原文核对");
  });

  it("读失败的节留在原位并说出原因——悄悄跳过，读者会以为它本来就没内容", () => {
    const d = base();
    d.chapters[0].sections.push({
      label: "第35章 6.4 Scientific Visualization",
      claims: [], evidence: [], actions: [], terms: [], open_questions: [],
      error: "provider timeout",
    });
    const html = buildComprehendPrintHtml(d, "手册");
    expect(html).toContain("这一节没有读到");
    expect(html).toContain("6.4 Scientific Visualization");
  });

  it("声明 UTF-8：这份文件由无头 Chromium 以 file:/// 打开，不声明就按 GBK 印成乱码", () => {
    expect(buildComprehendPrintHtml(base(), "手册")).toContain('<meta charset="utf-8">');
  });

  it("文件名不带路径分隔符——书名里出现 / 会让保存失败", () => {
    expect(comprehendFileName("人因/评估")).toBe("StoryLens_人因_评估_读懂.html");
  });
});
