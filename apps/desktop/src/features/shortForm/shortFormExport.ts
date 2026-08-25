/** 短篇精读 as a printable sheet.
 *
 * A different shape from the whole-book report, because the thing being printed is different.
 * That one is an argument — measurement, judgement, problem, recommendation — and is capped at
 * twenty pages because nobody finishes a report that grows with the book. This is a **worksheet**:
 * one row per scene, the same six columns the human breakdowns use, and it is as long as the
 * piece has scenes. Truncating it would defeat its only purpose, which is to be read beside the
 * text.
 *
 * So there is no page budget here. A 34-scene piece prints to roughly five sheets and that is
 * correct; the whole-book format's elastic appendix exists because an 800-chapter book cannot
 * print its chapter table, and a short piece has no such problem.
 */
import type { ShortFormReading, ShortFormResult, ShortFormSegment } from "../../services/shortFormApi";
import { saveBlobAsFile, type SavedFileResult } from "../../services/fileDownload";
import { VipRequiredError } from "../wholeBookV2/reportExport";

export { VipRequiredError };

const esc = (s: unknown): string =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[c]!,
  );

const ARROW: Record<string, string> = { up: "↑", down: "↓", flat: "—" };

function beatsBar(result: ShortFormResult): string {
  if (!result.beats.length) return "";
  const last = result.segments.length || 1;
  return `<table class="beats">${result.beats
    .map((b) => {
      const span = b.segment_end - b.segment_start + 1;
      return `<tr>
        <th>${esc(b.beat)}</th>
        <td class="where">第 ${b.segment_start}–${b.segment_end} 段<span>${Math.round(
          (span / last) * 100,
        )}%</span></td>
        <td><b>${esc(b.title)}</b><p>${esc(b.summary)}</p></td>
      </tr>`;
    })
    .join("")}</table>`;
}

function emotionRows(result: ShortFormResult): string {
  const rows = [
    ["上行", result.emotion_up],
    ["下行", result.emotion_down],
  ] as const;
  const filled = rows.filter(([, items]) => items.length);
  if (!filled.length) return "";
  return `<table class="emotion">${filled
    .map(
      ([label, items]) =>
        `<tr><th>${label}</th><td><ul>${items
          .map((x) => `<li>${esc(x)}</li>`)
          .join("")}</ul></td></tr>`,
    )
    .join("")}</table>`;
}

function segmentRow(s: ShortFormSegment): string {
  return `<tr class="dir-${s.emotion_direction}">
    <th>${s.index}<span class="para">p${s.paragraph_start}–${s.paragraph_end}</span></th>
    <td class="num">${s.characters}</td>
    <td class="phase">${esc(s.phase) || "—"}</td>
    <td class="setting">${esc(s.setting) || "—"}</td>
    <td>${
      s.beats.length
        ? `<ol>${s.beats.map((b) => `<li>${esc(b)}</li>`).join("")}</ol>`
        : "—"
    }</td>
    <td class="craft">${esc(s.craft) || "—"}${s.callback ? `<span class="cb">↩ ${esc(s.callback)}</span>` : ""}</td>
    <td class="emo"><b>${ARROW[s.emotion_direction] ?? "—"}</b>${esc(s.emotion_note)}</td>
  </tr>`;
}

