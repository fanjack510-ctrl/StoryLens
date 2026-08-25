/** 「读懂」的报告：专著、教材、工具书。
 *
 *  它跟评测/拆文那份报告刻意长得不一样，因为回答的问题不同。那两份回答「这本小说写得怎么样 /
 *  是怎么搭起来的」；这一份回答的是**「我不读原文，能知道什么」**——读者没时间，或者读不动
 *  原文的语言。
 *
 *  所以版面上第一位的不是内容，是**可信度**：覆盖了多少节、哪几节没读到。小说漏一段，报告读
 *  起来仍然完整；知识类书漏一节，读者拿它替代原文，而他不会知道自己漏了什么。把覆盖率藏进角
 *  落里，等于让他在不知情的情况下信一份残缺的东西。
 *
 *  每条主张都挂着节号，就是为了让他能翻回原文核对。对这类书，能不能翻回去，就是这份摘要可不
 *  可信的分界线。
 */
import { useState } from "react";
import type { ComprehendResult } from "../../../services/wholeBookFreeProductApi";
import {
  VipRequiredError,
  downloadComprehendHtml,
  downloadComprehendPdf,
} from "../comprehendDownload";
import { compactSection } from "../comprehendCompact";
import "../wholeBookV2.css";

function plainText(value: string | null | undefined): string {
  return String(value ?? "")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/^\s*[-*]\s+/gm, "")
    .trim();
}

type LabeledPart = { label: string; body: string };

/** The synthesis prompt occasionally returns light Markdown labels. Parse only that small,
 * known shape instead of treating model text as HTML or enabling a general Markdown surface. */
function labeledParts(value: string | null | undefined): LabeledPart[] {
  const source = String(value ?? "").trim();
  const parts: LabeledPart[] = [];
  const pattern = /\*\*([^*]+)\*\*\s*[：:]\s*([\s\S]*?)(?=\s*\*\*[^*]+\*\*\s*[：:]|$)/g;
  for (const match of source.matchAll(pattern)) {
    const label = plainText(match[1]);
    const body = plainText(match[2]);
    if (label && body) parts.push({ label, body });
  }
  if (parts.length) return parts;

  // Some providers omit Markdown emphasis but keep the same semantic labels. Only split
  // the labels this report owns so ordinary prose remains intact and model text never
  // becomes executable markup.
  const knownLabel = /(该读|不必读|适合|不适合|知道|会做|注意)[：:]/g;
  const matches = [...source.matchAll(knownLabel)];
  return matches.flatMap((match, index) => {
    const label = match[1];
    const start = (match.index ?? 0) + match[0].length;
    const end = matches[index + 1]?.index ?? source.length;
    const body = plainText(source.slice(start, end)).replace(/^[。；\s]+|[。；\s]+$/g, "");
    return label && body ? [{ label, body }] : [];
  });
}

function Takeaways({ value }: { value: string | null | undefined }) {
  const parts = labeledParts(value);
  if (!parts.length) return <p>{plainText(value)}</p>;
  return (
    <ul className="cmp-takeaways">
      {parts.map((part, index) => (
        <li key={`${part.label}-${index}`}>
          <b>{part.label}</b>
          <span>{part.body}</span>
        </li>
      ))}
    </ul>
  );
}

function chapterAnchor(index: number): string {
  return `cmp-chapter-${index + 1}`;
}

function Items({ label, items, tone }: { label: string; items: string[]; tone?: string }) {
  if (!items?.length) return null;
  return (
    <>
      <div className="cmp-k">{label}</div>
      <ul className={tone ? `cmp-list cmp-${tone}` : "cmp-list"}>
        {items.map((x, i) => (
          <li key={`${label}-${i}`}>{x}</li>
        ))}
      </ul>
    </>
  );
}

