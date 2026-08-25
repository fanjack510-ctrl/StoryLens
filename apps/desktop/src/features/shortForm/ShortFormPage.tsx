import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AnalysisFormSwitch } from "../../components/shortForm/AnalysisFormSwitch";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ErrorState, Loading } from "../../components/common/States";
import { ApiError } from "../../services/apiClient";
import {
  shortFormApi,
  type ShortFormReading,
  type ShortFormResult,
  type ShortFormSegment,
} from "../../services/shortFormApi";
import {
  downloadShortForm,
  downloadShortFormPdf,
  VipRequiredError,
} from "./shortFormExport";
import { ExternalUrlLink } from "../../components/common/ExternalUrlLink";
import { savedFileMessage } from "../../services/fileDownload";
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

function Reading({ bookId, reading }: { bookId: number; reading: ShortFormReading }) {
  const result = reading.result;
  const [pdfBusy, setPdfBusy] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [pdfSuccess, setPdfSuccess] = useState<string | null>(null);
  const [purchaseUrl, setPurchaseUrl] = useState("");

  const exportPdf = async () => {
    setPdfBusy(true);
    setPdfError(null);
    setPdfSuccess(null);
    setPurchaseUrl("");
    try {
      const saved = await downloadShortFormPdf(bookId, reading);
      setPdfSuccess(savedFileMessage(saved));
    } catch (err) {
      setPdfError(err instanceof Error ? err.message : "PDF 导出失败，请重试。");
      if (err instanceof VipRequiredError) setPurchaseUrl(err.afdianUrl);
    } finally {
      setPdfBusy(false);
    }
  };
  return (
    <>
      {result.one_line ? <p className="sf-one-line">{result.one_line}</p> : null}
      <p className="sf-meta">
        {result.character_count.toLocaleString()} 字 · {result.segments.length} 段
        {result.genre ? ` · ${result.genre}` : ""} · {reading.provider_calls} 次模型调用
        {reading.segments_resplit > 0 ? ` · ${reading.segments_resplit} 段过长已再切` : ""}
      </p>
      <div className="sf-export">
        {/* No page budget, unlike the whole-book report: that one is an argument and is capped
            at twenty pages, this is a worksheet read beside the text and is as long as the
            piece has scenes. Truncating it would defeat its only purpose. */}
        <button type="button" onClick={() => downloadShortForm(reading)}>
          导出 HTML
        </button>
        <button type="button" disabled={pdfBusy} onClick={() => void exportPdf()}>
          {pdfBusy ? "正在生成 PDF…" : "导出 PDF · PRO"}
        </button>
      </div>
      {pdfError ? (
        <p className="sf-export-error" role="alert">
          {pdfError}
          {purchaseUrl ? (
            <ExternalUrlLink url={purchaseUrl}>
              获取 Pro 授权
            </ExternalUrlLink>
          ) : null}
        </p>
      ) : null}
      {pdfSuccess ? <p className="sf-export-success" role="status">{pdfSuccess}</p> : null}

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
  const [resegment, setResegment] = useState(false);

  const prepare = useQuery({
    queryKey: ["short-form-prepare", bookId],
    queryFn: () => shortFormApi.prepare(bookId),
    enabled: bookId > 0,
    retry: false,
  });

  const analyse = useMutation({
    mutationFn: (force: boolean) => shortFormApi.analyse(bookId, { genre, force, resegment }),
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
    // ErrorState reads `error.message`, so handing it a bare `message` prop left `error`
    // undefined and the error screen threw on the way to reporting the error.
    return (
      <ErrorState
        error={
          prepare.error instanceof Error
            ? prepare.error
            : new Error("读不到这本书的信息。")
        }
        retry={() => void prepare.refetch()}
      />
    );
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
        <AnalysisFormSwitch bookId={bookId} />
      </header>

      {!data.is_short_form ? (
        <section className="sf-panel" data-testid="short-form-unavailable">
          {data.short_form_allowed !== false ? (
            <>
              <p>
                <b>这本书按长篇读，所以走全书分析。</b>
              </p>
              <p className="sf-muted">
                {data.chapter_count} 章、{data.character_count.toLocaleString()} 字。
                章数不参与这个判断——上面那行可以随时改。
              </p>
            </>
          ) : (
            <>
              <p>
                <b>
                  这本书超过 {(data.hard_max_chars ?? 150_000).toLocaleString()} 字，不能按短篇读。
                </b>
              </p>
              <p className="sf-muted">
                {data.chapter_count} 章、{data.character_count.toLocaleString()} 字。
                切段要把全文一次发给模型，超过这个长度就装不下——这一条改不了，
                不是偏好问题。
              </p>
            </>
          )}
          <p>
            <Link to={`/books/${bookId}/whole-book`}>去全书分析 →</Link>
          </p>
        </section>
      ) : (
        <section className="sf-panel" data-testid="short-form-start">
          <h2>{reading ? "重新分析" : "开始精读"}</h2>
          {!data.segmentation.fits && (
            // A warning, not a gate. Segmentation sends the whole piece in one call, so a long
            // work will not fit — but the reader asked for this reading, and the estimate is
            // what they need to decide, not a refusal. Shown before the button because that
            // one call is the most expensive of the run.
            <p className="sf-warn" role="alert" data-testid="short-form-oversize">
              <b>这篇大概率切不动。</b>
              切段要把全文一次发出去，估计约{" "}
              {Math.round(data.segmentation.estimated_tokens / 1000).toLocaleString()}k token，
              超过模型 {Math.round(data.segmentation.context_window / 1000)}k 的上下文。
              仍然可以开始，但那一次调用很可能失败，而它是整轮里最贵的一次。
            </p>
          )}
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
            <>
              <p className="sf-muted sf-stored">
                已有一份读法（{reading.created_at}）。重新分析会再花一次模型费用。
              </p>
              <label className="sf-reseg">
                <input
                  type="checkbox"
                  checked={resegment}
                  onChange={(e) => setResegment(e.target.checked)}
                />
                {/* Off by default. Re-reading is for a better reading; re-cutting renumbers every
                    segment, and every 「呼应第 N 段」 the last reading wrote stops lining up. */}
                重新切分场景（会改变段号，上一份读法里的「呼应第 N 段」将不再对应）
              </label>
            </>
          ) : null}
        </section>
      )}

      {reading ? <Reading bookId={bookId} reading={reading} /> : null}
    </div>
  );
}
