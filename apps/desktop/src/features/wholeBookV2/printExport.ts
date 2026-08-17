/** The report as paper: what an author prints, marks up, and rewrites against.
 *
 * Deliberately **not** the HTML export. That one is the audit surface — every section, every
 * row, the raw JSON embedded at the bottom — and it is right that it holds everything, because
 * its job is to let someone check the engine. This one has a different job and therefore a
 * different shape.
 *
 * Three rules, all of them consequences of what a professional reader told us about the screen
 * version:
 *
 * **Judgement first, measurement second.** The one module that reader valued was 综合诊断 —
 * the only one that states a conclusion and its reason in words. So the paper opens with what
 * to change and why, and the curve appears once, late, as support.
 *
 * **A hard page budget, and something has to lose.** Twenty pages. The per-chapter table is the
 * elastic section: it takes whatever is left and says plainly how many rows it dropped. Every
 * other section has a fixed allowance, because a report that grows with the book is a report
 * nobody finishes.
 *
 * **Nothing that cannot be acted on.** A finding with no chapter range is not printed. A
 * dimension with no conclusion is not printed. An empty section is omitted rather than shown
 * empty — on screen an empty panel is honest, on paper it is a wasted page.
 */
import type { WholeBookAnalysisV2 } from "./contracts";
import { DIMENSION_LABELS, PACING_SERIES, PACING_SCALE_NOTE } from "./presentation/labels";

const esc = (s: unknown): string =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!,
  );

const rng = (a: number, b: number): string => (a === b ? `第 ${a} 章` : `第 ${a}–${b} 章`);

/** Total pages the format may occupy. The number is the point: it forces the choices below. */
export const PAGE_BUDGET = 20;
/** What the fixed sections actually take once Chromium has laid them out.
 *
 *  Measured against a real render, twice — the first measurement was wrong in an instructive
 *  way. Nine declared sections came to twelve pages, so this was set to thirteen; then adding
 *  the doctype moved the page out of quirks mode, every metric shifted, and the same book
 *  printed twenty-one. The number below is from a standards-mode render with two pages of
 *  headroom, because a book with longer stage summaries overflows further and the budget has
 *  to hold for that book too. Calibrated by rendering: 14 lands an 800-chapter book on 19
 *  pages and 15 lands it on 18. Fifteen is the choice — the ceiling is a promise and one page
 *  of margin is not enough to keep it across books whose sections run longer.
 *
 *  This is what the elastic chapter table subtracts from, so an estimate that is too cautious
 *  does not cost pages — it costs chapters the author wanted to look up. */
const FIXED_PAGES = 15;
/** Rows of the per-chapter table that fit on one printed page, measured at this type size. */
const CHAPTER_ROWS_PER_PAGE = 46;

/** Quotations for a finding, resolved through the evidence index. */
function quotes(d: WholeBookAnalysisV2, ids: readonly string[] | undefined, max = 3): string {
  const rows = (ids ?? [])
    .map((id) => d.evidence_index[id])
    .filter(Boolean)
    .slice(0, max);
  if (!rows.length) return "";
  return `<div class="quotes">${rows
    .map(
      (r) =>
        `<p><span>第 ${r.chapter_index} 章</span>${esc(r.quote_or_excerpt)}</p>`,
    )
    .join("")}</div>`;
}

