/** The analysis as a formal report: the document a paying reader receives.
 *
 * Deliberately **not** the HTML export. That one is the audit surface — every section, every
 * row, the raw JSON at the bottom — and holding everything is right for that job. This one is
 * read cover to cover by someone deciding what to rewrite, so it is organised as an argument
 * rather than as a tour of the data.
 *
 * ## The argument
 *
 * Everything below follows one chain, and the chain is stated to the reader on page one so
 * they know how to read the rest:
 *
 *     测量 → 分项判断 → 问题 → 建议
 *
 * Each analytical chapter examines one aspect of the book, and each ends in **本章判断** — the
 * assessment's rating and conclusion for exactly that aspect. Those six judgements are what the
 * summary table on page one aggregates; the problems in 第七章 are the negative judgements made
 * specific; the recommendations in 第八章 are those problems made actionable. Nothing appears
 * that is not either evidence for a judgement, a judgement, or a consequence of one.
 *
 * That is the whole reason for the chapter order. An earlier draft led with the recommendations
 * and put the measurements after, on the theory that judgement should come first. It reads as
 * disorder: a recommendation before its evidence is an assertion. The summary on page one keeps
 * the judgement-first benefit without breaking the chain.
 *
 * ## Rules the format holds itself to
 *
 * **Twenty pages, and the appendix is what gives.** 附录 A takes the pages the report proper
 * leaves and states how many chapters it dropped. Every other section has a fixed allowance,
 * because a report that grows with the book is a report nobody finishes.
 *
 * **Nothing unusable is printed.** A model that answers "unknown" has told us nothing, and a
 * table row saying so wastes the reader's attention — see {@link val}. An empty section is
 * omitted rather than shown empty: on screen a blank panel is honest, on paper it is a wasted
 * sheet.
 *
 * **One typeface per job.** Sans for structure — numbering, headings, labels, chapter
 * references, figures. Serif for prose. The mixture is not decorative; it is what lets a reader
 * skip the furniture and find the sentences.
 */
import type { WholeBookAnalysisV2 } from "./contracts";
import { DIMENSION_LABELS, PACING_SCALE_NOTE, saidNothing } from "./presentation/labels";

const esc = (s: unknown): string =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[c]!,
  );

/** A field's usable text, or "" when there is nothing usable in it.
 *
 *  The placeholder rule itself lives in ./presentation/labels so the screen, the HTML
 *  export and this one cannot disagree about what counts as an answer. */
const val = (s: unknown): string => {
  const t = String(s ?? "").trim();
  return saidNothing(t) ? "" : t;
};

const rng = (a: number, b: number): string => (a === b ? `第 ${a} 章` : `第 ${a}–${b} 章`);

/** Cut prose to a length the layout can hold, on a sentence break where one is near. */
function clip(text: string, max: number): string {
  const t = val(text);
  if (t.length <= max) return t;
  const head = t.slice(0, max);
  const stop = Math.max(head.lastIndexOf("。"), head.lastIndexOf("；"), head.lastIndexOf("，"));
  return (stop > max * 0.6 ? head.slice(0, stop + 1) : head) + "…";
}

/** Total pages the format may occupy. The number is the point: it forces the choices below. */
export const PAGE_BUDGET = 20;
/** What the report proper takes once Chromium has laid it out.
 *
 *  **Measured, never counted from the section list.** A section that overflows takes two pages
 *  while still being one `<section>`, so counting declarations undercounts — by six pages, when
 *  it was last tried. The way to re-measure is to render the document with print media emulated
 *  and read each section's height against the printable area (263mm on A4 at these margins).
 *  Last measured: the 800-chapter fixture puts the cover, eight chapters and 附录 B at 14 pages,
 *  the real 《系统豪横》 document at 15. Fifteen, so the tighter book still holds. */
const FIXED_PAGES = 15;
/** Rows of 附录 A that fit on one printed page, measured at this type size. */
const CHAPTER_ROWS_PER_PAGE = 44;
/** 附录 A is a lookup table, not the argument. It may not crowd out the analysis even when the
 *  budget would allow it — the brief was explicitly that per-chapter blurbs should shrink and
 *  findings should grow. */
const APPENDIX_MAX_PAGES = 4;
/** 附录 A's first page is spent on A.1 and the 章节效率 judgement, not on rows. Measured at
 *  0.97 of a page; charging it a whole one is what keeps the total inside the budget. Leaving
 *  it out is the arithmetic error that printed twenty-one pages against a twenty-page promise. */
const APPENDIX_HEADER_PAGES = 1;

/** The dimension each analytical chapter is answerable to. This mapping *is* the report's
 *  spine: it is why every chapter can end in a judgement rather than trailing off. */
const CHAPTER_DIMENSION = {
  structure: "story_structure",
  pacing: "pacing",
  characters: "protagonist_growth",
  relationships: "character_relationships",
  suspense: "suspense_payoff",
  chapters: "chapter_efficiency",
} as const;

type Dim = WholeBookAnalysisV2["assessment"]["dimensions"][number];

/** Revision priorities are `unknown[]` in the contract because the shape settled late. */
type Priority = {
  priority?: string;
  chapter_ranges?: Array<[number, number]>;
  direction?: string;
  preserve?: string[];
};
const priorities = (d: WholeBookAnalysisV2): Priority[] =>
  (d.assessment.revision_priorities as Priority[]).filter((p) => p?.chapter_ranges?.length);

function dim(d: WholeBookAnalysisV2, key: string): Dim | undefined {
  return d.assessment.dimensions.find((x) => x.dimension === key && val(x.conclusion));
}

/** The closing paragraph of an analytical chapter: the rating for what the chapter examined,
 *  and the sentence that justifies it. Omitted rather than faked when the dimension is absent. */
function judgement(d: WholeBookAnalysisV2, ...keys: string[]): string {
  const rows = keys.map((k) => dim(d, k)).filter(Boolean) as Dim[];
  if (!rows.length) return "";
  return `<div class="judgement"><h3>本章判断</h3>${rows
    .map(
      (x) =>
        `<p><b class="grade">${esc(x.rating)}</b><span class="dimname">${esc(
          DIMENSION_LABELS[x.dimension] ?? x.dimension,
        )}</span>${esc(x.conclusion)}</p>`,
    )
    .join("")}</div>`;
}

/** Quotations for a claim, resolved through the evidence index. */
function quotes(d: WholeBookAnalysisV2, ids: readonly string[] | undefined, max = 3): string {
  const rows = (ids ?? [])
    .map((id) => d.evidence_index[id])
    .filter((r) => r && val(r.quote_or_excerpt))
    .slice(0, max);
  if (!rows.length) return "";
  return `<div class="quotes"><p class="qlabel">原文佐证</p>${rows
    .map((r) => `<p><span>第 ${r.chapter_index} 章</span>${esc(r.quote_or_excerpt)}</p>`)
    .join("")}</div>`;
}

