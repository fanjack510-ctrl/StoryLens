import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ErrorState, Loading } from "../../components/common/States";
import { ApiError } from "../../services/apiClient";
import {
  shortFormApi,
  type ShortFormReading,
  type ShortFormResult,
  type ShortFormSegment,
} from "../../services/shortFormApi";
import { downloadShortForm } from "./shortFormExport";
import "./shortForm.css";

/** 短篇精读 — the whole piece read in one sitting, one row per scene.
 *
 *  The layout is the corpus's own: sixty human breakdowns, twenty-one of which use a six-column
 *  table with one row per segment. It is a *table* rather than a set of panels because that is
 *  how it gets read — down the 情绪 column to find where the piece sags, across one row when
 *  something there looks worth learning from.
 */

const DIRECTION_LABEL: Record<string, string> = { up: "↑", down: "↓", flat: "—" };

function EmotionTrack({ segments }: { segments: ShortFormSegment[] }) {
  /** The emotional line as a strip, one cell per segment, widths in proportion to length.
   *
   *  Not a curve: the engine records a *direction* per segment, not a magnitude, and drawing a
   *  smooth line through three values would invent precision nobody measured. A strip shows the
   *  one thing that was measured — where it lifts and where it drops, and for how long.
   */
  if (!segments.length) return null;
  const total = segments.reduce((sum, s) => sum + Math.max(1, s.characters), 0);
  return (
    <div className="sf-track" role="img" aria-label="情绪走向">
      {segments.map((s) => (
        <div
          key={s.index}
          className={`sf-track-cell sf-${s.emotion_direction}`}
          style={{ flexGrow: Math.max(1, s.characters) / total }}
          title={`第 ${s.index} 段 · ${s.characters} 字 · ${s.emotion_note}`}
        >
          <span>{s.index}</span>
        </div>
      ))}
    </div>
  );
}

function BeatBar({ result }: { result: ShortFormResult }) {
  const last = result.segments.length || 1;
  if (!result.beats.length) return null;
  return (
    <div className="sf-beats">
      {result.beats.map((b) => {
        const span = b.segment_end - b.segment_start + 1;
        return (
          <section key={b.beat} style={{ flexGrow: span / last }}>
            <h3>
              <b>{b.beat}</b>
              <span>
                第 {b.segment_start}–{b.segment_end} 段 · {Math.round((span / last) * 100)}%
              </span>
            </h3>
            <p className="sf-beat-title">{b.title}</p>
            <p className="sf-beat-summary">{b.summary}</p>
          </section>
        );
      })}
    </div>
  );
}

