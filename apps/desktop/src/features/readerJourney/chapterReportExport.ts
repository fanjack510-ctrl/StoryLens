/** 单章的评测报告：一章分析交到作者手上的那份文件。
 *
 * 这一份**只做评测**。理由不是省事：翻完 35 份人写的拆文汇总，没有一份是按章拆的——
 * 拆文回答的是「这本书怎么搭起来的」，那个问题在一章的尺度上没有答案。一章能回答的是
 * 「这一章读起来怎么样、哪里掉、为什么」，所以这份文件从头到尾是一份体检报告。
 *
 * 版面沿用全书那份印刷报告的字体与色板（见 wholeBookV2/printExport.ts）：结构用无衬线，
 * 正文用衬线。两份文件出自同一个产品，读者不该在纸上看出两种审美。
 *
 * ## 章节顺序就是论证顺序
 *
 *     三项体检 → 曲线在哪掉 → 悬念欠了多少 → 逐场证据 → 能带走的写法
 *
 * 先给判断，再给证据，最后给能迁移的部分。第一页那三项是全篇的结论；后面每一章都是它们
 * 的依据，或者依据推出的下一步。
 *
 * ## 这份文件守的几条
 *
 * **不印没有内容的东西。** 模型答 unknown 等于没答，一行「unknown」白占一行注意力。空的
 * 段落整段略去——屏幕上留白是诚实，纸上是浪费一张纸。
 *
 * **数字旁边必须有刻度。** 「线索投放 0/5」单独放着只是一个数字：读者既不知道 5 分长什么
 * 样，也不知道这判断看的是哪几段。锚点和段号后端本来就有，这里一并印出来。
 *
 * **口径印在最后一页。** 公式版本、场景契约、模型——换了任何一个，分数就不可比。
 */
import type {
  JourneyCurvePoint,
  JourneySceneNode,
  HookVocabulary,
  JourneyTechniqueItem,
  JourneyWritingTakeaway,
  ReaderJourneyVisualization,
} from "../../types/readerJourneyVisualization";
import { buildChapterHookVitals } from "../../components/readerJourney/chapterHookVitals";

const esc = (s: unknown): string =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[c]!,
  );

/** 无内容的占位词。跟全书那份用同一套判断，两份文件不能对「算不算答了」有分歧。 */
const NOTHING = /^(unknown|未知|n\/?a|null|none|待补充|无|暂无|—|-)$/i;
const val = (s: unknown): string => {
  const t = String(s ?? "").trim();
  return !t || NOTHING.test(t) ? "" : t;
};

const num = (x: unknown): number | null => {
  const n = Number(x);
  return Number.isFinite(n) ? n : null;
};

const cut = (s: string, max: number): string => (s.length <= max ? s : `${s.slice(0, max - 1)}…`);

/** 段号 B0004-C0002-P0015 → P15。印全号占三行，读者要的是「第几段」。 */
const pnum = (id: unknown): string => {
  const m = /P(\d+)$/.exec(String(id ?? ""));
  return m ? `P${Number(m[1])}` : "";
};
const pnums = (ids: unknown): string =>
  (Array.isArray(ids) ? ids : []).map(pnum).filter(Boolean).join("、");

export type ChapterReportInput = {
  visualization: ReaderJourneyVisualization;
  chapterTitle: string;
  bookTitle?: string | null;
  analysisRunId?: number | null;
  journeyRunId?: number | null;
  providerName?: string | null;
  modelName?: string | null;
};

/** 主曲线上真正参与计算的场景——Beat 辅助点不在其中，均值也不算它们。 */
function mainScenes(v: ReaderJourneyVisualization): JourneySceneNode[] {
  return (v.scene_nodes || []).filter((n) => n.node_type !== "beat");
}

function curvePoints(v: ReaderJourneyVisualization): Array<{ x: number; y: number }> {
  const series = (v.curve_series?.engagement || []) as JourneyCurvePoint[];
  return series
    .filter((p) => p.include_in_main_curve !== false && p.node_type !== "beat")
    .map((p) => ({ x: Number(p.scene_ordinal), y: Number(p.value ?? 0) }))
    .filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y));
}

/* ---- 曲线图 -----------------------------------------------------------------
   屏幕上那条追读曲线，重画成静态 SVG。刻度写死 0—100：一章之内自适应量程会把 3 分的
   起伏画成悬崖，那正是这份文件要避免的误导。 */
