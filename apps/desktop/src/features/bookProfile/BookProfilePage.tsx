import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  AXIS_NAMES,
  AXIS_ORDER,
  SOURCE_NAMES,
  type BookProfile,
  confirmBookProfile,
  draftBookProfile,
  getBookProfile,
} from "./api";
import "./bookProfile.css";

/**
 * The confirmation gate — what kind of book is this, decided before anything expensive
 * reads it.
 *
 * The type judgement used to arrive with the final synthesis call, after every extraction
 * decision had already been made and could no longer be influenced by it. Now it comes
 * first, and a person ratifies it: the engine drafts, with the evidence behind each value on
 * screen, and the user's answer is what the run is carried out under.
 *
 * The dropdowns are closed sets because the axes dispatch extraction deltas and report
 * modules — a value the engine does not recognise is one it cannot act on. Their contents
 * come from the backend rather than a table kept here, for the same reason.
 */
export function BookProfilePage() {
  const { bookId } = useParams();
  const id = Number(bookId);
  const navigate = useNavigate();

  const [profile, setProfile] = useState<BookProfile | null>(null);
  const [choice, setChoice] = useState<Record<string, string>>({});
  const [error, setError] = useState<string>("");
  const [busy, setBusy] = useState(true);

  const load = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      // Drafting counts the whole text and costs nothing, so it is safe on load. It returns
      // an already-confirmed profile untouched rather than re-inferring over the user's
      // answer.
      const drafted = (await getBookProfile(id)) ?? (await draftBookProfile(id));
      setProfile(drafted);
      setChoice(
        Object.fromEntries(
          AXIS_ORDER.map((axis) => [axis, drafted.axes[axis]?.value ?? ""]),
        ),
      );
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "读取画像失败");
    } finally {
      setBusy(false);
    }
  }, [id]);

  useEffect(() => {
    if (Number.isFinite(id)) void load();
  }, [id, load]);

  async function confirm() {
    setBusy(true);
    setError("");
    try {
      await confirmBookProfile(id, choice);
      navigate(`/books/${id}/whole-book`);
    } catch (confirmError) {
      setError(confirmError instanceof Error ? confirmError.message : "确认失败");
      setBusy(false);
    }
  }

  if (busy && !profile) return <main className="bp-page"><p className="bp-status">正在统计全书…</p></main>;
  if (!profile) {
    return (
      <main className="bp-page">
        <p className="bp-status bp-error">{error || "没有可用的画像"}</p>
        <button type="button" onClick={() => void load()}>重试</button>
      </main>
    );
  }

  const stats = profile.statistics;
  const povDisagreement = profile.disagreements.find((d) => d.axis === "pov");
  const changed = (axis: string) => choice[axis] !== profile.axes[axis]?.value;
  const incomplete = AXIS_ORDER.filter((axis) => !choice[axis]);

  return (
    <main className="bp-page">
      <header className="bp-head">
        <div>
          <Link to={`/books/${id}`}>← 返回书籍</Link>
          <h1>画像确认</h1>
          <p>
            引擎已经把<b>全书正文</b>数过一遍，另外抽了 {profile.sample_chapters.length} 章交给模型判读。
            下面五项是草稿——<b>确认之后才会开始抽取</b>。这些标签决定要额外提取哪些事实、
            报告里出现哪些板块、评估按什么标准打分。
          </p>
        </div>
        <dl className="bp-stats">
          <div><dt>章节</dt><dd>{stats.chapters}</dd></div>
          <div><dt>字数</dt><dd>{stats.total_chars.toLocaleString()}</dd></div>
          <div><dt>状态</dt><dd>{profile.status === "confirmed" ? "已确认" : "草稿"}</dd></div>
        </dl>
      </header>

      {povDisagreement && !changed("pov") && (
        <section className="bp-conflict">
          <h2>两种方法给出了不同答案</h2>
          <p>
            <b>视角结构</b>上，全书计数与采样判读不一致。引擎采用了计数的结果，
            但这一项最值得你亲自看一眼。
          </p>
          <div className="bp-versus">
            <span>全书计数 → <b>{labelOf(profile, "pov", povDisagreement.counted)}</b></span>
            <span>采样判读（只看得到抽样章节）→ <b>{labelOf(profile, "pov", povDisagreement.read)}</b></span>
          </div>
        </section>
      )}

      <div className="bp-body">
        <section>
          <h2 className="bp-section">五项判断</h2>
          <p className="bp-hint">取值是固定的几种，不能自己填——引擎要靠它选择提取哪些字段。</p>

          {AXIS_ORDER.map((axis) => {
            const current = profile.axes[axis];
            const options = profile.options.find((o) => o.axis === axis)?.options ?? [];
            const source = changed(axis) ? "user" : current?.source ?? "";
            return (
              <div className="bp-axis" key={axis}>
                <div className="bp-axis-row">
                  <span className="bp-axis-name">{AXIS_NAMES[axis] ?? axis}</span>
                  <select
                    aria-label={AXIS_NAMES[axis] ?? axis}
                    value={choice[axis] ?? ""}
                    onChange={(e) => setChoice((p) => ({ ...p, [axis]: e.target.value }))}
                  >
                    <option value="">— 未判断，请选择 —</option>
                    {options.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                  {source && <span className="bp-src" data-source={source}>{SOURCE_NAMES[source] ?? source}</span>}
                </div>
                <p className="bp-why">{describe(axis, profile)}</p>
              </div>
            );
          })}

          <div className="bp-actions">
            <button type="button" className="bp-primary" disabled={busy || incomplete.length > 0} onClick={() => void confirm()}>
              确认并开始分析
            </button>
            <Link to={`/books/${id}`}>先不分析</Link>
            {incomplete.length > 0 && (
              <span className="bp-warn">
                还有 {incomplete.map((a) => AXIS_NAMES[a]).join("、")} 没有选择
              </span>
            )}
            {profile.active_deltas.length > 0 && (
              <span className="bp-deltas">将额外提取：{profile.active_deltas.join("、")}</span>
            )}
          </div>
          {error && <p className="bp-error">{error}</p>}
        </section>

        <section>
          <h2 className="bp-section">依据 · 人物出场分布</h2>
          <p className="bp-hint">
            全书按顺序切成十段，数每个人物在各段出现多少次。零成本，覆盖 100% 正文。
          </p>
          <NameCurves deciles={profile.name_deciles} />
          <p className="bp-foot">
            阴影是采样判读能看到的范围。后半本书才登场的人物落在样本之外，
            只有数完全书才看得见——这是视角结构由计数决定、而不是由采样决定的原因。
          </p>
        </section>
      </div>
    </main>
  );
}

