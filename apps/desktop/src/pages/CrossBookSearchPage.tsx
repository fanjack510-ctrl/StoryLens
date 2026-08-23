import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { crossBookApi } from "../services/crossBookApi";
import type { KeywordResult, MeaningMatch, MeaningResult, SearchHit } from "../services/crossBookApi";
import { ApiError } from "../services/apiClient";
import { Loading } from "../components/common/States";
import { PageHeader, PageSubtitle, PageTitle } from "../components/ui/PageHeader";

/** 跨书检索：在所有分析过的书里找东西。
 *
 *  一个输入框，两种找法，页面必须让这个差别看得见：
 *   · 关键词——确定、即时、覆盖全部条目（含逐章钩子和原文证据）。免费。
 *   · 按意思——一次模型判断，只覆盖写法层。Pro。
 *
 *  覆盖面不同这件事不能藏起来。用户以为搜过了全部、其实只搜了写法层，
 *  「没找到」就会被读成「这些书里没有」——那是一个错的结论。
 */
export function CrossBookSearchPage() {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");

  const scope = useQuery({ queryKey: ["cross-book-scope"], queryFn: crossBookApi.scope });
  const keyword = useQuery({
    queryKey: ["cross-book-search", submitted],
    queryFn: () => crossBookApi.search(submitted, { limit: 40 }),
    enabled: submitted.length > 0,
  });
  const meaning = useMutation<MeaningResult, unknown, string>({
    mutationFn: (q: string) => crossBookApi.byMeaning(q),
  });

  const proBlocked =
    meaning.error instanceof ApiError &&
    meaning.error.code === "CROSS_BOOK_SEARCH_REQUIRES_PRO";

  const run = () => {
    const q = query.trim();
    if (!q) return;
    setSubmitted(q);
    meaning.reset();
  };

  return (
    <section className="page cross-book" data-testid="cross-book-page">
      <PageHeader>
        <div>
          <PageTitle>跨书检索</PageTitle>
          <PageSubtitle data-testid="cb-scope">
            {scope.data
              ? `${scope.data.book_count} 本书 · ${scope.data.item_count.toLocaleString()} 条可检索内容`
              : "正在统计可检索范围…"}
          </PageSubtitle>
        </div>
        <Link className="secondary" to="/library" data-testid="cb-back">
          回书库
        </Link>
      </PageHeader>

      <div className="panel cb-search">
        <form
          className="cb-form"
          onSubmit={(e) => {
            e.preventDefault();
            run();
          }}
        >
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="想找什么？比如「反转」，或者「让主角一出场就打破读者预期的写法」"
            aria-label="检索内容"
            data-testid="cb-input"
          />
          <button type="submit" className="primary" disabled={!query.trim()} data-testid="cb-run">
            找
          </button>
        </form>
        {scope.data ? (
          <p className="muted cb-hint" data-testid="cb-hint">
            关键词检索覆盖全部 {scope.data.item_count.toLocaleString()} 条；
            「按意思找」只覆盖其中的写法层 {scope.data.craft_count} 条
            （技法、高光片段、配角功能、主要人物）。
          </p>
        ) : null}
      </div>

      {submitted ? (
        <>
          <div className="panel cb-keyword" data-testid="cb-keyword">
            <h2>关键词命中</h2>
            {keyword.isLoading ? (
              <Loading />
            ) : keyword.data ? (
              <KeywordResults data={keyword.data} />
            ) : null}
          </div>

          <div className="panel cb-meaning" data-testid="cb-meaning">
            <h2>按意思找</h2>
            {!meaning.data ? (
              <>
                <p className="muted cb-source">
                  关键词答不了「让主角一出场就打破读者预期的写法」这种问题——
                  「打破读者预期」这几个字可能一次都没出现过。这一步让模型读进每条写法，
                  挑出真正符合的，并说明为什么。
                </p>
                <button
                  type="button"
                  className="primary"
                  data-testid="cb-meaning-run"
                  disabled={meaning.isPending}
                  onClick={() => meaning.mutate(submitted)}
                >
                  {meaning.isPending ? "正在找……" : "按意思找这一句"}
                </button>
                {proBlocked ? <ProNotice error={meaning.error as ApiError} /> : null}
                {meaning.error && !proBlocked ? (
                  <p className="wbv2-error" data-testid="cb-meaning-error">
                    {meaning.error instanceof ApiError
                      ? meaning.error.message
                      : "这次检索没能完成，请重试。"}
                  </p>
                ) : null}
              </>
            ) : (
              <MeaningResults data={meaning.data} />
            )}
          </div>
        </>
      ) : null}
    </section>
  );
}