const INK = "#17201a";
const KEY = "#14503c";
const MUTE = "#6f7d74";
const RULE = "#d8e0da";
const WARN = "#a8551f";

function curveSvg(v: ReaderJourneyVisualization, label: string): string {
  const pts = curvePoints(v);
  if (pts.length < 2) return "";
  const W = 520;
  const H = 190;
  const L = 34;
  const R = 12;
  const T = 14;
  const B = 26;
  const iw = W - L - R;
  const ih = H - T - B;
  const n = pts.length;
  const px = (i: number) => L + (i / (n - 1)) * iw;
  const py = (y: number) => T + ih - (Math.max(0, Math.min(100, y)) / 100) * ih;

  const grid = [0, 25, 50, 75, 100]
    .map(
      (g) =>
        `<line x1="${L}" y1="${py(g).toFixed(1)}" x2="${W - R}" y2="${py(g).toFixed(1)}" stroke="${RULE}" stroke-width=".5"/>` +
        `<text x="${L - 5}" y="${(py(g) + 3).toFixed(1)}" text-anchor="end" font-size="7" fill="${MUTE}">${g}</text>`,
    )
    .join("");

  const line = pts.map((p, i) => `${px(i).toFixed(1)},${py(p.y).toFixed(1)}`).join(" ");
  const area = `${L},${(T + ih).toFixed(1)} ${line} ${(W - R).toFixed(1)},${(T + ih).toFixed(1)}`;

  let hi = 0;
  let lo = 0;
  pts.forEach((p, i) => {
    if (p.y > pts[hi].y) hi = i;
    if (p.y < pts[lo].y) lo = i;
  });

  const dots = pts
    .map((p, i) => {
      const fill = i === hi ? KEY : i === lo ? WARN : "#fff";
      const r = i === hi || i === lo ? 3.4 : 2.4;
      return `<circle cx="${px(i).toFixed(1)}" cy="${py(p.y).toFixed(1)}" r="${r}" fill="${fill}" stroke="${KEY}" stroke-width="1.1"/>`;
    })
    .join("");

  const callouts = ([
    [hi, `峰 ${Math.round(pts[hi].y)}`, KEY],
    [lo, `谷 ${Math.round(pts[lo].y)}`, WARN],
  ] as Array<[number, string, string]>)
    .map(([i, text, color]) => {
      const above = py(pts[i].y) > T + 26;
      const y = above ? py(pts[i].y) - 8 : py(pts[i].y) + 14;
      const anchor = i === 0 ? "start" : i === n - 1 ? "end" : "middle";
      return `<text x="${px(i).toFixed(1)}" y="${y.toFixed(1)}" text-anchor="${anchor}" font-size="7.5" font-weight="700" fill="${color}">${esc(text)}</text>`;
    })
    .join("");

  const ticks = pts
    .map((p, i) =>
      n > 14 && i % 2 === 1
        ? ""
        : `<text x="${px(i).toFixed(1)}" y="${H - 8}" text-anchor="middle" font-size="7" fill="${MUTE}">S${p.x}</text>`,
    )
    .join("");

  return `<figure class="chart">
<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${esc(label)}曲线">
${grid}
<polygon points="${area}" fill="${KEY}" opacity=".07"/>
<polyline points="${line}" fill="none" stroke="${KEY}" stroke-width="1.8" stroke-linejoin="round"/>
${dots}${callouts}${ticks}
</svg>
<figcaption>${esc(label)}逐场走势，纵轴固定 0—100。实心绿点是全章最高，褐点是最低。</figcaption>
</figure>`;
}

/* ---- 页 --------------------------------------------------------------------- */

