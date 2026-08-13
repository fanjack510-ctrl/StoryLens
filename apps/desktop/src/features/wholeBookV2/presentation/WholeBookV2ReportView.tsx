import { Fragment, useMemo, useState, type ReactNode } from "react";
import type { WholeBookAnalysisV2 } from "../contracts";
import { needsReanalysisWarning } from "../adapter";
import {
  MODULES,
  MODULE_DESCRIPTIONS,
  type ModuleKey,
} from "./modules";
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

const PACING_COLORS = ["#2f6b57", "#729f8d", "#d18b55", "#657a99", "#a06a85", "#8b8054"];
const PACING_LABELS = ["剧情推进", "阅读张力", "情绪强度", "阅读动力", "钩子密度", "节奏速度"];
const HEATMAP_DIMS: Array<{ key: keyof WholeBookAnalysisV2["chapters"]["heatmap"][number]; label: string }> = [
  { key: "mainline_progress", label: "主线推进" },
  { key: "character_development", label: "人物成长" },
  { key: "conflict", label: "冲突强度" },
  { key: "suspense", label: "悬念密度" },
  { key: "foreshadow", label: "伏笔铺设" },
  { key: "payoff", label: "回收兑现" },
  { key: "transition", label: "过渡衔接" },
];

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

function OverviewModule({ data }: { data: WholeBookAnalysisV2 }) {
  const [stage, setStage] = useState(0);
  const tp = data.type_profile;
  const ov = data.overview;
  const stages = data.story.structure_stages;
  const detail = stages[stage];

  return (
    <>
      <section className="wb2-soft-section wb2-work-profile">
        <div className="wb2-block-title">
          <small>作品画像</small>
          <h2>这是一部怎样的小说？</h2>
          <p>{ov.one_sentence_story}</p>
        </div>
        <div className="wb2-profile-grid">
          <div>
            <small>主类型</small>
            <strong>{tp.primary_genre}</strong>
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

      <section className="wb2-soft-section">
        <div className="wb2-block-title">
          <small>故事核心</small>
          <h2>{ov.one_sentence_story}</h2>
        </div>
        <div className="wb2-facts">
          {[
            ["主角", `${ov.protagonist}｜${ov.initial_state}`],
            ["核心目标", ov.core_goal],
            ["核心冲突", ov.core_conflict],
            ["核心悬念", ov.core_question],
            ["最终高潮", ov.final_climax],
            ["结局", ov.ending_resolution.join("；") || "—"],
          ].map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </div>
      </section>

      <section className="wb2-soft-section wb2-overview-rich">
        <div className="wb2-block-title">
          <small>全书分析摘要</small>
          <h2>{ov.one_sentence_story}</h2>
        </div>
        <p>{ov.full_summary}</p>
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
      </section>

      <section className="wb2-soft-section">
        <div className="wb2-overview-columns">
          <div>
            <div className="wb2-block-title">
              <small>核心目标演变</small>
              <h2>他想得到什么</h2>
            </div>
            <ol className="wb2-evolution-list">
              {ov.goal_evolution.map((x, i) => (
                <li key={`${x}-${i}`}>{x}</li>
              ))}
            </ol>
          </div>
          <div>
            <div className="wb2-block-title">
              <small>核心冲突演变</small>
              <h2>阻力如何升级</h2>
            </div>
            <ol className="wb2-evolution-list">
              {ov.conflict_evolution.map((x, i) => (
                <li key={`${x}-${i}`}>{x}</li>
              ))}
            </ol>
          </div>
        </div>
      </section>

      <section className="wb2-soft-section">
        <div className="wb2-block-title">
          <small>主要故事线</small>
          <h2>多条长线如何共同抵达结局</h2>
        </div>
        <div className="wb2-storyline-summaries">
          {ov.major_storylines.map((s, i) => (
            <article key={s}>
              <b>{String(i + 1).padStart(2, "0")}</b>
              <div>
                <h3>{s}</h3>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="wb2-soft-section">
        <div className="wb2-overview-columns">
          <div>
            <div className="wb2-block-title">
              <small>关键转折</small>
              <h2>改变故事方向的关键节点</h2>
            </div>
            {ov.major_turning_points.map((t) => (
              <p className="wb2-numbered-insight" key={t.title}>
                <b>
                  第 {t.chapter_start}
                  {t.chapter_end !== t.chapter_start ? `–${t.chapter_end}` : ""} 章
                </b>
                <span>
                  {t.title}：{t.description}
                </span>
              </p>
            ))}
          </div>
          <div>
            <div className="wb2-block-title">
              <small>核心悬念</small>
              <h2>读者持续追问的问题</h2>
            </div>
            {ov.major_suspense.map((x, i) => (
              <p className="wb2-numbered-insight" key={x}>
                <b>{String(i + 1).padStart(2, "0")}</b>
                <span>{x}</span>
              </p>
            ))}
          </div>
        </div>
      </section>

      {stages.length > 0 && (
        <section className="wb2-soft-section">
          <div className="wb2-block-title">
            <small>故事骨架 Timeline</small>
            <h2>各阶段的目标、选择与代价</h2>
          </div>
          <div className="wb2-stage-timeline">
            {stages.map((s, i) => (
              <article
                className={stage === i ? "active" : ""}
                onClick={() => setStage(i)}
                key={s.stage_id}
                title={`${s.stage_goal}｜点击查看详情`}
              >
                <b>{String(i + 1).padStart(2, "0")}</b>
                <div>
                  <strong>{s.title}</strong>
                  <small>
                    第 {s.chapter_start}–{s.chapter_end} 章
                  </small>
                  <p>{s.summary}</p>
                </div>
              </article>
            ))}
          </div>
          {detail && (
            <div className="wb2-detail-panel">
              <header>
                <div>
                  <small>
                    第 {detail.chapter_start}–{detail.chapter_end} 章
                  </small>
                  <h2>{detail.title}</h2>
                </div>
              </header>
              <p className="wb2-long-summary">{detail.summary}</p>
              <dl className="wb2-detail-grid">
                <div>
                  <dt>阶段目标</dt>
                  <dd>{detail.stage_goal}</dd>
                </div>
                <div>
                  <dt>核心冲突</dt>
                  <dd>{detail.core_conflict}</dd>
                </div>
                <div>
                  <dt>重大选择</dt>
                  <dd>{detail.major_choice}</dd>
                </div>
                <div>
                  <dt>付出</dt>
                  <dd>{detail.cost_paid.join("、") || "—"}</dd>
                </div>
                <div>
                  <dt>获得</dt>
                  <dd>{detail.gain_received.join("、") || "—"}</dd>
                </div>
              </dl>
              <Evidence ids={detail.evidence} />
            </div>
          )}
        </section>
      )}

      <section className="wb2-soft-section">
        <div className="wb2-block-title">
          <small>故事骨架列表</small>
          <h2>全书结构脉络</h2>
        </div>
        <ol className="wb2-evolution-list">
          {ov.story_skeleton.map((x, i) => (
            <li key={`${x}-${i}`}>{x}</li>
          ))}
        </ol>
      </section>

      <section className="wb2-soft-section">
        <div className="wb2-block-title">
          <small>最终高潮</small>
          <h2>{ov.final_climax}</h2>
        </div>
        <div className="wb2-overview-columns">
          <div>
            <h3>结局解决项</h3>
            <ul className="wb2-resolution-list">
              {ov.ending_resolution.map((x) => (
                <li key={x}>{x}</li>
              ))}
            </ul>
          </div>
          <div>
            <h3>结局遗留项</h3>
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

function StoryModule({ data }: { data: WholeBookAnalysisV2 }) {
  const [tab, setTab] = useState("结构阶段");
  const [selectedStage, setSelectedStage] = useState(0);
  const tabs = ["结构阶段", "主线与支线", "因果链"];
  const total = data.book_metadata.chapter_count;
  const story = data.story;
  const stage = story.structure_stages[selectedStage];

  return (
    <>
      <div className="wb2-tabs">
        {tabs.map((t) => (
          <button className={tab === t ? "active" : ""} onClick={() => setTab(t)} key={t}>
            {t}
          </button>
        ))}
      </div>
      {tab === "结构阶段" && (
        <>
          <div className="wb2-stage-table">
            {story.structure_stages.map((s, i) => (
              <div
                className={selectedStage === i ? "active" : ""}
                onClick={() => setSelectedStage(i)}
                key={s.stage_id}
              >
                <b>{i + 1}</b>
                <strong>{s.title}</strong>
                <RangeTrack range={[s.chapter_start, s.chapter_end]} total={total} />
                <span>
                  {s.chapter_start}–{s.chapter_end}
                </span>
                <p>{s.summary}</p>
              </div>
            ))}
          </div>
          {stage && (
            <div className="wb2-detail-panel">
              <header>
                <div>
                  <small>
                    第 {stage.chapter_start}–{stage.chapter_end} 章
                  </small>
                  <h2>{stage.title}</h2>
                </div>
              </header>
              <p className="wb2-long-summary">{stage.summary}</p>
              <dl className="wb2-detail-grid">
                <div>
                  <dt>阶段目标</dt>
                  <dd>{stage.stage_goal}</dd>
                </div>
                <div>
                  <dt>核心冲突</dt>
                  <dd>{stage.core_conflict}</dd>
                </div>
                <div>
                  <dt>重大选择</dt>
                  <dd>{stage.major_choice}</dd>
                </div>
                <div>
                  <dt>付出</dt>
                  <dd>{stage.cost_paid.join("、")}</dd>
                </div>
                <div>
                  <dt>获得</dt>
                  <dd>{stage.gain_received.join("、")}</dd>
                </div>
              </dl>
              <Evidence ids={stage.evidence} />
            </div>
          )}
        </>
      )}
      {tab === "主线与支线" && (
        <div className="wb2-tracks">
          {story.storylines.map((s) => (
            <div key={s.storyline_id}>
              <strong>
                {s.type === "main" ? "主线" : "支线"}｜{s.name}
              </strong>
              <RangeTrack range={[s.chapter_start, s.chapter_end]} total={total} />
              <span>
                {s.chapter_start}–{s.chapter_end} · {s.status}
              </span>
            </div>
          ))}
        </div>
      )}
      {tab === "因果链" && (
        // Vertical. As a horizontal strip these sixty links were 145px-wide cards with the
        // text squeezed to two characters a line, and reading them meant dragging sideways.
        // Down the page, cause and effect sit on one line and a dozen fit on a screen.
        <ol className="wb2-causal">
          {story.causal_chain.map((x, i) => {
            const [cause, effect] = x.split("→");
            return (
              <li key={`${i}-${x}`}>
                <b>{String(i + 1).padStart(2, "0")}</b>
                <span>
                  {cause.trim()}
                  {effect && <i>→</i>}
                  {effect?.trim()}
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </>
  );
}

function CharactersModule({ data }: { data: WholeBookAnalysisV2 }) {
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
        {["人物系统", "主角历程", "人物关系"].map((t) => (
          <button className={tab === t ? "active" : ""} onClick={() => setTab(t)} key={t}>
            {t}
          </button>
        ))}
      </div>
      {tab === "人物系统" && (
        <>
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
                  <td>{c.role}</td>
                  <td>{c.character_arc}</td>
                  <td>查看档案 →</td>
                </tr>
              ))}
            </tbody>
          </table>
          {major && (
            <div className="wb2-detail-panel">
              <header>
                <div>
                  <small>{major.role}</small>
                  <h2>{major.name}</h2>
                </div>
                <span>{major.character_arc}</span>
              </header>
              <Evidence ids={major.evidence} />
            </div>
          )}
        </>
      )}
      {tab === "主角历程" && (
        <>
          <p className="wb2-long-summary">
            {protagonist.initial_identity} → {protagonist.final_identity}｜
            {protagonist.arc_summary || protagonist.core_transformation || ""}
          </p>
          <div className="wb2-arc">
            {protagonist.stages.map((s, i) => (
              <button className={arc === i ? "active" : ""} onClick={() => setArc(i)} key={s.stage_name}>
                <b>{i + 1}</b>
                <strong>{s.stage_name}</strong>
                <small>第 {s.chapter} 章</small>
              </button>
            ))}
          </div>
          {arcStage && (
            <div className="wb2-detail-panel wb2-arc-detail">
              <header>
                <div>
                  <small>
                    第 {arcStage.chapter} 章 · 主角历程 {arc + 1}/{protagonist.stages.length}
                  </small>
                  <h2>{arcStage.stage_name}</h2>
                </div>
                <span>
                  {arcStage.entry_state} → {arcStage.exit_state}
                </span>
              </header>
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
              <dl className="wb2-detail-grid">
                <div>
                  <dt>能力变化</dt>
                  <dd>{arcStage.ability_change}</dd>
                </div>
                <div>
                  <dt>关系变化</dt>
                  <dd>{arcStage.relationship_change}</dd>
                </div>
                <div>
                  <dt>社会位置变化</dt>
                  <dd>{arcStage.status_change}</dd>
                </div>
                <div>
                  <dt>内在信念变化</dt>
                  <dd>{arcStage.internal_belief_change}</dd>
                </div>
                <div>
                  <dt>下一阶段触发</dt>
                  <dd>{arcStage.next_stage_trigger}</dd>
                </div>
              </dl>
              <h3>重大事件</h3>
              <ul>
                {arcStage.major_events.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
              <Evidence ids={arcStage.evidence} />
            </div>
          )}
          {(protagonist.ability_track.length > 0 ||
            protagonist.relationship_track.length > 0 ||
            protagonist.external_status_track.length > 0 ||
            protagonist.internal_belief_track.length > 0) && (
            <>
              <h2>四轨成长 · 与主时间线对齐</h2>
              <div className="wb2-growth-tracks">
                <header>
                  <b>成长轨道</b>
                  {protagonist.stages.map((a) => (
                    <span key={a.chapter}>C{a.chapter}</span>
                  ))}
                </header>
                {[
                  { name: "外在身份 / 社会位置", track: protagonist.external_status_track },
                  { name: "能力与资源", track: protagonist.ability_track },
                  { name: "内在信念", track: protagonist.internal_belief_track },
                  { name: "关系网络", track: protagonist.relationship_track },
                ]
                  .filter((t) => t.track.length > 0)
                  .map((track) => (
                    <div key={track.name}>
                      <strong>{track.name}</strong>
                      {track.track.map((v, i) => (
                        <button
                          className={arc === i ? "active" : ""}
                          title={v.state}
                          onClick={() => setArc(i)}
                          key={`${track.name}-${v.chapter}`}
                        >
                          {v.state.slice(0, 8)}
                        </button>
                      ))}
                    </div>
                  ))}
              </div>
            </>
          )}
        </>
      )}
      {tab === "人物关系" && <RelationshipGraph relationships={chars.relationships} />}
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
  const mine = relationships.filter((r) => r.person_a === active || r.person_b === active);

  return (
    <div className="wb2-graph-layout">
      <svg className="wb2-relgraph" viewBox="0 0 640 460" role="img" aria-label="人物关系网络图">
        {relationships.map((r, i) => {
          const a = positions.get(r.person_a);
          const b = positions.get(r.person_b);
          if (!a || !b) return null;
          const on = r.person_a === active || r.person_b === active;
          return (
            <line key={i} className={on ? "edge on" : "edge"}
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
        <small>{mine.length} 条关系</small>
        <ul>
          {mine.map((r, i) => {
            const other = r.person_a === active ? r.person_b : r.person_a;
            return (
              <li key={i}>
                <b>{other}</b>
                <span>{r.relationship_type}</span>
                <em>第 {r.chapter_start}–{r.chapter_end} 章</em>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

/** What each beat did to the question, as a reader would name it. */
const SUSPENSE_BEATS: Record<string, string> = {
  hook: "抛出", clue: "线索", foreshadow: "伏笔", misdirection: "误导",
  partial_reveal: "部分揭示", reveal: "揭示", twist: "反转", payoff: "兑现",
};

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
    <>
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
        <span className="wb2-wall-count">
          {threads.length} 条悬念，<b>{resolved}</b> 条已回收
        </span>
      </div>
      {chosen && (
        <div className="wb2-wall-detail">
          <h3>{chosen.question}</h3>
          <small>
            第 {chosen.chapter_start}–{chosen.chapter_end} 章 · 被回访 {chosen.events.length} 次 ·
            {chosen.status === "resolved" ? " 已回收" : " 未回收"}
          </small>
          {chosen.status === "resolved" ? (
            <p><b>答案</b>　{chosen.payoff}</p>
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
        </div>
      )}
    </>
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
    <>
      <div className="wb2-ledger-wrap">
        <table className="wb2-ledger">
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
                  <span className="beat" data-beat={r.beat}>{SUSPENSE_BEATS[r.beat] ?? r.beat}</span>
                  {r.clue}
                </td>
                <td className="q">{r.question}</td>
                <td className="next">{r.next ? `第 ${r.next} 章` : "无"}</td>
                <td>
                  <span className="state" data-resolved={r.resolved ? "1" : "0"}>
                    {r.resolved ? "已回收" : "未回收"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="wb2-ledger-note">
        共 {rows.length} 次线索揭示，分属 {data.suspense.lifecycles.length} 条悬念线，
        其中 <b>{resolved}</b> 条已回收。
        {resolved < data.suspense.lifecycles.length / 2 &&
          "「真实含义」需要线程被明确回收才填得出，目前多数线程未被标记为回收。"}
      </p>
    </>
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
                {h.status} · 第 {h.chapter_start}–{h.chapter_end} 章
              </small>
              <h2>{h.question}</h2>
            </div>
          </header>
          <div className="wb2-hook-timeline">
            {h.events.map((n, i) => (
              <article key={`${n.chapter}-${n.type}-${i}`}>
                <i>{i + 1}</i>
                <strong>{n.type}</strong>
                <small>第 {n.chapter} 章</small>
                <p>{n.description}</p>
              </article>
            ))}
          </div>
          <div className="wb2-detail-panel">
            <dl className="wb2-detail-grid">
              <div>
                <dt>最终回收</dt>
                <dd>{h.payoff}</dd>
              </div>
            </dl>
            <Evidence ids={h.evidence} />
          </div>
        </section>
      )}
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
  // Six curves drawn together are a ball of wool: at 96 points each they cross constantly
  // and none of them can be followed. Reading drive is the one that answers "would a reader
  // keep going", so it is the default; the rest are there when a comparison is wanted.
  const [shown, setShown] = useState<Set<number>>(() => new Set([3]));
  const pacing = data.pacing;
  const maxChapter = pacing.points.at(-1)?.chapter_end ?? data.book_metadata.chapter_count;
  const marker = pacing.event_markers[hover] ?? pacing.event_markers[0];
  const series = useMemo(
    () =>
      PACING_LABELS.map((name, si) => ({
        name,
        values: pacing.points.map((p) => ({
          chapter: p.chapter_index ?? p.chapter_start,
          value: [p.plot_progress, p.tension, p.emotion, p.reading_drive, p.hook_density, p.pace_speed][si],
        })),
      })),
    [pacing.points],
  );

  return (
    <>
      <div className="wb2-legend wb2-metric-toggle">
        {series.map((s, i) => (
          <button
            key={s.name}
            type="button"
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
            <i style={{ background: PACING_COLORS[i] }} />
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
                strokeWidth="2"
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
          // percentage, and the rows are on wildly different scales — 过渡衔接 runs 3.9–21.2
          // while 悬念密度 runs 0.4–1.0 — so six of the seven rendered as near-transparent
          // and the grid read as uniformly pale.
          const values = ch.heatmap.map((x) => Number(x[d.key]) || 0);
          const lo = Math.min(...values);
          const hi = Math.max(...values);
          const flat = hi - lo === 0;
          return (
          <Fragment key={d.key}>
            <strong data-empty={flat ? "1" : "0"}>{d.label}</strong>
            {ch.heatmap.map((x, i) => (
              <button
                aria-label={`${d.label} ${x.chapter_start}-${x.chapter_end} ${x[d.key]}`}
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
        每行按自身取值范围着色，行内对比才出得来。
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
const DIMENSION_LABELS: Record<string, string> = {
  story_structure: "故事结构",
  protagonist_growth: "主角成长",
  character_relationships: "人物关系",
  suspense_payoff: "悬念回收",
  pacing: "节奏",
  chapter_efficiency: "章节效率",
};

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
          <h2>{a.overall_assessment || a.overall_summary.slice(0, 48)}</h2>
        </div>
        <p>{a.overall_summary}</p>
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
          <div className="wb2-priority-legend">
            <span className="priority-P0">P0 必须优先处理</span>
            <span className="priority-P1">P1 明显影响体验</span>
            <span className="priority-P2">P2 局部优化</span>
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
            {assessmentRows.map((row) => (
              <div className="wb2-map-row" key={row}>
                <strong>{row}</strong>
                <i>
                  {a.issues
                    .filter((issue) => issue.category.includes(row.replace("效率", "")) || row === "章节效率")
                    .map((issue) => (
                      <span
                        className={`priority-${issue.priority}`}
                        title={`${issue.priority}｜${issue.symptom}`}
                        key={issue.issue_id}
                        style={{
                          left: pct(issue.chapter_start, total),
                          width: `${((issue.chapter_end - issue.chapter_start + 1) / Math.max(1, total)) * 100}%`,
                        }}
                      />
                    ))}
                </i>
              </div>
            ))}
          </div>
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
                    {item.category} · 第 {item.chapter_start}–{item.chapter_end} 章
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
                    {issue.category} · 第 {issue.chapter_start}–{issue.chapter_end} 章
                  </small>
                  <h2>{issue.symptom}</h2>
                </div>
                <span className={`priority-${issue.priority}`}>{issue.priority}</span>
              </header>
              <dl className="wb2-detail-grid">
                <div>
                  <dt>症状</dt>
                  <dd>{issue.symptom}</dd>
                </div>
                <div>
                  <dt>根本原因</dt>
                  <dd>{issue.root_cause}</dd>
                </div>
                <div>
                  <dt>读者影响</dt>
                  <dd>{issue.reader_impact}</dd>
                </div>
                <div>
                  <dt>支持指标</dt>
                  <dd>{issue.supporting_metrics.join(" · ")}</dd>
                </div>
                <div>
                  <dt>可能方向</dt>
                  <dd>{issue.recommended_direction || issue.possible_direction || "—"}</dd>
                </div>
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
  const activeLabel = MODULES.find((m) => m.key === activeModule)?.label ?? activeModule;
  const handleReanalyze = onReanalyzeClick ?? onReanalyze;
  const statusLabel = analysisStatusLabel ?? "已完成";
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
        {headerExtra}
      </header>

      <nav className="wb2-nav" aria-label="全书分析模块">
        {MODULES.map((m, i) => (
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
