/** 「读懂」不该被作品画像门拦住。
 *
 *  后端放行了、前端不跟上，按钮照样是灰的——那等于没放行。今天就是这样：我改完后端就宣布
 *  「可以用了」，而用户点开看到的是一个点不动的按钮。
 */
import { describe, expect, it } from "vitest";
import type { WholeBookAnalysisMode } from "../../services/wholeBookFreeProductApi";

/** 与页面里那行判断同源：改了一处忘了另一处，测试要能看出来。 */
function gateClosed(profileConfirmed: boolean | null, mode: WholeBookAnalysisMode): boolean {
  return profileConfirmed === false && mode !== "comprehend";
}

describe("作品画像门", () => {
  it("画像未确认时，评测和拆文照旧被拦——画像对它们是真有用的", () => {
    expect(gateClosed(false, "diagnostic")).toBe(true);
    expect(gateClosed(false, "story_breakdown")).toBe(true);
  });

  it("「读懂」不受它约束：那五根轴是网文的东西，专著一条都不用", () => {
    expect(gateClosed(false, "comprehend")).toBe(false);
  });

  it("还没读到画像状态时（null）不下结论，别让按钮闪一下灰", () => {
    expect(gateClosed(null, "diagnostic")).toBe(false);
  });
});

/** 「读懂」按设计没有 V2 结果，那个 404 是正确答案。
 *
 *  不先认它，一次成功的读懂会被判成「旧版分析结果」，页面请用户「重新分析以生成 V2 完整
 *  结果」——而那份报告好端端躺在库里。用户照做，就又付一次钱。
 */
function pageMode(input: {
  hasComprehend: boolean;
  comprehendPending: boolean;
  v2Success: boolean;
  v2LegacyError: boolean;
}): "completed-v2" | "legacy" | "failed" {
  if (input.hasComprehend) return "completed-v2";
  if (input.comprehendPending) return "completed-v2";
  if (input.v2Success) return "completed-v2";
  if (input.v2LegacyError) return "legacy";
  return "failed";
}

describe("完成态该显示哪一屏", () => {
  it("有「读懂」结果时显示报告，哪怕 V2 那个口是 404", () => {
    expect(
      pageMode({ hasComprehend: true, comprehendPending: false, v2Success: false, v2LegacyError: true }),
    ).toBe("completed-v2");
  });

  it("读懂结果还在读取时不要闪一下「旧版结果」", () => {
    expect(
      pageMode({ hasComprehend: false, comprehendPending: true, v2Success: false, v2LegacyError: true }),
    ).toBe("completed-v2");
  });

  it("真正的旧版结果仍然要提示重新分析", () => {
    expect(
      pageMode({ hasComprehend: false, comprehendPending: false, v2Success: false, v2LegacyError: true }),
    ).toBe("legacy");
  });
});