function KeywordResults({ data }: { data: KeywordResult }) {
  if (data.message) {
    return <p className="notice">{data.message}</p>;
  }
  if (data.total === 0) {
    return (
      <p className="notice" data-testid="cb-keyword-none">
        「{data.query}」在 {data.searched_items.toLocaleString()} 条内容里一次都没出现。
        换个说法试试，或者用下面的「按意思找」——它不靠字面匹配。
      </p>
    );
  }
  return (
    <>
      <p className="muted cb-source" data-testid="cb-keyword-count">
        在 {data.searched_items.toLocaleString()} 条里命中 {data.total} 条
        {data.truncated ? `，显示前 ${data.hits.length} 条` : ""}。
      </p>
      <ul className="cb-hits">
        {data.hits.map((h, i) => (
          <HitRow key={`${h.book_id}-${h.kind}-${h.title}-${i}`} hit={h} />
        ))}
      </ul>
    </>
  );
}

function HitRow({ hit }: { hit: SearchHit }) {
  return (
    <li className="cb-hit" data-testid={`cb-hit-${hit.kind}`}>
      <div className="cb-hit-head">
        <span className={`cb-kind cb-kind--${hit.kind}`}>{hit.kind_label}</span>
        <b>{hit.title}</b>
        <span className="cb-where">
          《{hit.book_title}》{hit.chapter ? ` 第 ${hit.chapter} 章` : ""}
        </span>
      </div>
      {hit.snippet && hit.snippet !== hit.title ? <p>{hit.snippet}</p> : null}
    </li>
  );
}

function MeaningResults({ data }: { data: MeaningResult }) {
  return (
    <>
      <p className="muted cb-source" data-testid="cb-meaning-scope">
        {data.scope_note} 本次读了 {data.searched_craft_items} 条
        {data.truncated ? `（共 ${data.total_craft_items} 条，超出部分未参与）` : ""}
        ，由 {data.provider_name} / {data.model_name} 判断。
      </p>
      {data.matches.length === 0 ? (
        <p className="notice" data-testid="cb-meaning-none">
          写法层里没有符合的。这是一个有用的答案——它说明这几本书里没有你要找的那种写法，
          而不是你问错了。
        </p>
      ) : (
        <ol className="cb-matches">
          {data.matches.map((m, i) => (
            <MatchRow key={`${m.book_id}-${m.title}-${i}`} match={m} />
          ))}
        </ol>
      )}
    </>
  );
}

function MatchRow({ match }: { match: MeaningMatch }) {
  return (
    <li className="cb-match" data-testid={`cb-match-${match.kind}`}>
      <div className="cb-hit-head">
        <span className={`cb-kind cb-kind--${match.kind}`}>{match.kind_label}</span>
        <b>{match.title}</b>
        <span className="cb-where">
          《{match.book_title}》{match.chapter ? ` 第 ${match.chapter} 章` : ""}
        </span>
      </div>
      {/* 「为什么符合」不是装饰——没有它，一条结果和一次随机命中没法区分。 */}
      {match.why ? <p className="cb-why">{match.why}</p> : null}
      {match.detail ? <p className="muted">{match.detail}</p> : null}
    </li>
  );
}

function ProNotice({ error }: { error: ApiError }) {
  const details = (error.detail ?? {}) as { afdian_product_url?: string; product_label?: string };
  return (
    <div className="notice cp-pro" data-testid="cb-pro-required" role="alert">
      <b>{error.message}</b>
      {details.afdian_product_url ? (
        <a href={details.afdian_product_url} target="_blank" rel="noreferrer">
          了解 {details.product_label || "Pro"} →
        </a>
      ) : null}
    </div>
  );
}
