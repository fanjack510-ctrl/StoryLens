/** 「读懂」交出去的那份文件。
 *
 *  版面沿用全书与单章那两份印刷报告的字体与色板（见 printExport.ts、
 *  readerJourney/chapterReportExport.ts）：结构用无衬线，正文用衬线。三份文件出自同一个产品，
 *  读者不该在纸上看出三种审美。
 *
 *  但顺序不同，因为它回答的问题不同。那两份回答「这本小说写得怎么样 / 怎么搭起来的」；这一份
 *  回答**「我不读原文，能知道什么」**。所以第一页不是内容，是**可信度**：覆盖了多少节、哪几
 *  节没读到。
 *
 *  小说漏一段，报告读起来仍然完整；知识类书漏一节，读者拿它替代原文，而他不会知道自己漏了
 *  什么。把覆盖率放在末尾的小字里，等于让他在不知情的情况下信一份残缺的东西——纸比屏幕更
 *  容易被当成定稿，所以这条在纸上比在屏幕上更要紧。
 */
import type { ComprehendResult } from "../../services/wholeBookFreeProductApi";

const esc = (s: unknown): string =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[c]!,
  );

const INK = "#17201a";
const KEY = "#14503c";
const MUTE = "#6f7d74";
const RULE = "#d8e0da";
const WARN = "#a8551f";

function list(label: string, items: string[] | undefined, cls = ""): string {
  if (!items?.length) return "";
  return (
    `<div class="k">${esc(label)}</div>` +
    `<ul class="${cls}">${items.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`
  );
}

