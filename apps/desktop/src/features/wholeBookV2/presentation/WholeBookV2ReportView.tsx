import { Fragment, useEffect, useMemo, useState, type ReactNode } from "react";
import type { JourneyAxis, JourneyResult, StageLedger, WholeBookAnalysisV2 } from "../contracts";
import { needsReanalysisWarning } from "../adapter";
import {
  MODULE_DESCRIPTIONS,
  modulesForDocument,
  type ModuleKey,
} from "./modules";
import {
  PACING_SERIES,
  PACING_SCALE_NOTE,
  HEATMAP_DIMS,
  STORYLINE_STATUS,
  JOURNEY_TAB,
  ROLE_LABEL,
  SUSPENSE_BEATS,
  DIMENSION_LABELS,
  CATEGORY_ROW,
} from "./labels";
import { downloadReport, downloadReportPdf, VipRequiredError } from "../reportExport";
import "../../wholeBookV2Mock/wholeBookV2Mock.css";

export type WholeBookV2ReportViewProps = {
  data: WholeBookAnalysisV2;
  activeModule: ModuleKey;
  onModuleChange: (m: ModuleKey) => void;
  mode: "formal" | "mock";
  bookId?: number;
  /** @deprecated use onReanalyzeClick */
  onReanalyze?: () => void;
  onReanalyzeClick?: () => void;
  showReanalyzeButton?: boolean;
  analysisStatusLabel?: string;
  headerBanner?: ReactNode;
  headerExtra?: ReactNode;
};

/** Three curves, told apart twice over: by hue-and-lightness, and by stroke pattern.
 *
 *  The old six were all desaturated mid-tones — ten of the fifteen pairs came out under a 1.5
 *  contrast ratio and the worst, 阅读动力 against 钩子密度, was 1.02, which is the same colour.
 *  Those two also happened to be the pair that moved together, so the two hardest lines to tell
 *  apart were also the two hardest to tell apart. Worst pair here is 1.39, and the dash pattern
 *  settles it regardless — which is also what makes the chart readable without colour vision. */
const PACING_COLORS = ["#14503c", "#d1793a", "#6b74a8"];
const PACING_DASHES = ["", "7 4", "2 4"];

function pct(chapter: number, total: number): string {
  return `${(chapter / Math.max(1, total)) * 100}%`;
}

function Evidence({ ids }: { ids: readonly string[] }) {
  if (!ids.length) return null;
  return (
    <div className="wb2-evidence">
      <b>证据</b>
      {ids.map((id) => (
        <code key={id}>{id}</code>
      ))}
    </div>
  );
}

function RangeTrack({
  range,
  total,
  label,
}: {
  range: [number, number];
  total: number;
  label?: string;
}) {
  const width = ((range[1] - range[0] + 1) / Math.max(1, total)) * 100;
  return (
    <div className="wb2-range">
      <i style={{ left: pct(range[0], total), width: `${width}%` }} />
      {label && <span>{label}</span>}
    </div>
  );
}

/** Which questions the 故事核心 block asks, and where each answer's history lives.
 *
 *  The page used to state the answer in one block and its evolution in another, a screen
 *  apart — so both looked thin and the reader had to hold one half in their head. */
const CORE_QUESTIONS = (ov: WholeBookAnalysisV2["overview"]) =>
  [
    { key: "主角", answer: `${ov.protagonist}｜${ov.initial_state}`, history: [] as string[] },
    { key: "核心目标", answer: ov.core_goal, history: ov.goal_evolution },
    { key: "核心冲突", answer: ov.core_conflict, history: ov.conflict_evolution },
    { key: "核心悬念", answer: ov.core_question, history: ov.major_suspense },
    { key: "最终高潮", answer: ov.final_climax, history: [] as string[] },
  ].filter((row) => row.answer);

/** 总览 — four blocks.
 *
 *  It was nine, holding five distinct facts: the core goal was stated in 故事核心 and again in
 *  核心目标演变; the climax, the核心悬念 and the ending each appeared twice; the skeleton was
 *  drawn once as a timeline and once as a list; and the one-sentence story was printed three
 *  times. The page read as long because it repeated, and each block read as thin because it
 *  held a fragment. Nothing is dropped here — each fact is simply said once.
 */
