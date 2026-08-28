/** 导出这份报告时，失败要说真话。
 *
 *  第一版的落回提示固定写「本机没有可用的打印内核」——它从没查过打印内核。用户机器上装着
 *  浏览器，真实原因是这个页面拿不到旅程任务号；那句编出来的诊断把人指向了完全错误的方向。
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { buildChapterBasicHtml, downloadChapterReportPdf, VipRequiredError } from "./chapterReportDownload";
import type { ChapterReportInput } from "./chapterReportExport";

vi.mock("../../services/apiClient", () => ({ getApiBase: () => "http://127.0.0.1:8000" }));

const input = {
  visualization: {
    visualization_version: "4.2",
    chapter_summary: { chapter_title: "第1章" },
    phases: [],
    curve_series: { engagement: [] },
    scene_nodes: [],
    role_counts: { core: 0, secondary: 0, beat: 0 },
    primary_question_chain: null,
    phase_question_chains: [],
    secondary_question_chains: [],
    payoff_markers: [],
    hook_markers: [],
    risk_intervals: [],
    formula_versions: {},
    calibration_status: {},
  },
  chapterTitle: "第1章",
} as unknown as ChapterReportInput;

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("单章报告的 PDF 导出", () => {
  it("拿不到旅程任务号时，说的就是这一条——而不是替它编一个打印内核的故事", async () => {
    await expect(downloadChapterReportPdf(input)).rejects.toThrow(/旅程任务号/);
  });

  it("有任务号时打到对应的旅程上，而不是全书那条路由", async () => {
    const fetchMock = vi.fn(async () => new Response(new Blob(["%PDF-"]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("URL", { createObjectURL: () => "blob:x", revokeObjectURL: () => undefined });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    await downloadChapterReportPdf({ ...input, journeyRunId: 42 });
    expect(fetchMock.mock.calls[0][0]).toBe(
      "http://127.0.0.1:8000/api/v1/reader-journey-runs/42/export-pdf",
    );
  });

  it("授权门拒绝要原样抛出来，不能被当成故障悄悄发一份 HTML 顶替", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              error_code: "PDF_REQUIRES_VIP",
              message: "PDF 导出是 VIP 功能",
              details: { afdian_product_url: "https://afdian.com/item/x" },
            }),
            { status: 403 },
          ),
      ),
    );
    await expect(downloadChapterReportPdf({ ...input, journeyRunId: 42 })).rejects.toBeInstanceOf(
      VipRequiredError,
    );
  });

  it("后端真的说没有打印内核时，才是没有打印内核", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              error_code: "PDF_BROWSER_NOT_FOUND",
              message: "未找到可用于打印的浏览器内核",
            }),
            { status: 501 },
          ),
      ),
    );
    await expect(downloadChapterReportPdf({ ...input, journeyRunId: 42 })).rejects.toThrow(
      /浏览器内核/,
    );
  });
});

describe("单章免费基础 HTML", () => {
  it("说明产品边界，且不携带 Pro 的图表与打印版式", () => {
    const html = buildChapterBasicHtml(input);
    expect(html).toContain("免费基础阅读版");
    expect(html).toContain("本章判断");
    expect(html).not.toContain("<svg");
    expect(html).not.toContain("@page");
  });
});
