/** 结构化报告导出。
 *
 *  One self-contained HTML file holding everything the seven on-screen modules hold —
 *  including the fields the screen summarises (full pacing table, every chapter's function,
 *  the complete evidence index with quotes) — plus the raw analysis JSON embedded in a
 *  <script type="application/json"> block, so a reviewer can audit the prose against the
 *  data without the app. Labels come from the same maps the screen uses; the export never
 *  invents its own vocabulary.
 *
 *  The file carries a print stylesheet: open in a browser → 打印 → PDF is the intended
 *  hand-off path.
 */
import type { WholeBookAnalysisV2 } from "./contracts";
import { buildPrintHtml } from "./printExport";
import {
  PACING_SERIES,
  PACING_SCALE_NOTE,
  HEATMAP_DIMS,
  STORYLINE_STATUS,
  JOURNEY_TAB,
  ROLE_LABEL,
  SUSPENSE_BEATS,
  DIMENSION_LABELS,
  saidNothing,
} from "./presentation/labels";

const esc = (x: unknown): string =>
  String(x ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/* ---- charts -----------------------------------------------------------------
   The same numbers the on-screen components draw, re-rendered as static SVG/HTML
   strings. Layout constants are copied from the components they mirror
   (DimensionRadar, JourneyChart, PacingModule, RelationshipGraph) — if a chart
   changes shape on screen, change it here too. */

const INK = "#1b2621", GREEN = "#2f6b57", FAINT = "#8a968f", LINE = "#dbe1dc",
  RED = "#a4523f", AMBER = "#b8791c";
const PAL = ["#2f6b57", "#7a6ba8", "#b8791c", "#5b7596", "#a4523f", "#3f7a75", "#b04e72", "#62744c"];
/** Must match the screen's pacing palette and dashes exactly — see `PACING_COLORS` there. */
const EXPORT_PACING_COLORS = ["#14503c", "#d1793a", "#6b74a8"];
const EXPORT_DASHES = ["", "7 4", "2 4"];
const DOWN_KINDS = new Set(["setback", "demote", "twist", "misdirect"]);
const RATING_SCORE: Record<string, number> = { A: 7, "A-": 6, "B+": 5, B: 4, "B-": 3, C: 2, D: 1 };

function svgRadar(dims: WholeBookAnalysisV2["assessment"]["dimensions"]): string {
  const n = dims.length;
  if (n < 3) return "";
  const cx = 150, cy = 132, R = 92;
  const at = (i: number, r: number): [number, number] => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / n;
    return [cx + Math.cos(a) * r, cy + Math.sin(a) * r];
  };
  const poly = (r: number) => dims.map((_, i) => at(i, r).map((v) => v.toFixed(1)).join(",")).join(" ");
  const pts = dims.map((d, i) => at(i, (R * (RATING_SCORE[d.rating] ?? 4)) / 7));
  return `<svg viewBox="0 0 300 268" style="width:300px;max-width:100%" role="img" aria-label="六维评估雷达图">
    ${[0.34, 0.67, 1].map((f) => `<polygon points="${poly(R * f)}" fill="none" stroke="${INK}" opacity=".2"/>`).join("")}
    <polygon points="${poly((R * RATING_SCORE.B) / 7)}" fill="none" stroke="${INK}" opacity=".45" stroke-dasharray="3 3"/>
    ${dims.map((_, i) => { const [x, y] = at(i, R); return `<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="${INK}" opacity=".2"/>`; }).join("")}
    <polygon points="${pts.map((p) => p.map((v) => v.toFixed(1)).join(",")).join(" ")}" fill="${GREEN}" fill-opacity=".22" stroke="${GREEN}" stroke-width="1.6"/>
    ${pts.map(([x, y]) => `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3" fill="${GREEN}"/>`).join("")}
    ${dims.map((d, i) => { const [x, y] = at(i, R + 25); const anchor = Math.abs(x - cx) < 12 ? "middle" : x > cx ? "start" : "end";
      return `<text x="${x.toFixed(1)}" y="${(y + 4).toFixed(1)}" text-anchor="${anchor}" font-size="11" fill="${INK}">${esc(DIMENSION_LABELS[d.dimension] ?? d.dimension)} ${esc(d.rating)}</text>`; }).join("")}
  </svg>
  <p class="metae">越靠外越好 · 虚线为 B 基准</p>`;
}

function svgPacing(d: WholeBookAnalysisV2): string {
  const points = d.pacing.points;
  if (!points.length) return "";
  const W = 1000, H = 300, L = 44, Rp = 12, T = 12, B = 24;
  const maxCh = points.at(-1)?.chapter_end ?? d.book_metadata.chapter_count;
  const x = (ch: number) => L + (Math.min(ch, maxCh) / Math.max(1, maxCh)) * (W - L - Rp);
  const y = (v: number) => T + (1 - v / 100) * (H - T - B);
  // Same three curves, same colours and dashes as the screen. An export that draws a different
  // chart from the app cannot be checked against it, which is the whole reason both read one
  // vocabulary out of `labels.ts`.
  const lines = PACING_SERIES.map((s, si) => {
    const path = points
      .map(
        (p, i) =>
          `${i ? "L" : "M"} ${x((p.chapter_start + p.chapter_end) / 2).toFixed(1)} ${y(Number(p[s.key] ?? 0)).toFixed(1)}`,
      )
      .join(" ");
    const dash = EXPORT_DASHES[si] ? ` stroke-dasharray="${EXPORT_DASHES[si]}"` : "";
    return `<path d="${path}" fill="none" stroke="${EXPORT_PACING_COLORS[si]}" stroke-width="1.8"${dash}/>`;
  });
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%" role="img" aria-label="全书节奏曲线">
    ${[0, 50, 100].map((v) => `<line x1="${L}" y1="${y(v)}" x2="${W - Rp}" y2="${y(v)}" stroke="${LINE}"/><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end" font-size="11" fill="${FAINT}">${v}</text>`).join("")}
    ${points.map((p) => `<text x="${x((p.chapter_start + p.chapter_end) / 2).toFixed(1)}" y="${H - 6}" text-anchor="middle" font-size="10" fill="${FAINT}">${p.chapter_start}</text>`).join("")}
    ${lines.join("")}
  </svg>
  <p class="legend">${PACING_SERIES.map((s, i) => `<span><i style="background:${EXPORT_PACING_COLORS[i]}"></i>${esc(s.label)}（${esc(s.measures)}）</span>`).join("")}</p>
  <p class="note">${esc(PACING_SCALE_NOTE)}</p>`;
}

function svgJourney(d: WholeBookAnalysisV2): string {
  const j = d.journey;
  if (!j || j.axis === "none") return "";
  const width = 1000, total = Math.max(1, d.book_metadata.chapter_count);
  const x = (ch: number) => 60 + (Math.min(ch, total) / total) * (width - 74);
  if (j.axis === "screen_time") {
    const bins = j.bins || j.bands[0]?.share.length || 0;
    if (!bins) return "";
    const top = 12, height = 240;
    let base = new Array(bins).fill(0);
    const polys = j.bands.map((band, index) => {
      const upper = band.share.map((v, i) => base[i] + v);
      const pts =
        upper.map((v, i) => `${x(((i + 0.5) * total) / bins).toFixed(1)},${(height - v * (height - top)).toFixed(1)}`).join(" ") +
        " " +
        base.map((v, i) => `${x(((bins - 0.5 - i) * total) / bins).toFixed(1)},${(height - base[bins - 1 - i] * (height - top)).toFixed(1)}`).join(" ");
      base = upper;
      return `<polygon points="${pts}" fill="${PAL[index % 8]}" fill-opacity=".8"><title>${esc(band.name)}</title></polygon>`;
    });
    return `<svg viewBox="0 0 ${width} ${height + 8}" style="width:100%" role="img" aria-label="戏份分布">${polys.join("")}</svg>
    <p class="legend">${j.bands.map((b, i) => `<span><i style="background:${PAL[i % 8]}"></i>${esc(b.name)}<small>（${b.chapters} 章）</small></span>`).join("")}</p>
    ${j.caveat ? `<p class="metae">${esc(j.caveat)}</p>` : ""}`;
  }
  const values = j.points.map((p) => p.value);
  const lo = Math.min(...values, 0), hi = Math.max(...values, lo + 1);
  const top = 20, height = 260;
  const y = (v: number) => height - ((v - lo) / (hi - lo)) * (height - top);
  const connected = j.points.filter((p) => p.load_bearing);
  const path =
    j.axis === "ladder"
      ? connected.map((p, i) => (i === 0 ? `M ${x(p.chapter).toFixed(1)} ${y(p.value).toFixed(1)}` : `L ${x(p.chapter).toFixed(1)} ${y(connected[i - 1].value).toFixed(1)} L ${x(p.chapter).toFixed(1)} ${y(p.value).toFixed(1)}`)).join(" ")
      : connected.map((p, i) => `${i ? "L" : "M"} ${x(p.chapter).toFixed(1)} ${y(p.value).toFixed(1)}`).join(" ");
  const down = j.points.filter((p) => DOWN_KINDS.has(p.kind)).length;
  return `<svg viewBox="0 0 ${width} ${height + 16}" style="width:100%" role="img" aria-label="${esc(j.axis_label)}">
    ${j.ticks.map((t, i) => { const atv = j.axis === "ladder" ? i + 1 : i === 0 ? lo : hi;
      return `<line x1="60" y1="${y(atv).toFixed(1)}" x2="${width - 14}" y2="${y(atv).toFixed(1)}" stroke="${LINE}"/><text x="54" y="${(y(atv) + 4).toFixed(1)}" text-anchor="end" font-size="11" fill="${FAINT}">${esc(t)}</text>`; }).join("")}
    ${path ? `<path d="${path}" fill="none" stroke="${GREEN}" stroke-width="1.6"/>` : ""}
    ${j.points.map((p) => `<circle cx="${x(p.chapter).toFixed(1)}" cy="${y(p.value).toFixed(1)}" r="${p.load_bearing ? 4.2 : 2.6}" fill="${DOWN_KINDS.has(p.kind) ? RED : GREEN}"/>`).join("")}
  </svg>
  <p class="metae">纵轴＝${esc(j.axis_label)}${j.lead ? `　主线＝${esc(j.lead)}` : ""}　共 ${j.points.length} 个读数，其中下跌 ${down} 次　红点＝下跌</p>
  ${j.caveat ? `<p class="metae">${esc(j.caveat)}</p>` : ""}`;
}

function svgRelGraph(rels: WholeBookAnalysisV2["characters"]["relationships"]): string {
  if (!rels.length) return "";
  const degree = new Map<string, number>();
  for (const r of rels) {
    degree.set(r.person_a, (degree.get(r.person_a) ?? 0) + 1);
    degree.set(r.person_b, (degree.get(r.person_b) ?? 0) + 1);
  }
  const ordered = [...degree.keys()].sort((a, b) => (degree.get(b) ?? 0) - (degree.get(a) ?? 0) || a.localeCompare(b));
  const lead = ordered[0] ?? "";
  const ring = ordered.slice(1);
  const place = new Map<string, [number, number]>([[lead, [320, 230]]]);
  ring.forEach((name, i) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / Math.max(1, ring.length);
    const radius = 118 + (i % 3) * 42;
    place.set(name, [320 + Math.cos(a) * radius, 230 + Math.sin(a) * radius]);
  });
  return `<svg viewBox="0 0 640 460" style="width:640px;max-width:100%" role="img" aria-label="人物关系网络图">
    ${rels.map((r) => { const a = place.get(r.person_a), b = place.get(r.person_b); if (!a || !b) return "";
      const w = 1 + Math.min(4, r.evolution?.length ?? 1) * 0.7;
      return `<line x1="${a[0].toFixed(1)}" y1="${a[1].toFixed(1)}" x2="${b[0].toFixed(1)}" y2="${b[1].toFixed(1)}" stroke="${GREEN}" stroke-opacity=".55" stroke-width="${w}"/>`; }).join("")}
    ${ordered.map((name) => { const [x, y] = place.get(name)!; const links = rels.filter((r) => r.person_a === name || r.person_b === name).length;
      const rr = name === lead ? 27 : 8 + Math.min(12, links * 3);
      return name === lead
        ? `<circle cx="${x}" cy="${y}" r="${rr}" fill="${GREEN}"/><text x="${x}" y="${y + 4}" text-anchor="middle" font-size="13" fill="#fff" font-weight="600">${esc(name)}</text>`
        : `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${rr}" fill="#fff" stroke="${GREEN}" stroke-width="1.5"/><text x="${x.toFixed(1)}" y="${(y + rr + 14).toFixed(1)}" text-anchor="middle" font-size="12" fill="${INK}">${esc(name)}</text>`; }).join("")}
  </svg>
  <p class="metae">中心＝关系最多的人物　线越粗＝演变步数越多</p>`;
}

function ganttBar(a: number, b: number, total: number, done: boolean): string {
  const left = ((a - 1) / Math.max(1, total)) * 100;
  const w = Math.max(1.5, ((b - a + 1) / Math.max(1, total)) * 100);
  return `<div class="bar"><i style="left:${left.toFixed(1)}%;width:${w.toFixed(1)}%;background:${done ? GREEN : "#f7ecd8"};${done ? "" : `border:2px solid ${AMBER};`}"></i></div>`;
}

