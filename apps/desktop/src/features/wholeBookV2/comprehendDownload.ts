/** 把「读懂」交出去：PDF 走后端的无头 Chromium，失败时落回 HTML。
 *
 *  跟全书、单章共用同一个 VIP 错误类型和同一条打印路径——三份文件的字体嵌入、纸张、边距因此
 *  一定一致。授权门拒绝时**不落回**：门拒绝是一个答案，不是故障，落回等于把收费的东西换个
 *  名字发出去。
 */
import type { ComprehendResult } from "../../services/wholeBookFreeProductApi";
import { saveBlobAsFile, type SavedFileResult } from "../../services/fileDownload";
import { VipRequiredError } from "./reportExport";
import { buildComprehendPrintHtml, comprehendFileName } from "./comprehendPrintExport";

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

export function downloadComprehendHtml(data: ComprehendResult, title: string): void {
  triggerDownload(
    new Blob([buildComprehendPrintHtml(data, title)], { type: "text/html;charset=utf-8" }),
    comprehendFileName(title),
  );
}

export async function downloadComprehendPdf(
  runId: number,
  data: ComprehendResult,
  title: string,
): Promise<SavedFileResult> {
  const { getApiBase } = await import("../../services/apiClient");
  const res = await fetch(
    `${getApiBase()}/api/v1/whole-book-runs/${runId}/comprehend/export-pdf`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ html: buildComprehendPrintHtml(data, title) }),
    },
  );
  if (!res.ok) {
    let message = `PDF 导出失败（${res.status}）`;
    let detail:
      | { error_code?: string; message?: string; details?: { afdian_product_url?: string } }
      | null = null;
    try {
      const body = await res.json();
      // 应用的错误中间件会把 HTTPException 的 detail 拍平到顶层；裸 FastAPI 保留 detail 这层。
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
  return saveBlobAsFile(
    await res.blob(),
    comprehendFileName(title).replace(/\.html$/, ".pdf"),
  );
}