/** The single chart the paper carries: how much story happens, chapter by chapter. */
function curve(d: WholeBookAnalysisV2): string {
  const pts = d.pacing.points;
  if (pts.length < 3) return "";
  const W = 720, H = 150, L = 26, R = 8, T = 8, B = 18;
  const maxCh = pts.at(-1)?.chapter_end ?? 1;
  const x = (c: number) => L + (c / Math.max(1, maxCh)) * (W - L - R);
  const y = (v: number) => T + (1 - v / 100) * (H - T - B);
  const path = pts
    .map((p, i) => `${i ? "L" : "M"} ${x(p.chapter_start).toFixed(1)} ${y(p.plot_progress).toFixed(1)}`)
    .join(" ");
  const bands = d.pacing.pacing_regions
    .map((r) => {
      const x1 = x(r.chapter_start), x2 = x(r.chapter_end);
      const fill = r.type === "fatigue" ? "#e8d3c4" : "#cfe0d6";
      return `<rect x="${x1.toFixed(1)}" y="${T}" width="${Math.max(2, x2 - x1).toFixed(1)}" height="${H - T - B}" fill="${fill}"/>`;
    })
    .join("");
  return `<svg viewBox="0 0 ${W} ${H}" class="curve" role="img" aria-label="剧情推进曲线">
    ${bands}
    ${[0, 50, 100].map((v) => `<line x1="${L}" y1="${y(v)}" x2="${W - R}" y2="${y(v)}" stroke="#d9e0da"/><text x="${L - 4}" y="${y(v) + 3}" text-anchor="end" font-size="8" fill="#8a968d">${v}</text>`).join("")}
    <path d="${path}" fill="none" stroke="#14503c" stroke-width="1.6"/>
    <text x="${L}" y="${H - 4}" font-size="8" fill="#8a968d">第 1 章</text>
    <text x="${W - R}" y="${H - 4}" font-size="8" fill="#8a968d" text-anchor="end">第 ${maxCh} 章</text>
  </svg>`;
}

function coverPage(d: WholeBookAnalysisV2): string {
  const a = d.assessment;
  const dims = a.dimensions
    .filter((x) => x.conclusion)
    .map(
      (x) =>
        `<tr><th>${esc(DIMENSION_LABELS[x.dimension] ?? x.dimension)}</th>
         <td class="grade">${esc(x.rating)}</td><td>${esc(x.conclusion)}</td></tr>`,
    )
    .join("");
  const top = a.revision_priorities
    .filter((p) => p.chapter_ranges?.length)
    .slice(0, 3)
    .map(
      (p, i) =>
        `<li><b>${i + 1}</b><span class="where">${p.chapter_ranges
          .map((r) => rng(r[0], r[1]))
          .join("、")}</span>${esc(p.direction)}</li>`,
    )
    .join("");
  const tp = d.type_profile;
  return `<section class="page cover">
    <p class="kicker">全书分析</p>
    <h1>${esc(d.book_metadata.title)}</h1>
    <p class="meta">${esc(tp.primary_genre || "未确认类型")} ·
      ${d.book_metadata.chapter_count} 章 · ${d.book_metadata.character_count.toLocaleString()} 字</p>
    ${d.overview.one_sentence_story ? `<p class="one-line">${esc(d.overview.one_sentence_story)}</p>` : ""}
    ${a.overall_summary ? `<p class="overall">${esc(a.overall_summary)}</p>` : ""}
    ${dims ? `<h2>六个维度</h2><table class="dims">${dims}</table>` : ""}
    ${top ? `<h2>最该改的三处</h2><ol class="top3">${top}</ol>` : ""}
  </section>`;
}

function revisionPages(d: WholeBookAnalysisV2): string {
  const a = d.assessment;
  const byRange = new Map<string, (typeof a.issues)[number]>();
  for (const issue of a.issues) byRange.set(`${issue.chapter_start}-${issue.chapter_end}`, issue);
  const rows = a.revision_priorities
    .filter((p) => p.chapter_ranges?.length)
    .map((p, i) => {
      // Pair each priority with the issue that shares its range: the priority says what to do,
      // the issue says why, and printed apart they read as two lists of the same three things.
      const key = p.chapter_ranges[0];
      const issue =
        byRange.get(`${key[0]}-${key[1]}`) ??
        a.issues.find((x) => x.chapter_start <= key[1] && x.chapter_end >= key[0]);
      return `<section class="page">
        <p class="kicker">要改什么 · 第 ${i + 1} 处</p>
        <h2 class="where">${p.chapter_ranges.map((r) => rng(r[0], r[1])).join("、")}</h2>
        <p class="direction">${esc(p.direction)}</p>
        ${
          issue
            ? `<dl class="why">
                 <dt>症状</dt><dd>${esc(issue.symptom)}</dd>
                 <dt>根因</dt><dd>${esc(issue.root_cause)}</dd>
                 <dt>读者会怎样</dt><dd>${esc(issue.reader_impact)}</dd>
               </dl>${quotes(d, issue.evidence)}`
            : ""
        }
        ${
          p.preserve?.length
            ? `<div class="keep"><h3>改的时候必须保住</h3><ul>${p.preserve
                .map((k) => `<li>${esc(k)}</li>`)
                .join("")}</ul></div>`
            : ""
        }
      </section>`;
    })
    .join("");
  return rows;
}

