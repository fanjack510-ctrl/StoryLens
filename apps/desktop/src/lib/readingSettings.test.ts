import { describe, expect, it } from "vitest";
import {
  DEFAULT_READING_SETTINGS,
  READING_SETTINGS_STORAGE_KEY,
  parseReadingSettings,
  readReadingSettings,
  writeReadingSettings,
} from "./readingSettings";

function memoryStorage(seed: Record<string, string> = {}) {
  const map = new Map(Object.entries(seed));
  return {
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => void map.set(k, v),
    dump: () => Object.fromEntries(map),
  };
}

describe("阅读设置的持久化", () => {
  it("写进去的读得回来——这四项以前只活在内存里，重启就没了", () => {
    const storage = memoryStorage();
    writeReadingSettings(
      { fontSize: 22, lineHeight: 1.5, contentWidth: "narrow", showParagraphIds: true },
      storage,
    );
    expect(readReadingSettings(storage)).toEqual({
      fontSize: 22,
      lineHeight: 1.5,
      contentWidth: "narrow",
      showParagraphIds: true,
    });
  });

  it("没存过时给默认值", () => {
    expect(readReadingSettings(memoryStorage())).toEqual(DEFAULT_READING_SETTINGS);
  });

  it("坏数据不会让页面回不来：越界的值夹回控件能表达的范围", () => {
    const storage = memoryStorage({
      [READING_SETTINGS_STORAGE_KEY]: JSON.stringify({
        fontSize: 999,
        lineHeight: -3,
        contentWidth: "沿用",
        showParagraphIds: "yes",
      }),
    });
    const got = readReadingSettings(storage);
    expect(got.fontSize).toBeLessThanOrEqual(28);
    expect(got.lineHeight).toBeGreaterThanOrEqual(1.2);
    expect(got.contentWidth).toBe(DEFAULT_READING_SETTINGS.contentWidth);
    expect(got.showParagraphIds).toBe(false);
  });

  it("不是 JSON 就当没存过，而不是抛出来", () => {
    expect(parseReadingSettings("{不是 JSON")).toBeNull();
    expect(readReadingSettings(memoryStorage({ [READING_SETTINGS_STORAGE_KEY]: "x" }))).toEqual(
      DEFAULT_READING_SETTINGS,
    );
  });

  it("存不下的时候不抛错——存储满了不该让刚拖动的滑块失灵", () => {
    const throwing = {
      getItem: () => null,
      setItem: () => {
        throw new Error("QuotaExceededError");
      },
    };
    expect(() => writeReadingSettings(DEFAULT_READING_SETTINGS, throwing)).not.toThrow();
  });
});
