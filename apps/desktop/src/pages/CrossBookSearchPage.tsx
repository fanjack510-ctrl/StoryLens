import { useState } from "react";
import { ProTag } from "../components/ui/ProTag";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { crossBookApi } from "../services/crossBookApi";
import type { KeywordResult, MeaningMatch, MeaningResult, SearchHit } from "../services/crossBookApi";
import { ApiError } from "../services/apiClient";
import { Loading } from "../components/common/States";
import { PageHeader, PageSubtitle, PageTitle } from "../components/ui/PageHeader";

type SearchMode = "keyword" | "meaning";

/** 找参考：从已经保存的分析产物中，跨书找回原句或相似写法。
 *
 *  这不是全文搜索，也不是知识库。两种找法必须从入口起就分开：
 *   · 找原句 / 定位——字面匹配，覆盖全部分析条目。免费。
 *   · 找相似写法——模型判断，只覆盖写法层。Pro。
 */
export function CrossBookSearchPage() {
  const [mode, setMode] = useState<SearchMode>("keyword");
  const [query, setQuery] = useState("");
  const [submittedKeyword, setSubmittedKeyword] = useState("");

  const scope = useQuery({ queryKey: ["cross-book-scope"], queryFn: crossBookApi.scope });
  const keyword = useQuery({
    queryKey: ["cross-book-search", submittedKeyword],
    queryFn: () => crossBookApi.search(submittedKeyword, { limit: 40 }),
    enabled: submittedKeyword.length > 0,
  });
  const meaning = useMutation<MeaningResult, unknown, string>({
    mutationFn: (q: string) => crossBookApi.byMeaning(q),
  });

  const proBlocked =
    meaning.error instanceof ApiError &&
    meaning.error.code === "CROSS_BOOK_SEARCH_REQUIRES_PRO";

  const selectMode = (next: SearchMode) => {
    setMode(next);
    meaning.reset();
  };

  const run = () => {
    const text = query.trim();
    if (!text) return;
    if (mode === "keyword") {
      setSubmittedKeyword(text);
      return;
    }
    meaning.mutate(text);
  };

  return (
    <section className="page cross-book" data-testid="cross-book-page">
      <PageHeader>
        <div>
          <PageTitle>找参考</PageTitle>
          <PageSubtitle data-testid="cb-scope">
            {scope.data
              ? `从 ${scope.data.book_count} 本已分析小说的 ${scope.data.item_count.toLocaleString()} 条内容中查找`
              : "正在统计可查找的分析内容…"}
          </PageSubtitle>
        </div>
        <Link className="secondary" to="/library" data-testid="cb-back">回书库</Link>
      </PageHeader>

      <div className="cb-purpose">
        <span className="cb-purpose-mark" aria-hidden="true">⌕</span>
        <div>
          <strong>这里找的是分析结果，不是整本小说全文</strong>
          <p>适合找回“哪本书用过这一招”或“某段分析在哪里”；找到后回原书核对，再决定是否沉淀进知识库。</p>
        </div>
      </div>

      <section className="cb-workspace" aria-label="选择找参考的方式">
        <div className="cb-mode-switch" role="tablist" aria-label="找参考方式">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "keyword"}
            className={mode === "keyword" ? "is-active" : ""}
            data-testid="cb-mode-keyword"
            onClick={() => selectMode("keyword")}
          >
            <span className="cb-mode-index">01</span>
            <span><b>找原句 / 定位</b><small>搜确切出现过的词</small></span>
            <em className="free-tag">免费</em>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "meaning"}
            className={mode === "meaning" ? "is-active" : ""}
            data-testid="cb-mode-meaning"
            onClick={() => selectMode("meaning")}
          >
            <span className="cb-mode-index">02</span>
            <span><b>找相似写法</b><small>描述想达到的创作效果</small></span>
            <ProTag capability="cross_book_search" />
          </button>
        </div>

        <div className="cb-search-area">
          <div className="cb-mode-copy">
            <span className="cb-eyebrow">{mode === "keyword" ? "精确定位" : "创作意图匹配"}</span>
            <h2>{mode === "keyword" ? "输入记得的词或短句" : "描述你想找的写法或效果"}</h2>
            <p>
              {mode === "keyword"
                ? "例如“身份反转”“雨夜”“未报名却入选”。只做字面匹配，适合核对原句和明确概念。"
                : "例如“让主角一出场就打破读者预期”。模型会从写法层挑选真正符合的案例并解释原因。"}
            </p>
          </div>

          <form className="cb-form" onSubmit={(event) => { event.preventDefault(); run(); }}>
            <label className="cb-query-field">
              <span aria-hidden="true">⌕</span>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={mode === "keyword" ? "输入关键词或记得的短句" : "描述一种写法或想达到的效果"}
                aria-label="检索内容"
                data-testid="cb-input"
              />
            </label>
            <button type="submit" className="primary" disabled={!query.trim() || meaning.isPending} data-testid="cb-run">
              {mode === "meaning" && meaning.isPending
                ? "正在判断…"
                : mode === "keyword"
                  ? "查找出现位置"
                  : "寻找相似写法"}
            </button>
          </form>

          {scope.data ? (
            <details className="cb-scope-details">
              <summary data-testid="cb-hint">
                当前范围：{scope.data.book_count} 本书 · {mode === "keyword"
                  ? `${scope.data.item_count.toLocaleString()} 条全部分析内容`
                  : `${scope.data.craft_count.toLocaleString()} 条写法内容`}
              </summary>
              <div className="cb-scope-body">
                <div><b>包含的书</b><p>{scope.data.books.map((book) => `《${book.title}》`).join("、")}</p></div>
                <div><b>分析内容构成</b><p>{scope.data.kinds.map((kind) => `${kind.label} ${kind.count}`).join(" · ")}</p></div>
              </div>
            </details>
          ) : null}
        </div>
      </section>

      {mode === "keyword" && submittedKeyword ? (
        <section className="panel cb-results" data-testid="cb-keyword">
          <div className="cb-results-heading"><div><span className="cb-eyebrow">字面匹配结果</span><h2>“{submittedKeyword}”出现在哪里</h2></div></div>
          {keyword.isLoading ? <Loading /> : keyword.data ? <KeywordResults data={keyword.data} /> : null}
        </section>
      ) : null}

      {mode === "meaning" && (meaning.data || meaning.error) ? (
        <section className="panel cb-results" data-testid="cb-meaning">
          <div className="cb-results-heading">
            <div><span className="cb-eyebrow">创作意图匹配结果</span><h2>与“{query.trim()}”相似的写法</h2></div>
            <ProTag capability="cross_book_search" />
          </div>
          {proBlocked ? <ProNotice error={meaning.error as ApiError} /> : null}
          {meaning.error && !proBlocked ? <p className="wbv2-error" data-testid="cb-meaning-error">{meaning.error instanceof ApiError ? meaning.error.message : "这次检索没能完成，请重试。"}</p> : null}
          {meaning.data ? <MeaningResults data={meaning.data} /> : null}
        </section>
      ) : null}
    </section>
  );
}

