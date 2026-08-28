import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { ComprehendResult } from "../../../services/wholeBookFreeProductApi";
import { ComprehendReportView } from "./ComprehendReportView";

const result: ComprehendResult = {
  schema_version: "comprehend/1.0",
  book: {
    one_paragraph: "这是一本关于主动选择的书。",
    argument: "**核心**：判断力和长期主义比追逐运气更可靠。",
    what_you_get: "**知道**：什么值得长期投入。 **会做**：用长期结果过滤当下选择。",
    who_should_read: "该读：想重新掌控生活的人。不必读：已经有稳定方法论的人。",
  },
  chapters: [
    {
      chapter: "第1章",
      title: "财富与判断",
      summary: "财富来自可复用的杠杆。",
      through_line: "先建立判断，再放大判断。",
      sections: [
        {
          label: "第一节",
          claims: ["判断先于杠杆"],
          actions: ["记录长期决策"],
          evidence: ["B0020-C0001-P0001"],
          terms: [],
          open_questions: [],
        },
      ],
    },
    {
      chapter: "第2章",
      title: "幸福与自由",
      summary: "减少欲望也是一种自由。",
      through_line: "先减少无谓需求。",
      sections: [],
    },
  ],
  sections_total: 2,
  sections_covered: 2,
  coverage: 1,
  trustworthy: true,
  provider_calls: 3,
  failures: [],
  rules: ["按节解析"],
};

describe("ComprehendReportView information hierarchy", () => {
  afterEach(cleanup);

  it("structures the overview, removes light Markdown markers and exposes chapter navigation", () => {
    const { container } = render(
      <ComprehendReportView data={result} title="测试工具书" runId={7} />,
    );

    expect(screen.getByRole("heading", { name: "测试工具书" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "先用三分钟掌握这本书" })).toBeInTheDocument();
    expect(screen.getByText("知道")).toBeInTheDocument();
    expect(screen.getByText("会做")).toBeInTheDocument();
    expect(screen.getByText("该读")).toBeInTheDocument();
    expect(screen.getByText("不必读")).toBeInTheDocument();
    expect(container.textContent).not.toContain("**");

    const chapterNav = screen.getByRole("navigation", { name: "章节导航" });
    expect(chapterNav.querySelectorAll("a")).toHaveLength(2);
    expect(screen.getByText("1 个主张")).toBeInTheDocument();
    expect(screen.getByText("1 个做法")).toBeInTheDocument();
    expect(screen.getByText("1 条依据")).toBeInTheDocument();
  });

  it("keeps details collapsed and the two export choices explicit", () => {
    render(<ComprehendReportView data={result} title="测试工具书" runId={7} />);

    expect(screen.getByRole("button", { name: "导出 PDF · PRO" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "导出基础 HTML" })).toBeInTheDocument();
    for (const detail of document.querySelectorAll(".cmp-fold")) {
      expect(detail).not.toHaveAttribute("open");
    }
  });
});
