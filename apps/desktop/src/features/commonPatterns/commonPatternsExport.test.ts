import { describe, expect, it } from "vitest";
import type { PatternsResult } from "../../services/commonPatternsApi";
import { buildCommonPatternsHtml, commonPatternsFileName } from "./commonPatternsExport";

const RESULT: PatternsResult = {
  books: [
    {
      book_id: 1,
      title: "甲书",
      usable: true,
      excluded_reason: "",
      primary_genre: "悬疑",
      chapters_analysed: 100,
      chapters_total: 100,
      scope_kind: "full",
      scope_label: "全书 100 章",
      technique_count: 8,
      hook_count: 80,
      hooks_per_chapter: 0.8,
      standout_moment_count: 6,
    },
    {
      book_id: 2,
      title: "乙书",
      usable: true,
      excluded_reason: "",
      primary_genre: "悬疑",
      chapters_analysed: 5,
      chapters_total: 500,
      scope_kind: "opening",
      scope_label: "开篇 5 章 / 全书 500 章",
      technique_count: 6,
      hook_count: 4,
      hooks_per_chapter: 0.8,
      standout_moment_count: 2,
    },
  ],
  usable_count: 2,
  total_count: 2,
  genres: [{ genre: "悬疑", count: 2 }],
  technique_total: 14,
  opening_only_count: 1,
  mixed_scope: true,
  can_synthesize: true,
  min_books: 2,
  blocked_reason: "",
  provider_name: "deepseek",
  model_name: "deepseek-v4-flash",
  patterns: [
    {
      name: "用认知冲突立人物",
      what_they_do: "让角色做出与身份预期相反的选择",
      why_it_works: "让读者立刻产生追问",
      book_count: 2,
      instances: [
        {
          book_id: 1,
          book_title: "甲书",
          technique_name: "反常识开场",
          how_this_book_does_it: "在第一场景直接推翻身份印象",
        },
        {
          book_id: 2,
          book_title: "乙书",
          technique_name: "身份反转",
          how_this_book_does_it: "用公开选择改变人物关系",
        },
      ],
    },
  ],
  not_shared: [{ book_id: 2, book_title: "乙书", what_only_this_one_does: "用倒计时推进开篇" }],
};

describe("榜单共性结构化 PDF", () => {
  it("报告包含范围、共性、逐书依据和独有做法", () => {
    const html = buildCommonPatternsHtml("新书榜第一批", RESULT);
    expect(html).toContain("榜单共性报告");
    expect(html).toContain("一、比较范围");
    expect(html).toContain("开篇 5 章 / 全书 500 章");
    expect(html).toContain("二、它们共同做了什么");
    expect(html).toContain("用认知冲突立人物");
    expect(html).toContain("逐书依据");
    expect(html).toContain("反常识开场");
    expect(html).toContain("只有它自己在做的");
    expect(html).toContain("用倒计时推进开篇");
    expect(html).toContain("@page { size: A4 portrait");
  });

  it("转义书名并生成 Windows 安全文件名", () => {
    const html = buildCommonPatternsHtml("A&B<榜>", RESULT);
    expect(html).toContain("A&amp;B&lt;榜&gt;");
    expect(commonPatternsFileName('A/B:榜单')).toBe("A_B_榜单-榜单共性报告.pdf");
  });
});