function KeywordResults({ data }: { data: KeywordResult }) {
  if (data.message) return <p className="notice">{data.message}</p>;
  if (data.total === 0) {
    return (
      <div className="cb-empty-result" data-testid="cb-keyword-none">
        <b>没有找到完全相同的字词</b>
        <p>“{data.query}”在 {data.searched_items.toLocaleString()} 条内容里一次都没出现。</p>
        <p>这不等于书里没有相似写法。切换到上方“找相似写法”，用创作效果来描述。</p>
      </div>
    );
  }
  return (
    <>
      <p className="muted cb-source" data-testid="cb-keyword-count">在 {data.searched_items.toLocaleString()} 条内容里命中 {data.total} 条{data.truncated ? `，当前显示前 ${data.hits.length} 条` : ""}。</p>
      <ul className="cb-hits">{data.hits.map((hit, index) => <HitRow key={`${hit.book_id}-${hit.kind}-${hit.title}-${index}`} hit={hit} />)}</ul>
    </>
  );
}

function HitRow({ hit }: { hit: SearchHit }) {
  return (
    <li className="cb-hit" data-testid={`cb-hit-${hit.kind}`}>
      <div className="cb-hit-head"><span className={`cb-kind cb-kind--${hit.kind}`}>{hit.kind_label}</span><b>{hit.title}</b></div>
      {hit.snippet && hit.snippet !== hit.title ? <p>{hit.snippet}</p> : null}
      <div className="cb-hit-foot"><span>《{hit.book_title}》{hit.chapter ? ` · 第 ${hit.chapter} 章` : ""}</span><Link to={`/books/${hit.book_id}`}>打开原书核对 →</Link></div>
    </li>
  );
}

function MeaningResults({ data }: { data: MeaningResult }) {
  return (
    <>
      <p className="muted cb-source" data-testid="cb-meaning-scope">{data.scope_note} 本次读了 {data.searched_craft_items} 条{data.truncated ? `（共 ${data.total_craft_items} 条，超出部分未参与）` : ""}，由 {data.provider_name} / {data.model_name} 判断。</p>
      {data.matches.length === 0 ? (
        <div className="cb-empty-result" data-testid="cb-meaning-none"><b>写法层里没有足够符合的案例</b><p>模型没有用勉强沾边的结果凑数。可以换一种效果描述后重试。</p></div>
      ) : (
        <ol className="cb-matches">{data.matches.map((match, index) => <MatchRow key={`${match.book_id}-${match.title}-${index}`} match={match} />)}</ol>
      )}
    </>
  );
}

function MatchRow({ match }: { match: MeaningMatch }) {
  return (
    <li className="cb-match" data-testid={`cb-match-${match.kind}`}>
      <div className="cb-hit-head"><span className={`cb-kind cb-kind--${match.kind}`}>{match.kind_label}</span><b>{match.title}</b></div>
      {match.why ? <p className="cb-why"><strong>为什么符合：</strong>{match.why}</p> : null}
      {match.detail ? <p className="muted">{match.detail}</p> : null}
      <div className="cb-hit-foot"><span>《{match.book_title}》{match.chapter ? ` · 第 ${match.chapter} 章` : ""}</span><Link to={`/books/${match.book_id}`}>打开原书核对 →</Link></div>
    </li>
  );
}

function ProNotice({ error }: { error: ApiError }) {
  const details = (error.detail ?? {}) as { afdian_product_url?: string; product_label?: string };
  return (
    <div className="notice cp-pro" data-testid="cb-pro-required" role="alert">
      <b>{error.message}</b>
      {details.afdian_product_url ? <a href={details.afdian_product_url} target="_blank" rel="noreferrer">了解 {details.product_label || "Pro"} →</a> : null}
    </div>
  );
}
