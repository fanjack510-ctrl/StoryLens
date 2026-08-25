import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { ErrorState, Loading } from "../components/common/States";
import { ProTag } from "../components/ui/ProTag";
import type {
  BookSkillArtifact,
  KnowledgeLibrarySummary,
  KnowledgeSourceList,
  MaterialItem,
  MaterialLabGenre,
  MaterialLabRunResult,
  MaterialListResult,
} from "../services/materialLabApi";
import { materialLabApi } from "../services/materialLabApi";
import { ApiError } from "../services/apiClient";
import { openExternalUrl } from "../services/openExternalUrl";
import "./knowledgeLibrary.css";

type KnowledgeView = "materials" | "skill";
type QueryState<T> = { data?: T; isLoading: boolean; error: Error | null };
type ExtractState = {
  isPending: boolean;
  variables?: { bookId: number; genreSlug?: string };
  error: Error | null;
  mutate: (value: { bookId: number; genreSlug?: string }) => void;
};
type SkillState = {
  isPending: boolean;
  error: Error | null;
  mutate: (bookId: number) => void;
  reset: () => void;
};

function saveSkillFile(artifact: BookSkillArtifact) {
  if (typeof URL.createObjectURL !== "function") return;
  const blob = new Blob([artifact.content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = artifact.filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function ProActionError({ error, fallback }: { error: Error | null; fallback: string }) {
  if (!error) return null;
  const proRequired = error instanceof ApiError && error.code === "PRO_FEATURE_REQUIRED";
  if (!proRequired) return <div className="notice" role="alert">{fallback}：{error.message}</div>;
  const detail = error.detail && typeof error.detail === "object"
    ? error.detail as { afdian_product_url?: string }
    : null;
  const buyUrl = detail?.afdian_product_url || "";
  return (
    <div className="notice knowledge-pro-notice" role="alert" data-testid="knowledge-pro-required">
      <div><b>需要 StoryLens Pro</b><span>{error.message}</span></div>
      <div>
        {buyUrl ? <button type="button" className="primary" onClick={() => void openExternalUrl(buyUrl)}>前往爱发电购买</button> : null}
        <Link className="secondary" to="/settings?tab=license">已有授权码，去激活</Link>
      </div>
    </div>
  );
}

/** The knowledge library is a product workspace, not a fourth view inside one book. */
export function KnowledgeLibraryPage() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const view: KnowledgeView = searchParams.get("view") === "skill" ? "skill" : "materials";
  const [genre, setGenre] = useState("");
  const [q, setQ] = useState("");
  const [representativeOnly, setRepresentativeOnly] = useState(false);
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(0);
  const [sourceGenres, setSourceGenres] = useState<Record<number, string>>({});
  const [selectedSkillBookId, setSelectedSkillBookId] = useState<number | null>(null);
  const [skillArtifact, setSkillArtifact] = useState<BookSkillArtifact | null>(null);
  const pageSize = 24;

  const summary = useQuery({ queryKey: ["material-knowledge-library-summary"], queryFn: materialLabApi.librarySummary });
  const sources = useQuery({ queryKey: ["material-knowledge-library-sources"], queryFn: materialLabApi.librarySources });
  const genres = useQuery({
    queryKey: ["material-lab-genres"],
    queryFn: materialLabApi.genres,
    staleTime: 60 * 60 * 1000,
  });
  const filters = useMemo(() => ({
    genre_slug: genre || undefined,
    q: q || undefined,
    category_key: category || undefined,
    primary_only: representativeOnly,
    limit: pageSize,
    offset: page * pageSize,
  }), [category, genre, page, q, representativeOnly]);
  const materials = useQuery({
    queryKey: ["material-knowledge-library", filters],
    queryFn: () => materialLabApi.materials(filters),
    enabled: view === "materials",
  });
  const extract = useMutation<MaterialLabRunResult, Error, { bookId: number; genreSlug?: string }>({
    mutationFn: ({ bookId, genreSlug }) => materialLabApi.extractLibrarySource(bookId, genreSlug),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["material-knowledge-library-summary"] }),
        queryClient.invalidateQueries({ queryKey: ["material-knowledge-library-sources"] }),
        queryClient.invalidateQueries({ queryKey: ["material-knowledge-library"] }),
      ]);
    },
  });
  const generateSkill = useMutation<BookSkillArtifact, Error, number>({
    mutationFn: (bookId) => materialLabApi.generateBookSkill(bookId),
    onSuccess: (artifact) => {
      setSkillArtifact(artifact);
      saveSkillFile(artifact);
    },
  });

  useEffect(() => {
    const first = sources.data?.items[0]?.book_id;
    if (selectedSkillBookId == null && first != null) setSelectedSkillBookId(first);
  }, [selectedSkillBookId, sources.data?.items]);

  if (summary.isLoading) return <Loading />;
  if (summary.error) return <ErrorState error={summary.error} />;
  const data = summary.data;
  if (!data) return null;

  const total = materials.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const resetPage = () => setPage(0);
  const switchView = (next: KnowledgeView) => {
    const params = new URLSearchParams(searchParams);
    if (next === "materials") params.delete("view");
    else params.set("view", next);
    setSearchParams(params);
  };

  return (
    <section className="page knowledge-hub" data-testid="knowledge-library-page">
      <header className="knowledge-hero">
        <div>
          <p className="knowledge-eyebrow">从读过的书，沉淀可复用的创作能力</p>
          <h1>创作知识库</h1>
          <p>
            素材是可检索的知识条目；榜单共性回答一批书共同怎么开篇；作品 Skill
            把一本完整拆解过的书变成可执行的创作约束。
          </p>
        </div>
        <div className="knowledge-hero-stats" aria-label="知识库统计">
          <strong>{data.knowledge_count}</strong><span>条题材素材</span><i />
          <strong>{sources.data?.total ?? 0}</strong><span>本全文来源</span>
          {data.legacy_source_book_count > 0 ? (
            <><i /><strong>{data.legacy_source_book_count}</strong><span>本参考语料</span></>
          ) : null}
        </div>
      </header>

      <nav className="knowledge-workspaces" aria-label="知识库功能">
        <button
          type="button"
          className={view === "materials" ? "is-active" : ""}
          onClick={() => switchView("materials")}
          data-testid="knowledge-workspace-materials"
        >
          <span className="knowledge-workspace-number">01</span>
          <span><b>素材知识</b><small>线索、天气、种植等纯知识干货</small></span>
          <em>{data.knowledge_count} 条</em>
        </button>
        <Link to="/patterns" data-testid="knowledge-workspace-patterns">
          <span className="knowledge-workspace-number">02</span>
          <span><b>榜单共性</b><small>比较多部小说的前 5 章或全书规律</small></span>
          <em>2 本起</em>
        </Link>
        <button
          type="button"
          className={view === "skill" ? "is-active" : ""}
          onClick={() => switchView("skill")}
          data-testid="knowledge-workspace-skill"
        >
          <span className="knowledge-workspace-number">03</span>
          <span><b>作品 Skill</b><small>把全书拆解结论变成可执行创作规范</small></span>
          <em>PRO · {sources.data?.total ?? 0} 本可选</em>
        </button>
      </nav>

      {view === "materials" ? (
        <MaterialsWorkspace
          data={data}
          sources={sources as QueryState<KnowledgeSourceList>}
          genres={genres as QueryState<{ items: MaterialLabGenre[] }>}
          materials={materials as QueryState<MaterialListResult>}
          extract={extract as ExtractState}
          sourceGenres={sourceGenres}
          setSourceGenres={setSourceGenres}
          genre={genre}
          setGenre={setGenre}
          q={q}
          setQ={setQ}
          category={category}
          setCategory={setCategory}
          representativeOnly={representativeOnly}
          setRepresentativeOnly={setRepresentativeOnly}
          page={page}
          setPage={setPage}
          pages={pages}
          total={total}
          resetPage={resetPage}
        />
      ) : (
        <SkillWorkspace
          sources={sources as QueryState<KnowledgeSourceList>}
          selectedBookId={selectedSkillBookId}
          setSelectedBookId={(bookId) => {
            setSelectedSkillBookId(bookId);
            setSkillArtifact(null);
            generateSkill.reset();
          }}
          generateSkill={generateSkill as SkillState}
          artifact={skillArtifact}
        />
      )}
    </section>
  );
}

