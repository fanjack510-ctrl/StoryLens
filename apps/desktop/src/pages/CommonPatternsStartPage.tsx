import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { booksApi } from "../services/booksApi";
import { collectionsApi } from "../services/collectionsApi";
import { ApiError } from "../services/apiClient";
import { Loading, ErrorState } from "../components/common/States";
import { PageHeader, PageSubtitle, PageTitle } from "../components/ui/PageHeader";

/** 共性视图的第一步：挑几本要比的书。
 *
 *  这一页存在的原因是用户的一句话：「这里两个书单是什么意思？为啥上来要建书单？
 *  这个功能最终不就是为了提炼共性，那是不是应该统一在共性分析大功能下？」
 *
 *  他说的对。书单原来在书库筛选条上独占一行，旁边还站着共性视图的入口——
 *  一个刚装好、一个书单都没有的库里，那两行合起来只干了一件事：
 *  **催人去建一个他还不知道有什么用的东西**。
 *
 *  真正的顺序反过来：先知道要比哪几本，再决定这组叫什么。
 *  所以圈书在这儿，起名是可选的；不填时生成一个带时间的临时名称。
 *  当前共性结果路由以书单 ID 为稳定范围，因此两种情况都会保存，不能把未命名组
 *  说成「一次性」——刷新后它仍然存在。
 */