function keepPage(d: WholeBookAnalysisV2): string {
  const a = d.assessment;
  if (!a.strengths.length && !a.preserve_list.length) return "";
  return `<section class="page">
    <p class="kicker">不要动什么</p>
    <h2>这本书已经做对的地方</h2>
    ${a.strengths
      .map(
        (s) =>
          `<div class="strength"><h3>${esc(s.title)}<span>${rng(s.chapter_start, s.chapter_end)}</span></h3>
           <p>${esc(s.why_good)}</p>${quotes(d, s.evidence, 2)}</div>`,
      )
      .join("")}
    ${
      a.preserve_list.length
        ? `<h3 class="plain">改稿时的保留清单</h3><ul class="keeplist">${a.preserve_list
            .map((x) => `<li>${esc(x)}</li>`)
            .join("")}</ul>`
        : ""
    }
  </section>`;
}

function storyPages(d: WholeBookAnalysisV2): string {
  const st = d.story;
  const ov = d.overview;
  const stages = st.structure_stages
    .map(
      (s) =>
        `<div class="stage"><h3><span>${rng(s.chapter_start, s.chapter_end)}</span>${esc(s.title)}</h3>
         <p>${esc(s.summary)}</p>${s.turning_point ? `<p class="turn"><span>转折</span>${esc(s.turning_point)}</p>` : ""}</div>`,
    )
    .join("");
  const open = st.storylines
    .filter((l) => l.status !== "resolved")
    .slice(0, 12)
    .map(
      (l) =>
        `<li><span class="where">${rng(l.chapter_start, l.chapter_end)}</span>${esc(l.name)}</li>`,
    )
    .join("");
  if (!stages && !open) return "";
  return `<section class="page">
    <p class="kicker">故事怎么走的</p>
    ${stages ? `<h2>结构阶段</h2>${stages}` : ""}
    ${
      open
        ? `<h2>走到最后仍未收束的线</h2>
           <p class="note">这些是读者读完还挂着的。有意留白就不用管；不是的话，是最容易被投诉的地方。</p>
           <ul class="lines">${open}</ul>`
        : ""
    }
  </section>`;
}

function pacingPage(d: WholeBookAnalysisV2): string {
  if (!d.pacing.points.length) return "";
  const regions = d.pacing.pacing_regions
    .map(
      (r) =>
        `<div class="region ${r.type}"><h3>${rng(r.chapter_start, r.chapter_end)}<span>${
          r.type === "fatigue" ? "偏缓" : "高强度"
        }</span></h3><p>${esc(r.reason)}</p><p class="diag">${esc(r.diagnosis)}</p></div>`,
    )
    .join("");
  return `<section class="page">
    <p class="kicker">节奏</p>
    <h2>剧情推进，逐章</h2>
    ${curve(d)}
    <p class="note">${esc(PACING_SCALE_NOTE)}底色标出的是引擎测到的异常区间。</p>
    ${regions ? `<h2>异常区间</h2>${regions}` : "<p class='note'>没有测到连续偏缓或连续高强度的区间。</p>"}
  </section>`;
}

function castPage(d: WholeBookAnalysisV2): string {
  const c = d.characters;
  const p = c.protagonist;
  const arc =
    p.initial_goal && p.final_goal && p.initial_goal !== p.final_goal
      ? `<p class="arc"><span>${esc(p.initial_goal)}</span><i>→</i><span>${esc(p.final_goal)}</span></p>`
      : "";
  const stages = (p.stages ?? [])
    .map(
      (s) =>
        `<li><span class="where">${rng(s.chapter, s.chapter_end ?? s.chapter)}</span>
         <b>${esc(s.stage_name)}</b>${s.entry_state ? `<em>${esc(s.entry_state)}</em>` : ""}</li>`,
    )
    .join("");
  const cast = c.major_characters
    .filter((m) => m.role !== "protagonist")
    .slice(0, 16)
    .map(
      (m) =>
        `<tr><th>${esc(m.name)}</th><td>${esc(m.relationship_to_protagonist || "—")}</td></tr>`,
    )
    .join("");
  if (!arc && !stages && !cast) return "";
  return `<section class="page">
    <p class="kicker">人物</p>
    <h2>${esc(p.initial_identity || "主角")}走过的路</h2>
    ${arc}
    ${stages ? `<ol class="pstages">${stages}</ol>` : ""}
    ${cast ? `<h2>其他人在这本书里做什么</h2><table class="cast">${cast}</table>` : ""}
  </section>`;
}