export function ComprehendReportView({
  data,
  title,
  runId,
}: {
  data: ComprehendResult;
  title: string;
  runId?: number | null;
}) {
  const pct = Math.round((data.coverage ?? 0) * 100);
  const missed = (data.sections_total ?? 0) - (data.sections_covered ?? 0);
  const [busy, setBusy] = useState(false);
  const [vip, setVip] = useState<{ message: string; url: string } | null>(null);
  const [note, setNote] = useState("");

  const onExport = async () => {
    if (busy || runId == null) return;
    setBusy(true);
    setVip(null);
    setNote("");
    try {
      await downloadComprehendPdf(runId, data, title);
    } catch (err) {
      if (err instanceof VipRequiredError) {
        // 门拒绝是一个答案，不是故障——这时不落回 HTML，否则等于把收费的东西换个名字发出去。
        setVip({ message: err.message, url: err.afdianUrl });
      } else {
        downloadComprehendHtml(data, title);
        setNote(
          (err instanceof Error && err.message ? err.message : "PDF 生成失败") +
            "；已导出同内容的 HTML，浏览器里打印即得 PDF",
        );
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="cmp-report" data-testid="comprehend-report">
      <header className="cmp-head">
        <div className="cmp-title-row">
          <div>
            <p className="cmp-kicker">读懂报告 · 专著与工具书</p>
            <h1>{title}</h1>
          </div>
          {runId != null && (
            <div className="cmp-actions">
              <button type="button" data-testid="comprehend-export-pdf" disabled={busy} onClick={() => void onExport()}>
                {busy ? "正在生成…" : "导出 PDF · PRO"}
              </button>
              <button type="button" onClick={() => downloadComprehendHtml(data, title)}>
                导出 HTML
              </button>
            </div>
          )}
        </div>
        {/* 可信度放在最前面，而不是报告末尾的小字。读者要先知道这份东西能不能替代原文。 */}
        <p
          className={missed === 0 ? "cmp-trust ok" : data.trustworthy ? "cmp-trust partial" : "cmp-trust warn"}
          data-testid="comprehend-coverage"
        >
          {missed === 0
            ? `覆盖 ${data.sections_covered}/${data.sections_total} 节——全书都读到了`
            : data.trustworthy
              ? `覆盖 ${data.sections_covered}/${data.sections_total} 节（${pct}%）· 有 ${missed} 节没读到，涉及它们的内容请回原文核对`
              : `只覆盖了 ${data.sections_covered}/${data.sections_total} 节（${pct}%），有 ${missed} 节没读到。` +
                "这份摘要不完整，涉及那几节的内容请回原文核对。"}
        </p>
        {note && <p className="cmp-note">{note}</p>}
        {vip && (
          <div className="cmp-vip" role="alert" data-testid="comprehend-vip-notice">
            <b>PDF 导出是专业版功能</b>
            <p>{vip.message}</p>
            <p>
              {vip.url ? (
                <a href={vip.url} target="_blank" rel="noreferrer">
                  前往爱发电购买 StoryLens Pro →
                </a>
              ) : (
                <span>购买入口尚未配置，请联系作者获取授权码。</span>
              )}
              　已有授权码？在 设置 → 授权 中激活。
            </p>
            <button type="button" onClick={() => setVip(null)}>
              知道了
            </button>
          </div>
        )}
      </header>

      {data.book?.error ? (
        <p className="cmp-error">全书层未能产出：{data.book.error}</p>
      ) : (
        <section className="cmp-overview" aria-labelledby="cmp-overview-title">
          <div className="cmp-section-heading">
            <p className="cmp-kicker">全书总览</p>
            <h2 id="cmp-overview-title">先用三分钟掌握这本书</h2>
          </div>
          <div className="cmp-summary-card">
            <h3>一段话读懂</h3>
            <p>{plainText(data.book?.one_paragraph)}</p>
          </div>
          <div className="cmp-overview-grid">
            <article className="cmp-overview-card cmp-argument">
              <h3>核心主张</h3>
              <p>{plainText(data.book?.argument)}</p>
            </article>
            <article className="cmp-overview-card cmp-actions-card">
              <h3>读完可以带走什么</h3>
              <Takeaways value={data.book?.what_you_get} />
            </article>
            <article className="cmp-overview-card cmp-audience-card">
              <h3>适合谁，也适合跳过谁</h3>
              <Takeaways value={data.book?.who_should_read} />
            </article>
          </div>
        </section>
      )}

      {data.chapters?.length > 0 && (
        <nav className="cmp-chapter-nav" aria-label="章节导航">
          <div>
            <span>章节导航</span>
            <small>{data.chapters.length} 章</small>
          </div>
          <ol>
            {data.chapters.map((chapter, index) => (
              <li key={`${chapter.chapter}-${chapter.title}`}>
                <a href={`#${chapterAnchor(index)}`}>
                  <b>{String(index + 1).padStart(2, "0")}</b>
                  <span>{plainText(chapter.title || chapter.chapter)}</span>
                </a>
              </li>
            ))}
          </ol>
        </nav>
      )}

      {/* 逐节默认折起来。读者要的是「不读原文也知道讲了什么」——那由上面四张卡和章级摘要
          回答；逐节是拿来查的，不是拿来读的。全都摊开，报告就跟正文一样长，等于没摘要。 */}
      <div className="cmp-chapters">
      {data.chapters?.map((chapter, chapterIndex) => {
        const sections = chapter.sections ?? [];
        const claimCount = sections.reduce((sum, section) => sum + (section.claims?.length ?? 0), 0);
        const actionCount = sections.reduce((sum, section) => sum + (section.actions?.length ?? 0), 0);
        const evidenceCount = sections.reduce((sum, section) => sum + (section.evidence?.length ?? 0), 0);
        return (
        <article className="cmp-ch" id={chapterAnchor(chapterIndex)} key={`${chapter.chapter}-${chapter.title}`}>
          <header className="cmp-ch-head">
            <span className="cmp-ch-number">{String(chapterIndex + 1).padStart(2, "0")}</span>
            <div>
              <p className="cmp-ch-label">{plainText(chapter.chapter)}</p>
              <h2>{plainText(chapter.title || chapter.chapter)}</h2>
            </div>
          </header>
          {chapter.summary && <p className="cmp-lead">{plainText(chapter.summary)}</p>}
          {chapter.through_line && <p className="cmp-line"><b>本章主线</b>{plainText(chapter.through_line)}</p>}
          {chapter.error && <p className="cmp-error">{chapter.error}</p>}

          <div className="cmp-ch-stats" aria-label="本章内容统计">
            <span>{sections.length} 节</span>
            <span>{claimCount} 个主张</span>
            <span>{actionCount} 个做法</span>
            <span>{evidenceCount} 条依据</span>
          </div>

          <details className="cmp-fold">
            <summary><span>展开逐节细看</span><small>{sections.length} 节</small></summary>
            {chapter.sections?.map((section, i) => {
              if (section.error) {
                // 读失败的节要留在原位并说出来。悄悄跳过，读者会以为这一节本来就没内容。
                return (
                  <div className="cmp-sec bad" key={`${section.label}-${i}`}>
                    <h4>{plainText(section.label)}</h4>
                    <p className="cmp-error">这一节没有读到：{section.error}</p>
                  </div>
                );
              }
              const k = compactSection(section);
              return (
                <div className="cmp-sec" key={`${section.label}-${i}`}>
                  <h4>{plainText(section.label)}</h4>
                  <Items label="主张" items={k.claims} />
                  <Items label="做法" items={k.actions} tone="do" />
                  {k.citations.length > 0 && (
                    <p className="cmp-cite">依据：{k.citations.join("、")}</p>
                  )}
                  {k.terms.length > 0 && (
                    <p className="cmp-cite">
                      术语：{k.terms.join("；")}
                      {k.hiddenTerms > 0 ? `　等 ${k.hiddenTerms + k.terms.length} 个` : ""}
                    </p>
                  )}
                  {/* 原文对依据的描述和模型的存疑不删，只是不摊开：删掉的东西读者不知道
                      自己没看到，收起来的他知道。 */}
                  {(k.fullEvidence.length > 0 || k.openQuestions.length > 0) && (
                    <details className="cmp-more">
                      <summary>依据原文与存疑</summary>
                      <Items label="依据" items={k.fullEvidence} />
                      <Items label="存疑" items={k.openQuestions} tone="q" />
                    </details>
                  )}
                </div>
              );
            })}
          </details>
        </article>
      )})}
      </div>

      <footer className="cmp-foot">
        <p>
          结构由程序从原书解析：{(data.rules ?? []).join("；") || "—"}。共 {data.provider_calls} 次模型调用。
        </p>
        {data.failures?.length > 0 && (
          <details data-testid="comprehend-failures">
            <summary>没读到的 {data.failures.length} 处</summary>
            <ul>
              {data.failures.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          </details>
        )}
      </footer>
    </section>
  );
}