export function CommonPatternsStartPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [picked, setPicked] = useState<Set<number>>(() => new Set());
  const [name, setName] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "analyzed" | "pending">("all");
  const [error, setError] = useState<string | null>(null);

  const library = useQuery({ queryKey: ["library"], queryFn: booksApi.library });
  const collections = useQuery({ queryKey: ["collections"], queryFn: collectionsApi.list });

  const rows = useMemo(() => library.data ?? [], [library.data]);
  const fictionRows = useMemo(() => rows.filter((book) => book.material_kind !== "reference"), [rows]);
  const pickedRows = useMemo(() => fictionRows.filter((book) => picked.has(book.id)), [fictionRows, picked]);
  const visibleRows = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return rows.filter((book) => {
      const analyzed = !book.analysis_state_label.includes("未分析");
      if (filter === "analyzed" && !analyzed) return false;
      if (filter === "pending" && analyzed) return false;
      return needle.length === 0 || book.title.toLocaleLowerCase().includes(needle);
    });
  }, [filter, query, rows]);

  const start = useMutation({
    mutationFn: async () => {
      const ids = [...picked];
      // 不起名也要有个名字——后端要一个。用当下这一刻做标签，
      // 让它在书单列表里显然是「随手比的那次」，而不是一个正式命名的收藏。
      const label = name.trim() || `临时比较 · ${new Date().toLocaleString()}`;
      const created = await collectionsApi.create({ name: label });
      await collectionsApi.addBooks(created.id, ids);
      return created.id;
    },
    onSuccess: (id) => {
      void qc.invalidateQueries({ queryKey: ["collections"] });
      navigate(`/collections/${id}/patterns`);
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "没能开始比较。"),
  });

  if (library.isLoading) return <Loading />;
  if (library.error) return <ErrorState error={library.error} />;

  const toggle = (id: number) =>
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <section className="page cp-start" data-testid="common-patterns-start">
      <PageHeader>
        <div>
          <PageTitle>榜单共性</PageTitle>
          <PageSubtitle>选几部榜单小说，比较它们的前 5 章或全书共同用了什么开篇机制。</PageSubtitle>
        </div>
        <Link className="secondary" to="/knowledge" data-testid="cp-back">
          回知识库
        </Link>
      </PageHeader>

      {/* 存过的组直接选，不用重挑。这是书单唯一剩下的用途，所以它长在这儿。 */}
      {(collections.data || []).length > 0 ? (
        <section className="cp-saved" data-testid="cp-saved" aria-label="最近比较">
          <div className="cp-saved-heading">
            <strong>最近比较</strong>
            <span>打开已有结果，不必重新挑书</span>
          </div>
          <div className="cp-saved-list">
            {(collections.data || []).map((c) => (
              <Link key={c.id} className="secondary" to={`/collections/${c.id}/patterns`}>
                {c.name}
                <em>{c.book_count} 本</em>
              </Link>
            ))}
          </div>
        </section>
      ) : null}

      <div className="cp-builder">
        <section className="cp-library" aria-labelledby="cp-library-title">
          <header className="cp-panel-heading">
            <div>
              <span className="cp-eyebrow">第 1 步</span>
              <h2 id="cp-library-title">选择对比小说</h2>
            </div>
            <span className="cp-total">{fictionRows.length} 本可选</span>
          </header>

          <div className="cp-tools">
            <label className="cp-search">
              <span aria-hidden="true">⌕</span>
              <input
                type="search"
                value={query}
                aria-label="搜索要比较的小说"
                placeholder="搜索书名"
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
            <div className="cp-filters" aria-label="分析状态筛选">
              {([
                ["all", "全部"],
                ["analyzed", "已分析"],
                ["pending", "未分析"],
              ] as const).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  className={filter === value ? "is-active" : ""}
                  aria-pressed={filter === value}
                  onClick={() => setFilter(value)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <ul className="cp-picklist" data-testid="cp-picklist">
            {visibleRows.map((b) => {
              // 工具书比不了：共性视图比的是小说怎么写，「读懂」的产出不在这个维度上。
              // 灰掉并写明原因，而不是让人选完拿到一屏空结果。
              const blocked = b.material_kind === "reference";
              const on = picked.has(b.id);
              return (
                <li key={b.id}>
                  <button
                    type="button"
                    className={`cp-pick ${on ? "is-on" : ""} ${blocked ? "is-blocked" : ""}`}
                    disabled={blocked}
                    aria-pressed={on}
                    data-testid={`cp-pick-${b.id}`}
                    onClick={() => toggle(b.id)}
                  >
                    <span className="cp-tick" aria-hidden="true">
                      {on ? "✓" : ""}
                    </span>
                    <span className="cp-book-copy">
                      <span className="cp-name">{b.title}</span>
                      <span className="cp-meta">
                        {blocked ? "工具书 · 比不了小说共性" : b.kind_label}
                      </span>
                    </span>
                    <span className={`cp-state ${b.analysis_state_label.includes("未分析") ? "is-muted" : ""}`}>
                      {b.analysis_state_label}
                      {!blocked && b.chapter_count > 0 ? ` · ${b.chapter_count} 章` : ""}
                    </span>
                  </button>
                </li>
              );
            })}
            {visibleRows.length === 0 ? (
              <li className="cp-empty">没有找到符合条件的小说。</li>
            ) : null}
          </ul>
        </section>

        <aside className="cp-compare" aria-labelledby="cp-compare-title">
          <header className="cp-panel-heading">
            <div>
              <span className="cp-eyebrow">第 2 步</span>
              <h2 id="cp-compare-title">比较篮子</h2>
            </div>
            {picked.size > 0 ? (
              <button type="button" className="cp-clear" onClick={() => setPicked(new Set())}>
                清空
              </button>
            ) : null}
          </header>

          <div className="cp-progress" aria-hidden="true">
            <span className={picked.size >= 1 ? "is-done" : ""} />
            <span className={picked.size >= 2 ? "is-done" : ""} />
          </div>
          <p className="cp-selection-summary" data-testid="cp-count">
            <strong>已选 {picked.size} 本</strong>
            <span>{picked.size < 2 ? `还需 ${2 - picked.size} 本即可比较` : "已经可以开始比较"}</span>
          </p>

          <div className="cp-selected-list" data-testid="cp-selected-list">
            {pickedRows.length > 0 ? (
              pickedRows.map((book) => (
                <div className="cp-selected-book" key={book.id}>
                  <span title={book.title}>{book.title}</span>
                  <button type="button" aria-label={`移除${book.title}`} onClick={() => toggle(book.id)}>
                    ×
                  </button>
                </div>
              ))
            ) : (
              <div className="cp-selected-empty">
                <span aria-hidden="true">＋</span>
                <p>从左侧挑选至少两本小说</p>
                <small>这里只保留要比较的书，随时可移除。</small>
              </div>
            )}
          </div>

          <label className="cp-name-field">
            <span>这次比较的名字 <em>可不填</em></span>
            <input
              value={name}
              placeholder="例如：种田榜前五开篇"
              aria-label="这一组的名字"
              maxLength={120}
              onChange={(e) => setName(e.target.value)}
            />
          </label>

          <button
            type="button"
            className="primary cp-start-button"
            data-testid="cp-start"
            // 一本书没有共性可言。两本才谈得上「它们共同做对了什么」。
            disabled={picked.size < 2 || start.isPending}
            onClick={() => {
              setError(null);
              start.mutate();
            }}
          >
            {start.isPending ? "正在准备…" : `分析这 ${picked.size} 本的共性 →`}
          </button>
          <p className="muted cp-hint">
            {picked.size < 2 ? "至少选两本；一本书无法形成共性。" : "默认比较前 5 章，进入后可切换全书。"}
          </p>
          {error ? (
            <p className="notice" role="alert" data-testid="cp-error">
              {error}
            </p>
          ) : null}
        </aside>
      </div>
    </section>
  );
}