function heatCell(v: number, max: number): string {
  const a = max > 0 ? 0.06 + 0.66 * (v / max) : 0.06;
  return `<td style="background:rgba(47,107,87,${a.toFixed(2)});${a > 0.45 ? "color:#fff" : ""}">${v.toFixed(1)}</td>`;
}

const list = (xs: readonly string[] | undefined, empty = "—"): string =>
  xs && xs.length ? `<ul>${xs.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : `<p class="none">${empty}</p>`;

const evd = (ids: readonly string[] | undefined): string =>
  ids && ids.length ? `<p class="evd">证据 ${ids.map((i) => `<code>${esc(i)}</code>`).join(" ")}</p>` : "";

// Same rule the on-screen report follows: a placeholder the model left behind
// (`unknown`, `未知`) is not an answer, so the row is dropped rather than printed.
// The exported HTML carried 13 of these before this guard existed.
const row = (k: string, v: string | undefined | null): string =>
  v && String(v).trim() && !saidNothing(v)
    ? `<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`
    : "";

const rng = (a: number, b: number): string => (a === b ? `第 ${a} 章` : `第 ${a}–${b} 章`);

function sectionOverview(d: WholeBookAnalysisV2): string {
  const ov = d.overview;
  const tp = d.type_profile;
  return `
  <h2 id="s1">1　全书总览</h2>
  <h3>作品画像</h3>
  <table>
    ${row("主类型", tp.primary_genre)}
    ${row("副类型", tp.secondary_genres.join("、"))}
    ${row("叙事驱动力", tp.narrative_drivers.join("、"))}
    ${row("叙事特征", tp.narrative_traits.join("、"))}
    ${row("重点分析方向", tp.analysis_focus.join("、"))}
    ${row("类型预期", (tp.genre_expectations ?? []).join("、"))}
  </table>
  <h3>故事核心</h3>
  <p class="lead">${esc(ov.one_sentence_story)}</p>
  <p>${esc(ov.full_summary)}</p>
  <table>
    ${row("主角", ov.protagonist)}
    ${row("起点状态", ov.initial_state)}
    ${row("终点状态", ov.final_state)}
    ${row("核心目标", ov.core_goal)}
    ${row("核心冲突", ov.core_conflict)}
    ${row("核心问题", ov.core_question)}
    ${row("最终高潮", ov.final_climax)}
  </table>
  <h3>目标演变</h3>${list(ov.goal_evolution, "无记录")}
  <h3>冲突演变</h3>${list(ov.conflict_evolution, "无记录")}
  <h3>故事骨架</h3>${list(ov.story_skeleton)}
  <h3>主要故事线</h3>${list(ov.major_storylines)}
  <h3>重大转折</h3>
  ${ov.major_turning_points.map((t) => `<p><b>${esc(t.title)}</b>（${rng(t.chapter_start, t.chapter_end)}）${esc(t.description)}</p>${evd(t.evidence)}`).join("") || '<p class="none">无记录</p>'}
  <h3>结局</h3>
  <p><b>已解决</b></p>${list(ov.ending_resolution)}
  <p><b>留下的问题</b></p>${list(ov.ending_open_questions)}
  ${evd(ov.evidence)}`;
}

function sectionStory(d: WholeBookAnalysisV2): string {
  const st = d.story;
  const reordered = st.chronology.filter((c) => c.story_order !== c.narrative_order).length;
  return `
  <h2 id="s2">2　故事</h2>
  <h3>结构阶段（${st.structure_stages.length}）</h3>
  ${st.structure_stages
    .map(
      (s, i) => `
    <h4>${String(i + 1).padStart(2, "0")}　${esc(s.title)}（${rng(s.chapter_start, s.chapter_end)}）</h4>
    <p>${esc(s.summary)}</p>
    <table>
      ${row("阶段目标", s.stage_goal)}
      ${row("核心冲突", s.core_conflict)}
      ${row("重大选择", s.major_choice)}
      ${row("付出", s.cost_paid.join("、"))}
      ${row("获得", s.gain_received.join("、"))}
    </table>
    ${evd(s.evidence)}`,
    )
    .join("")}
  <h3>主线与支线（${st.storylines.length}）</h3>
  <table>
    <tr><th>线</th><th>类型</th><th style="width:26%">覆盖</th><th>章节</th><th>状态</th><th>收束</th></tr>
    ${st.storylines
      .map(
        (s) =>
          `<tr><td>${esc(s.name)}</td><td>${s.type === "main" ? "主线" : "支线"}</td><td>${ganttBar(s.chapter_start, s.chapter_end, d.book_metadata.chapter_count, s.status === "resolved")}</td><td>${rng(s.chapter_start, s.chapter_end)}</td><td>${esc(STORYLINE_STATUS[s.status] ?? s.status)}</td><td>${esc(s.resolution || "—")}</td></tr>`,
      )
      .join("")}
  </table>
  <h3>因果链（${st.causal_chain.length}）</h3>${list(st.causal_chain)}
  <h3>时间线（${st.chronology.length}）</h3>
  <table>
    <tr><th>#</th><th>章</th><th>事件</th><th>证据</th></tr>
    ${st.chronology
      .map(
        (c) =>
          `<tr><td>${c.story_order}</td><td>第 ${c.chapter} 章</td><td>${esc(c.description)}</td><td>${c.evidence.map((e) => `<code>${esc(e)}</code>`).join(" ")}</td></tr>`,
      )
      .join("")}
  </table>
  <p>${reordered > 0 ? `<b>有 ${reordered} 处倒叙</b>：这些事件被讲述的顺序与实际发生顺序不一致。` : `<b>全书顺叙</b>：${st.chronology.length} 个事件的讲述顺序与发生顺序完全一致。`}</p>`;
}

function sectionCharacters(d: WholeBookAnalysisV2): string {
  const ch = d.characters;
  const p = ch.protagonist;
  const journey = d.journey;
  const tracks = [
    { name: "外在身份 / 社会位置", track: p.external_status_track },
    { name: "能力与资源", track: p.ability_track },
    { name: "内在信念", track: p.internal_belief_track },
    { name: "关系网络", track: p.relationship_track },
  ].filter((t) => t.track.length > 0);
  return `
  <h2 id="s3">3　人物</h2>
  <h3>主角历程${journey && journey.axis !== "none" ? `（${esc(JOURNEY_TAB[journey.axis])}·${esc(journey.axis_label)}）` : ""}</h3>
  ${svgJourney(d)}
  <table>
    ${row("身份", p.initial_identity === p.final_identity ? p.initial_identity : `${p.initial_identity} → ${p.final_identity}`)}
    ${row("目标", p.initial_goal === p.final_goal ? p.initial_goal : `${p.initial_goal} → ${p.final_goal}`)}
    ${row("弧线总述", p.arc_summary || p.core_transformation || "")}
  </table>
  ${p.stages
    .map(
      (s, i) => `
    <h4>第 ${i + 1} 程　${esc(s.stage_name)}（${rng(s.chapter, s.chapter_end)}）</h4>
    <table>
      ${row("起点", s.entry_state)}${row("终点", s.exit_state)}
      ${row("想得到什么", s.goal)}${row("遭遇什么", s.conflict)}${row("做出选择", s.choice)}
      ${row("付出", s.cost_paid.join("、"))}${row("获得", s.gain_received.join("、"))}
      ${row("能力变化", s.ability_change)}${row("关系变化", s.relationship_change)}
      ${row("社会位置变化", s.status_change)}${row("内在信念变化", s.internal_belief_change)}
      ${row("下一阶段触发", s.next_stage_trigger)}
    </table>
    <p><b>重大事件（${s.major_events.length}）</b></p>${list(s.major_events)}
    ${evd(s.evidence)}`,
    )
    .join("")}
  ${
    journey?.ledger?.length
      ? `<h3>行动台账</h3>${journey.ledger
          .map(
            (l) => `
      <h4>${esc(l.stage_name)}（${rng(l.chapter_start, l.chapter_end)}）</h4>
      <table>
        ${row(`做了什么 · 共 ${l.did_total}`, l.did.map((x) => `第${x.chapter}章 ${x.text}`).join("；"))}
        ${row(`遇见谁 · 共 ${l.met_total}`, l.met.map((m) => `${m.name}（第${m.chapter}章${m.relation ? "，" + m.relation : ""}）`).join("；"))}
        ${row(`得到 · 共 ${l.gained_total}`, l.gained.join("、"))}
        ${row(`失去 · 共 ${l.lost_total}`, l.lost.join("、"))}
      </table>`,
          )
          .join("")}`
      : ""
  }
  ${
    tracks.length
      ? `<h3>四轨成长</h3><table><tr><th>轨道</th><th>章</th><th>变化</th></tr>${tracks
          .map((t) =>
            t.track
              .map((v) => `<tr><td>${esc(t.name)}</td><td>第 ${v.chapter} 章</td><td>${esc(v.state)}</td></tr>`)
              .join(""),
          )
          .join("")}</table>`
      : ""
  }
  <h3>主要人物（${ch.major_characters.length}）</h3>
  ${ch.major_characters
    .map(
      (c) => `
    <h4>${esc(c.name)}　<small>${esc(ROLE_LABEL[c.role] ?? c.role)}</small></h4>
    <table>
      ${row("身份", c.identity)}
      ${row("全书变化", c.character_arc)}
      ${row("目标", c.initial_goal === c.final_goal ? c.final_goal : `${c.initial_goal ?? ""} → ${c.final_goal ?? ""}`)}
      ${row("与主角的关系", c.relationship_to_protagonist)}
      ${row("关系变化", (c.relationship_changes ?? []).join(" → "))}
      ${row("重大选择", c.major_choice)}
      ${row("付出", (c.cost_paid ?? []).join("、"))}
      ${row("获得", (c.gain_received ?? []).join("、"))}
      ${row("结局", c.ending)}
    </table>
    ${c.key_events?.length ? `<p><b>关键事件（${c.key_events.length}）</b></p>${list(c.key_events)}` : ""}
    ${evd(c.evidence)}`,
    )
    .join("")}
  <h3>人物关系（${ch.relationships.length}）</h3>
  ${svgRelGraph(ch.relationships)}
  <table>
    <tr><th>关系</th><th>章节</th><th>演变</th></tr>
    ${ch.relationships
      .map(
        (r) =>
          `<tr><td>${esc(r.person_a)} ⟷ ${esc(r.person_b)}</td><td>${rng(r.chapter_start, r.chapter_end)}</td><td>${esc((r.evolution?.length ? r.evolution : [r.relationship_type]).join(" → "))}</td></tr>`,
      )
      .join("")}
  </table>`;
}

function sectionSuspense(d: WholeBookAnalysisV2): string {
  const threads = d.suspense.lifecycles;
  const resolved = threads.filter((t) => t.status === "resolved").length;
  return `
  <h2 id="s4">4　悬念</h2>
  <p>${threads.length} 条悬念，${resolved} 条已回收。</p>
  <div class="wall">
    ${threads
      .map(
        (t) =>
          `<div class="tile" style="border-color:${t.status === "resolved" ? GREEN : AMBER};background:${t.status === "resolved" ? "#e8f1ec" : "#f7ecd8"}"><b>${esc(t.question)}</b><i>${rng(t.chapter_start, t.chapter_end)} · ${t.events.length} 次 · ${t.status === "resolved" ? "已回收" : "未回收"}</i></div>`,
      )
      .join("")}
  </div>
  ${threads
    .map(
      (t, i) => `
    <h4>${String(i + 1).padStart(2, "0")}　${esc(t.question)}　<small>${rng(t.chapter_start, t.chapter_end)} · ${t.status === "resolved" ? "已回收" : "未回收"}</small></h4>
    <table>
      <tr><th>章</th><th>动作</th><th>内容</th></tr>
      ${[...t.events]
        .sort((a, b) => a.chapter - b.chapter)
        .map(
          (e) =>
            `<tr><td>第 ${e.chapter} 章</td><td>${esc(SUSPENSE_BEATS[e.type] ?? e.type)}</td><td>${esc(e.description)}</td></tr>`,
        )
        .join("")}
    </table>
    ${
      t.payoff
        ? `<p><b>最终回收</b>　${esc(t.payoff)}</p>`
        : `<p class="open">全书未给出答案。如果是有意留到续作，这里就是伏笔；如果不是，这是个缺口。</p>`
    }
    ${evd(t.evidence)}`,
    )
    .join("")}`;
}

function sectionPacing(d: WholeBookAnalysisV2): string {
  const pc = d.pacing;
  return `
  <h2 id="s5">5　节奏</h2>
  <h3>节奏曲线</h3>
  ${svgPacing(d)}
  <h3>逐段指标（本书内百分位，0–100）</h3>
  <p class="note">${esc(PACING_SCALE_NOTE)}</p>
  <table class="wide">
    <tr><th>章段</th>${PACING_SERIES.map((s) => `<th>${esc(s.label)}<br><small>${esc(s.measures)}</small></th>`).join("")}<th>主导事件</th></tr>
    ${pc.points
      .map(
        (x) =>
          `<tr><td>${rng(x.chapter_start, x.chapter_end)}</td>${PACING_SERIES.map((s) => `<td>${Math.round(Number(x[s.key] ?? 0))}</td>`).join("")}<td>${esc(x.dominant_events.join("；") || "—")}</td></tr>`,
      )
      .join("")}
  </table>
  <h3>事件标记（${pc.event_markers.length}）</h3>
  ${pc.event_markers
    .map(
      (m) =>
        `<p><b>第 ${m.chapter} 章 · ${esc(m.title)}</b>　${esc(m.event)}${m.effect_on_pacing ? `（${esc(m.effect_on_pacing)}）` : ""}</p>${evd(m.evidence)}`,
    )
    .join("")}
  ${
    pc.pacing_regions.length
      ? `<h3>节奏区间</h3>${pc.pacing_regions.map((r) => `<p><b>${rng(r.chapter_start, r.chapter_end)} · ${esc(r.type)}</b>　${esc(r.diagnosis || r.reason)}</p>`).join("")}`
      : ""
  }`;
}

function sectionChapters(d: WholeBookAnalysisV2): string {
  const c = d.chapters;
  return `
  <h2 id="s6">6　章节</h2>
  <h3>每章功能（${c.functions.length}）</h3>
  <table class="wide">
    <tr><th>章</th><th>主功能</th><th>重要度</th><th>概要</th><th>证据</th></tr>
    ${c.functions
      .map(
        (f) =>
          `<tr><td>第 ${f.chapter_index} 章</td><td>${esc(f.primary_function)}</td><td>${f.importance.toFixed(1)}</td><td>${esc(f.summary || "—")}</td><td>${f.evidence.map((e) => `<code>${esc(e)}</code>`).join(" ")}</td></tr>`,
      )
      .join("")}
  </table>
  <h3>聚合热力（每 ${c.aggregation_size} 章一段）</h3>
  <p class="note">各列是清点结果的每章均值，不是评分；量纲不同（段落数 / 占比），深浅只在列内比较。</p>
  <table>
    <tr><th>章段</th>${HEATMAP_DIMS.map((h) => `<th>${esc(h.label)}<br><small>${esc(h.unit)}</small></th>`).join("")}</tr>
    ${(() => {
      const maxes = HEATMAP_DIMS.map((k) => Math.max(...c.heatmap.map((h) => Number(h[k.key])), 0));
      return c.heatmap
        .map(
          (h) =>
            `<tr><td>${rng(h.chapter_start, h.chapter_end)}</td>${HEATMAP_DIMS.map((k, i) => heatCell(Number(h[k.key]), maxes[i])).join("")}</tr>`,
        )
        .join("");
    })()}
  </table>`;
}

function sectionAssessment(d: WholeBookAnalysisV2): string {
  const a = d.assessment;
  return `
  <h2 id="s7">7　综合诊断</h2>
  ${a.overall_assessment ? `<p class="lead">${esc(a.overall_assessment)}</p>` : ""}
  <p>${esc(a.overall_summary)}</p>
  <h3>六维评估</h3>
  ${svgRadar(a.dimensions)}
  <table>
    <tr><th>维度</th><th>评级</th><th>结论</th></tr>
    ${a.dimensions
      .map(
        (x) =>
          `<tr><td>${esc(DIMENSION_LABELS[x.dimension] ?? x.dimension)}</td><td>${esc(x.rating)}</td><td>${esc(x.conclusion)}${x.supporting_metrics.length ? `<br><small>${esc(x.supporting_metrics.join(" · "))}</small>` : ""}</td></tr>`,
      )
      .join("")}
  </table>
  <h3>核心优势（${a.strengths.length}）</h3>
  ${a.strengths.map((x) => `<p><b>${esc(x.title)}</b>（${rng(x.chapter_start, x.chapter_end)}）${esc(x.why_good)}</p>${evd(x.evidence)}`).join("")}
  <h3>问题地图</h3>
  ${(() => {
    const total = d.book_metadata.chapter_count;
    const PRI: Record<string, string> = { P0: RED, P1: AMBER, P2: "#9db4a8" };
    const rows = [...new Set(a.issues.map((x) => DIMENSION_LABELS[x.category] ?? x.category))];
    return rows
      .map(
        (row) =>
          `<div class="maprow"><strong>${esc(row)}</strong><div class="bar">${a.issues
            .filter((x) => (DIMENSION_LABELS[x.category] ?? x.category) === row)
            .map((x) => `<i style="left:${(((x.chapter_start - 1) / Math.max(1, total)) * 100).toFixed(1)}%;width:${Math.max(1.5, ((x.chapter_end - x.chapter_start + 1) / Math.max(1, total)) * 100).toFixed(1)}%;background:${PRI[x.priority] ?? AMBER}"></i>`)
            .join("")}</div></div>`,
      )
      .join("");
  })()}
  <p class="legend"><span><i style="background:${RED}"></i>P0 必须优先处理</span><span><i style="background:${AMBER}"></i>P1 明显影响体验</span><span><i style="background:#9db4a8"></i>P2 局部优化</span></p>
  <h3>问题（${a.issues.length}）</h3>
  ${a.issues
    .map(
      (x) => `
    <h4>${esc(x.priority)}　${esc(x.symptom)}　<small>${esc(DIMENSION_LABELS[x.category] ?? x.category)} · ${rng(x.chapter_start, x.chapter_end)}</small></h4>
    <table>
      ${row("根本原因", x.root_cause)}
      ${row("读者影响", x.reader_impact)}
      ${row("支持指标", x.supporting_metrics.join(" · "))}
      ${row("可能方向", x.recommended_direction || x.possible_direction)}
    </table>
    ${evd(x.evidence)}`,
    )
    .join("")}
  <h3>修改优先级</h3>
  ${
    a.revision_priorities
      .map((x, i) => {
        if (typeof x === "string") return `<p><b>${String(i + 1).padStart(2, "0")}</b>　${esc(x)}</p>`;
        if (!x || typeof x !== "object") return "";
        const p = x as { priority?: string; chapter_ranges?: unknown; direction?: string; preserve?: unknown };
        const ranges = Array.isArray(p.chapter_ranges)
          ? p.chapter_ranges
              .filter((r): r is number[] => Array.isArray(r) && r.length >= 2)
              .map((r) => rng(r[0], r[1]))
              .join(" · ")
          : "";
        const preserve = Array.isArray(p.preserve) ? p.preserve.map(String).filter(Boolean) : [];
        return `<p><b>${String(i + 1).padStart(2, "0")}</b>　${esc(p.direction ?? "")}${ranges ? `（${esc(ranges)}）` : ""}${preserve.length ? `<br><small>改动时保留：${esc(preserve.join("、"))}</small>` : ""}</p>`;
      })
      .join("") || '<p class="none">无记录</p>'
  }
  <h3>建议保留</h3>${list(a.preserve_list)}`;
}

/** 拆文.
 *
 *  The exporter had no idea this section existed, so exporting a 拆文 report produced a file
 *  with none of its content and two empty sections where 评测 would have been — the same
 *  defect the screen had, surviving in the file people actually keep and send on.
 */
function sectionBreakdown(d: WholeBookAnalysisV2, index: number): string {
  const b = d.story_breakdown;
  if (!b?.four_beats?.length) return "";
  const moments = [...(b.standout_moments ?? [])].sort((x, y) => (x.rank ?? 999) - (y.rank ?? 999));
  return `
  <h2 id="sb">${index}　拆文</h2>
  <h3>四个部分</h3>
  <table>
    <tr><th>部分</th><th>章节</th><th>这一段在做什么</th></tr>
    ${b.four_beats
      .map(
        (x) =>
          `<tr><td>${esc(x.beat)}</td><td>${rng(x.chapter_start, x.chapter_end)}</td>           <td><b>${esc(x.title)}</b><br>${esc(x.summary)}</td></tr>`,
      )
      .join("")}
  </table>
  <h3>打动人的瞬间（${moments.length}）</h3>
  ${b.moment_count_rationale ? `<p class="note">${esc(b.moment_count_rationale)}</p>` : ""}
  ${moments
    .map(
      (m) => `
    <div class="moment">
      <p><b>${m.rank}. ${esc(m.title)}</b>　<span class="muted">第 ${m.chapter} 章</span></p>
      ${m.quote ? `<blockquote>${esc(m.quote)}</blockquote>` : ""}
      <p>${esc(m.why_it_lands)}</p>
      ${evd(m.evidence)}
    </div>`,
    )
    .join("")}
  <h3>每章留下的问题（${(b.chapter_hooks ?? []).length}）</h3>
  <table>
    <tr><th>章</th><th>这一章结尾留给读者的问题</th></tr>
    ${(b.chapter_hooks ?? [])
      .map((h) => `<tr><td>第 ${h.chapter} 章</td><td>${esc(h.question)}</td></tr>`)
      .join("")}
  </table>
  <h3>可复用的手法（${(b.reusable_techniques ?? []).length}）</h3>
  ${(b.reusable_techniques ?? [])
    .map(
      (t, i) => `
    <div class="moment">
      <p><b>${i + 1}. ${esc(t.name)}</b></p>
      <table>
        ${row("是什么", t.what_it_is)}
        ${row("为什么有效", t.why_it_works)}
        ${row("能用到哪", t.transfers_to)}
      </table>
    </div>`,
    )
    .join("")}
  <h3>配角功能（${(b.supporting_cast ?? []).length}）</h3>
  ${b.cast_note ? `<p class="note">${esc(b.cast_note)}</p>` : ""}
  <table>
    <tr><th>人物</th><th>承担的功能</th><th>是否越界</th></tr>
    ${(b.supporting_cast ?? [])
      .map(
        (c) =>
          `<tr><td>${esc(c.name)}</td><td>${esc(c.function)}</td>           <td>${esc(c.stays_in_lane ?? "—")}</td></tr>`,
      )
      .join("")}
  </table>`;
}

function sectionEvidence(d: WholeBookAnalysisV2): string {
  const entries = Object.values(d.evidence_index ?? {});
  if (!entries.length) return `<h2 id="appendix">附录A　证据索引</h2><p class="none">本文档没有携带证据索引。</p>`;
  return `
  <h2 id="appendix">附录A　证据索引（${entries.length}）</h2>
  <p>正文中的每个证据编号都指向这里的一条原文摘录，供与原著逐条对账。</p>
  <table class="wide">
    <tr><th>编号</th><th>章</th><th>摘录</th><th>提取理由</th></tr>
    ${entries
      .map(
        (e) =>
          `<tr><td><code>${esc(e.evidence_id)}</code></td><td>第 ${e.chapter_index} 章${e.chapter_title ? ` ${esc(e.chapter_title)}` : ""}</td><td>${esc(e.quote_or_excerpt)}</td><td>${esc(e.reason || "—")}</td></tr>`,
      )
      .join("")}
  </table>`;
}

export function reportFileName(d: WholeBookAnalysisV2): string {
  const safe = d.book_metadata.title.replace(/[\\/:*?"<>|\s]+/g, "_").slice(0, 40);
  return `${safe}-全书分析报告.html`;
}

export function buildReportHtml(d: WholeBookAnalysisV2, generatedAt: Date = new Date()): string {
  const meta = d.book_metadata;
  const am = d.analysis_metadata;
  // 目录按这份文档实际有什么来排，和屏幕上同一条规则：拆文那份没有总览和综合诊断，
  // 评测那份没有拆文。原先固定七节，于是拆文报告导出来是两节空的加一节缺失的。
  const hasBreakdown = Boolean(d.story_breakdown?.four_beats?.length);
  const hasOverview = Boolean(
    (d.overview?.one_sentence_story || "").trim() || (d.overview?.full_summary || "").trim(),
  );
  const hasAssessment = Boolean(
    (d.assessment?.overall_summary || "").trim() || d.assessment?.issues?.length,
  );
  // 编号本来就写在各节标题里，而两种读法各自的编号恰好都对：评测是总览 1…综合诊断 7，
  // 拆文是拆文 1、故事 2…章节 6。所以这里只决定哪几节出现，不重新编号。
  const bodySections: Array<[string, string, string]> = [];
  if (hasOverview) bodySections.push(["s1", "1 全书总览", sectionOverview(d)]);
  if (hasBreakdown) bodySections.push(["sb", "1 拆文", sectionBreakdown(d, 1)]);
  bodySections.push(["s2", "2 故事", sectionStory(d)]);
  bodySections.push(["s3", "3 人物", sectionCharacters(d)]);
  bodySections.push(["s4", "4 悬念", sectionSuspense(d)]);
  bodySections.push(["s5", "5 节奏", sectionPacing(d)]);
  bodySections.push(["s6", "6 章节", sectionChapters(d)]);
  if (hasAssessment) bodySections.push(["s7", "7 综合诊断", sectionAssessment(d)]);
  const toc = [
    ...bodySections.map(([id, label]) => [id, label] as const),
    ["appendix", "附录A 证据索引"] as const,
  ];
  // JSON inside <script> must not be able to close the tag early.
  const raw = JSON.stringify(d).replace(/</g, "\\u003c");
  return `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(meta.title)}·全书分析报告</title>