function suspensePage(d: WholeBookAnalysisV2): string {
  const all = d.suspense.lifecycles;
  if (!all.length) return "";
  const open = all.filter((l) => l.status !== "resolved");
  const closed = all.filter((l) => l.status === "resolved");
  return `<section class="page">
    <p class="kicker">悬念</p>
    <h2>没有回答的问题<small>${open.length} / ${all.length}</small></h2>
    <p class="note">这一页只为一件事存在：读者带着问题读完了，你知不知道是哪几个。</p>
    <ul class="qs">${open
      .slice(0, 24)
      .map(
        (l) =>
          `<li><span class="where">${rng(l.chapter_start, l.chapter_end)}</span>${esc(l.question)}</li>`,
      )
      .join("")}</ul>
    ${
      closed.length
        ? `<h3 class="plain">已经回答的</h3><ul class="qs done">${closed
            .map((l) => `<li>${esc(l.question)}</li>`)
            .join("")}</ul>`
        : ""
    }
  </section>`;
}

function chapterPages(d: WholeBookAnalysisV2, pagesLeft: number): string {
  const fns = d.chapters.functions;
  if (!fns.length || pagesLeft < 1) return "";
  const cap = Math.max(0, pagesLeft) * CHAPTER_ROWS_PER_PAGE;
  const shown = fns.slice(0, cap);
  const dropped = fns.length - shown.length;
  return `<section class="page">
    <p class="kicker">逐章速查</p>
    <h2>每一章在做什么<small>${shown.length} / ${fns.length} 章</small></h2>
    ${
      dropped > 0
        ? `<p class="note">页数上限是 ${PAGE_BUDGET} 页，这张表按顺序取到第 ${shown.at(-1)?.chapter_index} 章，
           <b>后面 ${dropped} 章没有印出来</b>。完整逐章表在 HTML 导出里。</p>`
        : ""
    }
    <table class="chapters">${shown
      .map(
        (f) =>
          `<tr><th>${f.chapter_index}</th><td class="fn">${esc(f.primary_function)}</td>
           <td>${esc(f.summary || "—")}</td></tr>`,
      )
      .join("")}</table>
  </section>`;
}

function methodPage(d: WholeBookAnalysisV2): string {
  const m = d.analysis_metadata;
  const missing: string[] = [];
  if (!d.assessment.dimensions.length) missing.push("六维评估");
  if (!d.story.structure_stages.length) missing.push("结构阶段");
  if (!d.suspense.lifecycles.length) missing.push("悬念");
  if (!d.pacing.points.length) missing.push("节奏曲线");
  return `<section class="page method">
    <p class="kicker">这份报告是怎么来的</p>
    <h2>方法</h2>
    <dl>
      <dt>引文</dt><dd>每一条引文都是原文里的句子，由抽取时记下的段落位置解析而来，不是模型复述的。</dd>
      <dt>曲线</dt><dd>${esc(PACING_SCALE_NOTE)}</dd>
      <dt>类型</dt><dd>${
        d.type_profile.genre_confidence === 1
          ? "由你确认的画像决定，不是模型的猜测。"
          : "画像未确认，类型是模型根据全文给出的判断。"
      }</dd>
      <dt>没有测的</dt><dd>${
        missing.length ? esc(missing.join("、")) + "：这些板块这次没有产出，页面上留空而不是编内容。" : "本次七个板块都有产出。"
      }</dd>
    </dl>
    <h2>出处</h2>
    <table class="meta-table">
      <tr><th>模型</th><td>${esc(m.provider)} · ${esc(m.model)}</td></tr>
      <tr><th>真实模型调用</th><td>${m.real_provider_calls} 次</td></tr>
      <tr><th>快照</th><td>#${d.book_metadata.snapshot_id} · ${esc(String(d.book_metadata.revision_hash).slice(0, 12))}</td></tr>
      <tr><th>证据条目</th><td>${Object.keys(d.evidence_index).length} 条</td></tr>
    </table>
  </section>`;
}