/** The label the backend gave this value, so the screen never invents its own wording. */
function labelOf(profile: BookProfile, axis: string, value: string): string {
  return profile.options.find((o) => o.axis === axis)?.options.find((o) => o.value === value)?.label ?? value;
}

function describe(axis: string, profile: BookProfile): string {
  const stats = profile.statistics;
  const current = profile.axes[axis];
  if (axis === "monetization") {
    return `章长中位 ${Math.round(stats.chapter_chars_median)} 字（p10 ${stats.chapter_chars_p10} / p90 ${stats.chapter_chars_p90}），快餐流通常 1500–2500`;
  }
  if (axis === "length") return `全书 ${stats.total_chars.toLocaleString()} 字`;
  if (axis === "engine") {
    const hits = Object.entries(stats.vocabulary_per_10k ?? {})
      .sort((a, b) => b[1] - a[1])
      .map(([k, v]) => `${k} ${v}`)
      .join(" · ");
    return `词表密度（每万字）：${hits}${current?.source === "L0-B" ? "；采样判读为准，词表仅作交叉验证" : ""}`;
  }
  if (axis === "pov") {
    const e = current?.evidence as { share_first?: number; share_second?: number } | undefined;
    return e?.share_first != null
      ? `全书提及占比：第一名 ${e.share_first}，第二名 ${e.share_second}`
      : "由全书人名分布决定";
  }
  return current?.value ? "采样判读" : "样本里判断不出，请自行选择";
}

/**
 * Mention counts per tenth of the book, one small chart per character.
 *
 * This is the evidence the viewpoint axis rests on, and the reason it is not left to a
 * sampled read: a character who only appears in the back half is invisible to any sample of
 * the opening, and shows up here for nothing.
 */
function NameCurves({ deciles }: { deciles: Record<string, number[]> }) {
  const names = Object.entries(deciles).slice(0, 8);
  if (names.length === 0) {
    return <p className="bp-hint">还没有候选人名——采样判读尚未运行。</p>;
  }
  const peak = Math.max(1, ...names.flatMap(([, counts]) => counts));
  const W = 200;
  const H = 26;

  return (
    <div className="bp-curves">
      {names.map(([name, counts]) => {
        const step = W / Math.max(1, counts.length - 1);
        const line = counts
          .map((v, i) => `${i ? "L" : "M"}${(i * step).toFixed(1)} ${(H - (v / peak) * (H - 2) - 1).toFixed(1)}`)
          .join(" ");
        const total = counts.reduce((a, b) => a + b, 0);
        return (
          <div className="bp-curve" key={name}>
            <span className="bp-curve-name">{name}</span>
            <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img"
                 aria-label={`${name}，全书共 ${total} 次提及`}>
              <rect x="0" y="0" width={step} height={H} className="bp-sample-band" />
              <path d={`${line} L${W} ${H} L0 ${H} Z`} className="bp-curve-fill" />
              <path d={line} className="bp-curve-line" vectorEffect="non-scaling-stroke" />
            </svg>
            <span className="bp-curve-total">{total.toLocaleString()}</span>
          </div>
        );
      })}
    </div>
  );
}