function coverPage(input: ChapterReportInput): string {
  const v = input.visualization;
  const s = (v.chapter_summary || {}) as Record<string, unknown>;
  const scenes = mainScenes(v);
  const vitals = buildChapterHookVitals(v);
  const curveLabel = v.main_curve?.label || "追读意愿";
  const avg = val((s.peaks as { engagement_average?: unknown } | undefined)?.engagement_average);
  const paragraphs = scenes.reduce((t, n) => t + (Number(n.paragraph_count) || 0), 0);
  const diagnosis =
    val((s.expanded_diagnosis as { one_sentence_diagnosis?: unknown } | undefined)?.one_sentence_diagnosis) ||
    val(s.diagnosis);
  const traction = val(s.primary_traction);

  const vitalRows = vitals
    .map(
      (x) => `<tr>
<th>${esc(x.label)}</th>
<td class="grade" data-band="${esc(x.band)}">${esc(x.display)}</td>
<td>${esc(x.reading)}<span class="basis">${esc(x.basis)}</span></td>
</tr>`,
    )
    .join("");

  const roles = v.role_counts;

  return `<section class="page cover">
<div class="cover-head">
<p class="kicker">STORYLENS 章节评测报告</p>
<h1>${esc(input.chapterTitle)}</h1>
<p class="cover-sub">${esc(val(input.bookTitle) || "单章分析")}</p>
</div>
${diagnosis ? `<p class="lead">${esc(diagnosis)}</p>` : ""}
${traction ? `<p class="note">本章主牵引：${esc(traction)}</p>` : ""}

${
  vitalRows
    ? `<h2><span class="num">体检</span>三项判断</h2>
<p class="note">
一章的成败在三个位置定下来：开头留不留得住人、结尾拉不拉得动人、第一个钩子来得早不早。
每一行都给了数、给了读法、也给了它是看着什么算出来的。
</p>
<table class="vitals">${vitalRows}</table>`
    : ""
}

<h2><span class="num">规模</span>本章体量</h2>
<table class="kv">
<tr><th>场景</th><td>${scenes.length} 个${
    roles ? `（核心 ${roles.core} · 次要 ${roles.secondary} · 节拍 ${roles.beat}）` : ""
  }</td></tr>
<tr><th>段落</th><td>${paragraphs} 段</td></tr>
<tr><th>阶段</th><td>${(v.phases || []).length} 段</td></tr>
${avg ? `<tr><th>${esc(curveLabel)}</th><td>全章均值 ${esc(avg)}</td></tr>` : ""}
</table>

<p class="cover-note">
这份报告只做评测，不做拆文。拆文回答的是「这本书怎么搭起来的」——那是全书尺度的问题，
一章里没有答案。要拆文，请在全书分析里选「拆文」。<br>
分析口径见文末附录：换了模型或公式版本，两份报告的分数之间就不再可比。
</p>
</section>`;
}

function curvePage(input: ChapterReportInput): string {
  const v = input.visualization;
  const label = v.main_curve?.label || "追读意愿";
  const why = val(v.main_curve?.why);
  const chart = curveSvg(v, label);
  const phases = v.phases || [];
  const s = (v.chapter_summary || {}) as Record<string, unknown>;
  const lowInterval = s.max_low_payoff_interval as { summary?: unknown; trigger?: unknown } | null | undefined;

  const phaseRows = phases
    .map((p) => {
      const q = val(p.primary_reader_question);
      const motive = val(p.continuation_motivation);
      const payoff = val(p.reading_payoff);
      const detail = [q && `主问题：${esc(q)}`, payoff && `兑现：${esc(payoff)}`, motive && `往下读的理由：${esc(motive)}`]
        .filter(Boolean)
        .join("<br>");
      // 不少分析里 summary 就是阶段名本身。印成「开端 … 开端」是白占一列。
      const rawSummary = val(p.summary);
      const summary = rawSummary === val(p.title) ? "" : rawSummary;
      return `<tr>
<th>${esc(p.title || `阶段 ${p.ordinal}`)}</th>
<td class="where">S${p.start_scene_ordinal}–S${p.end_scene_ordinal}</td>
<td class="n">${Number.isFinite(p.average_engagement) ? Math.round(p.average_engagement) : "—"}</td>
<td>${summary ? esc(cut(summary, 90)) : ""}${summary && detail ? "<br>" : ""}${detail}</td>
</tr>`;
    })
    .join("");

  const weak = val(lowInterval?.summary) || val(s.weak_interval);
  const trigger = val(lowInterval?.trigger);

  if (!chart && !phaseRows && !weak) return "";

  return `<section class="page">
<h2><span class="num">一</span>这一章读起来怎么样</h2>
${why ? `<p class="note">${esc(label)}：${esc(why)}</p>` : ""}
${chart}
${
  weak
    ? `<div class="region"><h4>最需要看的一段</h4><p>${esc(weak)}</p>${
        trigger ? `<p class="note">判定条件：${esc(trigger)}</p>` : ""
      }</div>`
    : ""
}
${
  phaseRows
    ? `<h3>阶段</h3>
<table class="pstages"><thead><tr><th>阶段</th><th class="where">场景</th><th class="n">均值</th><th>内容</th></tr></thead><tbody>${phaseRows}</tbody></table>`
    : ""
}
</section>`;
}