export function comprehendFileName(title: string): string {
  const safe = String(title || "书")
    .replace(/[\\/:*?"<>|]/g, "_")
    .slice(0, 60);
  return `StoryLens_${safe}_读懂.html`;
}

export function buildComprehendPrintHtml(data: ComprehendResult, title: string): string {
  const total = data.sections_total ?? 0;
  const covered = data.sections_covered ?? 0;
  const pct = Math.round((data.coverage ?? 0) * 100);
  const missed = total - covered;

  const cards = (
    [
      ["一段话说清这本书", data.book?.one_paragraph],
      ["全书的主张", data.book?.argument],
      ["读完能带走什么", data.book?.what_you_get],
      ["谁该读、谁不必读", data.book?.who_should_read],
    ] as Array<[string, string | undefined]>
  )
    .filter(([, body]) => Boolean((body || "").trim()))
    .map(([label, body]) => `<div class="card"><h3>${esc(label)}</h3><p>${esc(body)}</p></div>`)
    .join("");

  const chapters = (data.chapters ?? [])
    .map((chapter) => {
      const secs = (chapter.sections ?? [])
        .map((s) =>
          s.error
            ? // 读失败的节留在原位并说出原因。悄悄跳过，读者会以为这一节本来就没内容。
              `<div class="sec bad"><h4>${esc(s.label)}</h4>` +
              `<p class="err">这一节没有读到：${esc(s.error)}</p></div>`
            : `<div class="sec"><h4>${esc(s.label)}</h4>` +
              list("主张", s.claims) +
              list("依据", s.evidence) +
              list("做法", s.actions, "do") +
              list("术语", s.terms, "term") +
              list("存疑", s.open_questions, "q") +
              `</div>`,
        )
        .join("");
      return (
        `<section class="ch"><h2>${esc(chapter.chapter)} ${esc(chapter.title)}</h2>` +
        (chapter.summary ? `<p class="lead">${esc(chapter.summary)}</p>` : "") +
        (chapter.through_line ? `<p class="line">主线：${esc(chapter.through_line)}</p>` : "") +
        (chapter.error ? `<p class="err">${esc(chapter.error)}</p>` : "") +
        secs +
        `</section>`
      );
    })
    .join("");

  const trust = data.trustworthy
    ? `<p class="trust ok">覆盖 ${covered}/${total} 节（${pct}%）——全书都读到了。</p>`
    : `<p class="trust warn">只覆盖了 ${covered}/${total} 节（${pct}%），有 ${missed} 节没读到。` +
      `这份摘要不完整，涉及那几节的内容请回原文核对。</p>`;

  // 显式声明字符集。这份 HTML 会被写到磁盘、由无头 Chromium 以 file:/// 打开；不声明就走系统
  // 默认，中文 Windows 上是 GBK，整份报告会印成乱码。
  return `<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<title>${esc(title)} · 读懂</title>
<style>
@page { size: A4; margin: 18mm 17mm 16mm; }
:root {
  --sans: "PingFang SC", "Microsoft YaHei", "Hiragino Sans GB", sans-serif;
  --serif: "Songti SC", SimSun, "Noto Serif CJK SC", serif;
  --ink: ${INK}; --mute: ${MUTE}; --rule: ${RULE}; --key: ${KEY}; --warn: ${WARN};
}
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; color: var(--ink); background: #fff;
  font-family: var(--serif); font-size: 10.5pt; line-height: 1.75; }
h1, h2, h3, h4, .k, .kicker, .trust, .err, .term, .meta { font-family: var(--sans); }
p, li { font-family: var(--serif); }
.kicker { font-size: 8.5pt; letter-spacing: .3em; color: var(--key); margin: 0 0 3mm; }
h1 { font-size: 22pt; line-height: 1.3; margin: 0 0 2mm; }
.meta { font-size: 8.5pt; color: var(--mute); }
.trust { font-size: 10pt; padding: 3mm 4mm; margin: 4mm 0 7mm;
  border-left: 2pt solid var(--key); background: rgba(20,80,60,.05); }
.trust.warn { border-left-color: var(--warn); color: var(--warn); background: rgba(168,85,31,.06); }
.card { border-left: 2pt solid var(--key); padding: 0 0 0 4mm; margin: 0 0 5mm; break-inside: avoid; }
.card h3 { font-size: 11pt; color: var(--key); margin: 0 0 1.5mm; }
.card p { margin: 0; }
.ch { break-inside: auto; margin-top: 8mm; }
h2 { font-size: 13pt; color: var(--key); border-bottom: 1pt solid var(--key);
  padding-bottom: 2mm; margin: 0 0 3mm; }
.lead { margin: 0 0 1mm; }
.line { color: var(--mute); font-size: 9pt; margin: 0 0 3mm; }
.sec { margin: 4mm 0 0; padding-left: 3.5mm; border-left: .5pt solid var(--rule); break-inside: avoid; }
.sec.bad { border-left-color: var(--warn); }
.sec h4 { font-size: 10pt; margin: 0 0 1mm; }
.k { font-size: 8pt; letter-spacing: .08em; color: var(--mute); margin-top: 2mm; }
ul { margin: .5mm 0 0; padding-left: 5mm; }
li { padding: .3mm 0; }
.do li { color: var(--key); }
.q li { color: var(--warn); }
.term li { font-family: var(--sans); font-size: 8.5pt; color: var(--mute); }
.err { color: var(--warn); font-size: 9pt; }
.foot { margin-top: 10mm; padding-top: 3mm; border-top: .5pt solid var(--rule);
  font-size: 8.5pt; color: var(--mute); line-height: 1.7; }
</style>
<p class="kicker">STORYLENS · 读懂</p>
<h1>${esc(title)}</h1>
<p class="meta">专著与工具书 · ${data.provider_calls ?? 0} 次模型调用</p>
${trust}
${cards}
${chapters}
<p class="foot">
结构由程序从原书解析：${esc((data.rules ?? []).join("；") || "—")}。
每条主张都标注了所属章节，可回原文核对——对知识类书籍，能不能翻回去，就是这份摘要可不可信的
分界线。${(data.failures ?? []).length ? `本次有 ${data.failures.length} 处没有读到，已在正文中逐条标出。` : ""}
</p>
</html>`;
}
