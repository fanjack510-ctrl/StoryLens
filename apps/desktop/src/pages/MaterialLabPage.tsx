import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { materialLabApi } from "../services/materialLabApi";
import type { MaterialItem, MaterialLabSummary } from "../services/materialLabApi";
import { ApiError } from "../services/apiClient";
import { ErrorState, Loading } from "../components/common/States";
import { PageHeader, PageSubtitle, PageTitle } from "../components/ui/PageHeader";

/** 素材库：把一本书拆成可复用的创作资料。
 *
 *  这一页刻意长得不像本产品的其他分析页——没有任务进度条、没有预算提示、
 *  没有 Pro 门。因为它跑的是**本地确定性引擎**：不调云端模型、不要密钥、
 *  不花钱，整本书秒级到半分钟同步跑完。「重新提取」永远是安全按钮。
 *
 *  示例句由槽位重组、从不拼接原文；模式（corePattern）只保留抽象构型。
 *  所以这页展示的东西可以放心抄进自己的稿子。
 */
export function MaterialLabPage() {
  const params = useParams();
  const bookId = Number(params.bookId || 0);
  const queryClient = useQueryClient();

  const summary = useQuery({
    queryKey: ["material-lab-summary", bookId],
    queryFn: () => materialLabApi.summary(bookId),
    enabled: bookId > 0,
  });

  const run = useMutation({
    mutationFn: (genreSlug?: string) => materialLabApi.run(bookId, genreSlug),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["material-lab-summary", bookId] });
      void queryClient.invalidateQueries({ queryKey: ["material-lab-materials", bookId] });
    },
  });

  if (summary.isLoading) return <Loading />;
  if (summary.error) return <ErrorState error={summary.error} />;
  const data = summary.data;
  if (!data) return null;

  const hasMaterials = data.material_count > 0;

  return (
    <section className="page material-lab" data-testid="material-lab-page">
      <PageHeader>
        <div>
          <PageTitle>素材库</PageTitle>
          <PageSubtitle data-testid="ml-subtitle">
            {hasMaterials
              ? `${data.material_count} 条创作资料 · ${runLabel(data)}`
              : "本地引擎 · 不调云端模型 · 不花钱"}
          </PageSubtitle>
        </div>
        <Link className="secondary" to={`/books/${bookId}`} data-testid="ml-back">
          回这本书
        </Link>
      </PageHeader>

      {!hasMaterials ? (
        <RunPanel bookId={bookId} run={run} />
      ) : (
        <>
          <SummaryPanel data={data} run={run} />
          <MaterialsPanel bookId={bookId} summary={data} />
        </>
      )}
    </section>
  );
}

function runLabel(data: MaterialLabSummary): string {
  const r = data.last_run;
  if (!r) return "";
  const src = r.genre_source === "auto" ? "自动判定" : "手动指定";
  return `类型 ${r.genre_slug}（${src}） · ${r.chapters} 章 ${r.scenes} 场景`;
}

/** 首次提取：选类型（预填自动建议），一个按钮。 */
function RunPanel({
  bookId,
  run,
}: {
  bookId: number;
  run: ReturnType<typeof useMutation<Awaited<ReturnType<typeof materialLabApi.run>>, unknown, string | undefined>>;
}) {
  const genres = useQuery({ queryKey: ["material-lab-genres"], queryFn: materialLabApi.genres });
  const suggestion = useQuery({
    queryKey: ["material-lab-genre-suggestion", bookId],
    queryFn: () => materialLabApi.genreSuggestion(bookId),
    enabled: bookId > 0,
  });
  const [chosen, setChosen] = useState<string>("");

  // 用户没动过下拉时跟随建议；动过就以用户为准。
  const effective = chosen || suggestion.data?.genre_slug || "";
  const suggested = suggestion.data && suggestion.data.confidence > 0;

  return (
    <div className="panel" data-testid="ml-run-panel">
      <h2>把这本书拆成创作资料</h2>
      <p className="muted">
        场景切分 → 事实抽取 → 创作抽象。产出的每条资料带可发表示例、抽象模式、
        悬念问题——示例由槽位重组，不含原文片段和原书人名。
        整个过程在本机完成，不调云端模型，不产生费用。
      </p>
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <label>
          类型模板{" "}
          <select
            data-testid="ml-genre-select"
            value={effective}
            onChange={(e) => setChosen(e.target.value)}
          >
            <option value="">（自动判定）</option>
            {(genres.data?.items ?? []).map((g) => (
              <option key={g.slug} value={g.slug}>
                {g.label}（{g.category_count} 类目）
              </option>
            ))}
          </select>
        </label>
        {suggested && !chosen ? (
          <span className="muted" data-testid="ml-suggestion">
            建议：{suggestion.data!.label}（置信 {Math.round(suggestion.data!.confidence * 100)}%）
          </span>
        ) : null}
        <button
          type="button"
          className="primary"
          data-testid="ml-run"
          disabled={run.isPending}
          onClick={() => run.mutate(chosen || undefined)}
        >
          {run.isPending ? "正在提取……" : "开始提取"}
        </button>
      </div>
      {run.error ? (
        <p className="notice" data-testid="ml-run-error">
          {run.error instanceof ApiError ? run.error.message : "提取没能完成，请重试。"}
        </p>
      ) : null}
    </div>
  );
}

