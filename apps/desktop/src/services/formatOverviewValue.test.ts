import { describe, expect, it } from "vitest";
import { formatOverviewValue } from "./formatOverviewValue";

describe("formatOverviewValue", () => {
  it("formats single-item string arrays without JSON markers", () => {
    expect(formatOverviewValue(["齐夏"])).toEqual({ kind: "text", text: "齐夏" });
  });

  it("joins short multi-item arrays with顿号", () => {
    expect(formatOverviewValue(["悬疑", "无限流"])).toEqual({
      kind: "text",
      text: "悬疑、无限流",
    });
  });

  it("uses list for long multi-item arrays", () => {
    const longA = "a".repeat(45);
    const longB = "b".repeat(45);
    expect(formatOverviewValue([longA, longB])).toEqual({
      kind: "list",
      items: [longA, longB],
    });
  });

  it("prefers object summary fields over JSON", () => {
    expect(formatOverviewValue({ name: "齐夏", extra: 1 })).toEqual({
      kind: "text",
      text: "齐夏",
    });
    expect(formatOverviewValue({ nested: true })).toEqual({ kind: "unsupported" });
  });

  it("treats empty as empty", () => {
    expect(formatOverviewValue(null)).toEqual({ kind: "empty" });
    expect(formatOverviewValue("")).toEqual({ kind: "empty" });
    expect(formatOverviewValue([])).toEqual({ kind: "empty" });
  });
});
