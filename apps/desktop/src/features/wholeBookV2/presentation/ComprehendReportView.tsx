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
import type { ComprehendResult } from "../../../services/wholeBookFreeProductApi";

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
}: {
  data: ComprehendResult;
  title: string;
}) {
  const pct = Math.round((data.coverage ?? 0) * 100);
  const missed = (data.sections_total ?? 0) - (data.sections_covered ?? 0);

  return (
    <section className="cmp-report" data-testid="comprehend-report">
      <header className="cmp-head">
        <p className="cmp-kicker">读懂 · 专著与工具书</p>
        <h1>{title}</h1>
        {/* 可信度放在最前面，而不是报告末尾的小字。读者要先知道这份东西能不能替代原文。 */}
        <p
          className={data.trustworthy ? "cmp-trust ok" : "cmp-trust warn"}
          data-testid="comprehend-coverage"
        >
          {data.trustworthy
            ? `覆盖 ${data.sections_covered}/${data.sections_total} 节（${pct}%）——全书都读到了`
            : `只覆盖了 ${data.sections_covered}/${data.sections_total} 节（${pct}%），有 ${missed} 节没读到。` +
              "这份摘要不完整，涉及那几节的内容请回原文核对。"}
        </p>
      </header>

      {data.book?.error ? (
        <p className="cmp-error">全书层未能产出：{data.book.error}</p>
      ) : (
        <div className="cmp-cards">
          {[
            ["一段话说清这本书", data.book?.one_paragraph],
            ["全书的主张", data.book?.argument],
            ["读完能带走什么", data.book?.what_you_get],
            ["谁该读、谁不必读", data.book?.who_should_read],
          ]
            .filter(([, body]) => Boolean((body as string) || ""))
            .map(([label, body]) => (
              <div className="cmp-card" key={label as string}>
                <h3>{label as string}</h3>
                <p>{body as string}</p>
              </div>
            ))}
        </div>
      )}

      {data.chapters?.map((chapter) => (
        <section className="cmp-ch" key={`${chapter.chapter}-${chapter.title}`}>
          <h2>
            {chapter.chapter} {chapter.title}
          </h2>
          {chapter.summary && <p className="cmp-lead">{chapter.summary}</p>}
          {chapter.through_line && <p className="cmp-line">主线：{chapter.through_line}</p>}
          {chapter.error && <p className="cmp-error">{chapter.error}</p>}

          {chapter.sections?.map((section, i) =>
            section.error ? (
              // 读失败的节要留在原位并说出来。悄悄跳过，读者会以为这一节本来就没内容。
              <div className="cmp-sec bad" key={`${section.label}-${i}`}>
                <h4>{section.label}</h4>
                <p className="cmp-error">这一节没有读到：{section.error}</p>
              </div>
            ) : (
              <div className="cmp-sec" key={`${section.label}-${i}`}>
                <h4>{section.label}</h4>
                <Items label="主张" items={section.claims} />
                <Items label="依据" items={section.evidence} />
                <Items label="做法" items={section.actions} tone="do" />
                <Items label="术语" items={section.terms} tone="term" />
                <Items label="存疑" items={section.open_questions} tone="q" />
              </div>
            ),
          )}
        </section>
      ))}

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