function MaterialsWorkspace({
  data, sources, genres, materials, extract, sourceGenres, setSourceGenres,
  genre, setGenre, q, setQ, category, setCategory,
  representativeOnly, setRepresentativeOnly,
  page, setPage, pages, total, resetPage,
}: {
  data: KnowledgeLibrarySummary;
  sources: QueryState<KnowledgeSourceList>;
  genres: QueryState<{ items: MaterialLabGenre[] }>;
  materials: QueryState<MaterialListResult>;
  extract: ExtractState;
  sourceGenres: Record<number, string>;
  setSourceGenres: React.Dispatch<React.SetStateAction<Record<number, string>>>;
  genre: string; setGenre: (value: string) => void;
  q: string; setQ: (value: string) => void;
  category: string; setCategory: (value: string) => void;
  representativeOnly: boolean; setRepresentativeOnly: (value: boolean) => void;
  page: number; setPage: React.Dispatch<React.SetStateAction<number>>;
  pages: number; total: number; resetPage: () => void;
}) {
  const [sourceQuery, setSourceQuery] = useState("");
  const [sourceStatus, setSourceStatus] = useState<"all" | "extracted" | "pending">("all");
  const [sourcePage, setSourcePage] = useState(0);
  const sourcePageSize = 6;
  const sourceItems = useMemo(() => sources.data?.items ?? [], [sources.data?.items]);
  const extractedSourceCount = useMemo(() => sourceItems.filter((source) => source.extracted).length, [sourceItems]);
  const pendingSourceCount = sourceItems.length - extractedSourceCount;
  const filteredSources = useMemo(() => {
    const needle = sourceQuery.trim().toLocaleLowerCase();
    return sourceItems.filter((source) => {
      if (sourceStatus === "extracted" && !source.extracted) return false;
      if (sourceStatus === "pending" && source.extracted) return false;
      return needle.length === 0 || source.book_title.toLocaleLowerCase().includes(needle);
    });
  }, [sourceItems, sourceQuery, sourceStatus]);
  const sourcePages = Math.max(1, Math.ceil(filteredSources.length / sourcePageSize));
  const visibleSources = filteredSources.slice(sourcePage * sourcePageSize, (sourcePage + 1) * sourcePageSize);

  return (
    <div className="knowledge-workspace-body" data-testid="knowledge-materials-workspace">
      <details className="knowledge-ingest" data-testid="knowledge-library-sources">
        <summary>
          <span><b>管理全书来源</b><small>按题材分类提炼，每本只保留少量代表知识</small><i className="knowledge-pro-chip">PRO</i></span>
          <span className="knowledge-source-summary">
            <i>已提取 {extractedSourceCount}</i><i>待提取 {pendingSourceCount}</i><em>{sources.data?.total ?? 0} 本</em><b aria-hidden="true">⌄</b>
          </span>
        </summary>
        <div className="knowledge-ingest-body">
          {sources.isLoading ? <Loading /> : sources.error ? <ErrorState error={sources.error} /> : !sources.data?.items.length ? (
            <div className="notice" data-testid="knowledge-library-no-sources">
              还没有可用来源。先在书库打开一部小说，完成“拆文 · 全文”。 <Link to="/library">去书库 →</Link>
            </div>
          ) : (
            <>
              <div className="knowledge-source-tools">
                <label><span aria-hidden="true">⌕</span><input type="search" aria-label="搜索全书来源" placeholder="搜索书名" value={sourceQuery} onChange={(event) => { setSourceQuery(event.target.value); setSourcePage(0); }} /></label>
                <div className="knowledge-source-status-filter" aria-label="提取状态">
                  {([
                    ["all", `全部 ${sourceItems.length}`],
                    ["extracted", `已提取 ${extractedSourceCount}`],
                    ["pending", `待提取 ${pendingSourceCount}`],
                  ] as const).map(([value, label]) => (
                    <button type="button" key={value} aria-pressed={sourceStatus === value} className={sourceStatus === value ? "is-active" : ""} onClick={() => { setSourceStatus(value); setSourcePage(0); }}>{label}</button>
                  ))}
                </div>
                <span>{filteredSources.length} 本结果</span>
              </div>
              {visibleSources.length ? (
                <div className="knowledge-source-list" data-testid="knowledge-source-list">
                  {visibleSources.map((source) => {
                    const selectedGenre = sourceGenres[source.book_id] ?? source.genre_slug;
                    const isExtracting = extract.isPending && extract.variables?.bookId === source.book_id;
                    return (
                      <div className="knowledge-source-row" key={source.book_id} data-testid={`knowledge-source-${source.book_id}`}>
                        <div><Link to={`/books/${source.book_id}`}>{source.book_title}</Link><span>全文拆文已完成 · {source.extracted ? `${source.material_count} 条素材` : "尚未提取"}</span></div>
                        <span className={`knowledge-source-state ${source.extracted ? "is-extracted" : ""}`}>{source.extracted ? "已提取" : "待提取"}</span>
                        <select
                          aria-label={`${source.book_title}的题材类型`}
                          value={selectedGenre || ""}
                          onChange={(event) => setSourceGenres((current) => ({ ...current, [source.book_id]: event.target.value }))}
                        >
                          <option value="">自动判断题材</option>
                          {(genres.data?.items ?? []).map((item) => <option key={item.slug} value={item.slug}>{item.label}</option>)}
                        </select>
                        <button className="secondary" type="button" disabled={extract.isPending} onClick={() => extract.mutate({ bookId: source.book_id, genreSlug: selectedGenre || undefined })}>
                          {isExtracting ? "正在提取…" : source.extracted ? "重新提取 · Pro" : "提取素材 · Pro"}
                        </button>
                      </div>
                    );
                  })}
                </div>
              ) : <div className="knowledge-source-empty">没有符合当前条件的全书来源。</div>}
              {sourcePages > 1 ? (
                <div className="knowledge-source-pagination">
                  <button type="button" className="secondary" disabled={sourcePage === 0} onClick={() => setSourcePage((value) => value - 1)}>上一页</button>
                  <span>{sourcePage + 1} / {sourcePages}</span>
                  <button type="button" className="secondary" disabled={sourcePage + 1 >= sourcePages} onClick={() => setSourcePage((value) => value + 1)}>下一页</button>
                </div>
              ) : null}
            </>
          )}
          <ProActionError error={extract.error} fallback="提取失败" />
        </div>
      </details>

      <section className="knowledge-section knowledge-catalog" data-testid="knowledge-library-results">
        <div className="knowledge-section-title">
          <div><p>知识目录</p><h2>按创作问题查，不按书名翻</h2></div><span>{total} 条结果</span>
        </div>
        <div className="knowledge-taxonomy" data-testid="knowledge-taxonomy">
          <div className="knowledge-genre-tabs" aria-label="题材分类">
            <button type="button" className={!genre ? "is-active" : ""} onClick={() => { setGenre(""); setCategory(""); resetPage(); }}>全部题材</button>
            {data.taxonomy.map((item) => (
              <button type="button" key={item.slug} className={genre === item.slug ? "is-active" : ""} onClick={() => { setGenre(item.slug); setCategory(""); resetPage(); }}>
                {item.label}<b>{item.count}</b>
              </button>
            ))}
          </div>
          <div className="knowledge-category-tabs" aria-label={genre ? `${data.taxonomy.find((item) => item.slug === genre)?.label ?? "题材"}分类` : "常用分类"}>
            <button type="button" className={!category ? "is-active" : ""} onClick={() => { setCategory(""); resetPage(); }}>{genre ? "全部分类" : "全部分类"}</button>
            {(genre ? data.taxonomy.find((item) => item.slug === genre)?.categories ?? [] : data.by_category.slice(0, 12)).map((item) => (
              <button type="button" key={item.key} className={category === item.key ? "is-active" : ""} onClick={() => { setCategory(item.key); resetPage(); }}>
                {item.label}<b>{item.count}</b>
              </button>
            ))}
          </div>
        </div>
        <div className="knowledge-filters">
          <select aria-label="题材类型" value={genre} onChange={(event) => { setGenre(event.target.value); setCategory(""); resetPage(); }}>
            <option value="">全部题材</option>
            {data.by_genre.map((item) => <option key={item.slug} value={item.slug}>{item.label}（{item.count}）</option>)}
          </select>
          <select aria-label="展示范围" value={representativeOnly ? "primary" : "all"} onChange={(event) => { setRepresentativeOnly(event.target.value === "primary"); resetPage(); }}>
            <option value="all">本库全部知识</option>
            <option value="primary">跨书代表（去重）</option>
          </select>
          <label><span aria-hidden="true">⌕</span><input type="search" aria-label="搜索素材" placeholder="搜实物线索、开篇异常、天气变化、田间管理……" value={q} onChange={(event) => { setQ(event.target.value); resetPage(); }} /></label>
        </div>

        {materials.isLoading ? <Loading /> : materials.error ? <ErrorState error={materials.error} /> : total === 0 ? (
          <div className="notice" data-testid="knowledge-library-empty">素材库目前为空。可以从已完成全文分析的小说中识别线索，或稍后导入原始素材重新梳理。</div>
        ) : (
          <>
            <ol className="knowledge-cards">
              {materials.data!.items.map((item, index) => <KnowledgeCard key={item.id} item={item} number={page * 24 + index + 1} />)}
            </ol>
            {pages > 1 ? (
              <div className="knowledge-pagination">
                <button className="secondary" type="button" disabled={page === 0} onClick={() => setPage((value) => value - 1)}>上一页</button>
                <span>{page + 1} / {pages}</span>
                <button className="secondary" type="button" disabled={page + 1 >= pages} onClick={() => setPage((value) => value + 1)}>下一页</button>
              </div>
            ) : null}
          </>
        )}
      </section>
    </div>
  );
}