function questionPage(input: ChapterReportInput): string {
  const v = input.visualization;
  const vocab: Partial<HookVocabulary> = v.hook_vocabulary || {};
  const openWord = vocab.open || "提出疑问";
  const answerWord = vocab.answer || "给出回应";
  const carryWord = vocab.carry || "留到下章";

  const lifecycle = (v.question_lifecycle || []) as Array<{
    question_text?: string;
    setup_scene?: number;
    development_scenes?: number[];
    payoff_scene?: number | null;
    status?: string;
    strength?: number;
  }>;

  const STATUS: Record<string, string> = {
    paid_off: "已回应",
    open: "仍开着",
    created: "刚提出",
    deferred: carryWord,
    abandoned: "没有下文",
  };

  const rows = lifecycle
    .map((q) => {
      const text = val(q.question_text);
      if (!text) return "";
      const dev = (q.development_scenes || []).map((x) => `S${x}`).join("、");
      return `<tr>
<td>${esc(cut(text, 110))}</td>
<td class="where">${q.setup_scene != null ? `S${q.setup_scene}` : "—"}</td>
<td class="where">${esc(dev || "—")}</td>
<td class="where">${q.payoff_scene != null ? `S${q.payoff_scene}` : "—"}</td>
<td class="tag">${esc(STATUS[String(q.status)] || val(q.status))}</td>
<td class="n">${num(q.strength) ?? "—"}</td>
</tr>`;
    })
    .filter(Boolean)
    .join("");

  const chain = v.primary_question_chain;
  const scenes = mainScenes(v);
  const last = scenes[scenes.length - 1];
  // open_questions.opened / .closed 记的是**那一场**开了几个、收了几个，只有 balance 是
  // 累计。直接拿末场那两个数当「本章开几收几」，印出来会是「开 5 收 3，仍欠 12」——
  // 一个自己都对不上的账。本章的开与收要逐场相加。
  const ledger = last?.open_questions ?? null;
  const openedTotal = scenes.reduce((t, n) => t + (Number(n.open_questions?.opened) || 0), 0);
  const closedTotal = scenes.reduce((t, n) => t + (Number(n.open_questions?.closed) || 0), 0);
  const carried = (last?.reader_question_out || []).map((q) => val(q.question)).filter(Boolean);

  if (!rows && !chain && !carried.length && !ledger) return "";

  return `<section class="page">
<h2><span class="num">二</span>悬念账本</h2>
<p class="note">
一章开了多少疑问、收了多少、走到章末还欠着多少。欠着不是错——章末不欠，读者就没有理由
翻下一章；欠一堆而一个也没兑现，读者会觉得被耍。
</p>
${
  ledger
    ? `<table class="kv">
<tr><th>本章${esc(openWord)}</th><td>${openedTotal} 个</td></tr>
<tr><th>本章${esc(answerWord)}</th><td>${closedTotal} 个</td></tr>
<tr><th>章末仍欠</th><td><b class="grade">${ledger.balance}</b> 个</td></tr>
</table>`
    : ""
}
${
  chain
    ? `<h3>主问题链</h3>
<table class="kv">
<tr><th>问题</th><td>${esc(val(chain.canonical_question) || "—")}</td></tr>
<tr><th>提出</th><td>${chain.created_scene != null ? `S${chain.created_scene}` : "—"}</td></tr>
<tr><th>回应</th><td>${
        chain.answered_scene != null ? `S${chain.answered_scene}` : `未回应（${esc(carryWord)}）`
      }</td></tr>
<tr><th>强度</th><td>${num(chain.strength) ?? "—"}</td></tr>
</table>`
    : ""
}
${
  rows
    ? `<h3>疑问逐条</h3>
<table class="qtable"><thead><tr><th>疑问</th><th class="where">提出</th><th class="where">发展</th><th class="where">回应</th><th class="tag">状态</th><th class="n">强度</th></tr></thead><tbody>${rows}</tbody></table>`
    : ""
}
${
  carried.length
    ? `<h3>走到章末还开着的</h3>
<ol class="carried">${carried.map((q) => `<li>${esc(cut(q, 120))}</li>`).join("")}</ol>`
    : ""
}
</section>`;
}