<style>
  body{margin:0;background:#fff;color:#1b2621;font-family:"PingFang SC","Microsoft YaHei","Hiragino Sans GB",system-ui,sans-serif;font-size:16px;line-height:1.45}
  .wrap{max-width:960px;margin:0 auto;padding:40px 32px 80px}
  h1{font-size:32px;margin:0 0 4px;line-height:1.3}
  h2{font-size:24px;margin:48px 0 16px;padding-top:16px;border-top:3px solid #2f6b57;line-height:1.3}
  h3{font-size:20px;margin:24px 0 8px;line-height:1.3}
  h4{font-size:16px;margin:20px 0 8px}
  h4 small{font-weight:400;color:#606c65;font-size:12px}
  p{margin:8px 0}
  .sub{color:#606c65;margin:0 0 24px}
  .lead{font-size:20px;line-height:1.45}
  .none{color:#8a968f}
  .open{padding:8px 12px;background:#f7ecd8;border-left:4px solid #b8791c}
  ul{margin:8px 0;padding-left:24px}
  li{margin:4px 0}
  table{border-collapse:collapse;width:100%;margin:8px 0;font-size:16px}
  th,td{border:1px solid #dbe1dc;padding:8px 12px;text-align:left;vertical-align:top}
  th{background:#eef2ed;font-size:12px;white-space:nowrap}
  table:not(.wide) th:first-child{width:9em}
  td{font-variant-numeric:tabular-nums}
  code{background:#eef2ed;padding:1px 6px;font-size:12px;font-family:ui-monospace,Consolas,monospace}
  .evd{font-size:12px;color:#606c65}
  .toc{display:flex;flex-wrap:wrap;gap:8px 20px;padding:12px 16px;background:#eef2ed;margin:16px 0 0}
  .toc a{color:#2f6b57;text-decoration:none}
  .metae{font-size:12px;color:#8a968f}
  .legend{display:flex;flex-wrap:wrap;gap:8px 20px;font-size:12px;color:#606c65}
  .legend i{display:inline-block;width:14px;height:8px;margin-right:6px}
  .bar{position:relative;height:12px;background:#eef2ed;min-width:120px}
  .bar i{position:absolute;top:0;bottom:0;display:block;box-sizing:border-box}
  .wall{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px;margin:12px 0}
  .tile{border:1px solid;border-left-width:4px;padding:8px 12px}
  .tile b{display:block;font-size:12px;line-height:1.45}
  .tile i{font-style:normal;font-size:12px;color:#606c65}
  .maprow{display:grid;grid-template-columns:88px 1fr;gap:12px;align-items:center;margin:4px 0}
  .maprow strong{font-size:12px;color:#606c65}
  svg{display:block;margin:8px 0}
  @media print{
    body{font-size:12px}
    .wrap{max-width:none;padding:0}
    h2{break-before:page;margin-top:0}
    h2:first-of-type,#s1{break-before:auto}
    h4,table,tr{break-inside:avoid}
    .toc{display:none}
    a{color:inherit;text-decoration:none}
  }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>${esc(meta.title)}</h1>
    <p class="sub">Whole-Book V2 全书分析报告</p>
    <table>
      ${row("章节 / 字数", `${meta.chapter_count.toLocaleString()} 章 / ${meta.character_count.toLocaleString()} 字`)}
      ${row("作品画像", `${d.type_profile.primary_genre}${d.type_profile.secondary_genres.length ? "（" + d.type_profile.secondary_genres.join("、") + "）" : ""}`)}
      ${row("分析引擎", `${am.provider_name} / ${am.model_name}${am.pipeline_version ? ` · ${am.pipeline_version}` : ""}`)}
      ${row("结果来源", `${am.result_origin && !saidNothing(am.result_origin) ? am.result_origin + " · " : ""}run ${am.run_id} · 真实调用 ${am.real_provider_calls} 次`)}
      ${row("数据版本", `${d.schema_version} · snapshot ${meta.snapshot_id} · ${meta.revision_hash.slice(0, 12)}`)}
      ${row("导出时间", generatedAt.toLocaleString("zh-CN"))}
    </table>
    <nav class="toc">${toc.map(([id, label]) => `<a href="#${id}">${esc(label)}</a>`).join("")}</nav>
    <p class="metae">本文件为自包含单文件报告：正文之外，完整原始数据以 JSON 形式内嵌在文件末尾的
      <code>&lt;script id="raw-data"&gt;</code> 块中，可直接提取做机器对账。打印本页即可得到 PDF 版。</p>
  </header>
  ${bodySections.map(([, , html]) => html).join("")}
  ${sectionEvidence(d)}
</div>
<script id="raw-data" type="application/json">${raw}</script>
</body>
</html>`;
}

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

/** Trigger a browser download of the report. Kept apart from the builder so tests can
 *  exercise the pure part without a DOM. */
export function downloadReport(d: WholeBookAnalysisV2): void {
  triggerDownload(new Blob([buildReportHtml(d)], { type: "text/html;charset=utf-8" }), reportFileName(d));
}

/** PDF export is the Pro tier. The error carries what the notice UI needs — the message
 *  and the 爱发电 purchase URL — so the view layer never parses HTTP bodies. */
export class VipRequiredError extends Error {
  readonly afdianUrl: string;
  constructor(message: string, afdianUrl: string) {
    super(message);
    this.name = "VipRequiredError";
    this.afdianUrl = afdianUrl;
  }
}

/** PDF via the sidecar, which prints the same HTML through a headless Chromium — a real
 *  .pdf file, vector text, charts included. Throws VipRequiredError when the licence gate
 *  refuses, and a plain Error for operational failures the caller may fall back from. */
export async function downloadReportPdf(d: WholeBookAnalysisV2): Promise<void> {
  const { getApiBase } = await import("../../services/apiClient");
  const res = await fetch(
    `${getApiBase()}/api/v1/whole-book-runs/${d.analysis_metadata.run_id}/v2/export-pdf`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // The printed report is a different document from the HTML export, not a smaller copy
      // of it: that one is the audit surface and holds everything, this one is what an author
      // marks up, and it is capped at twenty pages. See printExport.ts.
      body: JSON.stringify({ html: buildPrintHtml(d) }),
    },
  );
  if (!res.ok) {
    let message = `PDF 导出失败（${res.status}）`;
    let detail: { error_code?: string; message?: string; details?: { afdian_product_url?: string } } | null = null;
    try {
      const body = await res.json();
      // The app's error middleware flattens HTTPException detail to the top level;
      // a bare FastAPI (tests, other deployments) keeps the `detail` wrapper.
      detail = body?.detail ?? body ?? null;
      message = detail?.message || message;
    } catch {
      /* keep the status-based message */
    }
    if (res.status === 403 && detail?.error_code === "PDF_REQUIRES_VIP") {
      throw new VipRequiredError(message, detail.details?.afdian_product_url ?? "");
    }
    throw new Error(message);
  }
  triggerDownload(await res.blob(), reportFileName(d).replace(/\.html$/, ".pdf"));
}