function KnowledgeCard({ item, number }: { item: MaterialItem; number: number }) {
  const paragraphIds = item.source_paragraph_ids.slice(0, 3);
  return (
    <li className="knowledge-card">
      <span className="knowledge-card-number">{String(number).padStart(2, "0")}</span>
      <div className="knowledge-card-main">
        <div className="knowledge-card-meta"><span>{item.category_label}</span><i>·</i><span>{item.subcategory_label}</span></div>
        <h3>{item.title}</h3>
        <p className="knowledge-card-example">{item.concise_example || item.source_excerpt || "当前条目暂无示例。"}</p>
        <dl>
          <dt>知识分类</dt><dd>{item.category_label} · {item.subcategory_label}</dd>
          {item.applicable_stage ? <><dt>出现位置</dt><dd>{item.applicable_stage}</dd></> : null}
        </dl>
        {item.origin === "whole_book" && item.book_id != null && item.chapter_id != null ? (
          <details className="knowledge-evidence">
            <summary>查看原文依据</summary>
            {item.source_excerpt ? <blockquote>{item.source_excerpt}</blockquote> : null}
            <p>来源：<Link to={`/books/${item.book_id}?chapter=${item.chapter_id}&view=reading`}>{item.source_book_title}</Link>{paragraphIds.length ? ` · 段落 ${paragraphIds.join("、")}` : " · 段落待定位"}{item.source_paragraph_ids.length > paragraphIds.length ? ` 等 ${item.source_paragraph_ids.length} 段` : ""}</p>
            <small>{item.verification_label}</small>
          </details>
        ) : item.origin === "reference_corpus" ? (
          <details className="knowledge-evidence">
            <summary>{item.source_material_kind === "reference" ? "查看资料依据" : "查看原文依据"}</summary>
            {item.source_excerpt ? <blockquote>{item.source_excerpt}</blockquote> : null}
            <p>来源：{item.source_book_title}{paragraphIds.length ? ` · ${paragraphIds.join("、")}` : ""}</p>
            <small>{item.verification_label}</small>
          </details>
        ) : null}
      </div>
    </li>
  );
}

