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
        <div className="wb2-causal">
          {story.causal_chain.map((x, i) => (
            <div key={x}>
              <b>{i + 1}</b>
              <span>{x}</span>
              {i < story.causal_chain.length - 1 && <i>→</i>}
            </div>
          ))}
        </div>
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
      {tab === "人物关系" && (
        <table>
          <thead>
            <tr>
              <th>关系</th>
              <th>类型</th>
              <th>章节范围</th>
            </tr>
          </thead>
          <tbody>
            {chars.relationships.map((r) => (
              <tr key={`${r.person_a}-${r.person_b}`}>
                <th>
                  {r.person_a} ↔ {r.person_b}
                </th>
                <td>{r.relationship_type}</td>
                <td>
                  {r.chapter_start}–{r.chapter_end}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

function SuspenseModule({ data }: { data: WholeBookAnalysisV2 }) {
  const [selected, setSelected] = useState(0);
  const hooks = data.suspense.lifecycles;
  const h = hooks[selected];

  return (
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
  );
}

function PacingModule({ data }: { data: WholeBookAnalysisV2 }) {
  const W = 1100;
  const H = 390;
  const pad = 48;
  const [hover, setHover] = useState(0);
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
      <div className="wb2-legend">
        {series.map((s, i) => (
          <span key={s.name}>
            <i style={{ background: PACING_COLORS[i] }} />
            {s.name}
          </span>
        ))}
      </div>
      <div className="wb2-chart-wrap">
        <svg className="wb2-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="全书节奏曲线">
          {[20, 40, 60, 80].map((v) => (
            <line className="grid" key={v} x1={pad} x2={W - 10} y1={H - 48 - v * 3} y2={H - 48 - v * 3} />
          ))}
          {series.map((s, si) => (
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
          ))}
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
        {HEATMAP_DIMS.map((d) => (
          <Fragment key={d.key}>
            <strong>{d.label}</strong>
            {ch.heatmap.map((x, i) => (
              <button
                aria-label={`${d.label} ${x.chapter_start}-${x.chapter_end} ${x[d.key]}`}
                onClick={() => setSelected(i)}
                key={`${d.key}${i}`}
                style={{
                  background: `color-mix(in srgb, #2f6b57 ${x[d.key]}%, #edf2ef)`,
                }}
              />
            ))}
          </Fragment>
        ))}
      </div>
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

function AssessmentModule({ data }: { data: WholeBookAnalysisV2 }) {
  const [selected, setSelected] = useState(0);
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
          <h2>等级只是入口，结论和依据更重要</h2>
        </div>
        <div className="wb2-dimensions">
          {a.dimensions.map((x) => (
            <article key={x.dimension}>
              <b>{x.rating}</b>
              <div>
                <h3>{x.dimension}</h3>
                <strong>{x.conclusion}</strong>
                <p>{x.supporting_metrics.join(" · ")}</p>
              </div>
            </article>
          ))}
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