/** 图 1. One curve: how much story happens, chapter by chapter, with the measured regions
 *  shaded. A second line would have to be defended; this one carries the chapter's argument. */
function curve(d: WholeBookAnalysisV2): string {
  const pts = d.pacing.points;
  if (pts.length < 3) return "";
  const W = 720, H = 156, L = 28, R = 8, T = 10, B = 20;
  const maxCh = pts.at(-1)?.chapter_end ?? 1;
  const x = (c: number) => L + (c / Math.max(1, maxCh)) * (W - L - R);
  const y = (v: number) => T + (1 - v / 100) * (H - T - B);
  const path = pts
    .map((p, i) => `${i ? "L" : "M"} ${x(p.chapter_start).toFixed(1)} ${y(p.plot_progress).toFixed(1)}`)
    .join(" ");
  const bands = d.pacing.pacing_regions
    .map((r) => {
      const x1 = x(r.chapter_start), x2 = x(r.chapter_end);
      const fill = r.type === "fatigue" ? "#eadbcc" : "#d6e4dc";
      return `<rect x="${x1.toFixed(1)}" y="${T}" width="${Math.max(2, x2 - x1).toFixed(1)}" height="${H - T - B}" fill="${fill}"/>`;
    })
    .join("");
  const grid = [0, 25, 50, 75, 100]
    .map(
      (v) =>
        `<line x1="${L}" y1="${y(v)}" x2="${W - R}" y2="${y(v)}" stroke="${v === 50 ? "#c9d4cc" : "#e6ece8"}"/>` +
        `<text x="${L - 5}" y="${y(v) + 3}" text-anchor="end" font-size="8" fill="#7b8a80">${v}</text>`,
    )
    .join("");
  const ticks = [1, Math.round(maxCh / 2), maxCh]
    .map(
      (c) =>
        `<text x="${x(c).toFixed(1)}" y="${H - 5}" font-size="8" fill="#7b8a80" text-anchor="${
          c === 1 ? "start" : c === maxCh ? "end" : "middle"
        }">${c}</text>`,
    )
    .join("");
  return `<figure class="fig">
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="剧情推进度曲线">
      ${bands}${grid}
      <path d="${path}" fill="none" stroke="#14503c" stroke-width="1.6"/>
      ${ticks}
    </svg>
    <figcaption>图 1　剧情推进度，按章。纵轴为本书内部百分位；底色为引擎测出的异常区间（暖色偏缓，冷色高强度）。</figcaption>
  </figure>`;
}

/* ── 封面 ─────────────────────────────────────────────────────────────────────────────── */

function coverPage(d: WholeBookAnalysisV2, toc: string[]): string {
  const m = d.book_metadata;
  const tp = d.type_profile;
  const meta: Array<[string, string]> = [
    ["分析对象", `《${m.title}》　${m.chapter_count} 章　${m.character_count.toLocaleString()} 字`],
    ["作品类型", val(tp.primary_genre) || "未确认"],
    ["报告编号", `WB-${String(d.analysis_metadata.run_id).padStart(4, "0")}`],
    ["数据快照", `#${m.snapshot_id}　${String(m.revision_hash).slice(0, 12)}`],
  ];
  return `<section class="page cover">
    <div class="cover-head">
      <p class="kicker">小说全书分析</p>
      <h1>${esc(m.title)}</h1>
      <p class="cover-sub">全书分析报告</p>
    </div>
    <table class="meta-table">${meta
      .map(([k, v]) => `<tr><th>${k}</th><td>${esc(v)}</td></tr>`)
      .join("")}</table>
    <div class="toc">
      <h2>目次</h2>
      <ol>${toc.map((t) => `<li>${esc(t)}</li>`).join("")}</ol>
    </div>
    <p class="cover-note">本报告的结论均由对全书正文的测量得出。每一章末的「本章判断」给出该项的评级与依据，
      第七章将各项判断中的负面结论整理为问题，第八章据此给出修订建议。附录 B 说明测量口径与数据来源。</p>
  </section>`;
}

/* ── 一、执行摘要 ─────────────────────────────────────────────────────────────────────── */

function summaryPage(d: WholeBookAnalysisV2): string {
  const a = d.assessment;
  const dims = a.dimensions
    .filter((x) => val(x.conclusion))
    .map(
      (x) =>
        `<tr><th>${esc(DIMENSION_LABELS[x.dimension] ?? x.dimension)}</th>
         <td class="grade">${esc(x.rating)}</td><td>${esc(x.conclusion)}</td></tr>`,
    )
    .join("");
  const top = priorities(d)
    .slice(0, 3)
    .map(
      (p, i) =>
        `<tr><th>${i + 1}</th><td class="where">${p.chapter_ranges!
          .map((r) => rng(r[0], r[1]))
          .join("、")}</td><td>${esc(val(p.direction))}</td></tr>`,
    )
    .join("");
  return `<section class="page">
    <h2><span class="num">一</span>执行摘要</h2>
    ${
      val(a.overall_summary)
        ? `<h3>1.1　总体判定</h3><p class="lead">${esc(a.overall_summary)}</p>`
        : ""
    }
    ${
      dims
        ? `<h3>1.2　分项评级</h3>
           <p class="note">评级为 A 至 C 六档，由模型在通读全书的测量结果上给出，A 为最佳。
             每一项的依据见对应章节末的「本章判断」。</p>
           <table class="dims">${dims}</table>`
        : ""
    }
    ${
      top
        ? `<h3>1.3　关键修订项</h3>
           <p class="note">按优先级排列，依据与保留边界见第七章。</p>
           <table class="top3">${top}</table>`
        : ""
    }
  </section>`;
}

/* ── 二、作品概况 ─────────────────────────────────────────────────────────────────────── */