function SkillWorkspace({ sources, selectedBookId, setSelectedBookId, generateSkill, artifact }: {
  sources: QueryState<KnowledgeSourceList>;
  selectedBookId: number | null;
  setSelectedBookId: (bookId: number) => void;
  generateSkill: SkillState;
  artifact: BookSkillArtifact | null;
}) {
  return (
    <div className="knowledge-workspace-body" data-testid="knowledge-skill-workspace">
      <section className="skill-builder">
        <div className="skill-builder-intro">
          <p>作品机制迁移</p><div className="skill-title"><h2>选择一本全文拆完的小说</h2><ProTag capability="book_skill_generation" /></div>
          <p>StoryLens 会把全书报告里的结构阶段、人物功能、悬念生命周期、节奏区间和章节职责整理成一个可下载的 SKILL.md。它学习机制，不复制原文与专有设定。</p>
          <div className="skill-boundary"><b>生成条件</b><span>小说</span><span>全文拆文完成</span><span>正式报告可读取</span></div>
        </div>
        <div className="skill-builder-panel">
          <h3>可生成的书</h3>
          {sources.isLoading ? <Loading /> : sources.error ? <ErrorState error={sources.error} /> : !sources.data?.items.length ? (
            <div className="notice">目前没有符合条件的小说。先完成一次“拆文 · 全文”。</div>
          ) : (
            <div className="skill-book-list" role="radiogroup" aria-label="选择生成 Skill 的小说">
              {sources.data.items.map((source) => (
                <button type="button" role="radio" aria-checked={selectedBookId === source.book_id} className={selectedBookId === source.book_id ? "is-selected" : ""} key={source.book_id} onClick={() => setSelectedBookId(source.book_id)}>
                  <span>{selectedBookId === source.book_id ? "✓" : ""}</span><b>{source.book_title}</b><small>{source.material_count ? `${source.material_count} 条素材已沉淀` : "全文报告已完成"}</small>
                </button>
              ))}
            </div>
          )}
          <button type="button" className="primary skill-generate" disabled={selectedBookId == null || generateSkill.isPending} onClick={() => selectedBookId != null && generateSkill.mutate(selectedBookId)} data-testid="generate-book-skill">
            {generateSkill.isPending ? "正在整理 Skill…" : "生成并下载 SKILL.md · Pro"}
          </button>
          <ProActionError error={generateSkill.error} fallback="生成失败" />
        </div>
      </section>

      {artifact ? (
        <section className="skill-result" data-testid="book-skill-result">
          <div><p>已生成</p><h2>{artifact.filename}</h2><span>来自全书任务 #{artifact.source_run_id} · {artifact.sections.length} 个执行模块</span></div>
          <button type="button" className="secondary" onClick={() => saveSkillFile(artifact)}>再次下载</button>
          <details><summary>预览 Skill 内容</summary><pre>{artifact.content}</pre></details>
        </section>
      ) : null}
    </div>
  );
}
