/** 把单章评测报告交出去：PDF 走后端的无头 Chromium，失败时落回 HTML。
 *
 *  跟全书那份共用同一个 VIP 错误类型和同一条打印路径——后端 `render_report_pdf` 两边都调，
 *  所以两份文件的字体嵌入、纸张、边距一定一致，不会出现「全书能印、单章印成乱码」。
 */
import { VipRequiredError } from "../wholeBookV2/reportExport";
import {
  buildChapterPrintHtml,
  chapterReportFileName,
  type ChapterReportInput,
} from "./chapterReportExport";

export { VipRequiredError };

function triggerDownload(blob: Blob, name: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** 自包含网页版。没有无头浏览器时点一下也能拿到东西，内容与 PDF 完全相同。 */
export function downloadChapterReportHtml(input: ChapterReportInput): void {
  triggerDownload(
    new Blob([buildChapterPrintHtml(input)], { type: "text/html;charset=utf-8" }),
    chapterReportFileName(input),
  );
}

/** PDF 走 sidecar。授权不足时抛 VipRequiredError——门拒绝是一个答案，不是故障，
 *  所以调用方不能把它当失败去悄悄发 HTML 顶替。 */
export async function downloadChapterReportPdf(input: ChapterReportInput): Promise<void> {
  const runId = input.journeyRunId;
  if (runId == null) throw new Error("这份分析没有旅程任务号，无法导出 PDF");

  const { getApiBase } = await import("../../services/apiClient");
  const res = await fetch(`${getApiBase()}/api/v1/reader-journey-runs/${runId}/export-pdf`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ html: buildChapterPrintHtml(input) }),
  });

  if (!res.ok) {
    let message = `PDF 导出失败（${res.status}）`;
    let detail:
      | { error_code?: string; message?: string; details?: { afdian_product_url?: string } }
      | null = null;
    try {
      const body = await res.json();
      // 应用的错误中间件会把 HTTPException 的 detail 拍平到顶层；裸 FastAPI（测试、别的
      // 部署）仍然保留 detail 这一层。两种都认。
      detail = body?.detail ?? body ?? null;
      message = detail?.message || message;
    } catch {
      /* 保留按状态码给出的那句 */
    }
    if (res.status === 403 && detail?.error_code === "PDF_REQUIRES_VIP") {
      throw new VipRequiredError(message, detail.details?.afdian_product_url ?? "");
    }
    throw new Error(message);
  }

  triggerDownload(await res.blob(), chapterReportFileName(input).replace(/\.html$/, ".pdf"));
}