function profilePage(d: WholeBookAnalysisV2): string {
  const tp = d.type_profile;
  const ov = d.overview;
  const list = (label: string, items: string[]) => {
    const ok = items.map(val).filter(Boolean);
    return ok.length ? `<tr><th>${label}</th><td>${esc(ok.join("、"))}</td></tr>` : "";
  };
  const rows = [
    val(tp.primary_genre) ? `<tr><th>主类型</th><td>${esc(tp.primary_genre)}</td></tr>` : "",
    list("次类型", tp.secondary_genres ?? []),
    list("叙事驱动", tp.narrative_drivers ?? []),
    list("文本特征", tp.narrative_traits ?? []),
    list("类型预期", tp.genre_expectations ?? []),
  ].join("");
  return `<section class="page">
    <h2><span class="num">二</span>作品概况</h2>
    <h3>2.1　类型与叙事定位</h3>
    <p class="note">${
      tp.genre_confidence === 1
        ? "类型取自已确认的作品画像，非模型推测；后续各项分析均按此类型的评判标准执行。"
        : "作品画像尚未确认，类型为模型依据全文给出的判断。确认画像后重跑可提高各项判断的针对性。"
    }</p>
    ${rows ? `<table class="kv">${rows}</table>` : ""}
    <h3>2.2　故事梗概</h3>
    ${val(ov.one_sentence_story) ? `<p class="lead">${esc(ov.one_sentence_story)}</p>` : ""}
    ${val(ov.full_summary) ? `<p>${esc(ov.full_summary)}</p>` : ""}
    ${
      val(ov.core_conflict)
        ? `<dl class="kvlist"><dt>核心冲突</dt><dd>${esc(ov.core_conflict)}</dd>
           ${val(ov.core_goal) ? `<dt>主角目标</dt><dd>${esc(ov.core_goal)}</dd>` : ""}
           ${val(ov.final_state) ? `<dt>终局状态</dt><dd>${esc(ov.final_state)}</dd>` : ""}</dl>`
        : ""
    }
  </section>`;
}

/* ── 三、结构分析 ─────────────────────────────────────────────────────────────────────── */

function structurePages(d: WholeBookAnalysisV2): string {
  const st = d.story;
  if (!st.structure_stages.length && !st.storylines.length) return "";
  const stages = st.structure_stages
    .map((s, i) => {
      const facts: Array<[string, string]> = [
        ["阶段目标", val(s.stage_goal)],
        ["核心冲突", val(s.core_conflict)],
        ["关键转折", val(s.turning_point)],
        ["期末状态", val(s.ending_state) || val(s.protagonist_state)],
      ].filter(([, v]) => v) as Array<[string, string]>;
      return `<div class="stage">
        <h4><span class="idx">阶段 ${i + 1}</span><span class="where">${rng(
          s.chapter_start,
          s.chapter_end,
        )}</span>${esc(val(s.title))}</h4>
        ${val(s.summary) ? `<p>${esc(clip(s.summary, 160))}</p>` : ""}
        ${
          facts.length
            ? `<dl class="kvlist">${facts
                .map(([k, v]) => `<dt>${k}</dt><dd>${esc(clip(v, 110))}</dd>`)
                .join("")}</dl>`
            : ""
        }
      </div>`;
    })
    .join("");

  const lines = st.storylines.filter((l) => val(l.name));
  const open = lines.filter((l) => l.status !== "resolved");
  const closed = lines.length - open.length;

  // Derived here, not by the engine: how many storylines each stage opens and how many it
  // closes. It is the one view that says whether the book settles what it raises as it goes or
  // defers everything to the end, and neither the screen nor the model reports it — it falls
  // out of crossing the storyline table with the stage boundaries.
  const flow = st.structure_stages
    .map((s, i) => {
      const opened = lines.filter(
        (l) => l.chapter_start >= s.chapter_start && l.chapter_start <= s.chapter_end,
      ).length;
      const shut = lines.filter(
        (l) =>
          l.status === "resolved" &&
          l.chapter_end >= s.chapter_start &&
          l.chapter_end <= s.chapter_end,
      ).length;
      return `<tr><th>阶段 ${i + 1}</th><td class="where">${rng(s.chapter_start, s.chapter_end)}</td>
        <td class="n">${opened}</td><td class="n">${shut}</td>
        <td class="n ${shut < opened ? "neg" : ""}">${shut - opened > 0 ? "+" : ""}${shut - opened}</td></tr>`;
    })
    .join("");
  const openTable = open
    .slice(0, 14)
    .map(
      (l) =>
        `<tr><th class="where">${rng(l.chapter_start, l.chapter_end)}</th>
         <td class="tag">${l.type === "main" ? "主线" : "支线"}</td><td>${esc(l.name)}</td></tr>`,
    )
    .join("");

  return `<section class="page">
    <h2><span class="num">三</span>结构分析</h2>
    <h3>3.1　阶段划分</h3>
    <p class="note">阶段边界由引擎按事件密度切分，非按章数均分；下列各项取自对该区间正文的测量。</p>
    ${stages}
    <h3>3.2　情节线收束情况</h3>
    ${
      lines.length
        ? `<p class="stat">全书共测出情节线 <b>${lines.length}</b> 条，已收束 <b>${closed}</b> 条
             （${Math.round((closed / lines.length) * 100)}%），走到最后仍未收束 <b>${open.length}</b> 条。</p>`
        : ""
    }
    ${
      flow
        ? `<table class="flow">
             <thead><tr><th></th><th>区间</th><th class="n">新开</th><th class="n">收束</th><th class="n">净额</th></tr></thead>
             <tbody>${flow}</tbody>
           </table>
           <p class="note">表 1　各阶段情节线进出。「净额」为负表示该阶段开启的线多于收束的线；
             全书累计为负是正常的，若集中在末段则说明结局承担了过多的收束负担。</p>`
        : ""
    }
    ${
      openTable
        ? `<p class="note">下列情节线在末章仍未给出结果。有意留作续篇的不在此列之限，其余为读者最易察觉的缺口。</p>
           <table class="lines">${openTable}</table>
           ${open.length > 14 ? `<p class="note">另有 ${open.length - 14} 条未列出，完整清单见 HTML 导出。</p>` : ""}`
        : `<p class="note">未测到走到最后仍未收束的情节线。</p>`
    }
    ${judgement(d, CHAPTER_DIMENSION.structure)}
  </section>`;
}

/* ── 四、节奏分析 ─────────────────────────────────────────────────────────────────────── */

function pacingPage(d: WholeBookAnalysisV2): string {
  if (!d.pacing.points.length) return "";
  const regions = d.pacing.pacing_regions
    .map(
      (r) =>
        `<div class="region ${r.type}">
           <h4><span class="where">${rng(r.chapter_start, r.chapter_end)}</span>
             <span class="tag">${r.type === "fatigue" ? "推进偏缓" : "高强度"}</span></h4>
           ${val(r.reason) ? `<p class="basis">${esc(r.reason)}</p>` : ""}
           ${val(r.diagnosis) ? `<p>${esc(r.diagnosis)}</p>` : ""}
         </div>`,
    )
    .join("");
  return `<section class="page">
    <h2><span class="num">四</span>节奏分析</h2>
    <h3>4.1　推进曲线</h3>
    ${curve(d)}
    <p class="note">${esc(PACING_SCALE_NOTE)}</p>
    <h3>4.2　异常区间</h3>
    ${
      regions
        ? `<p class="note">下列区间为连续多个测量单元同向偏离全书中位，非单章波动。</p>${regions}`
        : `<p class="note">未测到连续偏缓或连续高强度的区间，全书推进较为平稳。</p>`
    }
    ${judgement(d, CHAPTER_DIMENSION.pacing)}
  </section>`;
}

