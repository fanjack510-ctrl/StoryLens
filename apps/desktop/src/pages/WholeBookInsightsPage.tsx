import { useMemo, useState } from "react";
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
import { PRO_CAPABILITIES_SHIPPED } from "../services/productEdition";

const MISSING_CHAPTER_PREVIEW = 20;
const LOW_COVERAGE_RATIO = 0.25;

const PAGE_TITLE = "章节聚合洞察";
const PAGE_SUBTITLE = "基于已完成单章分析结果的精细资产覆盖和聚合视图";
const PAGE_EXPLANATION =
  "基于已经完成的单章精细分析结果，对章节覆盖、阅读旅程、节奏、钩子、回报和章节功能进行聚合展示。";

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

function coveragePercent(valid: number, total: number): number {
  if (total <= 0) return 0;
  return Math.round((valid / total) * 100);
}

function diagnosticSummary(item: unknown): string {
  if (typeof item === "string") return item;
  if (item && typeof item === "object") {
    const record = item as Record<string, unknown>;
    const code = typeof record.code === "string" ? record.code : null;
    const message =
      typeof record.message === "string"
        ? record.message
        : typeof record.summary === "string"
          ? record.summary
          : typeof record.detail === "string"
            ? record.detail
            : null;
    if (code && message) return `${code}：${message}`;
    if (message) return message;
    if (code) return code;
  }
  return "诊断项";
}