function Reading({ reading }: { reading: ShortFormReading }) {
  const result = reading.result;
  return (
    <>
      {result.one_line ? <p className="sf-one-line">{result.one_line}</p> : null}
      <p className="sf-meta">
        {result.character_count.toLocaleString()} 字 · {result.segments.length} 段
        {result.genre ? ` · ${result.genre}` : ""} · {reading.provider_calls} 次模型调用
        {reading.segments_resplit > 0 ? ` · ${reading.segments_resplit} 段过长已再切` : ""}
      </p>
      <p className="sf-export">
        {/* No page budget, unlike the whole-book report: that one is an argument and is capped
            at twenty pages, this is a worksheet read beside the text and is as long as the
            piece has scenes. Truncating it would defeat its only purpose. */}
        <button type="button" onClick={() => downloadShortForm(reading)}>
          导出这份拆稿（HTML，可打印）
        </button>
      </p>

      <h2>起承转合</h2>
      <BeatBar result={result} />

      <h2>情绪走向</h2>
      <EmotionTrack segments={result.segments} />
      <div className="sf-emotion-lists">
        <div>
          <h3>上行</h3>
          {result.emotion_up.length ? (
            <ul>{result.emotion_up.map((x) => <li key={x}>{x}</li>)}</ul>
          ) : (
            <p className="sf-muted">没有测到明显的上行段。</p>
          )}
        </div>
        <div>
          <h3>下行</h3>
          {result.emotion_down.length ? (
            <ul>{result.emotion_down.map((x) => <li key={x}>{x}</li>)}</ul>
          ) : (
            <p className="sf-muted">没有测到明显的下行段。</p>
          )}
        </div>
      </div>

      {result.recurring?.length ? (
        <>
          <h2>
            反复出现的说法<small>逐字比对原文得出，不是模型的判断</small>
          </h2>
          <ul className="sf-recurring">
            {result.recurring.map((r) => (
              <li key={r.phrase}>
                <b>{r.phrase}</b>
                <span>第 {r.segments.join("、")} 段</span>
              </li>
            ))}
          </ul>
        </>
      ) : null}

      <h2>
        逐段拆稿<small>{result.segments.length} 段</small>
      </h2>
      <table className="sf-table">
        <thead>
          <tr>
            <th>段</th>
            <th>字数</th>
            <th>故事进展</th>
            <th>地点/人物</th>
            <th>事件/冲突</th>
            <th>学习之处</th>
            <th>读者此刻</th>
          </tr>
        </thead>
        <tbody>
          {result.segments.map((s) => (
            <tr key={s.index} className={`sf-row sf-${s.emotion_direction}`}>
              <th>
                {s.index}
                <span className="sf-para">
                  p{s.paragraph_start}–{s.paragraph_end}
                </span>
              </th>
              <td className="sf-num">{s.characters}</td>
              <td className="sf-phase">{s.phase || "—"}</td>
              <td className="sf-setting">{s.setting || "—"}</td>
              <td>
                {s.beats.length ? (
                  <ol className="sf-beats-list">
                    {s.beats.map((b, i) => (
                      <li key={`${s.index}-${i}`}>{b}</li>
                    ))}
                  </ol>
                ) : (
                  "—"
                )}
              </td>
              {/* Empty rather than padded: the instruction tells the model to leave this blank
                  when a segment has nothing worth learning from, and a manufactured
                  「这里写得不错」 would be worse than a gap. */}
              <td className="sf-craft">
                {s.craft || <span className="sf-muted">—</span>}
                {/* Inside the craft cell rather than a seventh column: the corpus's template is
                    six wide, and a callback is a property of the craft note, not a peer of it. */}
                {s.callback ? <span className="sf-callback">↩ {s.callback}</span> : null}
              </td>
              <td className="sf-emotion">
                <span className={`sf-dir sf-${s.emotion_direction}`}>
                  {DIRECTION_LABEL[s.emotion_direction] ?? "—"}
                </span>
                {s.emotion_note}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

export function ShortFormPage() {
  const params = useParams();
  const bookId = Number(params.bookId ?? 0);
  const queryClient = useQueryClient();
  const [genre, setGenre] = useState("");
  const [error, setError] = useState<string | null>(null);

  const prepare = useQuery({
    queryKey: ["short-form-prepare", bookId],
    queryFn: () => shortFormApi.prepare(bookId),
    enabled: bookId > 0,
    retry: false,
  });

  const analyse = useMutation({
    mutationFn: (force: boolean) => shortFormApi.analyse(bookId, { genre, force }),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["short-form-prepare", bookId] });
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "分析失败，请重试。");
    },
  });

  if (prepare.isLoading) return <Loading />;
  if (prepare.isError || !prepare.data) {
    return <ErrorState message="读不到这本书的信息。" />;
  }

  const data = prepare.data;
  const reading = analyse.data ?? data.latest;

  return (
    <div className="sf-page">
      <p className="sf-back">
        <Link to={`/books/${bookId}`}>← 返回书籍</Link>
      </p>
      <header>
        <p className="sf-kicker">短篇精读</p>
        <h1>{data.book_title}</h1>
      </header>

      {!data.is_short_form ? (
        <section className="sf-panel" data-testid="short-form-unavailable">
          <p>
            <b>这本书走全书分析，不走短篇精读。</b>
          </p>
          <p className="sf-muted">
            短篇精读适用于 {data.thresholds.max_chars.toLocaleString()} 字以内，
            或 {data.thresholds.soft_max_chars.toLocaleString()} 字以内且不超过{" "}
            {data.thresholds.max_chapters} 章的作品。这本书是 {data.chapter_count} 章、
            {data.character_count.toLocaleString()} 字。
          </p>
          <p>
            <Link to={`/books/${bookId}/whole-book`}>去全书分析 →</Link>
          </p>
        </section>
      ) : (
        <section className="sf-panel" data-testid="short-form-start">
          <h2>{reading ? "重新分析" : "开始精读"}</h2>
          <p className="sf-muted">
            整篇按场景切段，逐段给出故事进展、事件冲突、学习之处与读者情绪，
            另给一句话梗概、起承转合与情绪走向。约十次模型调用，一分半钟。
          </p>
          <fieldset className="sf-genre">
            <legend>作品类型（决定「打动人」按哪一套看）</legend>
            {data.genres.map((g) => (
              <label key={g} data-selected={g === genre}>
                <input
                  type="radio"
                  name="short-form-genre"
                  value={g}
                  checked={g === genre}
                  onChange={() => setGenre(g)}
                />
                {g}
              </label>
            ))}
          </fieldset>
          {error ? <p className="sf-error">{error}</p> : null}
          <div className="sf-actions">
            <button
              type="button"
              disabled={analyse.isPending || !genre}
              onClick={() => analyse.mutate(Boolean(reading))}
            >
              {analyse.isPending ? "分析中…约一分半钟" : reading ? "重新分析" : "开始精读"}
            </button>
            {!genre ? <span className="sf-muted">请先选一个类型</span> : null}
          </div>
          {reading ? (
            <p className="sf-muted sf-stored">
              已有一份读法（{reading.created_at}）。重新分析会再花一次模型费用。
            </p>
          ) : null}
        </section>
      )}

      {reading ? <Reading reading={reading} /> : null}
    </div>
  );
}
