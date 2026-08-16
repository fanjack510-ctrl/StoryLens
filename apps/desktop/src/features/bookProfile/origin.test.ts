import { describe, expect, it } from "vitest";
import { confirmLabel, profileHref, readProfileOrigin, returnHref } from "./origin";

describe("画像页的来路（CHG-20260815-095）", () => {
  it("从单章来：确认后回到那一章并重开分析弹窗", () => {
    const origin = readProfileOrigin(2, new URLSearchParams("from=chapter&chapterId=807"));
    expect(origin).toEqual({ kind: "chapter", bookId: 2, chapterId: 807 });
    // The old behaviour sent every confirmation to whole-book analysis — a different and
    // more expensive thing than the one a chapter user asked for.
    expect(returnHref(origin)).toBe("/books/2?chapter=807&startAnalysis=1");
    expect(confirmLabel(origin)).toBe("确认并分析本章");
  });

  it("从全书来：确认后回全书页", () => {
    const origin = readProfileOrigin(2, new URLSearchParams("from=whole-book"));
    expect(returnHref(origin)).toBe("/books/2/whole-book");
    expect(confirmLabel(origin)).toBe("确认并开始全书分析");
  });

  it("直接访问：确认后不跳转，按钮不承诺分析", () => {
    const origin = readProfileOrigin(2, new URLSearchParams());
    expect(origin.kind).toBe("direct");
    expect(returnHref(origin)).toBeNull();
    expect(confirmLabel(origin)).toBe("保存画像");
  });

  it("章节号缺失或非法时退回直接访问，不构造坏链接", () => {
    for (const query of ["from=chapter", "from=chapter&chapterId=0", "from=chapter&chapterId=abc"]) {
      expect(readProfileOrigin(2, new URLSearchParams(query)).kind).toBe("direct");
    }
  });

  it("profileHref 是发起方唯一决定回程的地方", () => {
    expect(profileHref(5)).toBe("/books/5/profile");
    expect(profileHref(5, { from: "whole-book" })).toBe("/books/5/profile?from=whole-book");
    expect(profileHref(5, { from: "chapter", chapterId: 12 })).toBe(
      "/books/5/profile?from=chapter&chapterId=12",
    );
  });
});
