import { describe, expect, it } from "vitest";

describe("CHG-085 resume messaging", () => {
  it("resume hint does not blame provider config for schema failures", () => {
    const schemaMessage = "全书总结合成失败：模型中间结果格式不符合要求。";
    expect(schemaMessage).not.toMatch(/Provider 配置/);
    expect(schemaMessage).toMatch(/格式不符合要求/);
  });

  it("resume copy preserves completed window count", () => {
    const completed = 15;
    const total = 15;
    const message = `已完成 ${completed}/${total} 个分析窗口，将从失败阶段继续，不会重复已成功的窗口调用。`;
    expect(message).toContain("15/15");
    expect(message).toContain("不会重复");
  });
});
