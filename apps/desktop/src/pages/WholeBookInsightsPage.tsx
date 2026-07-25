import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ErrorState, Loading } from "../components/common/States";
import { useProductEdition } from "../hooks/useProductEdition";
import {
  wholeBookInsightsApi,
  type WholeBookInsightsChapterRow,
  type WholeBookInsightsDeepLink,
} from "../services/wholeBookInsightsApi";
import { booksApi } from "../services/booksApi";

function chapterResultHref(bookId: number, chapter: WholeBookInsightsChapterRow, link: WholeBookInsightsDeepLink) {
  const params = new URLSearchParams();
  params.set("chapter", String(link.chapter_id));
  params.set("view", "result");
  if (chapter.analysis_run_id) {
    params.set("analysisRun", String(chapter.analysis_run_id));
  }
  if (link.paragraph_id) {
    params.set("paragraph", link.paragraph_id);
  }
  if (link.scene_id) {
    params.set("scene", String(link.scene_id));
  }
  return `/books/${bookId}?${params.toString()}`;
}

function JourneyCurveSvg({
  points,
}: {
  points: Array<{ chapter_index: number; tension: number; hook: number; payoff: number }>;
}) {
  if (!points.length) {
    return <p className="muted">暂无可用旅程曲线数据</p>;
  }
  const width = 640;
  const height = 180;
  const pad = 16;
  const maxIndex = Math.max(...points.map((p) => p.chapter_index), 1);
  const xFor = (index: number) => pad + ((index - 1) / Math.max(maxIndex - 1, 1)) * (width - pad * 2);
  const yFor = (score: number) => height - pad - (score / 100) * (height - pad * 2);
  const line = (key: "tension" | "hook" | "payoff", color: string) => {
    const d = points
      .map((p, i) => `${i === 0 ? "M" : "L"} ${xFor(p.chapter_index).toFixed(1)} ${yFor(p[key]).toFixed(1)}`)
      .join(" ");
    return <path key={key} d={d} fill="none" stroke={color} strokeWidth={2} />;
  };
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="全书阅读旅程曲线"
      data-testid="whole-book-insights-journey-curve"
      className="whole-book-insights-curve"
    >
      <rect x={0} y={0} width={width} height={height} fill="transparent" />
      {line("tension", "#e45756")}
      {line("hook", "#4c78a8")}
      {line("payoff", "#72b7b2")}
    </svg>
  );
}

export function WholeBookInsightsPage() {
  const params = useParams();
  const navigate = useNavigate();
  const bookId = Number(params.bookId || 0);
  const edition = useProductEdition();
  const isPro = edition.loaded && edition.is_pro;

  const book = useQuery({
    queryKey: ["book", bookId],
    queryFn: () => booksApi.detail(bookId),
    enabled: bookId > 0,
  });

  const insights = useQuery({
    queryKey: ["whole-book-insights", bookId],
    queryFn: () => wholeBookInsightsApi.fetch(bookId),
    enabled: bookId > 0 && isPro,
    retry: false,
  });

  if (!isPro) {
    return (
      <section className="whole-book-insights-page" data-testid="whole-book-insights-upgrade">
        <h1>全书洞察</h1>
        <p>StoryLens Pro 功能：基于已完成单章分析聚合全书覆盖率、旅程曲线、节奏与诊断。</p>
        <button type="button" className="primary" onClick={() => navigate("/settings")}>
          查看授权说明
        </button>
        <Link className="secondary" to={`/books/${bookId}`}>
          返回书籍
        </Link>
      </section>
    );
  }

  if (insights.isLoading || book.isLoading) {
    return <Loading />;
  }

  if (insights.isError) {
    const code =
      (insights.error as { code?: string } | undefined)?.code ||
      "WHOLE_BOOK_INSIGHTS_ERROR";
    return (
      <section className="whole-book-insights-page" data-testid="whole-book-insights-error">
        <h1>全书洞察</h1>
        <ErrorState error={new Error(String(code))} />
        <Link className="secondary" to={`/books/${bookId}`}>
          返回书籍
        </Link>
      </section>
    );
  }

  const data = insights.data!;
  const coverage = data.coverage;

  return (
    <section className="whole-book-insights-page" data-testid="whole-book-insights-page">
      <header className="whole-book-insights-header">
        <div>
          <h1>全书洞察</h1>
          <p className="muted">{book.data?.title || `书籍 #${bookId}`}</p>
        </div>
        <Link className="secondary" to={`/books/${bookId}`}>
          返回书籍
        </Link>
      </header>

      <section data-testid="whole-book-insights-coverage">
        <h2>覆盖率</h2>
        <p>
          有效章节 {coverage.valid_chapters} / {coverage.total_chapters}
          {coverage.invalid_chapters > 0
            ? `（${coverage.invalid_chapters} 章缺少完整场景分析或阅读旅程）`
            : null}
        </p>
      </section>

      <section>
        <h2>旅程曲线</h2>
        <JourneyCurveSvg points={data.journey_curve || []} />
      </section>

      <section>
        <h2>节奏</h2>
        <p>{data.pacing?.summary || "—"}</p>
      </section>

      <section>
        <h2>峰值 / 低谷</h2>
        <p>峰值 {(data.peaks || []).length} 项 · 低谷 {(data.valleys || []).length} 项</p>
      </section>

      <section>
        <h2>钩子 / 回报 / 功能</h2>
        <ul>
          <li>钩子 {(data.hooks || []).length} 项</li>
          <li>回报 {(data.payoffs || []).length} 项</li>
          <li>章节功能 {(data.functions || []).length} 项</li>
        </ul>
      </section>

      <section>
        <h2>诊断</h2>
        {(data.diagnostics || []).length ? (
          <ul>
            {(data.diagnostics || []).map((item, index) => (
              <li key={index}>{typeof item === "string" ? item : JSON.stringify(item)}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">暂无额外诊断</p>
        )}
      </section>

      <section data-testid="whole-book-insights-chapter-list">
        <h2>章节列表</h2>
        <ul>
          {(data.chapters || []).map((chapter) => (
            <li key={chapter.chapter_id}>
              <strong>
                {chapter.chapter_index}. {chapter.display_title || chapter.chapter_title}
              </strong>
              {" — "}
              {chapter.is_valid ? "已纳入" : "未纳入"}
              {chapter.is_valid && chapter.scenes[0]?.deep_link ? (
                <>
                  {" · "}
                  <Link
                    to={chapterResultHref(bookId, chapter, chapter.scenes[0].deep_link)}
                    data-testid={`whole-book-insights-chapter-link-${chapter.chapter_id}`}
                  >
                    查看章节结果
                  </Link>
                </>
              ) : null}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2>数据来源</h2>
        <p className="muted">
          capability: {data.data_source?.capability_key || "pro_whole_book_insights"}
          {data.computed_at ? ` · 生成于 ${data.computed_at}` : null}
        </p>
      </section>
    </section>
  );
}
