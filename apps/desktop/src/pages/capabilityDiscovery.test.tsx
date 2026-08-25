import { describe, expect, it } from "vitest";
import {
  CAPABILITIES,
  capabilityAcceptsBook,
  PAID_FEATURE_LINES,
  SHIPPED_CAPABILITIES,
} from "../services/capabilityCatalog";

/** 功能要能被找到。
 *
 *  这一组测试来自一次以新用户身份的实走。当时的产品状态：
 *   - 17 个页面，顶栏只挂了 3 个
 *   - 素材库有页面、有 7 个接口、有测试，**界面里一个入口都没有**
 *   - 三种读法（评测/拆文/读懂）只在「还没分析」那一屏出现一次，分析完永远消失
 *   - 「按意思找」要先搜一次才渲染，所以落地页上看不出这里有付费能力
 *   - 同一件事三个名字：VIP（导出按钮）/ 专业版（顶栏）/ PRO
 *
 *  用户的原话是「作为用户根本不知道到底能干哪些功能」。
 *  下面钉的不是像素，是那几条让功能「存在但找不到」的性质。
 */
describe("能力清单说的是全部，不只是收费的", () => {
  it("免费的功能必须在清单里——只列收费项等于说免费部分不值一提", () => {
    // 这份清单的前身叫 PRO_CAPABILITIES，只有四条，全是要钱的。
    // 一个用户照着它读，会以为这个产品四个功能全收费。
    const free = SHIPPED_CAPABILITIES.filter((c) => c.tier === "free");
    expect(free.length).toBeGreaterThan(0);
    // 素材库是其中最该在的一条：它连模型钱都不花，却是最难被发现的一个。
    expect(free.map((c) => c.key)).toContain("material_lab");
  });

  it("素材能力定位为题材知识库，不再承诺写作方法论", () => {
    const knowledge = CAPABILITIES.find((c) => c.key === "material_lab");
    expect(knowledge?.name).toBe("题材知识库");
    expect(knowledge?.what).toMatch(/悬疑线索|种田天气|作物种植/);
    expect(knowledge?.what).not.toMatch(/写法|方法论|套路/);
  });

  it("每一项都得能从这儿点着开始，不是告诉人往哪儿走", () => {
    // 这条原来断言的是「位置」那一栏（「书库 → 打开任意一本书」）。用户看完说：
    // 「像一页说明书。正常的工具不是应该有个功能标签，点进去然后引导怎么操作？」
    // 他是对的——**一张写着路线的纸不是入口**。
    // 现在断言的是可执行性：每一项都得有按钮文案和落点。
    for (const cap of SHIPPED_CAPABILITIES) {
      expect(cap.cta.trim(), `${cap.name} 的按钮没有文案`).not.toBe("");
      expect(cap.to, `${cap.name} 点了不知道去哪儿`).not.toBeNull();
    }
  });

  it("要选对象的那几项，得说清楚选什么", () => {
    // needs 决定界面画不画选择器、画书还是画书单。写错的话按钮会指向一个不存在的目标。
    const needsTarget = SHIPPED_CAPABILITIES.filter((c) => c.needs !== "none");
    for (const cap of needsTarget) {
      // 要选对象 → 落点必须是个能吃 id 的函数，不能是写死的路径。
      expect(typeof cap.to, `${cap.name} 要选对象却指向固定路径`).toBe("function");
    }
    // 不用选对象的，落点必须是固定路径。
    for (const cap of SHIPPED_CAPABILITIES.filter((c) => c.needs === "none")) {
      expect(typeof cap.to, `${cap.name} 不用选对象却要一个 id`).toBe("string");
    }
  });

  it("部分收费的必须两边都写：免费到哪儿、付费买什么", () => {
    // 只写付费那半边，用户会以为不付钱一点都用不了——而这几项免费的半边本身就够用。
    for (const cap of CAPABILITIES.filter((c) => c.tier === "mixed")) {
      expect(cap.free.trim(), `${cap.name} 没写免费到哪儿`).not.toBe("");
      expect(cap.paid.trim(), `${cap.name} 没写付费买什么`).not.toBe("");
    }
  });

  it("跑不起来的不混在能用的里面", () => {
    // 设置页曾经列着「故事实验台」——产品里没有这个东西。
    // 一个列了六项、其中一项能用的清单，比不列更糟：买的人是照着它掏钱的。
    for (const cap of SHIPPED_CAPABILITIES) {
      expect(cap.status).toBe("available");
    }
  });

  it("三种读法各是一张卡，且按钮说哪种、链接就带哪种", () => {
    // 它们原来挤成一张卡叫「三种读法」——那是内部叫法。
    // 一个想「评测我的稿子」的人，不会在那四个字里认出自己。
    // 拆成三张之后还有一个必须成立的条件：**按钮写「开始评测」，进去就得真的是评测**，
    // 否则三张卡只是三个通往同一个选择器的入口，等于没拆。
    const modes = [
      ["diagnostic", "评测"],
      ["story_breakdown", "拆文"],
      ["comprehend", "读懂"],
    ] as const;
    for (const [key, label] of modes) {
      const cap = SHIPPED_CAPABILITIES.find((c) => c.key === key);
      expect(cap, `${label} 没有自己的卡`).toBeDefined();
      expect(cap!.name).toBe(label);
      expect(cap!.cta).toContain(label);
      const href = typeof cap!.to === "function" ? cap!.to(7) : String(cap!.to);
      expect(href, `${label} 的链接没带上模式`).toContain(`mode=${key}`);
    }
  });

  it("小说读法不列工具书，读懂不列小说，知识库只接小说", () => {
    const diagnostic = CAPABILITIES.find((c) => c.key === "diagnostic")!;
    const breakdown = CAPABILITIES.find((c) => c.key === "story_breakdown")!;
    const comprehend = CAPABILITIES.find((c) => c.key === "comprehend")!;
    const materialLab = CAPABILITIES.find((c) => c.key === "material_lab")!;

    expect(capabilityAcceptsBook(diagnostic, "fiction")).toBe(true);
    expect(capabilityAcceptsBook(diagnostic, "reference")).toBe(false);
    expect(capabilityAcceptsBook(breakdown, "reference")).toBe(false);
    expect(capabilityAcceptsBook(comprehend, "reference")).toBe(true);
    expect(capabilityAcceptsBook(comprehend, "fiction")).toBe(false);
    expect(capabilityAcceptsBook(materialLab, "fiction")).toBe(true);
    expect(capabilityAcceptsBook(materialLab, "reference")).toBe(false);
  });

  it("正式 Pro 权益都指向真实存在的能力", () => {
    // 用户点版本徽章进来是想知道掏钱买什么，不是想看目录。
    // 这五行如果和真实清单对不上，就又是一份会撒谎的价目表。
    expect(PAID_FEATURE_LINES).toHaveLength(5);
    for (const row of PAID_FEATURE_LINES) {
      const cap = CAPABILITIES.find((c) => c.key === row.key);
      expect(cap, `${row.label} 指向一个不存在的能力`).toBeDefined();
      expect(cap!.tier).not.toBe("free");
      expect(row.line.trim()).not.toBe("");
    }
  });
});