/* ── 五、人物分析 ─────────────────────────────────────────────────────────────────────── */

function charactersPage(d: WholeBookAnalysisV2): string {
  const c = d.characters;
  const p = c.protagonist;
  const name = val(p.initial_identity) || val(d.overview.protagonist) || "主角";
  const arc =
    val(p.initial_goal) && val(p.final_goal) && p.initial_goal !== p.final_goal
      ? `<p class="arc"><span>${esc(p.initial_goal)}</span><i>→</i><span>${esc(p.final_goal)}</span></p>`
      : "";
  const stages = (p.stages ?? [])
    .filter((s) => val(s.stage_name))
    .map(
      (s) =>
        `<tr><th class="where">${rng(s.chapter, s.chapter_end ?? s.chapter)}</th>
         <td class="sname">${esc(s.stage_name)}</td><td>${esc(clip(s.entry_state, 62))}</td></tr>`,
    )
    .join("");

  // A character we can say something about gets a row. One we cannot gets a name in a run at
  // the end — printing a table of "unknown" tells the reader nothing and costs a third of a page.
  const others = c.major_characters.filter((m) => m.role !== "protagonist" && val(m.name));
  const described = others.filter((m) => val(m.relationship_to_protagonist) || val(m.character_arc));
  const bare = others.filter((m) => !described.includes(m));
  const cast = described
    .slice(0, 14)
    .map(
      (m) =>
        `<tr><th>${esc(m.name)}</th>
         <td>${esc(clip(val(m.relationship_to_protagonist) || val(m.character_arc), 72))}</td></tr>`,
    )
    .join("");

  if (!arc && !stages && !cast) return "";
  return `<section class="page">
    <h2><span class="num">五</span>人物分析</h2>
    <h3>5.1　主角轨迹</h3>
    ${arc}
    ${stages ? `<table class="pstages">${stages}</table>` : ""}
    <h3>5.2　主要人物与主角的关系</h3>
    ${cast ? `<table class="cast">${cast}</table>` : ""}
    ${
      bare.length
        ? `<p class="note">另有 ${bare.length} 人登场，引擎未在正文中测到其与主角关系的明确变化，故不列入上表：
           ${esc(bare.slice(0, 20).map((m) => m.name).join("、"))}${bare.length > 20 ? " 等" : ""}。</p>`
        : ""
    }
    ${judgement(d, CHAPTER_DIMENSION.characters, CHAPTER_DIMENSION.relationships)}
  </section>`;
}

/* ── 六、悬念分析 ─────────────────────────────────────────────────────────────────────── */

function suspensePage(d: WholeBookAnalysisV2): string {
  const all = d.suspense.lifecycles.filter((l) => val(l.question));
  if (!all.length) return "";
  const open = all.filter((l) => l.status === "unresolved");
  const partial = all.filter((l) => l.status === "partial");
  const closed = all.filter((l) => l.status === "resolved");
  const table = (rows: typeof all, cls = "", max = 14): string => {
    const body = rows
      .slice(0, max)
      .map(
        (l) =>
          `<tr><th class="where">${rng(l.chapter_start, l.chapter_end)}</th><td>${esc(l.question)}</td></tr>`,
      )
      .join("");
    if (!body) return "";
    const rest = rows.length - max;
    return (
      `<table class="qs ${cls}">${body}</table>` +
      (rest > 0 ? `<p class="note">另有 ${rest} 条未列出，完整清单见 HTML 导出。</p>` : "")
    );
  };
  // Derived: how long a question stays open, in chapters. A book whose suspense spans are all
  // short is answering as it goes; one where they all run to the last chapter is asking the
  // reader to hold everything at once. Neither number is reported anywhere else.
  const spans = all.map((l) => l.chapter_end - l.chapter_start + 1);
  const mean = Math.round(spans.reduce((a, b) => a + b, 0) / spans.length);
  const total = d.book_metadata.chapter_count || Math.max(...all.map((l) => l.chapter_end));
  const long = all.filter((l) => l.chapter_end - l.chapter_start + 1 > total / 2).length;
  return `<section class="page">
    <h2><span class="num">六</span>悬念分析</h2>
    <h3>6.1　设置与回收</h3>
    <p class="stat">全书共测出悬念 <b>${all.length}</b> 条：已回收 <b>${closed.length}</b> 条
      （回收率 <b>${Math.round((closed.length / all.length) * 100)}%</b>），
      部分回收 <b>${partial.length}</b> 条，未回收 <b>${open.length}</b> 条。
      平均跨度 <b>${mean}</b> 章${long ? `，其中 <b>${long}</b> 条跨越全书半数以上章节` : ""}。</p>
    <p class="note">「部分回收」指该问题在正文中出现了推进信息但未给出结论。判定依据为引擎记录的
      线索与揭示事件，不是模型的复述。</p>
    ${open.length ? `<h3>6.2　未回收</h3>${table(open)}` : ""}
    ${partial.length ? `<h3>6.3　部分回收</h3>${table(partial, "half")}` : ""}
    ${judgement(d, CHAPTER_DIMENSION.suspense)}
  </section>`;
}

/* ── 七、问题与修订建议 ───────────────────────────────────────────────────────────────── */

/** One chapter, not two. The assessment produces an issue and a priority *for the same chapter
 *  range* — the issue says what is wrong, the priority says what to do about it — and printing
 *  them as separate chapters made the reader read the same three findings twice, once as a
 *  complaint and once as an instruction. Each entry below is one finding, complete: what is
 *  wrong, why, what it costs the reader, what to do, what not to damage, and the sentences it
 *  was read off. Entries flow; a finding does not get a page because a page is available. */
