import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { buildMockWholeBookAnalysisV2 } from "./mockAdapter";
import { WholeBookV2ReportView } from "./presentation/WholeBookV2ReportView";
import type { CoverageReport } from "./contracts";

afterEach(cleanup);

/** 开篇拆解只读前几章，报告必须自己说出这件事。
 *
 *  「只读了 5 章」和「丢了 537 章」在数字上一模一样——5/542——在意义上正好相反：
 *  一个是分析正常完成，一个是用户该重跑。所以判定只认后端声明的 scope_kind，
 *  不认前端拿两个数算出来的比例。这个文件钉的就是这条边界。
 */
function withCoverage(cov: Partial<CoverageReport> | null) {
  const doc = buildMockWholeBookAnalysisV2();
  return {
    ...doc,
    book_metadata: { ...doc.book_metadata, chapter_count: 542 },
    analysis_metadata: {
      ...doc.analysis_metadata,
      coverage: cov
        ? ({
            chapters_total: 542,
            chapters_analysed: 5,
            chapters_missing: [],
            blocks_total: 1,
            blocks_failed: 0,
            failure_reasons: [],
            ...cov,
          } as CoverageReport)
        : null,
    },
  };
}

function show(doc: ReturnType<typeof withCoverage>) {
  render(
    <WholeBookV2ReportView
      data={doc}
      activeModule="story"
      onModuleChange={() => {}}
      mode="formal"
    />,
  );
}

describe("开篇拆解的范围声明", () => {
  it("开篇运行会说明自己只读了前几章", () => {
    show(withCoverage({ scope_kind: "opening", scope_chapters: 5 }));
    const notice = screen.getByTestId("whole-book-v2-opening-notice");
    expect(notice).toHaveTextContent("开篇拆解");
    expect(notice).toHaveTextContent("前 5 章");
    expect(notice).toHaveTextContent("542");
    // 表头也要能一眼看到范围，而不是只有顶部一句话。
    expect(screen.getByTestId("wb2-scope-cell")).toHaveTextContent("开篇 5 章 / 全书 542 章");
  });

  it("整本运行不挂开篇告示", () => {
    show(withCoverage({ scope_kind: "full", chapters_analysed: 542, scope_chapters: 542 }));
    expect(screen.queryByTestId("whole-book-v2-opening-notice")).toBeNull();
    expect(screen.queryByTestId("wb2-scope-cell")).toBeNull();
  });

  it("丢了章节的失败运行不会被说成开篇拆解", () => {
    // 同样是「542 章里只有 5 章有结果」，但这一次是丢的。把它显示成「开篇拆解」，
    // 等于告诉用户一次残缺的分析是按他要求做的。
    show(
      withCoverage({
        scope_kind: "full",
        chapters_analysed: 5,
        chapters_missing: Array.from({ length: 537 }, (_, i) => i + 6),
        blocks_failed: 67,
      }),
    );
    expect(screen.queryByTestId("whole-book-v2-opening-notice")).toBeNull();
  });

  it("旧文档没有 coverage 也不会崩", () => {
    show(withCoverage(null));
    expect(screen.queryByTestId("whole-book-v2-opening-notice")).toBeNull();
    expect(screen.getByTestId("whole-book-v2-report")).toBeInTheDocument();
  });
});
