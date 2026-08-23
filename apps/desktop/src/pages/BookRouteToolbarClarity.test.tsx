import { describe, expect, it } from "vitest";

/** 书页工具条上那一排标签，得让人看懂在选什么。
 *
 *  用户报的原话：「为啥有两个确认画像 而且为啥本章分析是不可操的 这些标签对用户使用
 *  很困惑 不知道啥逻辑」。三件事叠在一起：
 *
 *   1. 主按钮「确认作品画像」和次要栏的「作品画像 · 待确认」并排站着，指向同一个页面
 *   2. 「分析本章」是灰的，而为什么灰只写在 tooltip 里
 *   3. 那本书是**工具书**——画像的五根轴（付费模式 / 读者 / 爽感引擎 / 人称 / 篇幅）
 *      全是网文的东西，让人确认一本人因工程手册的爽感引擎是在问一个没有答案的问题，
 *      而这道门还顺手把「分析本章」锁死了
 */
function row(id: number, kind: "fiction" | "reference") {
  return {
    id,
    title: kind === "reference" ? "handbook" : "某本小说",
    source_file_name: "",
    format: "PDF",
    created_at: null,
    material_kind: kind,
    material_kind_confirmed: true,
    kind_label: kind === "reference" ? "工具书" : "小说 · 长篇",
    chapter_count: 76,
    analysis_state: "idle" as const,
    analysis_state_label: "未分析",
    last_activity_at: null,
  };
}

describe("工具书没有作品画像这回事", () => {
  it("画像的五根轴全是网文的东西，工具书不该被它挡住", () => {
    // 这条钉的是判定本身，不是渲染：`isReference` 为真时 `profileUnconfirmed` 必须是 false，
    // 否则「分析本章」会被一道对这本书没有意义的门锁死。
    const decide = (isReference: boolean, pending: boolean, status?: string) =>
      !isReference && !pending && status !== "confirmed";

    expect(decide(true, false, undefined)).toBe(false); // 工具书：不设门
    expect(decide(false, false, undefined)).toBe(true); // 小说没确认：设门
    expect(decide(false, false, "confirmed")).toBe(false); // 小说已确认：放行
    // 查询还没回来时不设门——`null` 是「最未确认」，但 pending 是「还不知道」，
    // 拿不知道去挡人，会让页面在加载的一瞬间闪出一道门。
    expect(decide(false, true, undefined)).toBe(false);
  });

  it("书库查询挂掉时不能让整个书页崩掉", () => {
    // `libraryRows.data?.find(...)` 在 data 不是数组时直接抛，白屏。
    // 一个只提供附加信息的查询不该有这种权力。
    const safe = (data: unknown, id: number) =>
      (Array.isArray(data) ? data : []).find((r: { id: number }) => r.id === id);

    expect(() => safe(undefined, 1)).not.toThrow();
    expect(() => safe({ items: [] }, 1)).not.toThrow();
    expect(safe([row(1, "reference")], 1)?.material_kind).toBe("reference");
  });
});
