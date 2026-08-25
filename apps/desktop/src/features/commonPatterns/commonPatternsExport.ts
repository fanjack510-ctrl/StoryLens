import { getApiBase } from "../../services/apiClient";
import type { PatternBook, PatternsResult } from "../../services/commonPatternsApi";

const esc = (value: unknown): string =>
  String(value ?? "").replace(/[&<>"']/g, (char) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]!,
  );

function readableNumber(value: number | null): string {
  return value == null ? "—" : String(value);
}

function bookRow(book: PatternBook): string {
  if (!book.usable) {
    return `<tr class="excluded"><td>${esc(book.title || `#${book.book_id}`)}</td><td colspan="4">${esc(book.excluded_reason)}</td></tr>`;
  }
  return `<tr>
    <td><b>${esc(book.title)}</b></td>
    <td>${esc(book.primary_genre || "未标注")}</td>
    <td>${esc(book.scope_label)}</td>
    <td class="num">${book.technique_count}</td>
    <td class="num">${readableNumber(book.hooks_per_chapter)}</td>
  </tr>`;
}

export function buildCommonPatternsHtml(collectionName: string, result: PatternsResult): string {
  const generatedAt = new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date());
  const genres = result.genres.length
    ? result.genres.map((item) => `<span>${esc(item.genre)} <b>${item.count}</b></span>`).join("")
    : `<span>类型未标注</span>`;
  const scopeNotice = result.mixed_scope
    ? `<div class="scope-note"><b>范围提醒</b>：其中 ${result.opening_only_count} 本只分析了开篇。开篇观察只说明这些书如何开始，不能当作整本规律。</div>`
    : "";
  const patterns = result.patterns.length
    ? result.patterns
        .map(
          (pattern, index) => `<section class="pattern">
            <div class="pattern-title"><i>${String(index + 1).padStart(2, "0")}</i><div><h3>${esc(pattern.name)}</h3><span>${pattern.book_count} 本书共同采用</span></div></div>
            ${pattern.what_they_do ? `<div class="answer"><b>怎么做</b><p>${esc(pattern.what_they_do)}</p></div>` : ""}
            ${pattern.why_it_works ? `<div class="answer muted-answer"><b>为什么有效</b><p>${esc(pattern.why_it_works)}</p></div>` : ""}
            <div class="evidence"><b>逐书依据</b>${pattern.instances
              .map(
                (instance) => `<div class="evidence-row"><strong>《${esc(instance.book_title)}》</strong><em>${esc(instance.technique_name)}</em>${
                  instance.how_this_book_does_it ? `<p>${esc(instance.how_this_book_does_it)}</p>` : ""
                }</div>`,
              )
              .join("")}</div>
          </section>`,
        )
        .join("")
    : `<div class="empty">这组书之间没有找到经引用核对后仍然成立的共同手法。</div>`;
  const unique = result.not_shared.length
    ? `<section class="unique"><h2>只有它自己在做的</h2><p class="section-lead">差异不是噪音，它说明每本书没有被共性结论抹平。</p><ul>${result.not_shared
        .map(
          (item) => `<li><b>《${esc(item.book_title)}》</b><span>${esc(item.what_only_this_one_does)}</span></li>`,
        )
        .join("")}</ul></section>`
    : "";

  return `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>${esc(collectionName || "未命名榜单")} · 榜单共性报告</title>
<style>
@page { size: A4 portrait; margin: 17mm 17mm 16mm; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; color: #17201a; background: #fff; font: 10pt/1.7 "Songti SC", SimSun, "Noto Serif CJK SC", serif; }
h1, h2, h3, th, .kicker, .metrics, .genre-list, .scope-note, .pattern-title, .answer b, .evidence > b, .evidence-row em, .meta { font-family: "Microsoft YaHei", "PingFang SC", sans-serif; }
.cover { border-top: 3pt solid #1f6a52; padding-top: 14mm; padding-bottom: 12mm; }
.kicker { margin: 0 0 4mm; color: #1f6a52; font-size: 8pt; font-weight: 700; letter-spacing: .24em; }
h1 { margin: 0; max-width: 155mm; font-size: 26pt; line-height: 1.25; letter-spacing: -.03em; }
.deck { margin: 5mm 0 0; max-width: 145mm; color: #526159; font-size: 11pt; }
.meta { margin-top: 7mm; color: #748078; font-size: 8pt; }
.metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 3mm; margin: 0 0 8mm; }
.metric { padding: 4mm; border-radius: 2mm; background: #f2f6f3; border: .4pt solid #dce6df; }
.metric b { display: block; color: #1f6a52; font-size: 18pt; line-height: 1.1; }
.metric span { color: #657169; font-size: 8pt; }
h2 { margin: 9mm 0 2mm; padding-bottom: 2mm; border-bottom: 1pt solid #1f6a52; color: #1f6a52; font-size: 14pt; }
.section-lead { margin: 0 0 4mm; color: #66736b; }
.genre-list { display: flex; flex-wrap: wrap; gap: 2mm; margin-bottom: 4mm; }
.genre-list span { padding: 1.2mm 3mm; border-radius: 99px; background: #edf5f0; color: #315e4d; font-size: 8.5pt; }
.genre-list b { margin-left: 1mm; }
.scope-note { margin: 4mm 0; padding: 3mm 4mm; border-left: 2pt solid #c78b31; background: #fbf5e8; color: #5f5038; font-size: 8.5pt; }
table { width: 100%; border-collapse: collapse; font-size: 8.5pt; }
thead { display: table-header-group; }
th { padding: 2mm; border-bottom: 1pt solid #b7c8bd; color: #607067; text-align: left; font-size: 7.5pt; }
td { padding: 2.4mm 2mm; border-bottom: .4pt solid #e3e9e5; vertical-align: top; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tr.excluded { color: #8a948e; }
.pattern { margin-top: 6mm; padding: 5mm; border: .5pt solid #d8e2db; border-radius: 2mm; break-inside: auto; box-decoration-break: clone; -webkit-box-decoration-break: clone; }
.pattern-title { display: flex; gap: 3mm; align-items: flex-start; margin-bottom: 4mm; break-inside: avoid; }
.pattern-title i { color: #1f6a52; font-size: 12pt; font-style: normal; font-weight: 700; }
.pattern-title h3 { margin: 0; font-size: 13pt; line-height: 1.3; }
.pattern-title span { color: #638071; font-size: 8pt; }
.answer { display: grid; grid-template-columns: 24mm 1fr; gap: 3mm; padding: 2.5mm 0; border-top: .4pt solid #e4eae6; break-inside: avoid; }
.answer b, .evidence > b { color: #68756d; font-size: 8pt; }
.answer p { margin: 0; }
.muted-answer p { color: #526159; }
.evidence { margin-top: 2mm; padding-top: 3mm; border-top: .8pt solid #bdcdc3; }
.evidence-row { display: grid; grid-template-columns: 44mm 42mm 1fr; gap: 2.5mm; align-items: baseline; padding: 2mm 0; border-bottom: .35pt dotted #d7dfda; break-inside: avoid; }
.evidence-row strong { font-size: 8.5pt; }
.evidence-row em { padding: .8mm 2mm; border-radius: 1mm; background: #eef3ef; color: #486153; font-size: 7.5pt; font-style: normal; }
.evidence-row p { margin: 0; color: #4c5951; font-size: 8.5pt; }
.unique { break-before: auto; }
.unique ul { margin: 0; padding: 0; list-style: none; }
.unique li { display: grid; grid-template-columns: 50mm 1fr; gap: 4mm; padding: 3mm 0; border-bottom: .4pt solid #e0e7e2; break-inside: avoid; }
.unique li b { color: #26352d; }
.empty { margin-top: 4mm; padding: 6mm; border: .5pt dashed #b9c7be; color: #607067; text-align: center; }
.method { margin-top: 9mm; padding: 4mm; background: #f5f7f5; color: #637067; font-size: 8pt; break-inside: avoid; }
</style>
</head>
<body>
<header class="cover">
  <p class="kicker">STORYLENS · 榜单共性报告</p>
  <h1>《${esc(collectionName || "未命名榜单")}》</h1>
  <p class="deck">横向比较一组小说已经拆出的技法，找出不同说法背后真正重复出现的创作机制。</p>
  <p class="meta">生成时间 ${esc(generatedAt)} · ${esc(result.provider_name)} / ${esc(result.model_name)}</p>
</header>
<section class="metrics">
  <div class="metric"><b>${result.usable_count}</b><span>本书进入比较</span></div>
  <div class="metric"><b>${result.technique_total}</b><span>条技法参与归纳</span></div>
  <div class="metric"><b>${result.patterns.length}</b><span>条共性通过核对</span></div>
</section>
<section>
  <h2>一、比较范围</h2>
  <p class="section-lead">以下数据来自已完成的拆文结果；分析范围会直接影响结论可以解释到哪里。</p>
  <div class="genre-list">${genres}</div>
  ${scopeNotice}
  <table><thead><tr><th>书</th><th>类型</th><th>分析范围</th><th class="num">技法</th><th class="num">钩子/章</th></tr></thead><tbody>${result.books.map(bookRow).join("")}</tbody></table>
</section>
<section>
  <h2>二、它们共同做了什么</h2>
  <p class="section-lead">每条结论至少由两本书支持，下面直接列出对应书籍和技法名；引用不成立的条目不会进入报告。</p>
  ${patterns}
</section>
${unique}
<aside class="method"><b>核对说明</b>　本报告只归纳所选书籍已经拆出的技法，不评价哪本书更好。开篇样本与全书样本分别标注，避免把局部观察冒充整本规律。</aside>
</body>
</html>`;
}