function findingsPages(d: WholeBookAnalysisV2): string {
  const list = priorities(d);
  const issues = d.assessment.issues.filter((x) => val(x.symptom));
  const used = new Set<number>();
  const entries = list.map((p) => {
    const ranges = p.chapter_ranges!;
    const key = ranges[0];
    let at = issues.findIndex(
      (x, i) => !used.has(i) && x.chapter_start === key[0] && x.chapter_end === key[1],
    );
    if (at < 0)
      at = issues.findIndex(
        (x, i) => !used.has(i) && x.chapter_start <= key[1] && x.chapter_end >= key[0],
      );
    if (at >= 0) used.add(at);
    return { ranges, direction: val(p.direction), preserve: (p.preserve ?? []).map(val).filter(Boolean), issue: at >= 0 ? issues[at] : undefined };
  });
  // An issue nobody proposed a fix for is still a finding; it just has no 建议 line.
  issues.forEach((x, i) => {
    if (!used.has(i))
      entries.push({ ranges: [[x.chapter_start, x.chapter_end]], direction: val(x.possible_direction), preserve: [], issue: x });
  });
  if (!entries.length) return "";
  return `<section class="page">
    <h2><span class="num">七</span>问题与修订建议</h2>
    <p class="note">每一条对应前四章「本章判断」中的一项负面结论，按优先级排列：P0 直接影响读者留存，
      P1 次之，P2 为可选优化。「建议」是处理方向，不是改写方案；「须予保留」标出该处不可损及的部分。</p>
    ${entries
      .map(
        (e, i) =>
          `<div class="finding">
             <h4><span class="idx">${i + 1}</span>
               ${e.issue ? `<span class="pri ${e.issue.priority}">${esc(e.issue.priority)}</span>` : ""}
               <span class="where">${e.ranges.map((r) => rng(r[0], r[1])).join("、")}</span>
               ${e.issue && val(e.issue.symptom) ? esc(clip(e.issue.symptom, 40)) : ""}</h4>
             <dl class="kvlist">
               ${e.issue && val(e.issue.root_cause) ? `<dt>根因</dt><dd>${esc(e.issue.root_cause)}</dd>` : ""}
               ${e.issue && val(e.issue.reader_impact) ? `<dt>读者影响</dt><dd>${esc(e.issue.reader_impact)}</dd>` : ""}
               ${e.direction ? `<dt class="act">建议</dt><dd class="act">${esc(e.direction)}</dd>` : ""}
               ${e.preserve.length ? `<dt>须予保留</dt><dd>${esc(e.preserve.join("；"))}</dd>` : ""}
             </dl>
             ${quotes(d, e.issue?.evidence, 2)}
           </div>`,
      )
      .join("")}
  </section>`;
}

/* ── 八、须予保留项（承上） ───────────────────────────────────────────────────────────── */

function keepPage(d: WholeBookAnalysisV2): string {
  const a = d.assessment;
  const strengths = a.strengths.filter((s) => val(s.title) && val(s.why_good));
  const keeps = a.preserve_list.map(val).filter(Boolean);
  if (!strengths.length && !keeps.length) return "";
  return `<section class="page">
    <h2><span class="num">八</span>须予保留项</h2>
    <p class="note">下列各项为本书已经成立的部分。第七章的修订不应以损及这些内容为代价，
      列出的目的是给修订划一条边界。</p>
    <h3>8.1　已经成立的部分</h3>
    ${strengths
      .map(
        (s, i) =>
          `<div class="strength">
             <h4><span class="idx">保留 ${i + 1}</span><span class="where">${rng(
               s.chapter_start,
               s.chapter_end,
             )}</span>${esc(s.title)}</h4>
             <p>${esc(s.why_good)}</p>${quotes(d, s.evidence, 2)}
           </div>`,
      )
      .join("")}
    ${
      keeps.length
        ? `<h3>8.2　改稿保留清单</h3><ul class="keeplist">${keeps
            .map((x) => `<li>${esc(x)}</li>`)
            .join("")}</ul>`
        : ""
    }
  </section>`;
}

/* ── 附录 ─────────────────────────────────────────────────────────────────────────────── */

