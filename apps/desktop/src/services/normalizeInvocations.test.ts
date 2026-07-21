import { describe, expect, it } from "vitest";
import { normalizeInvocations } from "./normalizeInvocations";
import { ApiError } from "./apiClient";

describe("normalizeInvocations", () => {
  it("returns empty array for null/undefined", () => {
    expect(normalizeInvocations(null, 1)).toEqual([]);
    expect(normalizeInvocations(undefined, 1)).toEqual([]);
  });

  it("passes through arrays", () => {
    const rows = [{ id: 1 }];
    expect(normalizeInvocations(rows, 1)).toBe(rows);
  });

  it("throws ApiError for empty object error structure", () => {
    expect(() => normalizeInvocations({}, 9)).toThrow(ApiError);
    try {
      normalizeInvocations({ detail: "bad" }, 9);
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).message).toContain("bad");
    }
  });

  it("throws for non-array primitives", () => {
    expect(() => normalizeInvocations("nope", 3)).toThrow(/格式异常/);
  });
});