function scenePages(input: ChapterReportInput): string {
  const v = input.visualization;
  const vocab: Partial<HookVocabulary> = v.hook_vocabulary || {};
  const scenes = mainScenes(v);
  if (!scenes.length) return "";
  const ROLE: Record<string, string> = { core: "核心", secondary: "次要", beat: "节拍" };
  const curveLabel = v.main_curve?.label || "追读";

  const rows = scenes
    .map((n) => {
      const eng = num(n.engagement?.engagement_score) ?? num(n.scores?.reading_momentum);
      const created = (n.reader_question_created || []).map((q) => val(q.question)).filter(Boolean);
      const answered = (n.reader_question_answered || [])
        .map((q) => val(q.answer_summary) || val(q.question))
        .filter(Boolean);
      const risk = val(n.primary_risk?.summary) || val((n.risk_points || [])[0]?.summary);
      const diag = val(n.primary_diagnosis);
      const acts = [
        created.length ? `${esc(vocab.open || "提出疑问")}：${esc(cut(created[0], 60))}` : "",
        answered.length ? `${esc(vocab.answer || "给出回应")}：${esc(cut(answered[0], 60))}` : "",
      ]
        .filter(Boolean)
        .join("<br>");
      return `<tr>
<th class="idx">S${n.scene_ordinal}</th>
<td class="where">${esc(pnum(n.paragraph_range?.start_paragraph_id))}–${esc(pnum(n.paragraph_range?.end_paragraph_id))}</td>
<td class="tag">${esc(ROLE[String(n.final_level || n.role)] || "")}</td>
<td class="n">${eng != null ? Math.round(eng) : "—"}</td>
<td class="tag">${esc(val(n.dominant_emotion))}</td>
<td>${esc(cut(val(n.scene_value_summary), 120))}${acts ? `<span class="acts">${acts}</span>` : ""}${
        risk ? `<span class="risk">风险：${esc(cut(risk, 70))}</span>` : ""
      }${diag && diag !== risk ? `<span class="risk">诊断：${esc(cut(diag, 70))}</span>` : ""}</td>
</tr>`;
    })
    .join("");

  return `<section class="page">
<h2><span class="num">三</span>逐场景</h2>
<p class="note">
每一行是一场：占了哪几段、算不算核心、${esc(curveLabel)}多少分、主导什么情绪、把故事推到
哪、以及它对读者手里的疑问做了什么。段号可以回原文核对。
</p>
<table class="scenes"><thead><tr>
<th class="idx">场</th><th class="where">段落</th><th class="tag">角色</th>
<th class="n">${esc(curveLabel)}</th><th class="tag">情绪</th><th>这一场做了什么</th>
</tr></thead><tbody>${rows}</tbody></table>
</section>`;
}

function hasGenreAxes(v: ReaderJourneyVisualization): boolean {
  return mainScenes(v).some((n) => (n.genre_axes || []).some((a) => a?.key));
}

function genreAxisPage(input: ChapterReportInput): string {
  const scenes = mainScenes(input.visualization);
  // 画像轴里有「开篇抓力」「断章质量」这种和第一页三项体检同名的——同一个词，一个是
  // 0—100 的钩子强度，一个是画像自己的 0—5 档。不说破，读者会以为其中一个印错了。
  const vitalLabels = new Set(buildChapterHookVitals(input.visualization).map((x) => x.label));
  const byAxis = new Map<string, { label: string; anchors: string; rows: string[]; clash: boolean }>();
  for (const n of scenes) {
    for (const axis of n.genre_axes || []) {
      const key = String(axis.key || "");
      if (!key) continue;
      const bucket = byAxis.get(key) ?? {
        label: String(axis.label || key),
        anchors: "",
        rows: [] as string[],
        clash: vitalLabels.has(String(axis.label || "")),
      };
      if (!bucket.anchors && val(axis.anchors)) bucket.anchors = val(axis.anchors);
      bucket.rows.push(`<tr>
<th class="idx">S${n.scene_ordinal}</th>
<td class="grade">${num(axis.level) ?? "—"} / 5</td>
<td>${esc(cut(val(axis.rationale), 130))}</td>
<td class="where">${esc(pnums(axis.evidence_paragraph_ids))}</td>
</tr>`);
      byAxis.set(key, bucket);
    }
  }
  if (!byAxis.size) return "";

  const blocks = [...byAxis.values()]
    .map(
      (b) => `<div class="axis">
<h3>${esc(b.label)}</h3>
${
  b.clash
    ? `<p class="note">与第一页那项同名，但不是同一个数：第一页是 0—100 的钩子强度，这里是画像自己的 0—5 档。</p>`
    : ""
}
${b.anchors ? `<p class="note">这条怎么算分：${esc(b.anchors)}</p>` : ""}
<table class="axistable"><tbody>${b.rows.join("")}</tbody></table>
</div>`,
    )
    .join("");

  return `<section class="page">
<h2><span class="num">四</span>类型专项</h2>
<p class="note">
这几条轴是这本书的画像点名要的——悬疑量线索投放与信息公平，爽文量爽点兑现与憋屈控制。
对这个类型的读者来说它们就是阅读本身，所以分数旁边一并给出刻度和依据段号。
</p>
${blocks}
</section>`;
}