function appendixChapters(d: WholeBookAnalysisV2, pagesLeft: number): string {
  const fns = d.chapters.functions;
  if (!fns.length || pagesLeft < 1) return "";
  const cap =
    Math.max(0, Math.min(pagesLeft, APPENDIX_MAX_PAGES) - APPENDIX_HEADER_PAGES) *
    CHAPTER_ROWS_PER_PAGE;
  if (cap < 1) return "";
  const shown = fns.slice(0, cap);
  const dropped = fns.length - shown.length;
  // Derived: what the book actually spends its chapters on. Counting the function labels over
  // all chapters is a one-line summary of the book's chapter economy, and it is the evidence
  // the 章节效率 judgement below is answerable to.
  const tally = new Map<string, number>();
  for (const f of fns) {
    const k = val(f.primary_function);
    if (k) tally.set(k, (tally.get(k) ?? 0) + 1);
  }
  const mix = [...tally.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(
      ([k, n]) =>
        `<tr><th>${esc(k)}</th><td class="n">${n}</td><td class="n">${Math.round((n / fns.length) * 100)}%</td></tr>`,
    )
    .join("");
  return `<section class="page">
    <h2><span class="num">附录 A</span>逐章功能索引</h2>
    <h3>A.1　章节功能分布</h3>
    <p class="note">全书 ${fns.length} 章按主功能归类的结果，按占比排列。</p>
    ${mix ? `<table class="mix"><tbody>${mix}</tbody></table>` : ""}
    ${judgement(d, CHAPTER_DIMENSION.chapters)}
    <h3>A.2　逐章索引</h3>
    <p class="note">供定位使用，非分析结论。摘要经截断，完整内容见正文。</p>
    ${
      dropped > 0
        ? `<p class="note">受 ${PAGE_BUDGET} 页篇幅所限，本表列至第 ${shown.at(-1)?.chapter_index} 章，
           <b>其后 ${dropped} 章未列出</b>；完整逐章表见 HTML 导出。</p>`
        : ""
    }
    <table class="chapters">
      <thead><tr><th>章</th><th>功能</th><th>摘要</th></tr></thead>
      <tbody>${shown
        .map(
          (f) =>
            `<tr><th>${f.chapter_index}</th><td class="fn">${esc(val(f.primary_function) || "—")}</td>
             <td>${esc(clip(f.summary, 46) || "—")}</td></tr>`,
        )
        .join("")}</tbody>
    </table>
  </section>`;
}

function appendixMethod(d: WholeBookAnalysisV2): string {
  const m = d.analysis_metadata;
  const missing = (
    [
      [d.assessment.dimensions.length, "分项评级"],
      [d.story.structure_stages.length, "阶段划分"],
      [d.suspense.lifecycles.length, "悬念"],
      [d.pacing.points.length, "节奏曲线"],
      [d.chapters.functions.length, "逐章功能"],
    ] as Array<[number, string]>
  )
    .filter(([n]) => !n)
    .map(([, label]) => label);
  const origin: Record<string, string> = {
    real_provider: "真实模型调用",
    deterministic_local_merge: "本地确定性合并",
    deterministic_test: "确定性测试数据",
    fixture: "固定样例",
    mock: "模拟数据",
    legacy_migration: "旧版迁移",
  };
  const rows: Array<[string, string]> = [
    ["分析引擎", val(m.pipeline_version)],
    ["模型", [val(m.provider_name), val(m.model_name)].filter(Boolean).join(" / ")],
    ["结果来源", origin[String(m.result_origin)] ?? val(m.result_origin)],
    ["真实模型调用", m.real_provider_calls ? `${m.real_provider_calls} 次` : ""],
    ["数据快照", `#${d.book_metadata.snapshot_id}　${String(d.book_metadata.revision_hash).slice(0, 12)}`],
    ["证据条目", `${Object.keys(d.evidence_index).length} 条`],
    ["报告编号", `WB-${String(m.run_id).padStart(4, "0")}`],
  ];
  return `<section class="page">
    <h2><span class="num">附录 B</span>分析方法与数据口径</h2>
    <h3>B.1　口径说明</h3>
    <dl class="kvlist">
      <dt>原文佐证</dt><dd>报告中带章号的引文均为正文原句，由抽取阶段记录的段落位置解析而得，非模型复述。
        引文与其所支持的结论一一对应。</dd>
      <dt>曲线数值</dt><dd>${esc(PACING_SCALE_NOTE)}因此曲线必然铺满 0–100，且不同作品之间不可比较。</dd>
      <dt>分项评级</dt><dd>由模型在上述测量结果上给出，为对本书的定性判断。同一份数据重跑，评级可能相差一档。</dd>
      <dt>作品类型</dt><dd>${
        d.type_profile.genre_confidence === 1
          ? "取自用户已确认的作品画像，非模型推测。"
          : "由模型依据全文判断，用户尚未确认。"
      }</dd>
      <dt>未测到的项</dt><dd>${
        missing.length
          ? esc(missing.join("、")) + "：本次未产出，报告中留空而非补写。"
          : "本次各板块均有产出。"
      }</dd>
    </dl>
    <h3>B.2　数据来源</h3>
    <table class="meta-table">${rows
      .filter(([, v]) => val(v))
      .map(([k, v]) => `<tr><th>${k}</th><td>${esc(v)}</td></tr>`)
      .join("")}</table>
  </section>`;
}

/* ── 组装 ─────────────────────────────────────────────────────────────────────────────── */

/** The whole document. The report proper is assembled first; 附录 A then takes the pages that
 *  are left, which is how the budget is enforced rather than hoped for. */
/* ── 拆文 ───────────────────────────────────────────────────────────────────────────── */

/** 拆文 pages.
 *
 *  This renderer knew nothing about `story_breakdown`, so printing a 拆文 report produced a
 *  PDF with none of its content and several pages of empty 评测 sections — the same defect
 *  the screen and the HTML export had, surviving in the file people hand to other people.
 */
function breakdownPages(d: WholeBookAnalysisV2): string {
  const b = d.story_breakdown;
  if (!b?.four_beats?.length) return "";
  const moments = [...(b.standout_moments ?? [])].sort((x, y) => (x.rank ?? 999) - (y.rank ?? 999));
  const beats = b.four_beats
    .map(
      (x) =>
        `<tr><th>${esc(x.beat)}</th><td class="where">${rng(x.chapter_start, x.chapter_end)}</td>
         <td><b>${esc(val(x.title))}</b><br>${esc(val(x.summary))}</td></tr>`,
    )
    .join("");
  const momentRows = moments
    .map(
      (m) => `<div class="mom">
        <p class="qlabel">${m.rank}　${esc(val(m.title))}<span class="where">　第 ${m.chapter} 章</span></p>
        ${val(m.quote) ? `<blockquote>${esc(clip(val(m.quote), 160))}</blockquote>` : ""}
        <p>${esc(val(m.why_it_lands))}</p>
      </div>`,
    )
    .join("");
  const tech = (b.reusable_techniques ?? [])
    .map(
      (t, i) =>
        `<tr><th>${i + 1}</th><td><b>${esc(val(t.name))}</b><br>${esc(val(t.what_it_is))}</td>
         <td>${esc(val(t.why_it_works))}</td><td>${esc(val(t.transfers_to))}</td></tr>`,
    )
    .join("");
  const cast = (b.supporting_cast ?? [])
    .map(
      (c) =>
        `<tr><th>${esc(val(c.name))}</th><td>${esc(val(c.function))}</td>
         <td class="where">${esc(val(c.stays_in_lane ?? ""))}</td></tr>`,
    )
    .join("");
  const hooks = (b.chapter_hooks ?? [])
    .map((h) => `<tr><th class="idx">${h.chapter}</th><td>${esc(val(h.question))}</td></tr>`)
    .join("");
  return `<section class="page">
    <h2><span class="num">一</span>起承转合</h2>
    <table class="dims">${beats}</table>
    <h3>1.2　最打动人的瞬间（${moments.length}）</h3>
    ${val(b.moment_count_rationale) ? `<p class="note">${esc(b.moment_count_rationale)}</p>` : ""}
    ${momentRows}
  </section>
  ${
    tech
      ? `<section class="page">
    <h2><span class="num">二</span>可复用的手法</h2>
    <p class="note">每一条都写明是什么、为什么有效、能用到哪，便于直接挪用。</p>
    <table class="top3">${tech}</table>
    ${
      cast
        ? `<h3>2.2　配角功能（${(b.supporting_cast ?? []).length}）</h3>
           ${val(b.cast_note) ? `<p class="note">${esc(b.cast_note)}</p>` : ""}
           <table class="dims">${cast}</table>`
        : ""
    }
  </section>`
      : ""
  }
  ${
    hooks
      ? `<section class="page">
    <h2><span class="num">三</span>每章留下的问题</h2>
    <p class="note">共 ${(b.chapter_hooks ?? []).length} 章在结尾留下了一个待答的问题。</p>
    <table class="chidx">${hooks}</table>
  </section>`
      : ""
  }`;
}

const NUMERALS = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"];

/** Renumber top-level sections by the order they actually appear.
 *
 *  Each page hardcodes its own numeral, which was correct while every report had the same
 *  eight sections. A 拆文 report has a different set, so the fixed numerals collided — two
 *  sections both called 三. This rewrites the numeral and the section-scoped h3 prefixes
 *  (1.1, 1.2 …) to match the position the section ends up in.
 */
function renumberSections(body: string): string {
  let n = 0;
  return body.replace(/<section class="page">[\s\S]*?<\/section>/g, (page) => {
    if (!/<h2><span class="num">/.test(page)) return page;
    n += 1;
    const numeral = NUMERALS[n - 1] ?? String(n);
    return page
      .replace(/<h2><span class="num">[^<]*<\/span>/, `<h2><span class="num">${numeral}</span>`)
      .replace(/<h3>\d+\.(\d+)/g, (_m, sub) => `<h3>${n}.${sub}`);
  });
}
export function buildPrintHtml(d: WholeBookAnalysisV2): string {
  // 拆文 and 评测 fill different sections; printing all of them regardless is how a 拆文
  // report came out as several empty pages with its own content nowhere in the file.
  const breakdown = breakdownPages(d);
  const body = breakdown
    ? [breakdown, structurePages(d), pacingPage(d), charactersPage(d), suspensePage(d)].join("")
    : [
        summaryPage(d),
        profilePage(d),
        structurePages(d),
        pacingPage(d),
        charactersPage(d),
        suspensePage(d),
        findingsPages(d),
        keepPage(d),
      ].join("");
  // 章号写死在各节里，而拆文那份少了执行摘要和作品概况——不重排就会出现两个「三」。
  // 按正文里 h2 出现的顺序重编，顺带把该节内部的 1.1 / 1.2 这类小节号对上。
  const renumbered = renumberSections(body);

  const declared = (renumbered.match(/class="page"/g) ?? []).length;
  // +1 cover, +1 附录 B. Take the larger of the declared count and the measured allowance, so a
  // book whose sections overflow shortens the appendix rather than the budget.
  const used = Math.max(declared + 2, FIXED_PAGES);
  const toc = breakdown
    ? [
        "一　起承转合与最打动人的瞬间",
        "二　可复用的手法与配角功能",
        "三　每章留下的问题",
        "四　结构分析",
        "五　节奏分析",
        "六　人物分析",
        "七　悬念分析",
        "附录 A　逐章功能索引",
        "附录 B　分析方法与数据口径",
      ]
    : [
        "一　执行摘要",
        "二　作品概况",
        "三　结构分析",
        "四　节奏分析",
        "五　人物分析",
        "六　悬念分析",
        "七　问题与修订建议",
        "八　须予保留项",
        "附录 A　逐章功能索引",
        "附录 B　分析方法与数据口径",
      ];
  const appendix = appendixChapters(d, PAGE_BUDGET - used - 1);
  // Declared, not sniffed. This file is written to disk and opened as `file:///` by a headless
  // Chromium; with no charset the system default is used, and on a Chinese Windows that is GBK,
  // which prints the whole report as mojibake.
  return `<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<title>${esc(d.book_metadata.title)} · 全书分析报告</title>
<style>
@page { size: A4; margin: 18mm 17mm 16mm; }
:root {
  --sans: "PingFang SC", "Microsoft YaHei", "Hiragino Sans GB", sans-serif;
  --serif: "Songti SC", SimSun, "Noto Serif CJK SC", serif;
  --ink: #17201a; --mute: #6f7d74; --rule: #d8e0da; --key: #14503c; --warn: #a8551f;
}
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  margin: 0; color: var(--ink); background: #fff;
  font-family: var(--serif); font-size: 10.5pt; line-height: 1.75;
}
.page { break-after: page; }
.page:last-child { break-after: auto; }

/* Structure is sans, prose is serif — the one rule the whole document obeys. */
h1, h2, h3, h4, th, dt, .kicker, .note, .where, .tag, .idx, .num, .grade, .pri,
figcaption, .qlabel, .dimname, .stat, .cover-sub, .fn { font-family: var(--sans); }
p, dd, td, li, .lead, .arc { font-family: var(--serif); }

h1 { font-size: 26pt; line-height: 1.25; margin: 0 0 3mm; letter-spacing: .02em; }
h2 {
  font-size: 13pt; margin: 0 0 5mm; padding-bottom: 2mm;
  border-bottom: 1pt solid var(--key); color: var(--key); display: flex; align-items: baseline;
}
h2 .num {
  font-size: 9.5pt; letter-spacing: .1em; margin-right: 4mm; padding: .6mm 2mm;
  background: var(--key); color: #fff; white-space: nowrap;
}
h3 { font-size: 11pt; color: var(--key); margin: 7mm 0 2.5mm; }
h3.cont { margin-top: 0; }
h4 { font-size: 10pt; margin: 4mm 0 1.5mm; display: flex; gap: 3mm; align-items: baseline; }
p { margin: 0 0 2.5mm; }
.lead { font-size: 11.5pt; line-height: 1.7; }
.note { font-size: 8.5pt; color: var(--mute); line-height: 1.65; margin-bottom: 3mm; }
.stat { font-size: 9.5pt; }
.stat b { font-family: var(--sans); color: var(--key); font-size: 11pt; }
.where {
  font-size: 8.5pt; color: var(--key); white-space: nowrap; font-variant-numeric: tabular-nums;
}
.idx { font-size: 8pt; letter-spacing: .1em; color: var(--mute); white-space: nowrap; }
.tag { font-size: 8pt; color: var(--mute); white-space: nowrap; }

/* 封面 */
.cover-head { border-bottom: 2pt solid var(--key); padding-bottom: 6mm; margin-bottom: 6mm; }
.kicker { font-size: 8.5pt; letter-spacing: .3em; color: var(--key); margin: 0 0 3mm; }
.cover-sub { font-size: 12pt; color: var(--mute); letter-spacing: .2em; margin: 0; }
.cover-note {
  font-family: var(--sans); font-size: 8.5pt; color: var(--mute); line-height: 1.8;
  border-top: .5pt solid var(--rule); padding-top: 4mm; margin-top: 8mm;
}
.toc { margin-top: 9mm; }
.toc h2 { font-size: 10pt; border-bottom-width: .5pt; margin-bottom: 3mm; }
.toc ol { margin: 0; padding: 0; list-style: none; columns: 2; column-gap: 10mm; }
.toc li {
  font-family: var(--sans); font-size: 9pt; padding: 1.4mm 0;
  border-bottom: .4pt dotted var(--rule); break-inside: avoid;
}

/* 表 */
table { width: 100%; border-collapse: collapse; }
.meta-table th, .kv th {
  text-align: left; width: 24mm; font-size: 9pt; color: var(--mute); font-weight: 400;
  padding: 1.6mm 0; vertical-align: top;
}
.meta-table td, .kv td { padding: 1.6mm 0 1.6mm 4mm; vertical-align: top; }
.meta-table tr + tr th, .meta-table tr + tr td,
.kv tr + tr th, .kv tr + tr td { border-top: .4pt solid #eef2ef; }
.dims th { text-align: left; width: 22mm; font-size: 9.5pt; padding: 2mm 0; vertical-align: top; }
.dims td { padding: 2mm 0 2mm 3mm; vertical-align: top; }
.dims .grade, .grade { font-family: var(--sans); font-weight: 700; color: var(--key); }
.dims .grade { width: 12mm; font-size: 11pt; }
.dims tr + tr th, .dims tr + tr td { border-top: .4pt solid #eef2ef; }
.top3 th {
  width: 7mm; text-align: left; color: var(--key); font-size: 10pt; padding: 2mm 0; vertical-align: top;
}
.top3 td { padding: 2mm 0 2mm 3mm; vertical-align: top; }
.top3 td.where { width: 30mm; }
.top3 tr + tr th, .top3 tr + tr td { border-top: .4pt solid #eef2ef; }
.lines th, .qs th { text-align: left; width: 26mm; padding: 1.5mm 0; vertical-align: top; font-weight: 400; }
.lines td, .qs td { padding: 1.5mm 0 1.5mm 3mm; vertical-align: top; }
.lines td.tag { width: 12mm; padding-left: 0; }
.lines tr + tr th, .lines tr + tr td,
.qs tr + tr th, .qs tr + tr td { border-top: .4pt solid #eef2ef; }
.qs.half td { color: #4a5850; }
.pstages th { text-align: left; width: 26mm; padding: 1.6mm 0; vertical-align: top; font-weight: 400; }
.pstages td { padding: 1.6mm 0 1.6mm 3mm; vertical-align: top; }
.pstages .sname { font-family: var(--sans); width: 46mm; font-size: 9.5pt; }
.pstages tr + tr th, .pstages tr + tr td { border-top: .4pt solid #eef2ef; }
.cast th { text-align: left; width: 24mm; font-size: 9.5pt; padding: 1.5mm 0; vertical-align: top; }
.cast td { padding: 1.5mm 0 1.5mm 3mm; vertical-align: top; }
.cast tr + tr th, .cast tr + tr td { border-top: .4pt solid #eef2ef; }

/* 键值段 */
.kvlist { margin: 0 0 3mm; }
.kvlist dt { font-size: 8.5pt; color: var(--mute); letter-spacing: .06em; margin-top: 2.5mm; }
.kvlist dd { margin: .4mm 0 0; }

/* 派生统计表 —— 数字列右对齐并等宽，才读得出趋势 */
.flow th, .mix th { text-align: left; font-size: 9pt; font-weight: 400; padding: 1.4mm 0; }
.flow td, .mix td { padding: 1.4mm 0 1.4mm 3mm; vertical-align: baseline; }
.flow thead th, .mix thead th { color: var(--mute); font-size: 8pt; border-bottom: .6pt solid var(--rule); }
.flow .n, .mix .n {
  text-align: right; width: 14mm; font-family: var(--sans);
  font-variant-numeric: tabular-nums; padding-left: 0;
}
.flow .neg { color: var(--warn); }
.flow tbody tr + tr th, .flow tbody tr + tr td,
.mix tbody tr + tr th, .mix tbody tr + tr td { border-top: .4pt solid #eef2ef; }
.mix th { width: 30mm; }

/* 阶段 / 区间 / 结论 / 保留 */
.stage, .region, .finding, .strength { break-inside: avoid; margin-bottom: 4.5mm; }
.stage h4, .finding h4, .strength h4 { margin-bottom: 1mm; }
.finding { padding-bottom: 3mm; border-bottom: .4pt solid #eef2ef; }
.finding:last-child { border-bottom: 0; }
.finding h4 .idx {
  font-size: 9pt; color: var(--key); font-weight: 700; letter-spacing: 0;
}
.kvlist dt.act, .kvlist dd.act { color: var(--key); }
.kvlist dt.act { font-weight: 700; }
.region { padding-left: 3.5mm; border-left: 1.5pt solid var(--warn); }
.region.climax { border-left-color: var(--key); }
.region p { margin: 0 0 .8mm; font-size: 9.5pt; }
.region .basis { color: var(--mute); font-size: 8.5pt; font-family: var(--sans); }
.pri {
  font-size: 8pt; font-weight: 700; padding: .3mm 1.6mm; color: #fff; background: var(--mute);
}
.pri.P0 { background: var(--warn); }
.pri.P1 { background: var(--key); }
.arc { font-size: 11pt; margin-bottom: 4mm; }
.arc i { color: var(--key); font-style: normal; margin: 0 3mm; }
.keep { margin-top: 5mm; padding: 3.5mm 4mm; background: #f2f6f3; break-inside: avoid; }
.keep h4 { margin: 0 0 1.5mm; color: var(--key); }
.keep ul, .keeplist { margin: 0; padding-left: 5mm; }
.keeplist li { padding: .6mm 0; }

/* 判断 —— 每一章的落点 */
.judgement {
  margin-top: 7mm; padding: 3.5mm 4mm; background: #f4f7f5; border-left: 2pt solid var(--key);
  break-inside: avoid;
}
.judgement h3 {
  margin: 0 0 1.5mm; font-size: 9pt; letter-spacing: .1em; color: var(--key);
}
.judgement p { margin: 0 0 1.2mm; font-size: 9.5pt; }
.judgement p:last-child { margin-bottom: 0; }
.judgement .grade { font-size: 11pt; margin-right: 2.5mm; }
.dimname { font-size: 8.5pt; color: var(--mute); margin-right: 2.5mm; }

/* 引文 */
.quotes { border-left: 1.2pt solid var(--rule); padding-left: 4mm; margin: 3mm 0 0; }
.qlabel { font-size: 8pt; letter-spacing: .1em; color: var(--mute); margin: 0 0 1mm; }
.quotes p { margin: 0 0 1.5mm; font-size: 9.5pt; color: #39463e; }
.quotes span {
  font-family: var(--sans); font-size: 8pt; color: var(--key); margin-right: 2mm;
  font-variant-numeric: tabular-nums;
}

/* 图 */
.fig { margin: 0 0 3mm; }
.fig svg { width: 100%; height: auto; }
figcaption { font-size: 8.5pt; color: var(--mute); margin-top: 1.5mm; line-height: 1.6; }

/* 附录 A */
.chapters { font-size: 8.5pt; margin-top: 2mm; }
.chapters thead th {
  font-size: 8pt; color: var(--mute); font-weight: 400; text-align: left;
  border-bottom: .6pt solid var(--rule); padding-bottom: 1mm;
}
.chapters thead th:first-child { text-align: right; }
.chapters tbody th {
  text-align: right; width: 9mm; padding: .7mm 2.5mm .7mm 0; color: var(--key);
  font-weight: 400; font-variant-numeric: tabular-nums; vertical-align: top;
}
.chapters .fn { width: 24mm; font-size: 7.5pt; color: var(--mute); vertical-align: top; padding-right: 2.5mm; }
.chapters td { padding: .7mm 0; vertical-align: top; }
.chapters tbody tr + tr th, .chapters tbody tr + tr td { border-top: .3pt solid #f2f5f3; }
</style>
${coverPage(d, toc)}${renumbered}${appendix}${appendixMethod(d)}`;
}