export function buildShortFormHtml(reading: ShortFormReading): string {
  const r = reading.result;
  // Declared, not sniffed: this file is written to disk and opened as `file:///` by a headless
  // Chromium, and with no charset the system default is used — on a Chinese Windows that is GBK,
  // and the whole sheet prints as mojibake.
  return `<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<title>${esc(r.title)} · 短篇精读</title>
<style>
@page { size: A4 landscape; margin: 12mm 10mm; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  margin: 0; color: #17201a; background: #fff; font-size: 9pt; line-height: 1.6;
  font-family: "Songti SC", SimSun, "Noto Serif CJK SC", serif;
}
h1, h2, th, .kicker, .where, .num, .para, .emo b { font-family: "PingFang SC", "Microsoft YaHei", sans-serif; }
.kicker { font-size: 8pt; letter-spacing: .28em; color: #14503c; margin: 0 0 2mm; }
h1 { font-size: 19pt; margin: 0 0 2mm; }
h2 {
  font-size: 10.5pt; color: #14503c; margin: 6mm 0 2mm; padding-bottom: 1.2mm;
  border-bottom: .8pt solid #14503c;
}
.one-line { font-size: 12pt; line-height: 1.6; margin: 0 0 2mm; }
.meta { font-family: "PingFang SC", sans-serif; font-size: 8pt; color: #6f7d74; margin: 0; }
table { width: 100%; border-collapse: collapse; }

.beats th { width: 10mm; font-size: 14pt; color: #14503c; vertical-align: top; padding: 2mm 0; }
.beats td { padding: 2mm 0 2mm 3mm; vertical-align: top; }
.beats .where { width: 30mm; font-size: 8pt; color: #6f7d74; white-space: nowrap; }
.beats .where span { display: block; color: #14503c; }
.beats b { font-size: 10pt; }
.beats p { margin: 1mm 0 0; color: #3d4a42; }
.beats tr + tr th, .beats tr + tr td { border-top: .4pt solid #eef2ef; }

.emotion th { width: 14mm; text-align: left; font-size: 9pt; color: #6f7d74; vertical-align: top; padding: 1.5mm 0; }
.emotion td { padding: 1.5mm 0 1.5mm 3mm; }
.emotion ul { margin: 0; padding-left: 5mm; }
.rec { margin: 0; line-height: 2; }
.rec b { color: #14503c; }
.rec span { font-family: "PingFang SC", sans-serif; font-size: 7.5pt; color: #6f7d74;
  margin-left: 1.5mm; margin-right: 3mm; }

.sheet { font-size: 8.5pt; }
.sheet thead th {
  text-align: left; font-size: 7.5pt; color: #6f7d74; font-weight: 400;
  border-bottom: .8pt solid #cfd9d2; padding: 1.5mm 2mm;
}
.sheet tbody th {
  text-align: left; width: 14mm; padding: 2mm; vertical-align: top; color: #14503c;
  font-variant-numeric: tabular-nums;
}
.para { display: block; font-size: 7pt; color: #99a49c; }
.sheet td { padding: 2mm; vertical-align: top; }
.sheet tbody tr { border-bottom: .4pt solid #eef2ef; break-inside: avoid; }
.sheet .num { width: 13mm; color: #6f7d74; font-variant-numeric: tabular-nums; }
.sheet .phase { width: 28mm; font-weight: 600; }
.sheet .setting { width: 38mm; color: #3d4a42; font-size: 8pt; }
.sheet ol { margin: 0; padding-left: 4.5mm; }
.sheet .craft { width: 26%; color: #35443c; }
.sheet .cb { display: block; margin-top: 1mm; color: #14503c; font-size: 7.5pt;
  border-left: .8pt solid #cfe3d6; padding-left: 2mm; }
.sheet .emo { width: 36mm; }
.sheet .emo b { display: inline-block; width: 4mm; }
.dir-up { background: #f7fbf9; }
.dir-down { background: #fdfaf7; }
.dir-up .emo b { color: #14503c; }
.dir-down .emo b { color: #a8551f; }
</style>
<p class="kicker">短篇精读</p>
<h1>${esc(r.title)}</h1>
${r.one_line ? `<p class="one-line">${esc(r.one_line)}</p>` : ""}
<p class="meta">${r.character_count.toLocaleString()} 字 · ${r.segments.length} 段${
    r.genre ? ` · ${esc(r.genre)}` : ""
  } · ${reading.provider_calls} 次模型调用 · ${esc(reading.model_name)} · ${esc(reading.created_at)}</p>

${r.beats.length ? `<h2>起承转合</h2>${beatsBar(r)}` : ""}
${r.emotion_up.length || r.emotion_down.length ? `<h2>情绪走向</h2>${emotionRows(r)}` : ""}

${
  r.recurring?.length
    ? `<h2>反复出现的说法</h2><p class="rec">${r.recurring
        .map((x) => `<b>${esc(x.phrase)}</b><span>第 ${x.segments.join("、")} 段</span>`)
        .join("　")}</p>`
    : ""
}
<h2>逐段拆稿</h2>
<table class="sheet">
  <thead><tr>
    <th>段</th><th>字数</th><th>故事进展</th><th>地点/人物</th><th>事件/冲突</th><th>学习之处</th><th>读者此刻</th>
  </tr></thead>
  <tbody>${r.segments.map(segmentRow).join("")}</tbody>
</table>`;
}

function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function shortFormFileName(reading: ShortFormReading): string {
  const safe = (reading.result.title || "短篇").replace(/[\\/:*?"<>|]/g, "_");
  return `${safe}-短篇精读.html`;
}

export function downloadShortForm(reading: ShortFormReading): void {
  triggerDownload(
    new Blob([buildShortFormHtml(reading)], { type: "text/html;charset=utf-8" }),
    shortFormFileName(reading),
  );
}

/** Generate a real PDF through the same Pro-gated printer used by the whole-book and chapter
 * reports. The HTML remains the free, self-contained fallback; a rejected licence is surfaced
 * as a product answer instead of being disguised as a rendering failure. */
export async function downloadShortFormPdf(
  bookId: number,
  reading: ShortFormReading,
): Promise<SavedFileResult> {
  const { getApiBase } = await import("../../services/apiClient");
  const response = await fetch(
    `${getApiBase()}/api/v1/books/${bookId}/short-form/readings/${reading.id}/export-pdf`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ html: buildShortFormHtml(reading) }),
    },
  );

  if (!response.ok) {
    let message = `PDF 导出失败（${response.status}）`;
    let detail:
      | { error_code?: string; message?: string; details?: { afdian_product_url?: string } }
      | null = null;
    try {
      const body = await response.json();
      detail = body?.detail ?? body ?? null;
      message = detail?.message || message;
    } catch {
      /* retain the status-based message */
    }
    if (response.status === 403 && detail?.error_code === "PDF_REQUIRES_VIP") {
      throw new VipRequiredError(message, detail.details?.afdian_product_url ?? "");
    }
    throw new Error(message);
  }

  return saveBlobAsFile(
    await response.blob(),
    shortFormFileName(reading).replace(/\.html$/, ".pdf"),
  );
}