export class CommonPatternsPdfError extends Error {
  constructor(
    message: string,
    public readonly proRequired = false,
    public readonly upgradeUrl = "",
  ) {
    super(message);
  }
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

export function commonPatternsFileName(collectionName: string): string {
  const safe = (collectionName || "未命名榜单").replace(/[\\/:*?"<>|]/g, "_");
  return `${safe}-榜单共性报告.pdf`;
}

export async function downloadCommonPatternsPdf(
  collectionId: number,
  collectionName: string,
  result: PatternsResult,
): Promise<void> {
  const response = await fetch(
    `${getApiBase()}/api/v1/collections/${collectionId}/common-patterns/export-pdf`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ html: buildCommonPatternsHtml(collectionName, result) }),
    },
  );
  if (!response.ok) {
    let message = `PDF 导出失败（${response.status}）`;
    let errorCode = "";
    let upgradeUrl = "";
    try {
      const body = await response.json();
      const detail = body?.detail ?? body ?? {};
      message = detail.message || message;
      errorCode = detail.error_code || "";
      upgradeUrl = detail.details?.afdian_product_url || "";
    } catch {
      // Keep the status-based message when the sidecar returned non-JSON output.
    }
    throw new CommonPatternsPdfError(
      message,
      response.status === 403 && errorCode === "PDF_REQUIRES_VIP",
      upgradeUrl,
    );
  }
  triggerDownload(await response.blob(), commonPatternsFileName(collectionName));
}