/** The whole document. Sections are assembled in priority order, then the chapter table takes
 *  whatever pages are left — which is how the budget is actually enforced rather than hoped for. */
export function buildPrintHtml(d: WholeBookAnalysisV2): string {
  const revisions = revisionPages(d);
  const revisionCount = (revisions.match(/class="page"/g) ?? []).length;
  const fixed = [
    coverPage(d),
    revisions,
    keepPage(d),
    storyPages(d),
    pacingPage(d),
    castPage(d),
    suspensePage(d),
  ].join("");
  const used = 1 + revisionCount + 1 + 1 + 1 + 1 + 1 + 1; // + method page
  const chapters = chapterPages(d, Math.max(0, PAGE_BUDGET - Math.max(used, FIXED_PAGES) - 1));
  // Declared, not left to sniffing. This file is written to disk and opened as `file:///` by a
  // headless Chromium, and a document with no charset is decoded with the system default — on a
  // Chinese Windows that is GBK, and the whole report prints as mojibake. It happened to come
  // out right in testing, which is exactly the kind of luck that stops holding on someone
  // else's machine.
  return `<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<title>${esc(d.book_metadata.title)} · 全书分析</title>
<style>
@page { size: A4; margin: 16mm 15mm 14mm; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  margin: 0; color: #17201a; background: #fff;
  font-family: "Songti SC", SimSun, "Noto Serif CJK SC", serif;
  font-size: 10.5pt; line-height: 1.72;
}
.page { break-after: page; }
.page:last-child { break-after: auto; }
h1 { font-size: 24pt; margin: 0 0 2mm; line-height: 1.25; }
h2 {
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  font-size: 12pt; margin: 8mm 0 3mm; padding-bottom: 1.5mm;
  border-bottom: .6pt solid #14503c; color: #14503c;
  display: flex; justify-content: space-between; align-items: baseline;
}
h2 small { font-weight: 400; font-size: 9pt; color: #7b8a80; }
h3 { font-family: "PingFang SC", "Microsoft YaHei", sans-serif; font-size: 10.5pt; margin: 4mm 0 1.5mm; }
h3.plain { color: #7b8a80; font-size: 9.5pt; border-top: .5pt solid #dfe6e0; padding-top: 3mm; }
p { margin: 0 0 2.5mm; }
.kicker {
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  font-size: 8pt; letter-spacing: .18em; color: #14503c; margin: 0 0 2mm;
}
.cover .meta { font-family: "PingFang SC", sans-serif; color: #6b7a70; font-size: 9.5pt; margin-bottom: 6mm; }
.one-line { font-size: 13pt; line-height: 1.6; margin-bottom: 4mm; }
.overall { color: #3d4a42; }
.note { font-family: "PingFang SC", sans-serif; font-size: 8.5pt; color: #7b8a80; }
.where {
  font-family: "PingFang SC", sans-serif; font-size: 8.5pt; color: #14503c;
  white-space: nowrap; font-variant-numeric: tabular-nums;
}
table { width: 100%; border-collapse: collapse; }
.dims th { text-align: left; width: 20mm; font-weight: 600; padding: 1.5mm 0; vertical-align: top; }
.dims td { padding: 1.5mm 0 1.5mm 3mm; vertical-align: top; }
.dims .grade {
  width: 12mm; font-family: "PingFang SC", sans-serif; font-weight: 700; color: #14503c;
}
.dims tr + tr th, .dims tr + tr td { border-top: .4pt solid #eaefeb; }
.top3 { margin: 0; padding: 0; list-style: none; counter-reset: t; }
.top3 li { display: flex; gap: 3mm; padding: 2mm 0; border-top: .4pt solid #eaefeb; }
.top3 b { color: #14503c; font-family: "PingFang SC", sans-serif; }
.direction { font-size: 12pt; line-height: 1.6; margin-bottom: 5mm; }
h2.where { font-size: 11pt; border-bottom-color: #dfe6e0; }
.why { margin: 0 0 4mm; }
.why dt {
  font-family: "PingFang SC", sans-serif; font-size: 8.5pt; color: #7b8a80;
  letter-spacing: .08em; margin-top: 3mm;
}
.why dd { margin: .5mm 0 0; }
.quotes { border-left: 1.2pt solid #14503c; padding-left: 4mm; margin: 3mm 0 0; }
.quotes p { margin: 0 0 1.5mm; color: #3d4a42; }
.quotes span {
  font-family: "PingFang SC", sans-serif; font-size: 8pt; color: #14503c; margin-right: 2mm;
  font-variant-numeric: tabular-nums;
}
.keep { margin-top: 5mm; padding: 3mm 4mm; background: #f2f6f3; break-inside: avoid; }
.keep h3 { margin: 0 0 1.5mm; color: #14503c; }
.keep ul, .keeplist { margin: 0; padding-left: 5mm; }
.strength { break-inside: avoid; margin-bottom: 4mm; }
.strength h3 { display: flex; justify-content: space-between; gap: 4mm; }
.strength h3 span { font-weight: 400; font-size: 8.5pt; color: #14503c; }
.stage { break-inside: avoid; margin-bottom: 4mm; }
.stage h3 { display: flex; gap: 3mm; align-items: baseline; }
.stage h3 span { font-weight: 400; font-size: 8.5pt; color: #14503c; white-space: nowrap; }
.turn { font-size: 9.5pt; color: #3d4a42; }
.turn span {
  font-family: "PingFang SC", sans-serif; font-size: 8pt; color: #a8551f; margin-right: 2mm;
}
ul.lines, ul.qs { margin: 0; padding: 0; list-style: none; }
ul.lines li, ul.qs li {
  display: flex; gap: 3mm; padding: 1.2mm 0; border-top: .4pt solid #eaefeb; break-inside: avoid;
}
ul.qs.done li { color: #7b8a80; font-size: 9.5pt; }
.curve { width: 100%; height: auto; margin: 2mm 0 3mm; }
.region { break-inside: avoid; margin-bottom: 3mm; padding-left: 3mm; border-left: 1.2pt solid #a8551f; }
.region.climax { border-left-color: #14503c; }
.region h3 { margin: 0 0 1mm; display: flex; gap: 3mm; align-items: baseline; }
.region h3 span { font-weight: 400; font-size: 8.5pt; color: #7b8a80; }
.region p { margin: 0; font-size: 9.5pt; }
.region .diag { color: #3d4a42; }
.arc { display: flex; gap: 3mm; align-items: baseline; font-size: 11pt; margin-bottom: 4mm; }
.arc i { color: #14503c; font-style: normal; }
ol.pstages { margin: 0; padding: 0; list-style: none; }
ol.pstages li {
  display: flex; gap: 3mm; padding: 1.5mm 0; border-top: .4pt solid #eaefeb;
  align-items: baseline; break-inside: avoid;
}
ol.pstages em { font-style: normal; color: #7b8a80; font-size: 9.5pt; }
.cast th { text-align: left; width: 22mm; font-weight: 600; padding: 1.2mm 0; vertical-align: top; }
.cast td { padding: 1.2mm 0 1.2mm 3mm; color: #3d4a42; }
.cast tr + tr th, .cast tr + tr td { border-top: .4pt solid #eaefeb; }
.chapters { font-size: 8.5pt; }
.chapters th {
  text-align: right; width: 8mm; padding: .6mm 2mm .6mm 0; color: #14503c;
  font-weight: 400; font-variant-numeric: tabular-nums; vertical-align: top;
}
.chapters .fn {
  width: 22mm; font-family: "PingFang SC", sans-serif; font-size: 7.5pt; color: #7b8a80;
  vertical-align: top; padding-right: 2mm;
}
.chapters td { padding: .6mm 0; vertical-align: top; }
.chapters tr + tr th, .chapters tr + tr td { border-top: .3pt solid #f0f4f1; }
.method dl { margin: 0; }
.method dt {
  font-family: "PingFang SC", sans-serif; font-size: 8.5pt; color: #14503c;
  letter-spacing: .08em; margin-top: 3.5mm;
}
.method dd { margin: .5mm 0 0; color: #3d4a42; }
.meta-table th {
  text-align: left; width: 30mm; font-family: "PingFang SC", sans-serif; font-size: 9pt;
  color: #7b8a80; font-weight: 400; padding: 1.2mm 0;
}
.meta-table td { padding: 1.2mm 0; font-variant-numeric: tabular-nums; }
</style>
${fixed}${chapters}${methodPage(d)}`;
}
