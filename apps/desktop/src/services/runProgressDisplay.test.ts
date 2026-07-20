import { describe, expect, it } from "vitest";
import { formatRunProgress } from "./runProgressDisplay";

describe("formatRunProgress", () => {
  it("prefers scene counts when total_scene_count is present", () => {
    expect(
      formatRunProgress({
        total_scene_count: 4,
        completed_scene_count: 2,
        progress_current: 1,
        progress_total: 10,
      }),
    ).toBe("Scene Analysis：2 / 4");
  });

  it("uses progress_current/total when scene totals missing", () => {
    expect(formatRunProgress({ progress_current: 1, progress_total: 3 })).toBe("1/3");
  });

  it("shows 等待进度 when progress fields are undefined", () => {
    expect(formatRunProgress({})).toBe("等待进度");
    expect(formatRunProgress({ progress_current: undefined, progress_total: undefined })).toBe(
      "等待进度",
    );
  });

  it("never emits undefined/null/NaN text", () => {
    const text = formatRunProgress({
      progress_current: Number.NaN,
      progress_total: null as unknown as number,
    });
    expect(text).toBe("等待进度");
    expect(text).not.toMatch(/undefined|null|NaN/i);
  });
});