function OverviewModule({ data }: { data: WholeBookAnalysisV2 }) {
  const tp = data.type_profile;
  const ov = data.overview;
  const stages = data.story.structure_stages;

  return (
    <>
      <section className="wb2-soft-section wb2-work-profile is-tight">
        <div className="wb2-block-title">
          <small>作品画像</small>
          <h2>这是一部怎样的小说？</h2>
          <p>{ov.one_sentence_story}</p>
        </div>
        <div className="wb2-profile-grid">
          <div>
            <small>主类型</small>
            <strong>{tp.primary_genre || "—"}</strong>
          </div>
          <div>
            <small>副类型</small>
            <strong>{tp.secondary_genres.join(" · ") || "—"}</strong>
          </div>
          <div>
            <small>核心叙事驱动力</small>
            <strong>{tp.narrative_drivers.join(" · ") || "—"}</strong>
          </div>
          <div>
            <small>重点分析方向</small>
            <ul>
              {tp.analysis_focus.map((x) => (
                <li key={x}>{x}</li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="wb2-soft-section is-core">
        <div className="wb2-block-title">
          <small>故事核心</small>
          <h2>五个问题的答案</h2>
          <p>每个答案下面折着它一路是怎么变过来的。</p>
        </div>
        <div className="wb2-qa">
          {CORE_QUESTIONS(ov).map((row) =>
            row.history.length ? (
              <div key={row.key}>
                <details>
                  <summary>
                    <dt>{row.key}</dt>
                    <div className="wb2-qa-answer">{row.answer}</div>
                    <span className="wb2-qa-more">演变 {row.history.length} 步 ▾</span>
                  </summary>
                  <ul className="wb2-qa-history">
                    {row.history.map((x, i) => (
                      <li key={`${x}-${i}`}>{x}</li>
                    ))}
                  </ul>
                </details>
              </div>
            ) : (
              /* A question with nothing to unfold stays a plain row: an affordance that does
                 nothing is worse than no affordance. */
              <div key={row.key}>
                <div className="wb2-qa-row">
                  <dt>{row.key}</dt>
                  <div className="wb2-qa-answer">{row.answer}</div>
                </div>
              </div>
            ),
          )}
        </div>
      </section>

      <section className="wb2-soft-section is-tight">
        <div className="wb2-block-title">
          <small>全书脉络</small>
          <h2>这本书是怎么走下来的</h2>
        </div>
        <ol className="wb2-skeleton">
          {ov.story_skeleton.map((x, i) => (
            <li key={`${x}-${i}`}>{x}</li>
          ))}
        </ol>
        {stages.length > 0 && (
          <div className="wb2-stage-lines">
            {stages.map((s) => (
              <article key={s.stage_id}>
                <h3>{s.title}</h3>
                <span>
                  第 {s.chapter_start}–{s.chapter_end} 章
                </span>
                <p>{s.summary}</p>
              </article>
            ))}
          </div>
        )}
        {ov.major_storylines.length > 0 && (
          <ol className="wb2-skeleton wb2-skeleton-lines">
            {ov.major_storylines.map((x, i) => (
              <li key={`${x}-${i}`}>{x}</li>
            ))}
          </ol>
        )}
        {stages.length > 0 && stages.length < 3 && (
          /* A timeline through one point is not a line. The old nine-column grid left eight
             columns of white space here, which reads as a rendering fault rather than as
             "this book resolves into one stage". */
          <p className="wb2-why-empty">
            <b>没有画时间线。</b>
            这本书解析出 {stages.length} 个结构阶段，阶段数达到 3 个以上时时间线才会出现。
          </p>
        )}
      </section>

      <section className="wb2-soft-section wb2-overview-rich">
        <div className="wb2-block-title">
          <small>落点</small>
          <h2>这本书最后停在哪</h2>
        </div>
        {ov.final_climax && <p className="wb2-climax">{ov.final_climax}</p>}
        <p className="wb2-full-summary">{ov.full_summary}</p>
        <div className="wb2-compare">
          <div>
            <small>主角起点</small>
            <strong>{ov.initial_state}</strong>
          </div>
          <i>→</i>
          <div>
            <small>主角终点</small>
            <strong>{ov.final_state}</strong>
          </div>
        </div>
        <div className="wb2-overview-columns wb2-ending">
          <div>
            <h3>已经解决的</h3>
            <ul className="wb2-resolution-list">
              {ov.ending_resolution.map((x) => (
                <li key={x}>{x}</li>
              ))}
            </ul>
          </div>
          <div>
            <h3>留下的问题</h3>
            <ul className="wb2-resolution-list is-open">
              {ov.ending_open_questions.map((x) => (
                <li key={x}>{x}</li>
              ))}
            </ul>
          </div>
        </div>
      </section>
    </>
  );
}


/**  故事 —— 一页四段，没有内层页签。
 *
 *  It was three tabs holding eight facts: one structure stage, five storylines, two causal
 *  links. Three clicks to read what fits on one screen — and the outer module bar is already
 *  a set of seven tabs, so a second tier of tabs buries content rather than organising it.
 *
 *  The fourth section is new. The engine has been computing an 11-event chronology with two
 *  evidence ids apiece since v2.0, and the page's own description promised 时间线, but nothing
 *  ever rendered it.
 */
function StoryModule({ data }: { data: WholeBookAnalysisV2 }) {
  const total = data.book_metadata.chapter_count;
  const story = data.story;
  const chrono = story.chronology;
  // Told out of order is a fact about the book, not a rendering detail: if every event's
  // position in the story matches its position in the telling, there is no flashback to point at.
  const reordered = chrono.filter((c) => c.story_order !== c.narrative_order).length;
  const openFacts = story.structure_stages.length <= 4;

  return (
    <>
      <section className="wb2-soft-section is-tight">
        <div className="wb2-block-title">
          <small>结构阶段</small>
          <h2>这本书分成几段</h2>
        </div>
        <div className="wb2-stages">
          {story.structure_stages.map((s, i) => (
            <article key={s.stage_id}>
              <div className="wb2-stage-head">
                <b>{String(i + 1).padStart(2, "0")}</b>
                <h3>{s.title}</h3>
                <span>
                  第 {s.chapter_start}–{s.chapter_end} 章
                </span>
              </div>
              <RangeTrack range={[s.chapter_start, s.chapter_end]} total={total} />
              <p>{s.summary}</p>
              {/* Every stage's title, range and summary always show; only the four detail
                  facts fold, and only once there are enough stages that leaving them open
                  turns the page into a 2400px scroll. A book that resolves into two or
                  three stages shows everything at once. */}
              <details open={openFacts}>
                <summary>目标 · 冲突 · 选择 · 代价</summary>
                <dl className="wb2-stage-facts">
                  <div>
                    <dt>阶段目标</dt>
                    <dd>{s.stage_goal || "—"}</dd>
                  </div>
                  <div>
                    <dt>核心冲突</dt>
                    <dd>{s.core_conflict || "—"}</dd>
                  </div>
                  <div>
                    <dt>重大选择</dt>
                    <dd>{s.major_choice || "—"}</dd>
                  </div>
                  <div>
                    <dt>付出 / 获得</dt>
                    <dd>
                      {s.cost_paid.join("、") || "—"}
                      <i> → </i>
                      {s.gain_received.join("、") || "—"}
                    </dd>
                  </div>
                </dl>
                <Evidence ids={s.evidence} />
              </details>
            </article>
          ))}
        </div>
      </section>

      <section className="wb2-soft-section is-core">
        <div className="wb2-block-title">
          <small>主线与支线</small>
          <h2>几条线，各自走到哪</h2>
          <p>条的长度是它覆盖的章节；实心是已经收束的，空心是还开着的。</p>
        </div>
        <div className="wb2-gantt">
          {story.storylines.map((s) => {
            const done = s.status === "resolved";
            return (
              <Fragment key={s.storyline_id}>
                <div className="wb2-gantt-name">
                  <span className={s.type === "main" ? "wb2-tag" : "wb2-tag is-sub"}>
                    {s.type === "main" ? "主线" : "支线"}
                  </span>
                  <b>{s.name}</b>
                </div>
                <div className={done ? "wb2-gantt-track is-done" : "wb2-gantt-track is-open"}>
                  <RangeTrack range={[s.chapter_start, s.chapter_end]} total={total} />
                </div>
                <div className={done ? "wb2-gantt-state is-done" : "wb2-gantt-state is-open"}>
                  <b>{STORYLINE_STATUS[s.status] ?? s.status}</b>
                  <span>
                    第 {s.chapter_start}–{s.chapter_end} 章
                  </span>
                </div>
              </Fragment>
            );
          })}
        </div>
        <div className="wb2-gantt-legend">
          <span>
            <i className="is-done" />
            已收束
          </span>
          <span>
            <i className="is-open" />
            未收束
          </span>
        </div>
      </section>

      <section className="wb2-soft-section is-tight">
        <div className="wb2-block-title">
          <small>因果链</small>
          <h2>哪件事导致了哪件事</h2>
        </div>
        <ol className="wb2-causal">
          {story.causal_chain.map((x, i) => {
            const [cause, effect] = x.split("→");
            return (
              <li key={`${i}-${x}`}>
                <b>{String(i + 1).padStart(2, "0")}</b>
                <span className="wb2-causal-cause">{cause.trim()}</span>
                <i className="wb2-causal-arrow">→</i>
                <span className="wb2-causal-effect">{effect?.trim() ?? ""}</span>
              </li>
            );
          })}
        </ol>
      </section>

      {chrono.length > 0 && (
        <section className="wb2-soft-section is-tight">
          <div className="wb2-block-title">
            <small>时间线</small>
            <h2>按章顺序，发生了什么</h2>
          </div>
          <div className="wb2-chrono">
            {chrono.map((c) => (
              <div key={c.event_id}>
                <span className="wb2-chrono-ch">第 {c.chapter} 章</span>
                <span className="wb2-chrono-ev">{c.description}</span>
                <Evidence ids={c.evidence} />
              </div>
            ))}
          </div>
          <p className={reordered > 0 ? "wb2-chrono-note is-reordered" : "wb2-chrono-note"}>
            {reordered > 0 ? (
              <>
                <b>有 {reordered} 处倒叙。</b>这些事件在书里被讲述的顺序，和它们实际发生的顺序不一致。
              </>
            ) : (
              <>
                <b>全书顺叙。</b>{chrono.length} 个事件被讲述的顺序，和它们发生的顺序完全一致，没有倒叙或插叙。
              </>
            )}
          </p>
        </section>
      )}
    </>
  );
}


/** The protagonist journey, drawn on whatever axis the engine chose.
 *
 *  This replaced a staircase whose height was the stage index — which drew the same rising
 *  line for every book, because the height *was* the ordinal. Every axis here carries a
 *  quantity that can fall, and the fall is most of the information: the same engine measured
 *  1 downward move across 806 chapters of a mystery and 130 across 1299 of a progression
 *  novel. Nothing in this component decides the axis; it renders `journey.axis`.
 */
const JOURNEY_KIND_LABELS: Record<string, string> = {
  partial: "只揭一半",
  reveal: "揭示",
  resolve: "给出答案",
  close: "收束",
  twist: "反转 · 推翻先前认知",
  misdirect: "误导",
  promote: "晋升",
  gain: "获得",
  faceslap: "打脸压制",
  setback: "受挫",
  demote: "跌落",
};

function JourneyChart({ journey, chapterCount }: { journey: JourneyResult; chapterCount: number }) {
  const width = 1000;
  const total = Math.max(1, chapterCount);
  const x = (chapter: number) => 60 + (Math.min(chapter, total) / total) * (width - 74);
  // Which reading is expanded below the chart. The note each point carries — what was
  // revealed, what was overturned — was previously only in a hover <title>, which is content
  // the reader can never see all of and touch devices can never see at all.
  const [at, setAt] = useState<number | null>(null);

  if (journey.axis === "screen_time") {
    const bins = journey.bins || journey.bands[0]?.share.length || 0;
    const top = 12;
    const height = 240;
    let base = new Array(bins).fill(0);
    const bands = journey.bands.map((band, index) => {
      const upper = band.share.map((v, i) => base[i] + v);
      const points =
        upper.map((v, i) => `${x(((i + 0.5) * total) / bins).toFixed(1)},${(height - v * (height - top)).toFixed(1)}`).join(" ") +
        " " +
        base
          .map((v, i) => `${x(((bins - 0.5 - i) * total) / bins).toFixed(1)},${(height - base[bins - 1 - i] * (height - top)).toFixed(1)}`)
          .join(" ");
      base = upper;
      return { name: band.name, points, index, band };
    });
    return (
      <div className="wb2-journey">
        <svg viewBox={`0 0 ${width} ${height + 8}`} role="img" aria-label="戏份分布">
          {bands.map((b) => (
            <polygon key={b.name} points={b.points} className={`wb2-band wb2-band-${b.index % 8}`}>
              <title>{`${b.name}　第 ${b.band.first_chapter}–${b.band.last_chapter} 章，出现 ${b.band.chapters} 章`}</title>
            </polygon>
          ))}
        </svg>
        <ul className="wb2-journey-legend">
          {journey.bands.map((band, index) => (
            <li key={band.name}>
              <i className={`wb2-band-${index % 8}`} />
              {band.name}
              <small>{band.chapters} 章</small>
            </li>
          ))}
        </ul>
        {journey.caveat && <p className="wb2-journey-caveat">{journey.caveat}</p>}
      </div>
    );
  }

  const values = journey.points.map((p) => p.value);
  const lo = Math.min(...values, 0);
  const hi = Math.max(...values, lo + 1);
  const top = 20;
  const height = 260;
  const y = (v: number) => height - ((v - lo) / (hi - lo)) * (height - top);
  const connected = journey.points.filter((p) => p.load_bearing);
  // A ladder reading holds until the book states a new one, so the line steps rather than
  // sloping. A cognition curve is cumulative and slopes between its own points.
  const path =
    journey.axis === "ladder"
      ? connected
          .map((p, i) =>
            i === 0
              ? `M ${x(p.chapter).toFixed(1)} ${y(p.value).toFixed(1)}`
              : `L ${x(p.chapter).toFixed(1)} ${y(connected[i - 1].value).toFixed(1)} L ${x(p.chapter).toFixed(1)} ${y(p.value).toFixed(1)}`,
          )
          .join(" ")
      : connected.map((p, i) => `${i ? "L" : "M"} ${x(p.chapter).toFixed(1)} ${y(p.value).toFixed(1)}`).join(" ");

  return (
    <div className="wb2-journey">
      <svg viewBox={`0 0 ${width} ${height + 16}`} role="img" aria-label={journey.axis_label}>
        {journey.ticks.map((tick, i) => {
          const at = journey.axis === "ladder" ? i + 1 : i === 0 ? lo : hi;
          return (
            <g key={tick}>
              <line x1={60} y1={y(at)} x2={width - 14} y2={y(at)} className="wb2-journey-rule" />
              <text x={54} y={y(at) + 4} textAnchor="end" className="wb2-journey-tick">
                {tick}
              </text>
            </g>
          );
        })}
        {path && <path d={path} className="wb2-journey-line" />}
        {journey.points.map((p, i) => (
          <circle
            key={`${p.chapter}-${i}`}
            cx={x(p.chapter)}
            cy={y(p.value)}
            r={at === i ? 6 : p.load_bearing ? 4.2 : 2.6}
            className={`wb2-journey-dot${DOWN_KINDS.has(p.kind) ? " down" : ""}${p.load_bearing ? " lead" : ""}${at === i ? " selected" : ""}`}
            onClick={() => setAt(at === i ? null : i)}
          >
            <title>{`第 ${p.chapter} 章　${p.who || ""}${p.label ? " " + p.label : ""}　${p.kind}　${p.note}`}</title>
          </circle>
        ))}
      </svg>
      {at !== null && journey.points[at] && (
        <div className="wb2-journey-point-detail">
          <b className="wb2-journey-point-ch">第 {journey.points[at].chapter} 章</b>
          <span className={`wb2-journey-point-kind${DOWN_KINDS.has(journey.points[at].kind) ? " down" : ""}`}>
            {JOURNEY_KIND_LABELS[journey.points[at].kind] ?? journey.points[at].kind}
          </span>
          {journey.points[at].who && <span>{journey.points[at].who}</span>}
          {journey.points[at].label && <span>{journey.points[at].label}</span>}
          <p>{journey.points[at].note || "（这一处没有记录说明文字）"}</p>
        </div>
      )}
      <p className="wb2-journey-axis-note">
        纵轴＝{journey.axis_label}
        {journey.lead && `　主线＝${journey.lead}`}　共 {journey.points.length} 个读数，其中下跌{" "}
        {journey.points.filter((p) => DOWN_KINDS.has(p.kind)).length} 次　·　点任意一个点看它的内容
      </p>
      {journey.caveat && <p className="wb2-journey-caveat">{journey.caveat}</p>}
      <JourneyTurnList
        points={journey.points}
        active={at}
        onPick={(i) => setAt(at === i ? null : i)}
      />
    </div>
  );
}

/** The chart's down-moves and answers, as prose the reader can scan without hunting dots.
 *
 *  A mystery's reversals *are* the analysis — burying them behind 2.6px hover targets keeps
 *  the shape visible but the content unread. Only the information-heavy kinds are listed;
 *  the 31 partial reveals stay as dots, or the list would drown the seven moments that
 *  reorganise the book.
 */
function JourneyTurnList({
  points,
  active,
  onPick,
}: {
  points: JourneyResult["points"];
  active: number | null;
  onPick: (index: number) => void;
}) {
  const rows = points
    .map((p, i) => ({ ...p, index: i }))
    .filter((p) => DOWN_KINDS.has(p.kind) || p.kind === "resolve" || p.kind === "demote");
  if (!rows.length) return null;
  return (
    <ol className="wb2-journey-turns">
      {rows.map((p) => (
        <li key={p.index}>
          <button
            className={active === p.index ? "active" : ""}
            onClick={() => onPick(p.index)}
            aria-pressed={active === p.index}
          >
            <b>第 {p.chapter} 章</b>
            <i className={DOWN_KINDS.has(p.kind) ? "down" : ""}>
              {JOURNEY_KIND_LABELS[p.kind] ?? p.kind}
            </i>
            <span>{p.note || "（无说明）"}</span>
          </button>
        </li>
      ))}
    </ol>
  );
}

const DOWN_KINDS = new Set(["setback", "demote", "twist", "misdirect"]);

/** Per-stage 遇见谁 / 做了什么 / 得到 / 失去.
 *
 *  The chart answers how far the protagonist got; this answers what it cost him, and the two
 *  are different questions. It reads the engine's filtered ledger rather than
 *  `ArcStage.cost_paid` / `gain_received`, which carry the *options'* projected trade-offs —
 *  62% of those "costs" on a measured book are hypotheses like 「可能被识破」, so a reader
 *  scanning that column is reading risks that were considered, not prices that were paid.
 */
/** The card frame every block on this page lives in: a numbered title bar, a count at the
 *  right edge, the content indented below. Three ranks the eye can hold — tab band, card
 *  bar, content row — instead of sibling grey boxes floating unlabelled in the section. */
/** The 拆文 reading. Its data was complete on the very first real run — four beats, ten
 *  moments with the line quoted, sixty-one chapter hooks, eight techniques, eleven cast
 *  entries — and there was no module to put it in, so the reader saw 全书总览 and 综合诊断
 *  standing empty instead. */
function StoryBreakdownModule({ data }: { data: WholeBookAnalysisV2 }) {
  const [tab, setTab] = useState("起承转合");
  const b = data.story_breakdown;
  if (!b) return null;
  const moments = [...(b.standout_moments || [])].sort(
    (x, y) => (x.rank ?? 999) - (y.rank ?? 999),
  );
  const tabs = ["起承转合", "打动人的瞬间", "每章留下的问题", "可复用的手法", "配角功能"];
  return (
    <>
      <div className="wb2-tabs">
        {tabs.map((t) => (
          <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>

      {tab === "起承转合" && (
        <div className="wb2-sub-stack">
          <SubCard n={1} title="四个部分" meta={`${b.four_beats?.length ?? 0} 段`}>
            <table className="wb2-table">
              <thead>
                <tr>
                  <th>部分</th>
                  <th>章节</th>
                  <th>这一段在做什么</th>
                </tr>
              </thead>
              <tbody>
                {(b.four_beats || []).map((x, i) => (
                  <tr key={i}>
                    <td>
                      <b>{x.beat}</b>
                    </td>
                    <td className="wb2-num">
                      第 {x.chapter_start}–{x.chapter_end} 章
                    </td>
                    <td>
                      <b>{x.title}</b>
                      <p>{x.summary}</p>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </SubCard>
        </div>
      )}

      {tab === "打动人的瞬间" && (
        <div className="wb2-sub-stack">
          <SubCard
            n={1}
            title="选出来的瞬间"
            meta={`${moments.length} 处 · 按打动人的程度排序`}
          >
            {b.moment_count_rationale && (
              <p className="wb2-note">{b.moment_count_rationale}</p>
            )}
            {moments.map((m, i) => (
              <div className="wb2-moment" key={i}>
                <header>
                  <i>{m.rank ?? i + 1}</i>
                  <b>{m.title}</b>
                  <span>第 {m.chapter} 章</span>
                </header>
                {m.quote && <blockquote>{m.quote}</blockquote>}
                <p>{m.why_it_lands}</p>
              </div>
            ))}
          </SubCard>
        </div>
      )}

      {tab === "每章留下的问题" && (
        <div className="wb2-sub-stack">
          <SubCard
            n={1}
            title="章末钩子"
            meta={`${b.chapter_hooks?.length ?? 0} 章留下了问题`}
          >
            <table className="wb2-table">
              <thead>
                <tr>
                  <th>章</th>
                  <th>这一章结尾留给读者的问题</th>
                </tr>
              </thead>
              <tbody>
                {(b.chapter_hooks || []).map((h, i) => (
                  <tr key={i}>
                    <td className="wb2-num">第 {h.chapter} 章</td>
                    <td>{h.question}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </SubCard>
        </div>
      )}

      {tab === "可复用的手法" && (
        <div className="wb2-sub-stack">
          {(b.reusable_techniques || []).map((t, i) => (
            <SubCard n={i + 1} title={t.name} key={i}>
              <p>
                <b>是什么</b>
                {t.what_it_is}
              </p>
              <p>
                <b>为什么有效</b>
                {t.why_it_works}
              </p>
              <p>
                <b>能用到哪</b>
                {t.transfers_to}
              </p>
            </SubCard>
          ))}
        </div>
      )}

      {tab === "配角功能" && (
        <div className="wb2-sub-stack">
          <SubCard n={1} title="每个配角在担什么" meta={`${b.supporting_cast?.length ?? 0} 人`}>
            {b.cast_note && <p className="wb2-note">{b.cast_note}</p>}
            <table className="wb2-table">
              <thead>
                <tr>
                  <th>人物</th>
                  <th>承担的功能</th>
                </tr>
              </thead>
              <tbody>
                {(b.supporting_cast || []).map((c, i) => (
                  <tr key={i}>
                    <td>
                      <b>{c.name}</b>
                    </td>
                    <td>
                      {c.function}
                      {c.stays_in_lane ? <p>{c.stays_in_lane}</p> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </SubCard>
        </div>
      )}
    </>
  );
}

function SubCard({
  n,
  title,
  meta,
  children,
}: {
  n: number;
  title: string;
  meta?: string;
  children: ReactNode;
}) {
  return (
    <div className="wb2-sub">
      <header>
        <i>{n}</i>
        <h3>{title}</h3>
        {meta && <span>{meta}</span>}
      </header>
      <div className="wb2-sub-body">{children}</div>
    </div>
  );
}

/** 行动台账 —— 一列时间线，一列侧栏。
 *
 *  Four equal columns holding 1/8/1/1 items drew three tall empty walls beside one full
 *  column. The deeds are the record — they get the wide column; who was met, what was
 *  gained and lost are summaries, and stack beside it at whatever height they need.
 */
function StageLedgerTable({ ledger }: { ledger: StageLedger[] }) {
  const [at, setAt] = useState(0);
  const stage = ledger[Math.min(at, ledger.length - 1)];
  if (!stage) return null;

  return (
    <div className="wb2-ledger">
      {ledger.length > 1 && (
        <div className="wb2-ledger-stages">
          {ledger.map((row, i) => (
            <button
              key={`${row.stage_name}-${i}`}
              className={i === at ? "active" : ""}
              onClick={() => setAt(i)}
              aria-pressed={i === at}
            >
              第 {i + 1} 程　{row.stage_name}
            </button>
          ))}
        </div>
      )}
      <p className="wb2-ledger-range">
        第 {stage.chapter_start}–{stage.chapter_end} 章
      </p>
      <div className="wb2-ledger-split">
        <div className="wb2-ledger-main">
          {/* Counts are the full tally; the rows are the load-bearing few the engine kept. */}
          <h4>做了什么 · {stage.did_total}</h4>
          <ol className="wb2-evlist">
            {stage.did.length ? (
              stage.did.map((e, i) => (
                <li key={`${e.chapter}-${i}`}>
                  <span className="wb2-evlist-ch">第 {e.chapter} 章</span>
                  <span>{e.text}</span>
                </li>
              ))
            ) : (
              <li className="none">这一程没有记录到行动</li>
            )}
          </ol>
        </div>
        <div className="wb2-ledger-side">
          <div className="wb2-ledger-who">
            <h4>遇见谁 · {stage.met_total}</h4>
            {stage.met.length ? (
              stage.met.map((m) => (
                <p key={`${m.chapter}-${m.name}`}>
                  <b>{m.name}</b>
                  <i>
                    第 {m.chapter} 章 · {m.relation || "初次出现"}
                  </i>
                </p>
              ))
            ) : (
              <p className="none">这一程没有新的人</p>
            )}
          </div>
          <div className="wb2-ledger-g">
            <h4>得到 · {stage.gained_total}</h4>
            {stage.gained.length ? stage.gained.map((g) => <p key={g}>{g}</p>) : <p className="none">—</p>}
          </div>
          <div className="wb2-ledger-l">
            <h4>失去 · {stage.lost_total}</h4>
            {stage.lost.length ? (
              stage.lost.map((g) => <p key={g}>{g}</p>)
            ) : (
              <p className="none">这一程没有代价</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/** 四轨成长 · 与主时间线对齐。
 *
 *  It claimed alignment it did not have: the header printed one column per *stage* while the
 *  rows printed one cell per *track point*, so a book with one stage and three points drew a
 *  one-column header over three-cell rows. The columns are the chapters that actually carry a
 *  point, and every cell sits under its own chapter — which is what "对齐" has to mean here.
 *
 *  Cell text was also cut at `slice(0, 8)`, which severed 「克制情感 → 情感流露」 mid-phrase.
 *  A cell that cannot hold its sentence wraps; it does not lie about it.
 */
function GrowthTracks({
  protagonist,
}: {
  protagonist: WholeBookAnalysisV2["characters"]["protagonist"];
}) {
  const rows = [
    { name: "外在身份 / 社会位置", track: protagonist.external_status_track },
    { name: "能力与资源", track: protagonist.ability_track },
    { name: "内在信念", track: protagonist.internal_belief_track },
    { name: "关系网络", track: protagonist.relationship_track },
  ].filter((t) => t.track.length > 0);

  const chapters = [...new Set(rows.flatMap((r) => r.track.map((v) => v.chapter)))].sort(
    (a, b) => a - b,
  );
  if (!chapters.length) return null;
  const silent = ["外在身份 / 社会位置", "能力与资源", "内在信念", "关系网络"].filter(
    (n) => !rows.some((r) => r.name === n),
  );

  return (
    <SubCard n={5} title="四轨成长" meta={`${rows.length} 条轨道动过 · ${chapters.length} 个章节`}>
      <div
        className="wb2-tracks-grid"
        style={{ gridTemplateColumns: `minmax(120px,auto) repeat(${chapters.length}, 1fr)` }}
      >
        <b className="wb2-tracks-corner" />
        {chapters.map((c) => (
          <b key={`h-${c}`} className="wb2-tracks-ch">
            第 {c} 章
          </b>
        ))}
        {rows.map((r) => (
          <Fragment key={r.name}>
            <strong>{r.name}</strong>
            {chapters.map((c) => {
              const hit = r.track.find((v) => v.chapter === c);
              return (
                <span key={`${r.name}-${c}`} className={hit ? "is-hit" : ""}>
                  {hit?.state ?? ""}
                </span>
              );
            })}
          </Fragment>
        ))}
      </div>
      {silent.length > 0 && (
        <p className="wb2-quiet">
          <b>{silent.join("、")}这{silent.length === 1 ? "条" : "几条"}轨道全书没有记录到变化</b>
          ，所以不占行。
        </p>
      )}
    </SubCard>
  );
}


/** 人物档案。
 *
 *  This card used to print a name, a role and a row of evidence ids and stop — not because
 *  the analysis was thin but because contracts.ts declared five of the seventeen fields the
 *  engine returns. 慕秋阳's record carries eight key events, a choice, what it cost and what
 *  it bought; none of it had a way to reach the page.
 *
 *  Fields the book genuinely has nothing for are dropped rather than drawn as a labelled
 *  blank: a heading over empty space claims the page failed, when the truth is the book
 *  never said.
 */
function CharacterProfile({
  character: c,
}: {
  character: WholeBookAnalysisV2["characters"]["major_characters"][number];
}) {
  const goalMoved = Boolean(c.initial_goal && c.final_goal && c.initial_goal !== c.final_goal);
  const cost = (c.cost_paid ?? []).join("、");
  const gain = (c.gain_received ?? []).join("、");
  // hl marks the two facts that define the character — goal and choice — with a green top
  // edge; the rest keep the neutral edge, so the grid ranks its own contents.
  const facts: Array<{ k: string; v: ReactNode; text: string; hl?: boolean }> = [
    { k: "身份", v: c.identity, text: c.identity ?? "" },
    { k: "与主角的关系", v: c.relationship_to_protagonist, text: c.relationship_to_protagonist ?? "" },
    {
      k: goalMoved ? "目标演变" : "全书目标",
      v: goalMoved ? `${c.initial_goal} → ${c.final_goal}` : c.final_goal,
      text: c.final_goal ?? "",
      hl: true,
    },
    { k: "重大选择", v: c.major_choice, text: c.major_choice ?? "", hl: true },
    {
      k: "付出 / 获得",
      v:
        cost || gain ? (
          <>
            {cost || "—"}
            <i> → </i>
            {gain || "—"}
          </>
        ) : null,
      text: cost + gain,
    },
    { k: "关系变化", v: (c.relationship_changes ?? []).join(" → "), text: (c.relationship_changes ?? []).join("") },
    { k: "结局", v: c.ending, text: c.ending ?? "" },
  ];
  const shown = facts.filter((f) => f.text.trim().length > 0);
  const events = c.key_events ?? [];

  return (
    <div className="wb2-profile">
      <div className="wb2-profile-head">
        <h3>{c.name}</h3>
        <span>{ROLE_LABEL[c.role] ?? c.role}</span>
      </div>
      {shown.length > 0 && (
        <dl className="wb2-profile-facts">
          {shown.map((f) => (
            <div key={f.k} className={f.hl ? "hl" : ""}>
              <dt>{f.k}</dt>
              <dd>{f.v}</dd>
            </div>
          ))}
        </dl>
      )}
      {events.length > 0 && (
        <div className="wb2-profile-events">
          <h4>
            这个人做过的事<span>{events.length}</span>
          </h4>
          <ol className="wb2-evlist">
            {events.map((e, i) => {
              // The engine writes these as 「第N章｜…」; splitting lets the chapter sit in its
              // own column so the eye can run down the numbers instead of hunting them in prose.
              const m = /^(第\s*\d+\s*章)｜(.*)$/.exec(e);
              return (
                <li key={`${i}-${e}`}>
                  <span className="wb2-evlist-ch">{m ? m[1] : ""}</span>
                  <span>{m ? m[2] : e}</span>
                </li>
              );
            })}
          </ol>
        </div>
      )}
      {shown.length === 0 && events.length === 0 && (
        <p className="wb2-why-empty">
          <b>这个人物只有证据，没有档案。</b>引擎为 {c.name} 建立了索引，但没有提取出身份、目标或事件——通常是因为出场集中在少数几章。
        </p>
      )}
      <Evidence ids={c.evidence} />
    </div>
  );
}

function CharactersModule({ data }: { data: WholeBookAnalysisV2 }) {
  const journey = data.journey;
  const journeyAxis: JourneyAxis = journey && journey.axis !== "none" ? journey.axis : "none";
  const journeyTab = JOURNEY_TAB[journeyAxis];
  const [tab, setTab] = useState("人物系统");
  const [selectedCharacter, setSelectedCharacter] = useState(0);
  const [arc, setArc] = useState(0);
  const chars = data.characters;
  const protagonist = chars.protagonist;
  const arcStage = protagonist.stages[arc];
  const major = chars.major_characters[selectedCharacter];

  return (
    <>
      <div className="wb2-tabs">
        {["人物系统", journeyTab, "人物关系"].map((t) => (
          <button className={tab === t ? "active" : ""} onClick={() => setTab(t)} key={t}>
            {t}
          </button>
        ))}
      </div>
      {tab === "人物系统" && (
        <div className="wb2-sub-stack">
          <SubCard n={1} title="全员一览" meta={`${chars.major_characters.length} 人`}>
            <table>
              <thead>
                <tr>
                  <th>人物</th>
                  <th>叙事角色</th>
                  <th>全书变化</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {chars.major_characters.map((c, i) => (
                  <tr
                    className={selectedCharacter === i ? "selected" : ""}
                    onClick={() => setSelectedCharacter(i)}
                    key={c.character_id}
                  >
                    <th>{c.name}</th>
                    <td>{ROLE_LABEL[c.role] ?? c.role}</td>
                    {/* An empty cell reads as a rendering fault. A character whose stated goal
                        is the same at the end as at the start did not fail to be analysed —
                        not changing is the finding. */}
                    <td>{c.character_arc || (c.initial_goal ? "目标全书未变" : "—")}</td>
                    <td>查看档案 →</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </SubCard>
          {major && (
            <SubCard n={2} title="人物档案" meta={`当前：${major.name}`}>
              <CharacterProfile character={major} />
            </SubCard>
          )}
        </div>
      )}
      {tab === journeyTab && (
        <>
          {/* 「慕秋阳 → 慕秋阳｜」 — an arrow to itself followed by a separator with nothing
              after it. When the identity does not move and there is no summary, there is no
              sentence to print. */}
          {(() => {
            const moved = protagonist.initial_identity !== protagonist.final_identity;
            const summary = protagonist.arc_summary || protagonist.core_transformation || "";
            if (!moved && !summary) return null;
            return (
              <p className="wb2-long-summary">
                {moved && (
                  <b>
                    {protagonist.initial_identity} → {protagonist.final_identity}
                  </b>
                )}
                {moved && summary ? "｜" : ""}
                {summary}
              </p>
            );
          })()}
          {journey && journeyAxis !== "none" && (
            <JourneyChart journey={journey} chapterCount={data.book_metadata.chapter_count} />
          )}
          {/* A picker over one item is not a picker — it was one small chip stranded in an
              otherwise empty band, which reads as a chart that failed to draw. */}
          {protagonist.stages.length > 1 && (
            <div className="wb2-arc">
              {protagonist.stages.map((s, i) => (
                <button className={arc === i ? "active" : ""} onClick={() => setArc(i)} key={s.stage_name}>
                  <b>{i + 1}</b>
                  <strong>{s.stage_name}</strong>
                  <small>第 {s.chapter} 章</small>
                </button>
              ))}
            </div>
          )}
          {arcStage && (
            <div className="wb2-sub-stack">
              <SubCard
                n={1}
                title="这一程的起止"
                meta={`${arcStage.stage_name} · 第 ${arcStage.chapter}–${arcStage.chapter_end} 章 · ${arc + 1}/${protagonist.stages.length} 程`}
              >
                <div className="wb2-fromto">
                  <div>
                    <small>起点</small>
                    {arcStage.entry_state || "—"}
                  </div>
                  <i>→</i>
                  <div>
                    <small>终点</small>
                    {arcStage.exit_state || "—"}
                  </div>
                </div>
              </SubCard>

              <SubCard n={2} title="抉择链" meta="想要 → 遭遇 → 选择，以及这一步的代价">
                <div className="wb2-choice-chain">
                  <div>
                    <small>想得到什么</small>
                    <b>{arcStage.goal}</b>
                  </div>
                  <i>→</i>
                  <div>
                    <small>遭遇什么</small>
                    <b>{arcStage.conflict}</b>
                  </div>
                  <i>→</i>
                  <div>
                    <small>做出选择</small>
                    <b>{arcStage.choice}</b>
                  </div>
                </div>
                <div className="wb2-cost-gain">
                  <div>
                    <small>付出 COST</small>
                    <strong>{arcStage.cost_paid.join("、") || "—"}</strong>
                  </div>
                  <div>
                    <small>获得 GAIN</small>
                    <strong>{arcStage.gain_received.join("、") || "—"}</strong>
                  </div>
                </div>
              </SubCard>

              {/* One list of deeds, said once. The same eight events used to appear here
                  three times — in the ledger, under 重大事件, and again in the profile tab. */}
              {journey?.ledger?.length ? (
                <SubCard
                  n={3}
                  title="行动台账"
                  meta={
                    journey.ledger.length > 1
                      ? `${journey.ledger.length} 程`
                      : `做了什么 ${journey.ledger[0].did_total} · 遇见 ${journey.ledger[0].met_total} · 得到 ${journey.ledger[0].gained_total} · 失去 ${journey.ledger[0].lost_total}`
                  }
                >
                  <StageLedgerTable ledger={journey.ledger} />
                </SubCard>
              ) : (
                arcStage.major_events.length > 0 && (
                  <SubCard n={3} title="行动台账" meta={`做了什么 ${arcStage.major_events.length}`}>
                    <ol className="wb2-evlist">
                      {arcStage.major_events.map((x, i) => (
                        <li key={`${i}-${x}`}>
                          <span>{x}</span>
                        </li>
                      ))}
                    </ol>
                  </SubCard>
                )
              )}

              {(() => {
                const tracks: Array<[string, string]> = [
                  ["能力变化", arcStage.ability_change],
                  ["关系变化", arcStage.relationship_change],
                  ["社会位置变化", arcStage.status_change],
                  ["内在信念变化", arcStage.internal_belief_change],
                ];
                const filled = tracks.filter(([, v]) => v.trim().length > 0);
                const blank = tracks.filter(([, v]) => !v.trim().length).map(([k]) => k.replace("变化", ""));
                return (
                  <SubCard
                    n={4}
                    title="这一程带来的变化"
                    meta={`${filled.length} 项有记录${blank.length ? ` · ${blank.length} 项书中未写` : ""}`}
                  >
                    {filled.length > 0 && (
                      <dl className="wb2-changes">
                        {filled.map(([k, v]) => (
                          <div key={k}>
                            <dt>{k}</dt>
                            <dd>{v}</dd>
                          </div>
                        ))}
                      </dl>
                    )}
                    {blank.length > 0 && (
                      <p className="wb2-quiet">
                        <b>
                          {blank.join("、")}
                          {blank.length === 1 ? "这一项" : blank.length === 2 ? "这两项" : "这几项"}
                          没有记录
                        </b>
                        ——引擎没有抽到相应的变化，通常是原文里没有明写。
                      </p>
                    )}
                    {arcStage.next_stage_trigger && (
                      <div className="wb2-nextq">
                        <small>下一阶段触发</small>
                        {arcStage.next_stage_trigger}
                      </div>
                    )}
                    <Evidence ids={arcStage.evidence} />
                  </SubCard>
                );
              })()}

              {(protagonist.ability_track.length > 0 ||
                protagonist.relationship_track.length > 0 ||
                protagonist.external_status_track.length > 0 ||
                protagonist.internal_belief_track.length > 0) && (
                <GrowthTracks protagonist={protagonist} />
              )}
            </div>
          )}
        </>
      )}
      {tab === "人物关系" && (
        <div className="wb2-sub-stack">
          <SubCard
            n={1}
            title="关系网络 + 演变明细"
            meta={`${new Set(chars.relationships.flatMap((r) => [r.person_a, r.person_b])).size} 人 · ${chars.relationships.length} 条关系`}
          >
            <RelationshipGraph relationships={chars.relationships} />
          </SubCard>
        </div>
      )}
    </>
  );
}

/**
 * The cast as a network.
 *
 * As thirty rows of 「X ↔ 邓肯」 the table reads as a ledger and hides the thing worth
 * seeing: eleven of those edges do not touch the protagonist at all — 凡娜–瓦伦丁,
 * 海蒂–莫里斯, 劳伦斯–玛莎 — which is what makes this an ensemble rather than a hub.
 *
 * The layout is radial and derived from the data, not force-simulated. A simulation would
 * settle differently on each render, and a report that draws a different picture every time
 * it is opened cannot be referred to.
 */
function RelationshipGraph({
  relationships,
}: {
  relationships: WholeBookAnalysisV2["characters"]["relationships"];
}) {
  const [picked, setPicked] = useState<string>("");

  const { nodes, positions, lead } = useMemo(() => {
    const degree = new Map<string, number>();
    for (const r of relationships) {
      degree.set(r.person_a, (degree.get(r.person_a) ?? 0) + 1);
      degree.set(r.person_b, (degree.get(r.person_b) ?? 0) + 1);
    }
    const ordered = [...degree.keys()].sort(
      (a, b) => (degree.get(b) ?? 0) - (degree.get(a) ?? 0) || a.localeCompare(b),
    );
    const centre = ordered[0] ?? "";
    const ring = ordered.slice(1);
    const place = new Map<string, [number, number]>([[centre, [320, 230]]]);
    ring.forEach((name, i) => {
      const angle = -Math.PI / 2 + (i * 2 * Math.PI) / ring.length;
      const radius = 118 + (i % 3) * 42;
      place.set(name, [320 + Math.cos(angle) * radius, 230 + Math.sin(angle) * radius]);
    });
    return { nodes: ordered, positions: place, lead: centre };
  }, [relationships]);

  const active = picked || lead;
  const mine = relationships
    .filter((r) => r.person_a === active || r.person_b === active)
    .sort((a, b) => (b.evolution?.length ?? 1) - (a.evolution?.length ?? 1));

  return (
    <div className="wb2-graph-layout">
      <svg className="wb2-relgraph" viewBox="0 0 640 460" role="img" aria-label="人物关系网络图">
        {relationships.map((r, i) => {
          const a = positions.get(r.person_a);
          const b = positions.get(r.person_b);
          if (!a || !b) return null;
          const on = r.person_a === active || r.person_b === active;
          // A relationship that turned three times is a thicker thread than one stated once —
          // the structure view carries the amount of story each edge holds.
          const steps = Math.min(4, r.evolution?.length ?? 1);
          return (
            <line key={i} className={on ? "edge on" : "edge"}
                  strokeWidth={1 + steps * 0.7}
                  x1={a[0].toFixed(1)} y1={a[1].toFixed(1)}
                  x2={b[0].toFixed(1)} y2={b[1].toFixed(1)}>
              <title>{`${r.person_a}–${r.person_b}：${r.relationship_type}`}</title>
            </line>
          );
        })}
        {nodes.map((name) => {
          const [x, y] = positions.get(name) ?? [0, 0];
          const links = relationships.filter((r) => r.person_a === name || r.person_b === name).length;
          const radius = name === lead ? 27 : 8 + Math.min(12, links * 3);
          const classes = ["node", name === lead ? "lead" : "", name === active ? "on" : ""]
            .filter(Boolean).join(" ");
          return (
            <g key={name} className={classes} tabIndex={0} role="button" aria-label={name}
               onClick={() => setPicked(name)}
               onKeyDown={(e) => {
                 if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setPicked(name); }
               }}>
              <circle cx={x.toFixed(1)} cy={y.toFixed(1)} r={radius} />
              <text x={x.toFixed(1)} y={(y + (name === lead ? 4 : radius + 13)).toFixed(1)}>{name}</text>
            </g>
          );
        })}
      </svg>
      <div className="wb2-graph-detail">
        <h3>{active}</h3>
        <small>{mine.length} 条关系，按演变步数排序</small>
        <div className="wb2-rel-list">
          {mine.map((r, i) => {
            const other = r.person_a === active ? r.person_b : r.person_a;
            // The structure view says the thread exists; this says where it went. A
            // relationship that moved shows every turn; one stated once shows that state.
            const steps = r.evolution?.length ? r.evolution : [r.relationship_type];
            return (
              <div className={i === 0 && steps.length > 1 ? "wb2-rel on" : "wb2-rel"} key={i}>
                <div className="wb2-rel-pair">
                  <b>{other}</b>
                  <span>
                    第 {r.chapter_start}–{r.chapter_end} 章 · {steps.length} 步
                  </span>
                </div>
                <div className="wb2-rel-arc">
                  {steps.map((s, j) => (
                    <Fragment key={`${j}-${s}`}>
                      {j > 0 && <i>→</i>}
                      <span>{s}</span>
                    </Fragment>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}


/**
 * One tile per suspense thread, coloured by whether the book ever answers it.
 *
 * The per-thread panel shows one at a time, so comparing forty means forty clicks and the
 * proportion — the thing an author actually wants from this page — is never visible. As a
 * wall of tiles it is the first thing read: 40 questions, 24 closed.
 */
function SuspenseWall({ data }: { data: WholeBookAnalysisV2 }) {
  const [picked, setPicked] = useState(0);
  const threads = data.suspense.lifecycles;
  const chosen = threads[picked];
  const resolved = threads.filter((t) => t.status === "resolved").length;

  return (
    <div className="wb2-sub-stack">
      <SubCard n={1} title="全部悬念" meta={`${threads.length} 条 · ${resolved} 条已回收`}>
        <div className="wb2-wall">
          {threads.map((t, i) => (
            <button
              key={t.suspense_id}
              type="button"
              className="wb2-tile"
              data-resolved={t.status === "resolved" ? "1" : "0"}
              data-picked={picked === i ? "1" : "0"}
              onClick={() => setPicked(i)}
            >
              <u />
              <b>{t.question}</b>
              <i>
                第 {t.chapter_start}–{t.chapter_end} 章 · {t.events.length} 次
              </i>
            </button>
          ))}
        </div>
        <div className="wb2-wall-legend">
          <span><i data-resolved="1" />已回收</span>
          <span><i data-resolved="0" />未回收</span>
        </div>
      </SubCard>
      {chosen && (
        <SubCard
          n={2}
          title="这条悬念的经过"
          meta={`第 ${chosen.chapter_start}–${chosen.chapter_end} 章 · 回访 ${chosen.events.length} 次 · ${chosen.status === "resolved" ? "已回收" : "未回收"}`}
        >
          <h3 className="wb2-wall-q">{chosen.question}</h3>
          {chosen.status === "resolved" ? (
            <p className="wb2-payoff"><small>答案</small>{chosen.payoff}</p>
          ) : (
            // Said plainly rather than left blank: an unanswered question is a finding, and
            // whether it is deliberate is the author's call, not the engine's.
            <p className="wb2-wall-open">全书未给出答案。如果是有意留到续作，这里就是伏笔；如果不是，这是个缺口。</p>
          )}
          {chosen.events.length > 0 && (
            <ol className="wb2-wall-beats">
              {[...chosen.events]
                .sort((a, b) => a.chapter - b.chapter)
                .map((e, i) => (
                  <li key={`${e.chapter}-${i}`}>
                    <b>第 {e.chapter} 章</b>
                    <span className="wb2-beat" data-beat={e.type}>
                      {SUSPENSE_BEATS[e.type] ?? e.type}
                    </span>
                    {e.description}
                  </li>
                ))}
            </ol>
          )}
        </SubCard>
      )}
    </div>
  );
}

/** Every clue reveal in chapter order — kept as a drill-down from the wall. */
function SuspenseLedger({ data }: { data: WholeBookAnalysisV2 }) {
  const rows = useMemo(() => {
    const chapterSummary = new Map(
      data.chapters.functions.map((f) => [f.chapter_index, f.summary]),
    );
    return data.suspense.lifecycles
      .flatMap((lifecycle) => {
        const events = [...lifecycle.events].sort((a, b) => a.chapter - b.chapter);
        return events.map((event, i) => ({
          key: `${lifecycle.suspense_id}-${i}`,
          chapter: event.chapter,
          surface: chapterSummary.get(event.chapter) ?? "",
          beat: event.type,
          clue: event.description,
          question: lifecycle.question,
          next: events[i + 1]?.chapter ?? null,
          resolved: lifecycle.status === "resolved",
        }));
      })
      .sort((a, b) => a.chapter - b.chapter);
  }, [data]);

  const resolved = data.suspense.lifecycles.filter((l) => l.status === "resolved").length;

  return (
    <div className="wb2-sub-stack">
      <SubCard
        n={1}
        title="每一次线索揭示"
        meta={`${rows.length} 次揭示 · ${data.suspense.lifecycles.length} 条线 · ${resolved} 条已回收`}
      >
        <div className="wb2-cluetable-wrap">
          {/* The status pill's class used to be `state`, which an app-global empty-state rule
              (.sl-state, .state {min-height:180px; display:grid}) also matches — every row
              inflated to 158px to hold a 12px word. Names here are wb2-prefixed or nothing. */}
          <table className="wb2-cluetable">
            <thead>
              <tr>
                <th>章段</th><th>表面事件</th><th>露出线索</th><th>读者疑问</th><th>下次回响</th><th>状态</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key}>
                  <td className="ch">第 {r.chapter} 章</td>
                  <td>{r.surface || "—"}</td>
                  <td>
                    <span className="wb2-beat" data-beat={r.beat}>{SUSPENSE_BEATS[r.beat] ?? r.beat}</span>
                    {r.clue}
                  </td>
                  <td className="q">{r.question}</td>
                  <td className="next">{r.next ? `第 ${r.next} 章` : "无"}</td>
                  <td>
                    <span className="wb2-pill" data-resolved={r.resolved ? "1" : "0"}>
                      {r.resolved ? "已回收" : "未回收"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="wb2-cluetable-note">
          共 {rows.length} 次线索揭示，分属 {data.suspense.lifecycles.length} 条悬念线，
          其中 <b>{resolved}</b> 条已回收。
          {resolved < data.suspense.lifecycles.length / 2 &&
            "「真实含义」需要线程被明确回收才填得出，目前多数线程未被标记为回收。"}
        </p>
      </SubCard>
    </div>
  );
}

function SuspenseModule({ data }: { data: WholeBookAnalysisV2 }) {
  const [tab, setTab] = useState("悬念全景");
  const [selected, setSelected] = useState(0);
  const hooks = data.suspense.lifecycles;
  const h = hooks[selected];

  return (
    <>
      <div className="wb2-tabs">
        {["悬念全景", "线索顺序表", "单条追踪"].map((t) => (
          <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>
      {tab === "悬念全景" && <SuspenseWall data={data} />}
      {tab === "线索顺序表" && <SuspenseLedger data={data} />}
      {tab === "单条追踪" && (
        <div className="wb2-sub-stack">
          <SubCard n={1} title="逐条追踪" meta={`${hooks.length} 条悬念`}>
            <div className="wb2-hook-layout">
              <aside>
                {hooks.map((x, i) => (
                  <button className={i === selected ? "active" : ""} onClick={() => setSelected(i)} key={x.suspense_id}>
                    <b>{String(i + 1).padStart(2, "0")}</b>
                    {x.question.slice(0, 24)}
                  </button>
                ))}
              </aside>
              {h && (
                <section>
                  <header className="wb2-inline-head">
                    <div>
                      <small>
                        {h.status === "resolved" ? "已回收" : "未回收"} · 第 {h.chapter_start}–{h.chapter_end} 章
                      </small>
                      <h2>{h.question}</h2>
                    </div>
                  </header>
                  <div className="wb2-hook-timeline">
                    {h.events.map((n, i) => (
                      <article key={`${n.chapter}-${n.type}-${i}`}>
                        <i>{i + 1}</i>
                        <strong>{SUSPENSE_BEATS[n.type] ?? n.type}</strong>
                        <small>第 {n.chapter} 章</small>
                        <p>{n.description}</p>
                      </article>
                    ))}
                  </div>
                  {/* 最终回收 used to render as a labelled blank for every unresolved thread —
                      a full-width bordered panel holding a heading and nothing. The unanswered
                      case is a finding and gets the same sentence the wall uses. */}
                  {h.payoff ? (
                    <p className="wb2-payoff"><small>最终回收</small>{h.payoff}</p>
                  ) : (
                    <p className="wb2-wall-open">全书未给出答案。如果是有意留到续作，这里就是伏笔；如果不是，这是个缺口。</p>
                  )}
                  <Evidence ids={h.evidence} />
                </section>
              )}
            </div>
          </SubCard>
        </div>
      )}
    </>
  );
}

function PacingModule({ data }: { data: WholeBookAnalysisV2 }) {
  const W = 1100;
  const H = 390;
  const pad = 48;
  const [hover, setHover] = useState(0);
  // Curves drawn together cross constantly and none can be followed, so one is on by default
  // and the others join it on request. Plot progress is the one that answers "is the story
  // moving", which is what a reader opens this chart to ask.
  const [shown, setShown] = useState<Set<number>>(() => new Set([0]));
  const pacing = data.pacing;
  const maxChapter = pacing.points.at(-1)?.chapter_end ?? data.book_metadata.chapter_count;
  const marker = pacing.event_markers[hover] ?? pacing.event_markers[0];
  const series = useMemo(
    () =>
      PACING_SERIES.map((s) => ({
        name: s.label,
        measures: s.measures,
        values: pacing.points.map((p) => ({
          chapter: p.chapter_index ?? p.chapter_start,
          value: Number(p[s.key] ?? 0),
        })),
      })),
    [pacing.points],
  );

  return (
    <>
      <p className="wb2-scale-note">{PACING_SCALE_NOTE}</p>
      <div className="wb2-legend wb2-metric-toggle">
        {series.map((s, i) => (
          <button
            key={s.name}
            type="button"
            title={`${s.name}：${s.measures}（本书内百分位）`}
            aria-pressed={shown.has(i)}
            onClick={() =>
              setShown((prev) => {
                const next = new Set(prev);
                // Never leave the chart empty — turning the last curve off would look like
                // a broken render rather than a choice.
                if (next.has(i)) { if (next.size > 1) next.delete(i); } else next.add(i);
                return next;
              })
            }
          >
            <i
              style={{
                background: PACING_DASHES[i]
                  ? `repeating-linear-gradient(90deg, ${PACING_COLORS[i]} 0 5px, transparent 5px 9px)`
                  : PACING_COLORS[i],
              }}
            />
            {s.name}
          </button>
        ))}
      </div>
      <div className="wb2-chart-wrap">
        <svg className="wb2-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="全书节奏曲线">
          {/* The regions the engine measured, behind everything. A stretch a reader would
              feel as slow is a band, not a line to be inferred from six crossing curves. */}
          {pacing.pacing_regions.map((r) => {
            const x1 = pad + (r.chapter_start / Math.max(1, maxChapter)) * (W - pad - 10);
            const x2 = pad + (r.chapter_end / Math.max(1, maxChapter)) * (W - pad - 10);
            return (
              <rect
                key={`${r.type}-${r.chapter_start}`}
                x={x1} y="42" width={Math.max(2, x2 - x1)} height="280"
                className={r.type === "fatigue" ? "region-fatigue" : "region-climax"}
              >
                <title>{`第${r.chapter_start}–${r.chapter_end}章 ${r.reason}`}</title>
              </rect>
            );
          })}
          {[20, 40, 60, 80].map((v) => (
            <line className="grid" key={v} x1={pad} x2={W - 10} y1={H - 48 - v * 3} y2={H - 48 - v * 3} />
          ))}
          {series.map((s, si) =>
            shown.has(si) ? (
              <polyline
                key={s.name}
                fill="none"
                stroke={PACING_COLORS[si]}
                strokeDasharray={PACING_DASHES[si] || undefined}
                strokeWidth="2.4"
                points={s.values
                  .map(
                    (v) =>
                      `${pad + (v.chapter / Math.max(1, maxChapter)) * (W - pad - 10)},${H - 48 - v.value * 3}`,
                  )
                  .join(" ")}
              />
            ) : null,
          )}
          {pacing.event_markers.map((m, i) => {
            const x = pad + (m.chapter / Math.max(1, maxChapter)) * (W - pad - 10);
            return (
              <g
                key={`${m.chapter}-${m.title}`}
                className="event-marker"
                onMouseEnter={() => setHover(i)}
                onFocus={() => setHover(i)}
                tabIndex={0}
              >
                <line x1={x} x2={x} y1="42" y2="322" />
                <circle cx={x} cy={55 + (i % 3) * 13} r={hover === i ? 5 : 3} />
                <title>{`第${m.chapter}章 ${m.title}：${m.effect_on_pacing}`}</title>
              </g>
            );
          })}
        </svg>
      </div>
      {marker && (
        <div className="wb2-chart-detail">
          <header>
            <div>
              <small>曲线标记详情</small>
              <h2>
                第 {marker.chapter} 章｜{marker.title}
              </h2>
            </div>
          </header>
          <p>{marker.event}</p>
          <p>
            <b>节奏影响：</b>
            {marker.effect_on_pacing}
          </p>
          <Evidence ids={marker.evidence} />
        </div>
      )}
      {pacing.pacing_regions.length > 0 && (
        <>
          <h2>节奏异常区域</h2>
          <div className="wb2-anomalies">
            {pacing.pacing_regions.map((a) => (
              <details key={`${a.chapter_start}-${a.type}`}>
                <summary>
                  <b>{a.type}</b>
                  <span>
                    第 {a.chapter_start}–{a.chapter_end} 章
                  </span>
                  <p>{a.reason}</p>
                </summary>
                <div>
                  <b>诊断</b>
                  <p>{a.diagnosis}</p>
                </div>
              </details>
            ))}
          </div>
        </>
      )}
    </>
  );
}

function ChaptersModule({ data }: { data: WholeBookAnalysisV2 }) {
  const [selected, setSelected] = useState(0);
  const ch = data.chapters;
  const cell = ch.heatmap[selected];
  const agg = ch.aggregation_size;
  const sampleFns = ch.functions.filter(
    (f) => cell && f.chapter_index >= cell.chapter_start && f.chapter_index <= cell.chapter_end,
  ).slice(0, 5);

  return (
    <>
      <p className="wb2-long-summary">
        按 {agg} 章聚合展示热力图；下方表格汇总区间内章节功能，避免渲染数百张卡片。
      </p>
      <div
        className="wb2-heatmap"
        style={{ gridTemplateColumns: `100px repeat(${ch.heatmap.length}, minmax(22px,1fr))` }}
      >
        <span></span>
        {ch.heatmap.map((x, i) => (
          <button key={x.chapter_start} onClick={() => setSelected(i)} className={i === selected ? "active" : ""}>
            {x.chapter_start}
          </button>
        ))}
        {HEATMAP_DIMS.map((d) => {
          // Each row scaled to its own range. The raw value was being used directly as a
          // percentage, and the rows are on different scales by nature — 对话段落 runs 13–23
          // per chapter while 章末留钩 is a 0–1 proportion — so most rows rendered as
          // near-transparent and the grid read as uniformly pale.
          const values = ch.heatmap.map((x) => Number(x[d.key]) || 0);
          const lo = Math.min(...values);
          const hi = Math.max(...values);
          const flat = hi - lo === 0;
          return (
          <Fragment key={d.key}>
            <strong data-empty={flat ? "1" : "0"} title={`${d.label}（${d.unit}）`}>
              {d.label}
              <small>{d.unit}</small>
            </strong>
            {ch.heatmap.map((x, i) => (
              <button
                aria-label={`${d.label} 第${x.chapter_start}-${x.chapter_end}章 ${x[d.key]} ${d.unit}`}
                onClick={() => setSelected(i)}
                key={`${d.key}${i}`}
                // A row with no variation is marked as *absent*, not drawn as a low value:
                // 伏笔铺设 and 回收兑现 are 0 for the whole book because extraction never
                // produced them, and a pale cell would read as "a little" rather than "none".
                className={flat ? "wb2-heat-empty" : undefined}
                style={
                  flat
                    ? undefined
                    : {
                        background: `color-mix(in srgb, #2f6b57 ${(
                          12 + ((values[i] - lo) / (hi - lo)) * 88
                        ).toFixed(0)}%, #edf2ef)`,
                      }
                }
              />
            ))}
          </Fragment>
          );
        })}
      </div>
      <p className="wb2-heat-note">
        这里是<b>清点结果的每章均值</b>，不是评分：各行量纲不同（段落数 / 占比），只在行内比较，
        深浅按该行自身的取值范围着色。
        {HEATMAP_DIMS.filter((d) => {
          const values = ch.heatmap.map((x) => Number(x[d.key]) || 0);
          return Math.max(...values) - Math.min(...values) === 0;
        }).map((d) => d.label).join("、") &&
          `　斜纹行表示全书取值恒定（${HEATMAP_DIMS.filter((d) => {
            const values = ch.heatmap.map((x) => Number(x[d.key]) || 0);
            return Math.max(...values) - Math.min(...values) === 0;
          }).map((d) => d.label).join("、")}）——是没有数据，不是数值低。`}
      </p>
      {cell && (
        <div className="wb2-range-detail">
          <h2>
            第 {cell.chapter_start}–{cell.chapter_end} 章
          </h2>
          <table>
            <thead>
              <tr>
                <th>章节</th>
                <th>主要功能</th>
                <th>次要功能</th>
                <th>摘要</th>
              </tr>
            </thead>
            <tbody>
              {(sampleFns.length ? sampleFns : ch.functions.slice(0, 5)).map((f) => (
                <tr key={f.chapter_id}>
                  <th>
                    第 {f.chapter_index} 章 · {f.title}
                  </th>
                  <td>{f.primary_function}</td>
                  <td>{f.secondary_functions.join("、") || "—"}</td>
                  <td>{f.summary}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

/**
 * What the six assessment dimensions are called on screen.
 *
 * The document carries the identifier — `story_structure`, `suspense_payoff` — because that
 * is what code matches on, and those identifiers were being rendered to the reader as the
 * headings of the assessment page. The label belongs on the contract beside the identifier,
 * and there is now an optional field for it, but a backend built before that field exists
 * rejects a document carrying it. So the mapping lives here until a build ships that
 * understands the field, at which point this becomes the fallback.
 */


const REVISION_RANK: Record<string, string> = {
  first: "第一优先级",
  second: "第二优先级",
  third: "第三优先级",
};

/**
 * Render one revision priority.
 *
 * The contract carries these as objects — rank, chapter ranges, direction, and what must
 * survive the edit — but this block had no renderer for that shape and fell through to
 * `JSON.stringify`, so the page showed a reader the raw object. The string branch stays for
 * the older shape, which some stored results still use.
 */
function renderRevisionPriority(x: unknown) {
  if (typeof x === "string") return <h3>{x}</h3>;
  if (!x || typeof x !== "object") return null;
  const p = x as {
    priority?: string;
    chapter_ranges?: unknown;
    direction?: string;
    preserve?: unknown;
  };
  const ranges = Array.isArray(p.chapter_ranges)
    ? p.chapter_ranges
        .filter((r): r is number[] => Array.isArray(r) && r.length >= 2)
        .map((r) => `第 ${r[0]}–${r[1]} 章`)
        .join(" · ")
    : "";
  const preserve = Array.isArray(p.preserve) ? p.preserve.map(String).filter(Boolean) : [];
  return (
    <>
      {p.priority && <small>{REVISION_RANK[p.priority] ?? p.priority}</small>}
      <h3>{p.direction ?? ""}</h3>
      {ranges && <p>{ranges}</p>}
      {preserve.length > 0 && <p>改动时保留：{preserve.join("、")}</p>}
    </>
  );
}

/** Grade → distance from the centre. A is the rim, D is near it. */
const RATING_SCORE: Record<string, number> = {
  A: 7, "A-": 6, "B+": 5, B: 4, "B-": 3, C: 2, D: 1,
};

/**
 * The six dimensions as one shape.
 *
 * Six side-by-side grade cards make a reader compare letters in sequence; the shape says
 * which side of the book is weak before any of them are read. The dashed ring is B, so a
 * dent in the outline is a dimension below competent — for this book, suspense payoff and
 * pacing, both B-.
 */
function DimensionRadar({
  dimensions,
  selected,
  onSelect,
}: {
  dimensions: WholeBookAnalysisV2["assessment"]["dimensions"];
  selected: number;
  onSelect: (index: number) => void;
}) {
  const n = dimensions.length;
  if (n < 3) return null;
  const cx = 150, cy = 132, R = 92;
  const at = (i: number, r: number): [number, number] => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / n;
    return [cx + Math.cos(a) * r, cy + Math.sin(a) * r];
  };
  const poly = (r: number) =>
    dimensions.map((_, i) => at(i, r).map((v) => v.toFixed(1)).join(",")).join(" ");
  const points = dimensions.map((d, i) => at(i, (R * (RATING_SCORE[d.rating] ?? 4)) / 7));

  return (
    <svg viewBox="0 0 300 268" className="wb2-radar" role="img" aria-label="六维评估雷达图">
      {[0.34, 0.67, 1].map((f) => (
        <polygon key={f} points={poly(R * f)} fill="none" stroke="currentColor" opacity=".2" />
      ))}
      <polygon points={poly((R * RATING_SCORE.B) / 7)} fill="none" stroke="currentColor"
               opacity=".45" strokeDasharray="3 3" />
      {dimensions.map((_, i) => {
        const [x, y] = at(i, R);
        return <line key={i} x1={cx} y1={cy} x2={x.toFixed(1)} y2={y.toFixed(1)}
                     stroke="currentColor" opacity=".2" />;
      })}
      <polygon points={points.map((p) => p.map((v) => v.toFixed(1)).join(",")).join(" ")}
               className="wb2-radar-area" />
      {points.map(([x, y], i) => (
        <circle key={i} cx={x.toFixed(1)} cy={y.toFixed(1)} r={selected === i ? 5 : 3}
                className="wb2-radar-dot" data-selected={selected === i ? "1" : "0"} />
      ))}
      {/* Each axis is its own control. The shape says which dimension is weak; clicking it is
          how a reader gets from that to the sentence explaining why. */}
      {dimensions.map((d, i) => {
        const [x, y] = at(i, R + 25);
        const anchor = Math.abs(x - cx) < 12 ? "middle" : x > cx ? "start" : "end";
        const [hx, hy] = at(i, R);
        return (
          <g key={d.dimension} className="wb2-radar-axis" data-selected={selected === i ? "1" : "0"}
             tabIndex={0} role="button"
             aria-label={`${DIMENSION_LABELS[d.dimension] ?? d.dimension} ${d.rating}`}
             onClick={() => onSelect(i)}
             onKeyDown={(e) => {
               if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(i); }
             }}>
            <line x1={cx} y1={cy} x2={hx.toFixed(1)} y2={hy.toFixed(1)} className="wb2-radar-hit" />
            <text x={x.toFixed(1)} y={(y + 4).toFixed(1)} textAnchor={anchor}
                  fontSize="11" className="wb2-radar-label">
              {DIMENSION_LABELS[d.dimension] ?? d.dimension}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function AssessmentModule({ data }: { data: WholeBookAnalysisV2 }) {
  const [selected, setSelected] = useState(0);
  // Which radar axis the reader is asking about. Separate from the issue selection below.
  const [dimension, setDimension] = useState(0);
  const a = data.assessment;
  const issue = a.issues[selected];
  const total = data.book_metadata.chapter_count;
  const assessmentRows = ["结构", "人物", "悬念", "节奏", "章节效率"];

  return (
    <>
      <section className="wb2-soft-section wb2-assessment-summary">
        <div className="wb2-block-title">
          <small>全书总体判断</small>
          {/* overall_assessment is a distinct one-line verdict when the engine emits one.
              When it is empty the summary is not truncated into a fake title — the same
              sentence printed twice, the first copy cut mid-clause, reads as a bug. */}
          {a.overall_assessment && <h2>{a.overall_assessment}</h2>}
        </div>
        <p className={a.overall_assessment ? undefined : "wb2-verdict-lead"}>{a.overall_summary}</p>
      </section>

      <section className="wb2-soft-section">
        <div className="wb2-block-title">
          <small>六维评估</small>
          <h2>形状先说明哪一维拖了后腿</h2>
        </div>
        <div className="wb2-dimension-layout">
          <figure className="wb2-radar-wrap">
            <DimensionRadar dimensions={a.dimensions} selected={dimension} onSelect={setDimension} />
            <figcaption>越靠外越好 · 虚线为 B 基准 · 点轴看说明</figcaption>
          </figure>
          <div className="wb2-dimension-list">
            {a.dimensions.map((x, i) => (
              <article key={x.dimension} data-selected={dimension === i ? "1" : "0"}>
                <b data-below={(RATING_SCORE[x.rating] ?? 4) < RATING_SCORE.B ? "1" : "0"}>
                  {x.rating}
                </b>
                <div>
                  <h3>{DIMENSION_LABELS[x.dimension] ?? x.dimension}</h3>
                  <strong>{x.conclusion}</strong>
                  {x.supporting_metrics.length > 0 && <p>{x.supporting_metrics.join(" · ")}</p>}
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="wb2-soft-section">
        <div className="wb2-block-title">
          <small>核心优势</small>
          <h2>建议保留、不应轻易修改的设计</h2>
        </div>
        <div className="wb2-strengths">
          {a.strengths.map((x, i) => (
            <article key={x.title}>
              <b>{String(i + 1).padStart(2, "0")}</b>
              <div>
                <h3>{x.title}</h3>
                <p>{x.why_good}</p>
                <small>
                  第 {x.chapter_start}–{x.chapter_end} 章
                </small>
                <Evidence ids={x.evidence} />
              </div>
            </article>
          ))}
        </div>
      </section>

      {a.issues.length > 0 && (
        <section className="wb2-soft-section">
          <div className="wb2-block-title">
            <small>全书问题地图</small>
            <h2>问题集中在哪些章节？</h2>
          </div>
          {(() => {
            // The old filter compared English categories (`pacing`, `suspense_payoff`)
            // against Chinese row names with includes(), which never matched — and a
            // `row === "章节效率"` fallback then dumped every issue into the last row.
            // Four empty rails and one wrong bar. The mapping is explicit now, and only
            // rows that actually carry an issue are drawn.
            const rowOf = (cat: string): string =>
              CATEGORY_ROW[cat] ?? DIMENSION_LABELS[cat] ?? cat;
            const rows = assessmentRows.filter((row) => a.issues.some((x) => rowOf(x.category) === row));
            const silent = assessmentRows.filter((r) => !rows.includes(r));
            const priorities = [...new Set(a.issues.map((x) => x.priority))].sort();
            return (
              <>
                <div className="wb2-priority-legend">
                  {priorities.includes("P0") && <span className="priority-P0">P0 必须优先处理</span>}
                  {priorities.includes("P1") && <span className="priority-P1">P1 明显影响体验</span>}
                  {priorities.includes("P2") && <span className="priority-P2">P2 局部优化</span>}
                </div>
                <div className="wb2-issue-map">
                  <div className="wb2-map-axis">
                    <span></span>
                    {[1, Math.round(total * 0.25), Math.round(total * 0.5), Math.round(total * 0.75), total].map(
                      (x) => (
                        <b key={x} style={{ left: pct(x, total) }}>
                          {x}
                        </b>
                      ),
                    )}
                  </div>
                  {rows.map((row) => (
                    <div className="wb2-map-row" key={row}>
                      <strong>{row}</strong>
                      <i>
                        {a.issues
                          .filter((x) => rowOf(x.category) === row)
                          .map((x) => (
                            <span
                              className={`priority-${x.priority}`}
                              title={`${x.priority}｜${x.symptom}`}
                              key={x.issue_id}
                              style={{
                                left: pct(x.chapter_start, total),
                                width: `${((x.chapter_end - x.chapter_start + 1) / Math.max(1, total)) * 100}%`,
                              }}
                            />
                          ))}
                      </i>
                    </div>
                  ))}
                </div>
                {silent.length > 0 && (
                  <p className="wb2-quiet">
                    <b>{silent.join("、")}没有登记问题</b>，所以不占行。
                  </p>
                )}
              </>
            );
          })()}
        </section>
      )}

      <section className="wb2-soft-section">
        <div className="wb2-block-title">
          <small>核心问题</small>
          <h2>症状、根因与读者影响</h2>
        </div>
        <div className="wb2-assessment-layout">
          <div className="wb2-issue-list">
            {a.issues.map((item, i) => (
              <button className={selected === i ? "active" : ""} onClick={() => setSelected(i)} key={item.issue_id}>
                <span className={`priority-${item.priority}`}>{item.priority}</span>
                <div>
                  <b>{item.symptom.slice(0, 40)}</b>
                  <small>
                    {DIMENSION_LABELS[item.category] ?? item.category} · 第 {item.chapter_start}–{item.chapter_end} 章
                  </small>
                </div>
              </button>
            ))}
          </div>
          {issue && (
            <div className="wb2-detail-panel">
              <header>
                <div>
                  <small>
                    {DIMENSION_LABELS[issue.category] ?? issue.category} · 第 {issue.chapter_start}–{issue.chapter_end} 章
                  </small>
                  <h2>{issue.symptom}</h2>
                </div>
                <span className={`priority-${issue.priority}`}>{issue.priority}</span>
              </header>
              {/* The title IS the symptom — repeating it as the first row said everything
                  twice. And rows the engine left empty (支持指标 on this book) are dropped
                  rather than drawn as a labelled blank. */}
              <dl className="wb2-detail-grid">
                {(
                  [
                    ["根本原因", issue.root_cause],
                    ["读者影响", issue.reader_impact],
                    ["支持指标", issue.supporting_metrics.join(" · ")],
                    ["可能方向", issue.recommended_direction || issue.possible_direction],
                  ] as Array<[string, string]>
                )
                  .filter(([, v]) => v && v.trim().length > 0)
                  .map(([k, v]) => (
                    <div key={k}>
                      <dt>{k}</dt>
                      <dd>{v}</dd>
                    </div>
                  ))}
              </dl>
              <Evidence ids={issue.evidence} />
            </div>
          )}
        </div>
      </section>

      {(a.revision_priorities.length > 0 || a.preserve_list.length > 0) && (
        <section className="wb2-soft-section">
          <div className="wb2-block-title">
            <small>修改优先级</small>
            <h2>先改什么，以及哪些地方不要乱改</h2>
          </div>
          <div className="wb2-revision-priorities">
            {a.revision_priorities.map((x, i) => (
              <article key={i}>
                <b>{String(i + 1).padStart(2, "0")}</b>
                <div>{renderRevisionPriority(x)}</div>
              </article>
            ))}
          </div>
          {a.preserve_list.length > 0 && (
            <div className="wb2-block-title" style={{ marginTop: 24 }}>
              <small>建议保留</small>
              <ul className="wb2-resolution-list">
                {a.preserve_list.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}
    </>
  );
}

export function WholeBookV2ReportView({
  data,
  activeModule,
  onModuleChange,
  mode,
  onReanalyze,
  onReanalyzeClick,
  showReanalyzeButton = false,
  analysisStatusLabel,
  headerBanner,
  headerExtra,
}: WholeBookV2ReportViewProps) {
  const meta = data.book_metadata;
  const tp = data.type_profile;
  // Which modules this document actually filled. A 拆文 document has `story_breakdown` and
  // leaves 全书总览 / 综合诊断 nearly empty; a diagnostic one is the other way round. Listing
  // all seven regardless is how a 拆文 run showed two blank pages and hid the one section it
  // had filled.
  const hasBreakdown = Boolean(data.story_breakdown?.four_beats?.length);
  const modules = modulesForDocument(hasBreakdown);
  const activeLabel = modules.find((m) => m.key === activeModule)?.label ?? activeModule;

  // A module the current document has no page for — a deep link, or a mode switch under a
  // remembered tab. Fall to the first module this document does fill rather than rendering
  // an empty frame.
  useEffect(() => {
    if (!modules.length) return;
    if (modules.some((m) => m.key === activeModule)) return;
    onModuleChange(modules[0].key);
  }, [activeModule, modules, onModuleChange]);
  const handleReanalyze = onReanalyzeClick ?? onReanalyze;
  const statusLabel = analysisStatusLabel ?? "已完成";
  const [exporting, setExporting] = useState(false);
  const [vipNotice, setVipNotice] = useState<{ message: string; url: string } | null>(null);
  const showNonRealWarning = mode === "formal" && needsReanalysisWarning(data);

  return (
    <div
      className="wb2-page"
      data-testid="whole-book-v2-report"
      data-module={activeModule}
      data-mode={mode}
    >
      {showNonRealWarning ? (
        <div className="wbv2-nonreal-warning" data-testid="whole-book-v2-nonreal-warning">
          当前结果不是完整真实 V2 分析，需要重新分析。
        </div>
      ) : null}
      {headerBanner}
      <header className="wb2-book-header">
        <div className="wb2-book-title">
          {mode === "mock" && <span className="wb2-dev-badge">DEV</span>}
          <div>
            <h1>{meta.title}</h1>
            <p>Whole-Book V2 全书分析报告</p>
          </div>
        </div>
        <dl>
          <div>
            <dt>章节</dt>
            <dd>{meta.chapter_count.toLocaleString()}</dd>
          </div>
          <div>
            <dt>字数</dt>
            <dd>{meta.character_count.toLocaleString()}</dd>
          </div>
          <div>
            <dt>作品画像</dt>
            <dd>{tp.primary_genre}</dd>
          </div>
          <div>
            <dt>分析状态</dt>
            <dd>
              <i /> {statusLabel}
            </dd>
          </div>
        </dl>
        <div className="wb2-header-actions">
          <button
            type="button"
            className="wbv2-reanalyse-btn wb2-export-btn"
            data-testid="whole-book-v2-export-button"
            disabled={exporting}
            onClick={async () => {
              setExporting(true);
              setVipNotice(null);
              try {
                await downloadReportPdf(data);
              } catch (err) {
                if (err instanceof VipRequiredError) {
                  // The gate refusing is an answer, not an outage — no silent fallback
                  // that would hand out the gated artifact by another name.
                  setVipNotice({ message: err.message, url: err.afdianUrl });
                } else {
                  // No headless browser on this machine, or the sidecar is down — the
                  // HTML file carries the same report, so the click still delivers one.
                  downloadReport(data);
                }
              } finally {
                setExporting(false);
              }
            }}
          >
            {exporting ? "正在生成 PDF…" : "导出 PDF · VIP"}
          </button>
          <button
            type="button"
            className="wbv2-reanalyse-btn"
            data-testid="whole-book-v2-export-html-button"
            title="自包含网页版，内嵌完整原始 JSON，可做机器对账"
            onClick={() => downloadReport(data)}
          >
            HTML
          </button>
          {showReanalyzeButton && handleReanalyze ? (
            <button
              type="button"
              className="wbv2-reanalyse-btn"
              data-testid="whole-book-v2-reanalyse-button"
              onClick={handleReanalyze}
            >
              重新分析 V2
            </button>
          ) : null}
        </div>
        {headerExtra}
      </header>
      {vipNotice && (
        <div className="wb2-vip-notice" data-testid="whole-book-v2-vip-notice" role="alert">
          <b>PDF 导出是 VIP 功能</b>
          <p>{vipNotice.message}</p>
          <p>
            {vipNotice.url ? (
              <a href={vipNotice.url} target="_blank" rel="noreferrer">
                前往爱发电购买月卡授权 →
              </a>
            ) : (
              <span>购买入口尚未配置，请联系作者获取授权码。</span>
            )}
            　已有授权码？在 设置 → 授权 中激活。
          </p>
          <button type="button" onClick={() => setVipNotice(null)}>
            知道了
          </button>
        </div>
      )}

      <nav className="wb2-nav" aria-label="全书分析模块">
        {modules.map((m, i) => (
          <button
            key={m.key}
            className={activeModule === m.key ? "active" : ""}
            onClick={() => onModuleChange(m.key)}
          >
            <b>{i + 1}</b>
            {m.label}
          </button>
        ))}
      </nav>

      <main className="wb2-content">
        <div className="wb2-page-heading">
          <h1>{activeLabel}</h1>
          <p>{MODULE_DESCRIPTIONS[activeModule]}</p>
        </div>

        {activeModule === "overview" && <OverviewModule data={data} />}
        {activeModule === "story_breakdown" && <StoryBreakdownModule data={data} />}
        {activeModule === "story" && <StoryModule data={data} />}
        {activeModule === "characters" && <CharactersModule data={data} />}
        {activeModule === "suspense" && <SuspenseModule data={data} />}
        {activeModule === "pacing" && <PacingModule data={data} />}
        {activeModule === "chapters" && <ChaptersModule data={data} />}
        {activeModule === "assessment" && <AssessmentModule data={data} />}
      </main>
    </div>
  );
}