function takeawayPage(input: ChapterReportInput): string {
  const scenes = mainScenes(input.visualization);
  const seen = new Set<string>();
  const items: string[] = [];

  for (const n of scenes) {
    for (const raw of n.writing_takeaways || []) {
      const t = (typeof raw === "string" ? { summary: raw } : raw) as JourneyWritingTakeaway;
      const summary = val(t?.summary);
      if (!summary || seen.has(summary)) continue;
      seen.add(summary);
      const when = val(t?.applicable_when);
      const avoid = val(t?.avoid_when);
      items.push(`<div class="take">
<h4><span class="idx">S${n.scene_ordinal}</span>${esc(summary)}</h4>
${when ? `<p class="note">适用：${esc(when)}</p>` : ""}
${avoid ? `<p class="note">别用在：${esc(avoid)}</p>` : ""}
</div>`);
    }
  }

  const techRows: string[] = [];
  const techSeen = new Set<string>();
  for (const n of scenes) {
    for (const raw of n.techniques || []) {
      const t = raw as JourneyTechniqueItem;
      const name = val(t?.name) || val(t?.code);
      const formula = val(t?.transfer_formula);
      if (!name || !formula || techSeen.has(name)) continue;
      techSeen.add(name);
      techRows.push(`<tr>
<th>${esc(name)}</th>
<td>${esc(cut(formula, 140))}${
        val(t?.reader_effect) ? `<span class="basis">读者感受：${esc(val(t.reader_effect))}</span>` : ""
      }${val(t?.risk) ? `<span class="risk">风险：${esc(val(t.risk))}</span>` : ""}</td>
<td class="where">S${n.scene_ordinal}</td>
</tr>`);
    }
  }

  if (!items.length && !techRows.length) return "";

  return `<section class="page">
<h2><span class="num">五</span>能带走的写法</h2>
<p class="note">
这一节不评价这一章。它挑出来的是换一篇稿子也用得上的那部分：一个做法、它管用的场合、
以及它会砸在什么地方。
</p>
${items.slice(0, 12).join("")}
${
  techRows.length
    ? `<h3>手法与迁移公式</h3>
<table class="tech"><tbody>${techRows.slice(0, 10).join("")}</tbody></table>`
    : ""
}
</section>`;
}

