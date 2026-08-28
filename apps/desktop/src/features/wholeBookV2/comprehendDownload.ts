/** 把「读懂」交出去：PDF 走后端的无头 Chromium，HTML 是独立的基础阅读版。
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

const esc = (s: unknown): string =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[c]!,
  );

/** 免费版保留全书结论和逐章摘要，不交付逐节主张/做法/依据/术语的结构化替代读物。 */
export function buildComprehendBasicHtml(data: ComprehendResult, title: string): string {
  const total = data.sections_total ?? 0;
  const covered = data.sections_covered ?? 0;
  const pct = Math.round((data.coverage ?? 0) * 100);
  const overview = [
    ["一段话说清", data.book?.one_paragraph],
    ["全书主张", data.book?.argument],
    ["读完能带走什么", data.book?.what_you_get],
    ["谁适合读", data.book?.who_should_read],
  ].filter(([, value]) => Boolean(String(value ?? "").trim()));
  const chapters = (data.chapters ?? []).map((chapter) =>
    `<section><h2>${esc(chapter.chapter)} ${esc(chapter.title)}</h2>${chapter.summary ? `<p>${esc(chapter.summary)}</p>` : ""}${chapter.through_line ? `<p class="line"><b>主线：</b>${esc(chapter.through_line)}</p>` : ""}${chapter.error ? `<p class="warn">未完整读到：${esc(chapter.error)}</p>` : ""}</section>`,
  ).join("");
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)} · 读懂基础版</title><style>
body{margin:0;background:#f5f6f2;color:#17201a;font-family:"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.8}main{max-width:800px;margin:auto;padding:48px 28px 80px;background:#fff;min-height:100vh}h1{margin:0}h2{margin:30px 0 8px;font-size:19px;color:#14503c;border-bottom:1px solid #d8e0da;padding-bottom:6px}.meta,.line{color:#6f7d74}.notice{margin:22px 0;padding:14px 16px;background:#eef5f1;border-left:4px solid #2f6b57}.warn{color:#a8551f}
</style></head><body><main><p class="meta">StoryLens · 免费基础阅读版</p><h1>${esc(title)}</h1><p class="meta">覆盖 ${covered}/${total} 节（${pct}%）</p>
<div class="notice"><b>本文件保留全书结论与逐章摘要。</b><br>逐节主张、做法、引用依据、术语整理和专业排版请使用 StoryLens Pro PDF。</div>
${overview.map(([label, value]) => `<section><h2>${esc(label)}</h2><p>${esc(value)}</p></section>`).join("")}${chapters}</main></body></html>`;
}

export function downloadComprehendHtml(data: ComprehendResult, title: string): Promise<SavedFileResult> {
  return saveBlobAsFile(
    new Blob([buildComprehendBasicHtml(data, title)], { type: "text/html;charset=utf-8" }),
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