/** 已有资料时的头部：类型分布 + 重新提取。 */
function SummaryPanel({
  data,
  run,
}: {
  data: MaterialLabSummary;
  run: ReturnType<typeof useMutation<Awaited<ReturnType<typeof materialLabApi.run>>, unknown, string | undefined>>;
}) {
  return (
    <div className="panel" data-testid="ml-summary">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {Object.entries(data.by_type).map(([t, n]) => (
            <span key={t} className="notice" style={{ padding: "2px 10px" }} data-testid={`ml-type-${t}`}>
              {t} <b>{n}</b>
            </span>
          ))}
        </div>
        <button
          type="button"
          className="secondary"
          data-testid="ml-rerun"
          disabled={run.isPending}
          onClick={() => run.mutate(undefined)}
          title="本地引擎重跑免费；会替换这本书现有的资料"
        >
          {run.isPending ? "正在重新提取……" : "重新提取"}
        </button>
      </div>
    </div>
  );
}

/** 资料列表 + 筛选。筛选都在服务端做——13,000 条资料不该整批进浏览器。 */
function MaterialsPanel({ bookId, summary }: { bookId: number; summary: MaterialLabSummary }) {
  const [category, setCategory] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [primaryOnly, setPrimaryOnly] = useState(true);
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  const pageSize = 20;

  const filters = useMemo(
    () => ({
      book_id: bookId,
      category_key: category || undefined,
      min_score: minScore > 0 ? minScore : undefined,
      primary_only: primaryOnly,
      q: q || undefined,
      limit: pageSize,
      offset: page * pageSize,
    }),
    [bookId, category, minScore, primaryOnly, q, page],
  );

  const materials = useQuery({
    queryKey: ["material-lab-materials", bookId, filters],
    queryFn: () => materialLabApi.materials(filters),
  });

  const total = materials.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="panel" data-testid="ml-materials">
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
        <select
          data-testid="ml-filter-category"
          value={category}
          onChange={(e) => {
            setCategory(e.target.value);
            setPage(0);
          }}
        >
          <option value="">全部类目</option>
          {summary.by_category.map((c) => (
            <option key={c.key} value={c.key}>
              {c.label}（{c.count}）
            </option>
          ))}
        </select>
        <label className="muted">
          质量 ≥{" "}
          <select
            data-testid="ml-filter-score"
            value={minScore}
            onChange={(e) => {
              setMinScore(Number(e.target.value));
              setPage(0);
            }}
          >
            <option value={0}>不限</option>
            <option value={60}>60</option>
            <option value={75}>75</option>
          </select>
        </label>
        <label className="muted" title="同一抽象模式的资料只看质量最高的一条">
          <input
            type="checkbox"
            data-testid="ml-filter-primary"
            checked={primaryOnly}
            onChange={(e) => {
              setPrimaryOnly(e.target.checked);
              setPage(0);
            }}
          />{" "}
          每个模式只看代表
        </label>
        <input
          type="search"
          data-testid="ml-filter-q"
          placeholder="搜标题 / 示例 / 模式 / 标签"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(0);
          }}
          style={{ flex: 1, minWidth: 160 }}
        />
        <span className="muted" data-testid="ml-total">
          {total} 条
        </span>
      </div>

      {materials.isLoading ? (
        <Loading />
      ) : materials.error ? (
        <ErrorState error={materials.error} />
      ) : (materials.data?.items.length ?? 0) === 0 ? (
        <p className="notice" data-testid="ml-empty">
          这个筛选下没有资料。放宽质量线或取消「每个模式只看代表」试试。
        </p>
      ) : (
        <>
          <ol style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 12 }}>
            {materials.data!.items.map((m) => (
              <MaterialCard key={m.id} m={m} />
            ))}
          </ol>
          {pages > 1 ? (
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 12 }}>
              <button
                type="button"
                className="secondary"
                data-testid="ml-prev"
                disabled={page === 0}
                onClick={() => setPage((p) => p - 1)}
              >
                上一页
              </button>
              <span className="muted">
                {page + 1} / {pages}
              </span>
              <button
                type="button"
                className="secondary"
                data-testid="ml-next"
                disabled={page + 1 >= pages}
                onClick={() => setPage((p) => p + 1)}
              >
                下一页
              </button>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

/** 一条资料的五件套：示例、模式、机制、悬念问题、适用位置。
 *  全部平铺不折叠——这页的用途是"翻到一条能用的"，折叠只会增加翻的成本。 */
function MaterialCard({ m }: { m: MaterialItem }) {
  return (
    <li
      data-testid={`ml-material-${m.id}`}
      style={{ border: "1px solid var(--border, #3333)", borderRadius: 8, padding: "10px 14px" }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
        <b>{m.title}</b>
        <span className="muted">
          {m.category_label} · {m.subcategory_label} · 质量 {m.quality_score}
        </span>
      </div>
      <p style={{ margin: "6px 0" }}>{m.concise_example}</p>
      <p className="muted" style={{ margin: "4px 0" }}>
        构型：{m.core_pattern}
        {m.mechanism ? ` ｜ ${m.mechanism}` : ""}
      </p>
      {m.suspense_question ? (
        <p className="muted" style={{ margin: "4px 0" }}>
          可挂的问题:{m.suspense_question}
        </p>
      ) : null}
      <p className="muted" style={{ margin: "4px 0", fontSize: "0.85em" }}>
        适用:{m.applicable_stage || "任意阶段"} · {m.applicable_scene}
        {m.emotion ? ` · 情绪:${m.emotion}` : ""}
        {m.tags.length ? ` · ${m.tags.join(" / ")}` : ""}
      </p>
    </li>
  );
}
