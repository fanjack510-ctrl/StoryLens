/** 把单章评测报告交出去：PDF 走后端的无头 Chromium，HTML 是独立的基础阅读版。
 *
 *  跟全书那份共用同一个 VIP 错误类型和同一条打印路径——后端 `render_report_pdf` 两边都调，
 *  所以两份文件的字体嵌入、纸张、边距一定一致，不会出现「全书能印、单章印成乱码」。
 */
import { VipRequiredError } from "../wholeBookV2/reportExport";
import { saveBlobAsFile, type SavedFileResult } from "../../services/fileDownload";
import {
  buildChapterPrintHtml,
  chapterReportFileName,
  type ChapterReportInput,
} from "./chapterReportExport";

export { VipRequiredError };

const esc = (s: unknown): string =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[c]!,
  );
const pnum = (id: unknown): string => {
  const match = /P(\d+)$/.exec(String(id ?? ""));
  return match ? `P${Number(match[1])}` : String(id ?? "");
};

/** 免费版只保留本章判断和场景概览；曲线、评分、悬念账本和证据表属于 Pro PDF。 */
export function buildChapterBasicHtml(input: ChapterReportInput): string {
  const v = input.visualization;
  const summary = v.chapter_summary;
  const scenes = (v.scene_nodes ?? []).filter((scene) => scene.node_type !== "beat").slice(0, 20);
  const phases = (v.phases ?? []).map((phase) =>
    `<section><h2>${esc(phase.ordinal)} · ${esc(phase.title)}</h2><p>${esc(phase.summary)}</p>${phase.continuation_motivation ? `<p class="meta"><b>继续读的理由：</b>${esc(phase.continuation_motivation)}</p>` : ""}</section>`,
  ).join("");
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(input.chapterTitle)} · 本章基础报告</title><style>
body{margin:0;background:#f5f6f2;color:#17201a;font-family:"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.8}main{max-width:800px;margin:auto;padding:48px 28px 80px;background:#fff;min-height:100vh}h1{margin:0}h2{margin:30px 0 8px;font-size:19px;color:#14503c;border-bottom:1px solid #d8e0da;padding-bottom:6px}.meta{color:#6f7d74}.notice{margin:22px 0;padding:14px 16px;background:#eef5f1;border-left:4px solid #2f6b57}ol{padding-left:24px}li{padding:10px 0;border-bottom:1px solid #e7ebe8}li p{margin:3px 0}
</style></head><body><main><p class="meta">StoryLens · 免费基础阅读版${input.bookTitle ? ` · ${esc(input.bookTitle)}` : ""}</p><h1>${esc(input.chapterTitle)}</h1>
<div class="notice"><b>本文件保留本章判断与场景概览。</b><br>追读曲线、维度评分、悬念账本、逐场证据和专业排版请使用 StoryLens Pro PDF。</div>
<section><h2>本章判断</h2><p>${esc(summary.diagnosis || summary.expanded_diagnosis?.one_sentence_diagnosis || "暂无总体判断")}</p>${summary.primary_traction ? `<p><b>主要追读力：</b>${esc(summary.primary_traction)}</p>` : ""}${summary.weak_interval ? `<p><b>需要注意：</b>${esc(summary.weak_interval)}</p>` : ""}</section>
${phases}<section><h2>场景概览</h2><ol>${scenes.map((scene) => `<li><b>场景 ${scene.scene_ordinal} · ${pnum(scene.paragraph_range.start_paragraph_id)}–${pnum(scene.paragraph_range.end_paragraph_id)}</b><p>${esc(scene.scene_value_summary)}</p>${scene.dominant_emotion ? `<p class="meta">情绪：${esc(scene.dominant_emotion)}</p>` : ""}</li>`).join("")}</ol></section>
</main></body></html>`;
}

export function downloadChapterReportHtml(input: ChapterReportInput): Promise<SavedFileResult> {
  return saveBlobAsFile(
    new Blob([buildChapterBasicHtml(input)], { type: "text/html;charset=utf-8" }),
    chapterReportFileName(input),
  );
}

/** PDF 走 sidecar。授权不足时抛 VipRequiredError——门拒绝是一个答案，不是故障，
 *  所以调用方不能把它当失败去悄悄发 HTML 顶替。 */
export async function downloadChapterReportPdf(
  input: ChapterReportInput,
): Promise<SavedFileResult> {
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

  return saveBlobAsFile(
    await res.blob(),
    chapterReportFileName(input).replace(/\.html$/, ".pdf"),
  );
}