function appendixPage(input: ChapterReportInput, generatedAt: Date): string {
  const v = input.visualization;
  const f = v.formula_versions || ({} as ReaderJourneyVisualization["formula_versions"]);
  const c = v.calibration_status || ({} as ReaderJourneyVisualization["calibration_status"]);
  const two = (x: number) => String(x).padStart(2, "0");
  const stamp =
    `${generatedAt.getFullYear()}-${two(generatedAt.getMonth() + 1)}-${two(generatedAt.getDate())} ` +
    `${two(generatedAt.getHours())}:${two(generatedAt.getMinutes())}`;

  const rows: Array<[string, string]> = [
    ["生成时间", stamp],
    ["模型", [val(input.providerName), val(input.modelName)].filter(Boolean).join(" · ")],
    ["分析任务", input.analysisRunId != null ? `#${input.analysisRunId}` : ""],
    ["旅程任务", input.journeyRunId != null ? `#${input.journeyRunId}` : ""],
    ["可视化版本", val(v.visualization_version)],
    ["追读分公式", val(f.engagement_formula_version)],
    ["重要度公式", val(f.importance_formula_version)],
    ["场景契约", val(c.scene_contract_version)],
    ["语义来源", val(c.semantic_source)],
  ];

  return `<section class="page">
<h2><span class="num">附录</span>分析方法与口径</h2>
<p class="note">
分数只在同一套口径内可比。下面任何一行变了——换了模型、改了公式版本、换了场景契约——
新旧两份报告的数字就不能直接放在一起看。
</p>
<table class="kv">
${rows
  .filter(([, value]) => value)
  .map(([k, value]) => `<tr><th>${esc(k)}</th><td>${esc(value)}</td></tr>`)
  .join("")}
</table>
<h3>怎么读这些分</h3>
<p>
0—100 是同一本书内部的相对刻度，不是跨书排名。三项体检里的「开篇抓力」「章末牵引」取的是
首场与末场的钩子强度；「${esc(v.hook_vocabulary?.first_mark || "首钩位置")}」是全章第一个钩子
落在第几段——它是位置不是分数，所以不给颜色：P10 算不算晚取决于这一章有多长，读法那一列
已经说了它落在哪一侧。
</p>
${
  hasGenreAxes(v)
    ? `<p>
类型专项那几条各有自己的 0/3/5 刻度，印在每条轴的开头。一条轴给 0 分，意思是「按这条刻度
它落在最低那一档」，不是「这一章不好」——解释一份文件里没有的章节，只会让读者去翻一张不
存在的页。
</p>`
    : ""
}
</section>`;
}

