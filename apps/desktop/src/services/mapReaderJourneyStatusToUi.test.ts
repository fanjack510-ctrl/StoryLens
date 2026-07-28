import { describe, expect, it } from "vitest";
import { mapReaderJourneyStatusToUi } from "./mapReaderJourneyStatusToUi";
import { parseBackendUtcTimestamp } from "./parseBackendUtcTimestamp";
import { journeyElapsedMs } from "./resolveCurrentReaderJourney";

describe("mapReaderJourneyStatusToUi", () => {
  it("maps failed to 阅读旅程生成失败 and never paused", () => {
    const mapped = mapReaderJourneyStatusToUi({ journeyStatus: "failed", retryable: false });
    expect(mapped.status).toBe("failed");
    expect(mapped.label).toBe("阅读旅程生成失败");
    expect(mapped.sidebarUiState).toBe("failed");
    expect(mapped.label).not.toContain("暂停");
  });

  it("maps paused only for paused", () => {
    expect(mapReaderJourneyStatusToUi({ journeyStatus: "paused" }).label).toBe("分析已暂停");
  });

  it("maps interrupted / running / succeeded", () => {
    expect(mapReaderJourneyStatusToUi({ journeyStatus: "interrupted" }).label).toBe(
      "阅读旅程已中断",
    );
    expect(mapReaderJourneyStatusToUi({ journeyStatus: "running" }).label).toContain("正在生成");
    expect(mapReaderJourneyStatusToUi({ journeyStatus: "succeeded" }).label).toContain("已完成");
  });

  it("main and sidebar use one mapping for failed", () => {
    const mapped = mapReaderJourneyStatusToUi({ journeyStatus: "failed" });
    expect(mapped.label).toBe("阅读旅程生成失败");
    expect(mapped.sidebarUiState).toBe("failed");
    expect([mapped.label, mapped.sidebarUiState].filter((x) => String(x).includes("暂停"))).toHaveLength(
      0,
    );
  });
});

describe("parseBackendUtcTimestamp", () => {
  it("parses Z and offset", () => {
    expect(parseBackendUtcTimestamp("2026-07-28T15:05:07.191528Z")).toBe(
      Date.parse("2026-07-28T15:05:07.191528Z"),
    );
    expect(parseBackendUtcTimestamp("2026-07-28T15:05:07.191528+00:00")).toBe(
      Date.parse("2026-07-28T15:05:07.191528Z"),
    );
  });

  it("treats legacy naive as UTC", () => {
    const ms = parseBackendUtcTimestamp("2026-07-28 15:05:07.191528");
    expect(ms).toBe(Date.parse("2026-07-28T15:05:07.191528Z"));
  });

  it("avoids +8h skew for UTC+8 viewers", () => {
    const start = parseBackendUtcTimestamp("2026-07-28 15:05:07.191528")!;
    const viewer = Date.parse("2026-07-28T23:16:39+08:00");
    const hours = (viewer - start) / 3600000;
    expect(hours).toBeGreaterThan(0);
    expect(hours).toBeLessThan(1);
  });
});

describe("journeyElapsedMs terminal ends", () => {
  it("uses completed_at/updated_at for failed and stays under 5 minutes for fresh run", () => {
    const ms = journeyElapsedMs({
      journey: {
        id: 2,
        status: "failed",
        started_at: "2026-07-28T15:05:07.191528Z",
        completed_at: "2026-07-28T15:05:36.172844Z",
        updated_at: "2026-07-28T15:06:02.241914Z",
      },
    });
    expect(ms).toBeGreaterThan(0);
    expect(ms!).toBeLessThan(5 * 60 * 1000);
  });
});
