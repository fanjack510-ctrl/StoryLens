import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { booksApi } from "../services/booksApi";
import { analysisApi } from "../services/analysisApi";
import { formatSceneDisplayLabel } from "../services/formatSceneDisplayLabel";
import {
  adjacentBodyChapters,
  applyNavigateToChapterReading,
  bodyChapters,
  scrollReadingPaneToTop,
} from "../services/chapterNavigation";
import {
  prefetchAdjacentChapterParagraphs,
  prefetchChapterParagraphs,
} from "../services/chapterParagraphPrefetch";
import { useUiStore } from "../stores/uiStore";
import { Empty, ErrorState, Loading, Badge } from "../components/common/States";
import { StateView } from "../components/ui/StateView";
import { ReparseDialog } from "../components/books/ReparseDialog";
import { ChapterListViewport } from "../components/books/ChapterListViewport";
import { ChapterAdjacentNav } from "../components/books/ChapterAdjacentNav";


function fileExtLabel(name?: string) {
  if (!name) return null;
  const m = name.match(/\.([a-z0-9]+)$/i);
  return m ? m[1].toUpperCase() : null;
}

function parsePositiveInt(value: string | null): number | null {
  if (!value) return null;
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : null;
}

export function BookWorkspacePage() {
  const params = useParams();
  const bookId = Number(params.bookId || 1);
  const [searchParams, setSearchParams] = useSearchParams();
  const chapterFromUrl = parsePositiveInt(searchParams.get("chapter"));
  const [chapter, setChapter] = useState(chapterFromUrl || 0);
  const [selectedScene, setScene] = useState<any>();
  const [evidence, setEvidence] = useState<string[]>([]);
  const [offset, setOffset] = useState(0);
  const [loaded, setLoaded] = useState<any[]>([]);
  const [displayedChapterId, setDisplayedChapterId] = useState(0);
  const [diagnostics, setDiagnostics] = useState<any>();
  const [reparseOpen, setReparseOpen] = useState(false);
  const chapterListRef = useRef<HTMLDivElement>(null);
  const pendingScrollTopRef = useRef(false);
  const qc = useQueryClient();
  const { fontSize, lineHeight, setReading, demo } = useUiStore();
  const book = useQuery({
    queryKey: ["book", bookId],
    queryFn: () => booksApi.detail(bookId),
    enabled: !!bookId,
  });
  const chapters = useQuery({
    queryKey: ["chapters", bookId],
    queryFn: () => booksApi.chapters(bookId),
    enabled: !!bookId,
  });
  useEffect(() => {
    if (chapterFromUrl && chapterFromUrl !== chapter) {
      setChapter(chapterFromUrl);
    }
  }, [chapterFromUrl, chapter]);
  useEffect(() => {
    if (chapter || !chapters.data?.length) return;
    if (chapterFromUrl) return;
    const first =
      chapters.data.find((item) => item.section_type === "chapter") || chapters.data[0];
    if (first) setChapter(first.id);
  }, [chapters.data, chapter, chapterFromUrl]);
  useEffect(() => {
    setOffset(0);
    pendingScrollTopRef.current = true;
    // Keep previous `loaded` until the new chapter body is ready (no blank flash).
  }, [chapter]);
  const paragraphs = useQuery({
    queryKey: ["paragraphs", chapter, offset],
    queryFn: () => booksApi.paragraphs(chapter, offset, 200),
    enabled: !!chapter,
    placeholderData: keepPreviousData,
  });
  useEffect(() => {
    if (!paragraphs.data || paragraphs.isPlaceholderData) return;
    setLoaded((current) =>
      offset === 0
        ? paragraphs.data.items
        : [...current, ...paragraphs.data.items],
    );
    if (offset === 0) {
      setDisplayedChapterId(chapter);
      if (pendingScrollTopRef.current) {
        pendingScrollTopRef.current = false;
        requestAnimationFrame(() => {
          scrollReadingPaneToTop();
        });
      }
    }
  }, [paragraphs.data, paragraphs.isPlaceholderData, offset, chapter]);
  const adjacent = useMemo(
    () => adjacentBodyChapters(chapters.data, chapter),
    [chapters.data, chapter],
  );
  useEffect(() => {
    if (!chapter || paragraphs.isPlaceholderData || paragraphs.isFetching) return;
    prefetchAdjacentChapterParagraphs(qc, adjacent.prev?.id, adjacent.next?.id);
  }, [
    chapter,
    paragraphs.isPlaceholderData,
    paragraphs.isFetching,
    adjacent.prev?.id,
    adjacent.next?.id,
    qc,
  ]);
  const scenes = useQuery({
    queryKey: ["scenes", chapter],
    queryFn: () => analysisApi.scenes(chapter),
    enabled: !!chapter,
  });
  const artifacts = useQuery({
    queryKey: ["artifacts", selectedScene?.scene_key],
    queryFn: () => analysisApi.artifacts(selectedScene.scene_key),
    enabled: !!selectedScene,
  });

  const currentChapter = useMemo(
    () => chapters.data?.find((c) => c.id === chapter),
    [chapters.data, chapter],
  );
  const formatLabel = fileExtLabel(book.data?.source_file_name);
  const bodyCount = bodyChapters(chapters.data).length;
  const chapterCount = bodyCount || chapters.data?.length;
  const chapterMissing =
    Boolean(chapterFromUrl) &&
    Boolean(chapters.data?.length) &&
    !chapters.data?.some((c) => c.id === chapterFromUrl);

  const switchingChapter =
    Boolean(chapter) &&
    (paragraphs.isFetching || paragraphs.isPlaceholderData) &&
    loaded.length > 0 &&
    displayedChapterId !== 0 &&
    displayedChapterId !== chapter;

  const showInitialLoading =
    Boolean(chapter) &&
    !chapterMissing &&
    paragraphs.isLoading &&
    loaded.length === 0 &&
    !paragraphs.isPlaceholderData;

  const selectChapter = (id: number) => {
    if (id === chapter) return;
    setChapter(id);
    applyNavigateToChapterReading(setSearchParams, id);
  };

  const handlePrefetchChapter = (id: number) => {
    prefetchChapterParagraphs(qc, id);
  };

  const locate = async (id: number) => {
    const rows = await analysisApi.evidence(id);
    const paragraphIds = rows.map((row) => row.paragraph_id);
    if (paragraphIds[0]) {
      const page = await booksApi.paragraphs(chapter, 0, 200, paragraphIds[0]);
      setLoaded(page.items);
      setOffset(page.offset);
    }
    setEvidence(paragraphIds);
    setTimeout(
      () =>
        document
          .getElementById(paragraphIds[0])
          ?.scrollIntoView({ behavior: "smooth", block: "center" }),
      0,
    );
  };

  if (book.isLoading) return <Loading />;

  const bookTitle = book.data?.title || "选择一本书";
  const chapterTitle = currentChapter?.display_title || currentChapter?.title;
  const switchingOrdinal =
    bodyChapters(chapters.data).findIndex((c) => c.id === chapter) + 1;

  return (
    <section className="workspace workspace-content" data-testid="book-workspace-page">
      <aside className="structure-pane workspace-book-nav" data-testid="workspace-book-nav">
        <div className="pane-head workspace-book-info">
          <small>当前书籍</small>
          <h2 className="workspace-book-title" title={bookTitle}>
            {bookTitle}
          </h2>
          {(formatLabel || chapterCount != null) && (
            <p className="workspace-book-meta">
              {[formatLabel, chapterCount != null ? `${chapterCount} 章` : null]
                .filter(Boolean)
                .join(" · ")}
            </p>
          )}
        </div>

        <div className="workspace-book-tools">
          <span className="workspace-nav-label">书籍工具</span>
          <div className="workspace-book-tools-actions">
            <button
              type="button"
              className="workspace-tool-link"
              onClick={async () =>
                setDiagnostics(await booksApi.diagnostics(bookId))
              }
            >
              导入诊断
            </button>
            <span className="workspace-tool-sep" aria-hidden="true">
              ·
            </span>
            <button
              type="button"
              className="workspace-tool-link"
              onClick={() => setReparseOpen(true)}
            >
              重新识别章节
            </button>
          </div>
          {diagnostics && (
            <div className="notice workspace-diagnostics">
              <b>识别结果</b>
              <span>编码 {diagnostics.encoding}</span>
              <span>
                候选 {diagnostics.candidate_count} · 最终{" "}
                {diagnostics.final_chapter_count}章
              </span>
              {diagnostics.warning && <span>CHAPTER_DETECTION_SUSPECT</span>}
            </div>
          )}
        </div>

        <div className="workspace-nav-section workspace-nav-section--chapters">
          <div className="workspace-chapter-heading-row">
            <h3 className="workspace-nav-label">章节</h3>
            {bodyCount > 0 ? (
              <span className="workspace-chapter-count-hint">{bodyCount} 章</span>
            ) : null}
          </div>
          <ChapterListViewport
            chapters={chapters.data || []}
            currentChapterId={chapter}
            onSelect={selectChapter}
            onPrefetch={handlePrefetchChapter}
            listRef={chapterListRef}
          />
        </div>

        <div className="workspace-nav-section">
          <h3 className="workspace-nav-label">场景</h3>
          <div className="workspace-scene-list">
            {!scenes.data?.length ? (
              <StateView
                kind="empty"
                title="尚未生成场景"
                description="完成场景边界分析后会显示在这里。"
                className="workspace-scene-empty"
                data-testid="workspace-scene-empty"
              />
            ) : (
              scenes.data.map((s) => (
                <button
                  type="button"
                  className={`workspace-scene-item${selectedScene?.id === s.id ? " selected" : ""}`}
                  onClick={() => setScene(s)}
                  key={s.id}
                  data-scene-id={s.id}
                  title={s.scene_key || formatSceneDisplayLabel(s)}
                >
                  <span className="workspace-scene-ordinal">
                    {formatSceneDisplayLabel(s)}
                  </span>
                  {s.scene_key && typeof s.ordinal === "number" && Number.isFinite(s.ordinal) ? (
                    <span className="workspace-scene-name">{s.scene_key}</span>
                  ) : null}
                  <Badge tone={s.boundary_detected ? "success" : "neutral"}>
                    {s.boundary_detected ? "边界" : "章末"}
                  </Badge>
                </button>
              ))
            )}
          </div>
        </div>
      </aside>

      <article className="reader workspace-reader">
        <div className="reader-tools">
          <button
            onClick={() => setReading(Math.max(14, fontSize - 1), lineHeight)}
          >
            A−
          </button>
          <span>{fontSize}px</span>
          <button onClick={() => setReading(fontSize + 1, lineHeight)}>
            A＋
          </button>
          <button
            onClick={() => setReading(fontSize, lineHeight === 1.9 ? 2.2 : 1.9)}
          >
            行距
          </button>
          <button onClick={() => setEvidence([])}>完整正文</button>
        </div>

        <div
          className="reading-content-scroll-region"
          data-testid="reading-content-scroll-region"
        >
        <div className="workspace-reading-canvas">
          <header className="workspace-reading-header">
            <p className="eyebrow workspace-reading-label">正文阅读</p>
            {chapterMissing ? (
              <StateView
                kind="empty"
                title="当前章节不存在或已失效"
                description="请返回第一章，或回到书库重新打开书籍。"
                data-testid="workspace-chapter-missing"
                primaryAction={{
                  label: "返回第一章",
                  testId: "workspace-goto-first-chapter",
                  onClick: () => {
                    const first = bodyChapters(chapters.data)[0];
                    if (first) selectChapter(first.id);
                  },
                }}
                secondaryAction={{
                  label: "返回书库",
                  testId: "workspace-back-library-missing",
                  variant: "secondary",
                  onClick: () => {
                    window.location.href = "/library";
                  },
                }}
              />
            ) : !chapter ? (
              <StateView
                kind="empty"
                title="选择一个章节开始阅读"
                data-testid="workspace-no-chapter"
              />
            ) : (
              <h1 className="workspace-chapter-heading" title={chapterTitle}>
                {chapterTitle}
              </h1>
            )}
            {!chapterMissing && chapter ? (
              <ChapterAdjacentNav
                compact
                prev={adjacent.prev}
                next={adjacent.next}
                chapters={chapters.data || []}
                onSelect={selectChapter}
                onPrefetch={handlePrefetchChapter}
              />
            ) : null}
          </header>

          {switchingChapter ? (
            <div
              className="workspace-chapter-switch-hint"
              data-testid="workspace-chapter-switching"
              role="status"
            >
              <span className="workspace-chapter-switch-bar" aria-hidden="true" />
              <span>
                正在打开第{switchingOrdinal > 0 ? switchingOrdinal : ""}章…
              </span>
            </div>
          ) : null}

          {(paragraphs.data?.total || 0) > 2000 && (
            <p className="notice">当前章节异常偏大，可能需要重新识别章节。</p>
          )}

          <div
            className={`prose workspace-prose${switchingChapter ? " workspace-prose--switching" : ""}`}
            style={{ fontSize, lineHeight }}
            data-displayed-chapter={displayedChapterId || undefined}
            data-target-chapter={chapter || undefined}
          >
            {chapterMissing || !chapter ? null : showInitialLoading ? (
              <StateView
                kind="loading"
                title="正在载入章节"
                data-testid="workspace-chapter-loading"
              />
            ) : paragraphs.error && !loaded.length ? (
              <ErrorState error={paragraphs.error} />
            ) : loaded.length ? (
              loaded.slice(Math.max(0, loaded.length - 600)).map((p) => (
                <div
                  id={p.id}
                  className={`paragraph ${evidence.includes(p.id) ? "highlight" : ""}`}
                  key={p.id}
                >
                  <button
                    title="复制段落ID"
                    onClick={() => navigator.clipboard?.writeText(p.id)}
                  >
                    {p.id}
                  </button>
                  <p>{p.raw_text}</p>
                </div>
              ))
            ) : (
              <StateView
                kind="empty"
                title="这个章节没有可显示的正文"
                data-testid="workspace-empty-body"
              />
            )}
            {paragraphs.data?.has_more && !paragraphs.isPlaceholderData && (
              <button onClick={() => setOffset(offset + paragraphs.data!.limit)}>
                继续加载正文
              </button>
            )}
          </div>

          {!chapterMissing && chapter ? (
            <ChapterAdjacentNav
              prev={adjacent.prev}
              next={adjacent.next}
              chapters={chapters.data || []}
              onSelect={selectChapter}
              onPrefetch={handlePrefetchChapter}
            />
          ) : null}
        </div>
        </div>
      </article>

      <aside className="analysis-pane workspace-inspector">
        <div className="tabs">
          <button className="active">场景结构</button>
          <button>证据</button>
          <button>历史</button>
        </div>
        {selectedScene ? (
          <>
            <div className="scene-title">
              <Badge tone="success">真实数据</Badge>
              <h2>{selectedScene.scene_key}</h2>
              <p>
                {selectedScene.start_paragraph_id} →{" "}
                {selectedScene.end_paragraph_id}
              </p>
            </div>
            {artifacts.data?.map((a) => (
              <div className="artifact" key={a.id}>
                <header>
                  <b>结构分析</b>
                  <button onClick={() => locate(a.id)}>定位证据</button>
                </header>
                {Object.entries(JSON.parse(a.payload_json))
                  .slice(0, 9)
                  .map(([k, v]) => (
                    <details open key={k}>
                      <summary>{k}</summary>
                      <pre>{JSON.stringify(v, null, 2)}</pre>
                    </details>
                  ))}
              </div>
            ))}
          </>
        ) : (
          <Empty text="选择一个场景查看分析" />
        )}
        <div className="planned">
          <Badge>规划中</Badge>
          <span>情节链 · 钩子 · 人物塑造 · 场景描写</span>
          {demo && <small>演示模式已开启，不写入数据库</small>}
        </div>
      </aside>

      {reparseOpen && (
        <ReparseDialog
          bookId={bookId}
          onClose={() => setReparseOpen(false)}
          onDone={async (id) => {
            setReparseOpen(false);
            await qc.invalidateQueries({ queryKey: ["chapters", bookId] });
            if (id !== bookId) location.href = `/books/${id}`;
            else {
              setChapter(0);
              await chapters.refetch();
            }
          }}
        />
      )}
    </section>
  );
}