function JourneyCurveSvg({
  points,
}: {
  points: Array<{ chapter_index: number; tension: number; hook: number; payoff: number }>;
}) {
  if (!points.length) {
    return <p className="muted">暂无可用旅程曲线数据（需更多已完成精细单章分析）</p>;
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
      aria-label="章节阅读旅程曲线"
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

function ChapterRow({
  bookId,
  chapter,
}: {
  bookId: number;
  chapter: WholeBookInsightsChapterRow;
}) {
  return (
    <li>
      <strong>
        {chapter.chapter_index}. {chapter.display_title || chapter.chapter_title}
      </strong>
      {" — "}
      {chapter.is_valid ? "已纳入聚合" : "尚未完成精细单章分析"}
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
  );
}

export function WholeBookInsightsPage() {
  const params = useParams();
  const navigate = useNavigate();
  const bookId = Number(params.bookId || 0);
  const edition = useProductEdition();
  const isPro = edition.loaded && edition.is_pro;
  const [showAllMissing, setShowAllMissing] = useState(false);
  const shipped = PRO_CAPABILITIES_SHIPPED;

  const book = useQuery({
    queryKey: ["book", bookId],
    queryFn: () => booksApi.detail(bookId),
    enabled: shipped && bookId > 0,
  });

  const insights = useQuery({
    queryKey: ["whole-book-insights", bookId],
    queryFn: () => wholeBookInsightsApi.fetch(bookId),
    enabled: shipped && bookId > 0 && isPro,
    retry: false,
  });

  const chapters = insights.data?.chapters || [];
  const { validChapters, missingChapters } = useMemo(() => {
    const valid: WholeBookInsightsChapterRow[] = [];
    const missing: WholeBookInsightsChapterRow[] = [];
    for (const chapter of chapters) {
      if (chapter.is_valid) valid.push(chapter);
      else missing.push(chapter);
    }
    return { validChapters: valid, missingChapters: missing };
  }, [chapters]);

  // CHG-20260727-016: 1.1.0 single-chapter release keeps aggregate insights unshipped.
  if (!shipped) {
    return (
      <section
        className="whole-book-insights-page"
        data-testid="whole-book-insights-coming-soon"
      >
        <h1>{PAGE_TITLE}</h1>
        <p data-testid="whole-book-insights-coming-soon-message">
          该功能正在完善中，当前版本暂未开放。
        </p>
        <p className="muted">
          本版本聚焦单章导入、场景确认与单章结构化分析。
        </p>
        <Link className="secondary" to={`/books/${bookId}`} data-testid="whole-book-insights-back">
          返回书籍
        </Link>
      </section>
    );
  }

  if (!isPro) {
    return (
      <section className="whole-book-insights-page" data-testid="whole-book-insights-upgrade">
        <h1>{PAGE_TITLE}</h1>
        <p className="muted">{PAGE_SUBTITLE}</p>
        <p>
          StoryLens Pro 功能：{PAGE_EXPLANATION}
          激活专业版授权后可使用。
        </p>
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
        <h1>{PAGE_TITLE}</h1>
        <ErrorState error={new Error(String(code))} />
        <Link className="secondary" to={`/books/${bookId}`}>
          返回书籍
        </Link>
      </section>
    );
  }

  const data = insights.data!;
  const coverage = data.coverage;
  const percent = coveragePercent(coverage.valid_chapters, coverage.total_chapters);
  const isLowCoverage =
    coverage.total_chapters === 0 ||
    coverage.valid_chapters === 0 ||
    coverage.valid_chapters / Math.max(coverage.total_chapters, 1) < LOW_COVERAGE_RATIO;
  const visibleMissing = showAllMissing
    ? missingChapters
    : missingChapters.slice(0, MISSING_CHAPTER_PREVIEW);
  const diagnostics = data.diagnostics || [];

  return (
    <section className="whole-book-insights-page" data-testid="whole-book-insights-page">
      <header className="whole-book-insights-header">
        <div>
          <h1>{PAGE_TITLE}</h1>
          <p className="muted">{PAGE_SUBTITLE}</p>
          <p className="muted">{book.data?.title || `书籍 #${bookId}`}</p>
        </div>
        <Link className="secondary" to={`/books/${bookId}`}>
          返回书籍
        </Link>
      </header>

      <p data-testid="whole-book-insights-explanation">{PAGE_EXPLANATION}</p>

      <section data-testid="whole-book-insights-coverage">
        <h2>章节资产覆盖</h2>
        <p>
          已完成精细单章分析：{coverage.valid_chapters} / {coverage.total_chapters} 章
        </p>
        <p>章节资产覆盖率：{percent}%</p>
        <p className="muted" data-testid="whole-book-insights-coverage-note">
          小说原文仍完整保存在 StoryLens 中；这里显示的是精细单章分析资产覆盖，不是原文覆盖。
        </p>
        {coverage.invalid_chapters > 0 ? (
          <p className="muted">
            其中 {coverage.invalid_chapters} 章尚未完成精细单章分析，暂未纳入聚合。
          </p>
        ) : null}
      </section>

      {isLowCoverage ? (
        <section
          className="notice"
          data-testid="whole-book-insights-low-coverage"
        >
          <p>
            当前仅有少量章节完成了精细单章分析，聚合视图会偏稀疏——这不代表系统故障，也不代表对未分析章节已有原生全书理解。
          </p>
          <p>
            请先在各章完成单章精细分析；完成的章节越多，章节覆盖、阅读旅程、节奏、钩子与回报的聚合会越完整。
          </p>
        </section>
      ) : null}

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

      <section data-testid="whole-book-insights-diagnostics">
        <h2>诊断</h2>
        {diagnostics.length ? (
          <>
            <ul data-testid="whole-book-insights-diagnostics-summary">
              {diagnostics.map((item, index) => (
                <li key={index}>{diagnosticSummary(item)}</li>
              ))}
            </ul>
            <details data-testid="whole-book-insights-diagnostics-details">
              <summary>开发者详情</summary>
              <pre className="muted">{JSON.stringify(diagnostics, null, 2)}</pre>
            </details>
          </>
        ) : (
          <p className="muted">暂无额外诊断</p>
        )}
      </section>

      <section data-testid="whole-book-insights-chapter-list">
        <h2>章节列表</h2>
        {validChapters.length ? (
          <>
            <h3>已纳入聚合</h3>
            <ul>
              {validChapters.map((chapter) => (
                <ChapterRow key={chapter.chapter_id} bookId={bookId} chapter={chapter} />
              ))}
            </ul>
          </>
        ) : (
          <p className="muted">尚无已纳入聚合的章节。</p>
        )}

        {missingChapters.length ? (
          <div data-testid="whole-book-insights-missing-chapters">
            <h3>尚未完成精细单章分析（{missingChapters.length}）</h3>
            <ul>
              {visibleMissing.map((chapter) => (
                <ChapterRow key={chapter.chapter_id} bookId={bookId} chapter={chapter} />
              ))}
            </ul>
            {missingChapters.length > MISSING_CHAPTER_PREVIEW ? (
              <button
                type="button"
                className="secondary"
                data-testid="whole-book-insights-missing-toggle"
                onClick={() => setShowAllMissing((v) => !v)}
              >
                {showAllMissing ? "收起" : "查看全部"}
              </button>
            ) : null}
          </div>
        ) : null}
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
