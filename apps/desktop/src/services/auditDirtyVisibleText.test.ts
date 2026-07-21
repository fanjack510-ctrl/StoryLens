import { describe, expect, it } from "vitest";
import { findDirtyVisibleToken } from "./auditDirtyVisibleText";

describe("findDirtyVisibleToken", () => {
  it("fails on Sundefined and bare undefined", () => {
    expect(findDirtyVisibleToken("Sundefined")).toBeTruthy();
    expect(findDirtyVisibleToken("场景 Sundefined")).toBeTruthy();
    expect(findDirtyVisibleToken("undefined")).toBeTruthy();
  });

  it("fails on NaN and null and [object Object]", () => {
    expect(findDirtyVisibleToken("NaN")).toBeTruthy();
    expect(findDirtyVisibleToken("value null here")).toBeTruthy();
    expect(findDirtyVisibleToken("[object Object]")).toBeTruthy();
  });

  it("allows clean scene labels", () => {
    expect(findDirtyVisibleToken("S01")).toBeNull();
    expect(findDirtyVisibleToken("章末")).toBeNull();
    expect(findDirtyVisibleToken("选择一个章节开始阅读")).toBeNull();
  });
});
