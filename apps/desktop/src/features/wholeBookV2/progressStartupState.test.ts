/** 分析刚开始、还没有第一条进度时，屏幕上不该是一个红色的失败。
 *
 *  接口在那一刻答「这次分析还没有进度可读」是对的：任务刚创建，切章和窗口规划都还没跑完。
 *  但页面把它画成了「无法读取数据」加红色感叹号——用户看见的是失败，于是去关程序、去重开、
 *  来问是不是坏了。
 *
 *  难点在于「还没准备好」和「出事了」在接口上都是一个非 200。分错了两个方向都要命：
 *  一边是把正常启动画成失败，另一边是把真故障藏在一个转圈里。
 */
import { describe, expect, it } from "vitest";
import { ApiError } from "../../services/apiClient";
import { isNotReadyYet, progressPanelState } from "./WholeBookV2ProductPage";

const NOT_READY = new ApiError("WHOLE_BOOK_V2_PROGRESS_NOT_FOUND", "还没有进度可读", 404);
const BLEW_UP = new ApiError("WHOLE_BOOK_V2_FAILED", "分析炸了", 500);

const base = { isLoading: false, hasData: false, error: undefined, everHadData: false, waitedMs: 0 };

describe("哪些错误算「还没准备好」", () => {
  it("只认这条错误码和 404", () => {
    expect(isNotReadyYet(NOT_READY)).toBe(true);
    expect(isNotReadyYet(new ApiError("ANYTHING", "x", 404))).toBe(true);
  });

  it("500 是真出事了，网络错误也是——都不算启动中", () => {
    expect(isNotReadyYet(BLEW_UP)).toBe(false);
    expect(isNotReadyYet(new Error("boom"))).toBe(false);
    expect(isNotReadyYet(undefined)).toBe(false);
  });
});

describe("进度面板该显示哪一屏", () => {
  it("刚开始、还没有进度 → 正在启动，不是无法读取数据", () => {
    expect(progressPanelState({ ...base, error: NOT_READY })).toBe("starting");
  });

  it("真出事了 → 照常报错，启动阶段不是把故障藏起来的借口", () => {
    expect(progressPanelState({ ...base, error: BLEW_UP })).toBe("error");
  });

  it("等太久还是没有第一条进度 → 报错，不能永远转下去", () => {
    expect(progressPanelState({ ...base, error: NOT_READY, waitedMs: 91_000 })).toBe("error");
  });

  it("已经见过进度之后再读不到 → 报错，别拿启动态盖住它", () => {
    expect(
      progressPanelState({ ...base, error: NOT_READY, everHadData: true, waitedMs: 1 }),
    ).toBe("error");
  });

  it("有数据就是有数据", () => {
    expect(progressPanelState({ ...base, hasData: true })).toBe("ready");
    // 首次加载优先，避免开屏闪一下错误。
    expect(progressPanelState({ ...base, isLoading: true, error: BLEW_UP })).toBe("loading");
  });
});
