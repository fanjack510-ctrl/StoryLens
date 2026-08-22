/** 把报告收到能读完的长度。
 *
 *  第一版实测 48,168 字，是原书的 10.5%——跟正文差不多长，就等于没摘要。而读者要它，恰恰
 *  是因为没时间读原文。
 */
import { describe, expect, it } from "vitest";
import { TERMS_SHOWN, citationsOf, compactSection } from "./comprehendCompact";

describe("依据压成「引了谁」", () => {
  it("留下作者与年份——那是读者翻回原文的抓手", () => {
    expect(
      citationsOf(["原文引用Friendly（2006）指出图形通信可追溯到公元前二世纪，并引用Der & Everitt（2015）"]),
    ).toEqual(["Friendly 2006", "Der & Everitt 2015"]);
  });

  it("同一个出处只留一次", () => {
    expect(citationsOf(["Tufte (2001) 提出…", "又见 Tufte (2001)"])).toEqual(["Tufte 2001"]);
  });

  it("中文著者也认", () => {
    expect(citationsOf(["张三（2019）的实验表明…"])).toEqual(["张三 2019"]);
  });

  it("抠不出引用时保留首条并截断——「基于人眼视锥细胞的生理机制」也是依据", () => {
    const out = citationsOf(["依据人眼视锥细胞的生理机制，色相分辨能力有限"]);
    expect(out).toHaveLength(1);
    expect(out[0].length).toBeLessThanOrEqual(40);
  });

  it("没有依据就是没有，不要凭空造一条", () => {
    expect(citationsOf([])).toEqual([]);
    expect(citationsOf(undefined)).toEqual([]);
  });
});

describe("一节收完之后", () => {
  it("主张和做法一条不动——那是这份东西本身", () => {
    const k = compactSection({
      claims: ["分类数据应当用色相区分"],
      actions: ["从 ColorBrewer 选不超过 12 种"],
      evidence: ["Palmer & Schloss (2010) 的色彩偏好实验表明蓝色最受偏好"],
      terms: Array.from({ length: 20 }, (_, i) => `term${i}`),
      open_questions: ["如何量化？"],
    });
    expect(k.claims).toHaveLength(1);
    expect(k.actions).toHaveLength(1);
    expect(k.citations).toEqual(["Palmer & Schloss 2010"]);
  });

  it("术语封顶，但要说出还有多少——藏起来的读者知道，删掉的他不知道", () => {
    const k = compactSection({ terms: Array.from({ length: 20 }, (_, i) => `t${i}`) });
    expect(k.terms).toHaveLength(TERMS_SHOWN);
    expect(k.hiddenTerms).toBe(20 - TERMS_SHOWN);
  });

  it("依据原文和存疑一条不删，只是不摊开", () => {
    const k = compactSection({
      evidence: ["Tufte (2001) 说…", "另有实验支持"],
      open_questions: ["还有什么没答"],
    });
    expect(k.fullEvidence).toHaveLength(2);
    expect(k.openQuestions).toHaveLength(1);
  });
});