export function chapterReportFileName(input: ChapterReportInput): string {
  const safe = String(input.chapterTitle || "章节")
    .replace(/[\\/:*?"<>|]/g, "_")
    .slice(0, 60);
  return `StoryLens_${safe}_章节评测报告.html`;
}

export function buildChapterPrintHtml(input: ChapterReportInput, generatedAt: Date = new Date()): string {
  const body = [
    coverPage(input),
    curvePage(input),
    questionPage(input),
    scenePages(input),
    genreAxisPage(input),
    takeawayPage(input),
    appendixPage(input, generatedAt),
  ]
    .filter(Boolean)
    .join("");

  // 显式声明字符集。这份 HTML 会被写到磁盘、由无头 Chromium 以 file:/// 打开；不声明就走
  // 系统默认，中文 Windows 上是 GBK，整份报告会印成乱码。
  return `<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<title>${esc(input.chapterTitle)} · 章节评测报告</title>
<style>
@page { size: A4; margin: 18mm 17mm 16mm; }
:root {
  --sans: "PingFang SC", "Microsoft YaHei", "Hiragino Sans GB", sans-serif;
  --serif: "Songti SC", SimSun, "Noto Serif CJK SC", serif;
  --ink: ${INK}; --mute: ${MUTE}; --rule: ${RULE}; --key: ${KEY}; --warn: ${WARN};
}
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  margin: 0; color: var(--ink); background: #fff;
  font-family: var(--serif); font-size: 10.5pt; line-height: 1.75;
}
.page { break-after: page; }
.page:last-child { break-after: auto; }

/* 结构用无衬线，正文用衬线——全篇只守这一条。 */
h1, h2, h3, h4, th, .kicker, .note, .where, .tag, .idx, .num, .grade, .basis, .acts, .risk,
figcaption, .cover-sub, .n { font-family: var(--sans); }
p, td, li, .lead { font-family: var(--serif); }

h1 { font-size: 24pt; line-height: 1.25; margin: 0 0 3mm; letter-spacing: .02em; }
h2 {
  font-size: 13pt; margin: 8mm 0 4mm; padding-bottom: 2mm;
  border-bottom: 1pt solid var(--key); color: var(--key); display: flex; align-items: baseline;
}
.page > h2:first-of-type { margin-top: 0; }
h2 .num {
  font-size: 9.5pt; letter-spacing: .1em; margin-right: 4mm; padding: .6mm 2mm;
  background: var(--key); color: #fff; white-space: nowrap;
}
h3 { font-size: 11pt; color: var(--key); margin: 6mm 0 2.5mm; }
h4 { font-size: 10pt; margin: 3.5mm 0 1mm; display: flex; gap: 3mm; align-items: baseline; }
p { margin: 0 0 2.5mm; }
.lead { font-size: 11.5pt; line-height: 1.7; }
.note { font-size: 8.5pt; color: var(--mute); line-height: 1.65; margin-bottom: 3mm; }
.where { font-size: 8.5pt; color: var(--key); white-space: nowrap; font-variant-numeric: tabular-nums; }
.idx { font-size: 8.5pt; letter-spacing: .06em; color: var(--key); white-space: nowrap; font-weight: 700; }
.tag { font-size: 8pt; color: var(--mute); white-space: nowrap; }
.n { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.basis, .acts, .risk { display: block; font-size: 8pt; color: var(--mute); line-height: 1.6; margin-top: .8mm; }
.risk { color: var(--warn); }

/* 封面 */
.cover-head { border-bottom: 2pt solid var(--key); padding-bottom: 6mm; margin-bottom: 6mm; }
.kicker { font-size: 8.5pt; letter-spacing: .3em; color: var(--key); margin: 0 0 3mm; }
.cover-sub { font-size: 11pt; color: var(--mute); letter-spacing: .12em; margin: 0; }
.cover-note {
  font-family: var(--sans); font-size: 8.5pt; color: var(--mute); line-height: 1.8;
  border-top: .5pt solid var(--rule); padding-top: 4mm; margin-top: 8mm;
}

/* 表 */
table { width: 100%; border-collapse: collapse; }
th { text-align: left; font-weight: 400; vertical-align: top; }
td { vertical-align: top; }
.kv th { width: 26mm; font-size: 9pt; color: var(--mute); padding: 1.6mm 0; }
.kv td { padding: 1.6mm 0 1.6mm 4mm; }
.kv tr + tr th, .kv tr + tr td { border-top: .4pt solid #eef2ef; }

.vitals th { width: 24mm; font-size: 10pt; padding: 2.4mm 0; color: var(--ink); }
.vitals td { padding: 2.4mm 0 2.4mm 4mm; }
.vitals tr + tr th, .vitals tr + tr td { border-top: .4pt solid #eef2ef; }
.grade { font-family: var(--sans); font-weight: 700; color: var(--key); font-size: 13pt; }
.vitals .grade { width: 16mm; padding-left: 3mm; }
.grade[data-band="weak"] { color: var(--warn); }
.grade[data-band="unknown"] { color: var(--mute); }

thead th { color: var(--mute); font-size: 8pt; border-bottom: .6pt solid var(--rule); padding-bottom: 1.4mm; }
.pstages th, .qtable th, .scenes th, .tech th, .axistable th { padding: 1.8mm 0; }
.pstages td, .qtable td, .scenes td, .tech td, .axistable td { padding: 1.8mm 0 1.8mm 3mm; }
.pstages tbody tr + tr th, .pstages tbody tr + tr td,
.qtable tbody tr + tr th, .qtable tbody tr + tr td,
.scenes tbody tr + tr th, .scenes tbody tr + tr td,
.tech tr + tr th, .tech tr + tr td,
.axistable tr + tr th, .axistable tr + tr td { border-top: .4pt solid #eef2ef; }
.pstages th { width: 26mm; font-family: var(--sans); font-size: 9.5pt; }
.scenes th.idx { width: 9mm; padding-left: 0; }
.scenes tbody tr, .qtable tbody tr { break-inside: avoid; }
.tech th { width: 30mm; font-family: var(--sans); font-size: 9.5pt; }
.axistable th { width: 9mm; padding-left: 0; }
.axistable .grade { width: 16mm; font-size: 10.5pt; }
.qtable td:first-child { padding-left: 0; }

.chart { margin: 0 0 5mm; break-inside: avoid; }
figcaption { font-size: 8pt; color: var(--mute); margin-top: 1.5mm; }

.region { padding-left: 3.5mm; border-left: 1.5pt solid var(--warn); margin-bottom: 4.5mm; break-inside: avoid; }
.region h4 { margin-top: 0; color: var(--warn); }
.take { break-inside: avoid; margin-bottom: 3.5mm; }
.axis { break-inside: avoid; margin-bottom: 5mm; }
.carried { margin: 0; padding-left: 5mm; }
.carried li { padding: 1mm 0; }
</style>
${body}
</html>`;
}
