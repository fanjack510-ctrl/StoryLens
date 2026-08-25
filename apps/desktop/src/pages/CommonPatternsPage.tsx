import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { commonPatternsApi } from "../services/commonPatternsApi";
import type { CommonPattern, PatternBook, PatternsResult } from "../services/commonPatternsApi";
import { collectionsApi } from "../services/collectionsApi";
import { ApiError } from "../services/apiClient";
import { ErrorState, Loading } from "../components/common/States";
import { PageHeader, PageSubtitle, PageTitle } from "../components/ui/PageHeader";
import { ExternalUrlLink } from "../components/common/ExternalUrlLink";
import {
  CommonPatternsPdfError,
  downloadCommonPatternsPdf,
} from "../features/commonPatterns/commonPatternsExport";

/** 共性视图：把一组书摆在一起，看它们共同做对了什么。
 *
 *  页面分成两半，因为两半的可信度不一样：
 *   · 上半是**数出来的**——类型分布、每本读到第几章。任何时候都成立，不要钱。
 *   · 下半是**归纳出来的**——需要被检验，所以每条共性都摊开它引用的书和技法名原文。
 *
 *  把两者混在一起而不标明来源，读的人就分不清哪一半可以直接信。
 */
export function CommonPatternsPage() {
  const params = useParams();
  const collectionId = Number(params.collectionId || 0);

  const collection = useQuery({
    queryKey: ["collection", collectionId],
    queryFn: () => collectionsApi.read(collectionId),
    enabled: collectionId > 0,
  });
  const overview = useQuery({
    queryKey: ["common-patterns-overview", collectionId],
    queryFn: () => commonPatternsApi.overview(collectionId),
    enabled: collectionId > 0,
  });
  const synth = useMutation<PatternsResult, unknown, void>({
    mutationFn: () => commonPatternsApi.synthesize(collectionId),
  });
  const exportPdf = useMutation<void, unknown, void>({
    mutationFn: () =>
      downloadCommonPatternsPdf(
        collectionId,
        collection.data?.name ?? "未命名榜单",
        synth.data!,
      ),
  });

  if (overview.isLoading) return <Loading />;
  if (overview.error) return <ErrorState error={overview.error} />;
  const data = overview.data;
  if (!data) return null;

  const result = synth.data;
  const proBlocked =
    synth.error instanceof ApiError && synth.error.code === "COMMON_PATTERNS_REQUIRES_PRO";

  return (
    <section className="page common-patterns" data-testid="common-patterns-page">
      <PageHeader>
        <div>
          <PageTitle>榜单共性</PageTitle>
          <PageSubtitle data-testid="cp-subtitle">
            《{collection.data?.name ?? "书单"}》 · {data.usable_count} 本可比 · 共{" "}
            {data.technique_total} 条技法
          </PageSubtitle>
        </div>
        <Link className="secondary" to="/knowledge" data-testid="cp-back">
          回知识库
        </Link>
      </PageHeader>

      {/* ——— 数出来的那一半 ——— */}
      <div className="panel cp-counted" data-testid="cp-counted">
        <h2>这一组是什么</h2>
        <p className="muted cp-source">以下都是数出来的，可以逐条回到原书核对。</p>

        {data.genres.length > 0 ? (
          <div className="cp-genres" data-testid="cp-genres">
            {data.genres.map((g) => (
              <span key={g.genre} className="cp-genre">
                {g.genre}
                <i>{g.count}</i>
              </span>
            ))}
          </div>
        ) : null}

        {/* 有的书只拆了开篇、有的拆了整本。混着比不是错，但拿五章的观察当整本的规律是错的。 */}
        {data.mixed_scope ? (
          <p className="notice cp-mixed" data-testid="cp-mixed-scope">
            这组里有 {data.opening_only_count} 本只拆了开篇。开篇的观察说明的是「它们怎么开头」，
            不能当成整本书的规律——下面每本书后面都标着它读到第几章。
          </p>
        ) : null}

        <table className="cp-table" data-testid="cp-book-table">
          <thead>
            <tr>
              <th>书</th>
              <th>类型</th>
              <th>读到哪儿</th>
              <th className="num">技法</th>
              <th className="num">钩子/章</th>
            </tr>
          </thead>
          <tbody>
            {data.books.map((b) => (
              <BookRow key={b.book_id} book={b} />
            ))}
          </tbody>
        </table>
      </div>

      {/* ——— 归纳出来的那一半 ——— */}
      <div className="panel cp-synth" data-testid="cp-synth">
        <div className="cp-result-heading">
          <div>
            <h2>它们共同做了什么</h2>
            {result ? <span>已形成可核对的结构化结论</span> : null}
          </div>
          {result ? (
            <button
              type="button"
              className="secondary cp-export-pdf"
              data-testid="cp-export-pdf"
              disabled={exportPdf.isPending}
              onClick={() => exportPdf.mutate()}
            >
              {exportPdf.isPending ? "正在生成 PDF…" : "导出结构化 PDF · Pro"}
            </button>
          ) : null}
        </div>

        {exportPdf.error ? <PdfExportNotice error={exportPdf.error} /> : null}

        {!data.can_synthesize ? (
          <p className="notice" data-testid="cp-blocked">
            {data.blocked_reason}
          </p>
        ) : !result ? (
          <>
            <p className="muted cp-source">
              这一步要读进每本书的技法，看出不同说法背后的同一件事——
              「用一句反常识的话立住人物」和「用粗俗细节打破严肃场合」，说法不同，做的是同一件事。
              这是共性视图里唯一省不掉的一段，也是它收费的地方。
            </p>
            <button
              type="button"
              className="primary"
              data-testid="cp-run"
              disabled={synth.isPending}
              onClick={() => synth.mutate()}
            >
              {synth.isPending ? "正在归纳……" : `归纳这 ${data.usable_count} 本书`}
            </button>
            {proBlocked ? <ProNotice error={synth.error as ApiError} /> : null}
            {synth.error && !proBlocked ? (
              <p className="wbv2-error" data-testid="cp-error">
                {synth.error instanceof ApiError ? synth.error.message : "归纳没能完成，请重试。"}
              </p>
            ) : null}
          </>
        ) : (
          <>
            <p className="muted cp-source" data-testid="cp-provenance">
              由 {result.provider_name} / {result.model_name} 归纳。
              每条共性下面列出它引用的书和技法名原文——引用对不上的条目已经被丢掉。
            </p>
            {result.patterns.length === 0 ? (
              <p className="notice" data-testid="cp-none">
                这几本书之间没有找到站得住的共同手法。这不一定是坏事——
                一组风格差得远的书本来就该是这个结果。
              </p>
            ) : (
              <ol className="cp-patterns">
                {result.patterns.map((p) => (
                  <PatternCard key={p.name} pattern={p} />
                ))}
              </ol>
            )}
            {result.not_shared.length > 0 ? (
              <div className="cp-unique" data-testid="cp-not-shared">
                <h3>只有它自己在做的</h3>
                <ul>
                  {result.not_shared.map((n) => (
                    <li key={n.book_id}>
                      <b>《{n.book_title}》</b>
                      {n.what_only_this_one_does}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </>
        )}
      </div>
    </section>
  );
}

function BookRow({ book }: { book: PatternBook }) {
  if (!book.usable) {
    return (
      <tr data-testid={`cp-book-${book.book_id}`} data-usable="false">
        <td>{book.title || `#${book.book_id}`}</td>
        {/* 从比较里消失而不说明原因，用户会以为自己选错了书。 */}
        <td colSpan={4} className="cp-excluded">
          {book.excluded_reason}
        </td>
      </tr>
    );
  }
  return (
    <tr data-testid={`cp-book-${book.book_id}`} data-usable="true">
      <td>{book.title}</td>
      <td>{book.primary_genre || "—"}</td>
      <td data-scope={book.scope_kind}>{book.scope_label}</td>
      <td className="num">{book.technique_count}</td>
      <td className="num">{book.hooks_per_chapter ?? "—"}</td>
    </tr>
  );
}

function PatternCard({ pattern }: { pattern: CommonPattern }) {
  return (
    <li className="cp-pattern" data-testid={`cp-pattern-${pattern.name}`}>
      <div className="cp-pattern-head">
        <b>{pattern.name}</b>
        <span className="cp-support">{pattern.book_count} 本书这么做</span>
      </div>
      {pattern.what_they_do ? <p>{pattern.what_they_do}</p> : null}
      {pattern.why_it_works ? <p className="muted">{pattern.why_it_works}</p> : null}
      {/* 引用不是脚注，是这条结论能不能信的全部依据。所以它和结论放在一起，不折叠。 */}
      <ul className="cp-instances">
        {pattern.instances.map((i, idx) => (
          <li key={`${i.book_id}-${i.technique_name}-${idx}`}>
            <span className="cp-instance-book">《{i.book_title}》</span>
            <span className="cp-instance-tech">{i.technique_name}</span>
            {i.how_this_book_does_it ? <span>{i.how_this_book_does_it}</span> : null}
          </li>
        ))}
      </ul>
    </li>
  );
}

function ProNotice({ error }: { error: ApiError }) {
  const details = (error.detail ?? {}) as { afdian_product_url?: string; product_label?: string };
  return (
    <div className="notice cp-pro" data-testid="cp-pro-required" role="alert">
      <b>{error.message}</b>
      {details.afdian_product_url ? (
        <ExternalUrlLink url={details.afdian_product_url}>
          了解 {details.product_label || "Pro"} →
        </ExternalUrlLink>
      ) : null}
    </div>
  );
}

function PdfExportNotice({ error }: { error: unknown }) {
  const pdfError = error instanceof CommonPatternsPdfError ? error : null;
  return (
    <div className="notice cp-pdf-error" role="alert" data-testid="cp-pdf-error">
      <b>{pdfError?.message || "PDF 没能生成，请重试。"}</b>
      {pdfError?.proRequired && pdfError.upgradeUrl ? (
        <ExternalUrlLink url={pdfError.upgradeUrl}>
          了解 StoryLens Pro →
        </ExternalUrlLink>
      ) : null}
    </div>
  );
}
