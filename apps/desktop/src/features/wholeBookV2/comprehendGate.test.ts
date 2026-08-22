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
