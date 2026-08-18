import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { booksApi } from "../services/booksApi";
import { ApiError } from "../services/apiClient";
import { ErrorState, Loading } from "../components/common/States";
import { QwenFirstLaunchBanner } from "../components/onboarding/QwenFirstLaunchBanner";
import { FirstLaunchWizard } from "../components/onboarding/FirstLaunchWizard";
import { TelemetryInviteCard } from "../components/onboarding/TelemetryInviteCard";
import { useOnboardingStore } from "../stores/onboardingStore";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { OverflowMenu } from "../components/layout/OverflowMenu";
import { PageHeader, PageSubtitle, PageTitle } from "../components/ui/PageHeader";
import { StateView } from "../components/ui/StateView";
import { isLocalWebShell, useRuntimeInfo } from "../services/runtimeCapabilities";
import type { Book, ImportDiagnostics } from "../types";

const FORMAT_OPTIONS = ["TXT", "DOCX", "EPUB"] as const;
type FormatOption = (typeof FORMAT_OPTIONS)[number];

function fileFormat(name: string): FormatOption | "OTHER" {
  const ext = name.split(".").pop()?.toUpperCase();
  if (ext === "TXT" || ext === "DOCX" || ext === "EPUB") return ext;
  return "OTHER";
}

function importErrorKind(error: unknown): {
  title: string;
  tone: "danger" | "warning";
} {
  if (error instanceof ApiError) {
    const msg = `${error.code} ${error.message} ${String(error.detail || "")}`.toLowerCase();
    if (error.status === 413 || /过大|too large|size/i.test(msg)) {
      return { title: "文件过大", tone: "danger" };
    }
    if (/编码|encoding/i.test(msg)) {
      return { title: "编码无法识别", tone: "danger" };
    }
    if (/格式|format|不支持|invalid_file_type/i.test(msg)) {
      return { title: "文件格式不支持", tone: "danger" };
    }
    if (
      error.status === 409 ||
      error.code === "DUPLICATE_BOOK" ||
      /重复|duplicate|已存在|已导入/i.test(msg)
    ) {
      return { title: "书籍可能已存在", tone: "warning" };
    }
  }
  return { title: "导入失败", tone: "danger" };
}

/** Say which thing is wrong, not that something is.
 *
 *  The panel used to print one fixed sentence — "文件较大但只识别出一个章节" — for every kind of
 *  failure, and it was usually false: 《碧血洗银枪》 has two chapters and 《最终进化》 has 206. A
 *  warning that misdescribes what it found teaches the reader to dismiss it. */
function describeSuspectReasons(d: ImportDiagnostics): string {
  const reasons = d.suspect_reasons ?? [];
  const said: string[] = [];
  if (reasons.includes("SINGLE_CHAPTER")) said.push("整本书只切出了一章");
  if (reasons.includes("ONE_CHAPTER_DOMINATES") && d.max_chapter_share) {
    said.push(`其中一章占了全书 ${Math.round(d.max_chapter_share * 100)}%`);
  }
  if (reasons.includes("OVERSIZED_CHAPTER")) {
    said.push(`最长的一章有 ${d.max_chapter_characters.toLocaleString()} 字`);
  }
  if (reasons.includes("CHAPTER_TOO_MANY_PARAGRAPHS")) {
    said.push(`最长的一章有 ${d.max_chapter_paragraphs.toLocaleString()} 个自然段`);
  }
  if (reasons.includes("MARKERS_FOUND_BUT_NOT_ADOPTED")) {
    said.push(`找到 ${d.candidate_count} 处疑似章节标题，但都没能采纳`);
  }
  // Older diagnostics carry the warning without the reasons behind it.
  return said.length ? said.join("；") + "。" : "章节标题的格式可能没有被识别。";
}

export function LibraryPage() {
  const onboardingStatus = useOnboardingStore((s) => s.status);
  const [searchParams] = useSearchParams();
  const input = useRef<HTMLInputElement>(null);
  const runtime = useRuntimeInfo();
  const webShell = isLocalWebShell(runtime.data);
  const [search, setSearch] = useState("");
  const [formats, setFormats] = useState<Record<FormatOption, boolean>>({
    TXT: true,
    DOCX: true,
    EPUB: true,
  });
  const [sort, setSort] = useState<"recent" | "title">("recent");
  const [pendingFile, setPendingFile] = useState<File>();
  const [dragOver, setDragOver] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const qc = useQueryClient();
  const books = useQuery({ queryKey: ["books"], queryFn: booksApi.list });
  const upload = useMutation({
    mutationFn: booksApi.importFile,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["books"] }),
  });
  const preview = useMutation({ mutationFn: booksApi.preview });
  const accept = (files: FileList | null) => {
    const file = files?.[0];
    if (file) {
      setPendingFile(file);
      preview.mutate(file);
    }
  };
  const clearImport = () => {
    setPendingFile(undefined);
    preview.reset();
    upload.reset();
    if (input.current) input.current.value = "";
  };

  const visible = useMemo(() => {
    const list = (books.data || []).filter((book) => {
      const hay = book.title + book.source_file_name;
      if (search && !hay.includes(search)) return false;
      const fmt = fileFormat(book.source_file_name);
      if (fmt === "OTHER") return true;
      return formats[fmt];
    });
    const sorted = [...list];
    if (sort === "title") {
      sorted.sort((a, b) => a.title.localeCompare(b.title, "zh"));
    } else {
      sorted.sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at));
    }
    return sorted;
  }, [books.data, search, formats, sort]);

  const hasActiveFilter = Boolean(search) || !FORMAT_OPTIONS.every((f) => formats[f]);
  const isEmptyLibrary = !books.isLoading && !books.error && (books.data?.length ?? 0) === 0;
  const listHasRows = visible.length > 0;

  useEffect(() => {
    if (searchParams.get("import") === "1") {
      input.current?.click();
    }
  }, [searchParams]);

  const chapterPreviewLimit = 8;
  const previewTitles = preview.data?.chapter_titles || [];
  const moreChapters = Math.max(0, (preview.data?.final_chapter_count || 0) - chapterPreviewLimit);

  return (
    <section className="page library-page-compact" data-testid="library-page">
      {onboardingStatus === "pending" && <FirstLaunchWizard />}
      {onboardingStatus !== "pending" && <TelemetryInviteCard />}
      <QwenFirstLaunchBanner />
      <PageHeader className="library-title-compact">
        <div>
          <PageTitle>我的书库</PageTitle>
          <PageSubtitle>管理已导入的小说和分析项目</PageSubtitle>
          {webShell ? (
            <p className="muted library-local-upload-hint" data-testid="library-local-upload-hint">
              文件仅发送到本机 StoryLens 服务，不会上传互联网。
            </p>
          ) : null}
        </div>
        <Button
          variant="primary"
          data-testid="import-book"
          onClick={() => input.current?.click()}
        >
          导入小说
        </Button>
        <input
          ref={input}
          hidden
          type="file"
          accept=".txt,.docx,.epub"
          onChange={(event) => accept(event.target.files)}
        />
      </PageHeader>

      {preview.isPending && (
        <div className="import-panel import-panel--info" data-testid="import-panel-parsing">
          <h2>正在解析文件</h2>
          <p>正在提取文本并识别章节，请稍候…</p>
          <Loading />
        </div>
      )}
      {preview.error && (
        <div
          className={`import-panel import-panel--${importErrorKind(preview.error).tone}`}
          data-testid="import-panel-error"
          role="alert"
        >
          <h2>{importErrorKind(preview.error).title}</h2>
          <ErrorState error={preview.error as Error} />
          <div className="import-panel-actions">
            <Button variant="secondary" onClick={clearImport}>
              重新选择文件
            </Button>
          </div>
        </div>
      )}
      {preview.data && pendingFile && (
        <div
          className={`import-panel ${
            preview.data.warning === "CHAPTER_DETECTION_SUSPECT"
              ? "import-panel--warning"
              : "import-panel--success"
          }`}
          data-testid="import-panel"
        >
          <h2>文件已解析</h2>
          <p className="import-panel-file">
            <strong>{pendingFile.name}</strong>
            <span>
              {fileFormat(pendingFile.name)} · {preview.data.encoding.toUpperCase()} ·{" "}
              {(preview.data.byte_count / 1024 / 1024).toFixed(2)} MB
            </span>
          </p>
          {preview.data.warning === "CHAPTER_DETECTION_SUSPECT" ? (
            <div className="notice" role="status">
              <p>
                <b>识别出 {preview.data.final_chapter_count} 个章节，但看起来不对：</b>
                {describeSuspectReasons(preview.data)}
              </p>
              <p>
                后面的分析全部按章计算，分错了会一路算错且不会报错。
                <b>请对照下面的格式看一眼原文件</b>——改好再传，比让程序猜要准。
              </p>
              {preview.data.supported_chapter_formats?.length ? (
                <ul className="import-formats">
                  {preview.data.supported_chapter_formats.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              ) : null}
              <p className="muted">本来就不分章的作品，可以直接继续导入。</p>
            </div>
          ) : (
            <p role="status">已识别 {preview.data.final_chapter_count} 个章节</p>
          )}
          <ol className="import-chapter-list">
            {previewTitles.slice(0, chapterPreviewLimit).map((title, index) => (
              <li key={`${index}-${title}`}>
                <span className="import-chapter-index">{String(index + 1).padStart(2, "0")}</span>
                {title}
              </li>
            ))}
          </ol>
          {moreChapters > 0 && <p className="muted">还有 {moreChapters} 个章节</p>}
          <div className="import-panel-actions">
            {preview.data.warning === "CHAPTER_DETECTION_SUSPECT" ? (
              <>
                <Button
                  variant="primary"
                  onClick={() => {
                    upload.mutate(pendingFile);
                    setPendingFile(undefined);
                    preview.reset();
                  }}
                >
                  继续导入
                </Button>
                <Button variant="secondary" onClick={clearImport}>
                  重新选择文件
                </Button>
              </>
            ) : (
              <Button
                variant="primary"
                onClick={() => {
                  upload.mutate(pendingFile);
                  setPendingFile(undefined);
                  preview.reset();
                }}
              >
                完成导入
              </Button>
            )}
          </div>
        </div>
      )}

      <div className="library-filter-bar" data-testid="library-filter-bar">
        <label className="library-search-field">
          <span className="sr-only">搜索</span>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="搜索书名或文件名"
            data-testid="library-search"
          />
        </label>
        <div className="library-filter-types" role="group" aria-label="格式">
          <span className="library-filter-label">格式：</span>
          {FORMAT_OPTIONS.map((type) => (
            <label key={type} className="library-format-chip">
              <input
                type="checkbox"
                checked={formats[type]}
                onChange={(e) => setFormats((prev) => ({ ...prev, [type]: e.target.checked }))}
              />
              <span>{type}</span>
            </label>
          ))}
        </div>
        <label className="library-sort-field">
          排序
          <select
            data-testid="library-sort"
            value={sort}
            onChange={(e) => setSort(e.target.value as "recent" | "title")}
          >
            <option value="recent">最近导入</option>
            <option value="title">书名</option>
          </select>
        </label>
      </div>

      <div
        className={`panel library-main library-main-wide ${
          isEmptyLibrary ? "library-main--empty" : listHasRows ? "library-main--populated" : ""
        }${dragOver ? " is-drag-over" : ""}`}
        data-testid="library-list"
        data-drag-active={dragOver ? "true" : "false"}
        onDragEnter={(event) => {
          event.preventDefault();
          setDragOver(true);
        }}
        onDragOver={(event) => {
          event.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={(event) => {
          event.preventDefault();
          if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
          setDragOver(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setDragOver(false);
          accept(event.dataTransfer.files);
        }}
      >
        {upload.isPending && (
          <div className="import-panel import-panel--info import-progress">
            <b>正在导入</b>
            <span>上传文件 → 文本提取 → 章节识别 → 段落编号 → 入库</span>
          </div>
        )}
        {upload.error && (
          <div
            className={`import-panel import-panel--${importErrorKind(upload.error).tone}`}
            role="alert"
            data-testid={
              importErrorKind(upload.error).title === "书籍可能已存在"
                ? "import-duplicate-alert"
                : "import-upload-error"
            }
          >
            <h2>{importErrorKind(upload.error).title}</h2>
            <ErrorState error={upload.error as Error} />
            <div className="import-panel-actions">
              <Button variant="secondary" onClick={clearImport}>
                重新选择文件
              </Button>
            </div>
          </div>
        )}
        {toast ? (
          <p className="notice library-delete-toast" role="status" data-testid="library-delete-toast">
            {toast}
          </p>
        ) : null}
        {books.isLoading ? (
          <Loading />
        ) : books.error ? (
          <ErrorState error={books.error} />
        ) : visible.length > 0 ? (
          visible.map((book) => (
            <BookRow
              key={book.id}
              book={book}
              onDeleted={(deleted) => {
                setToast(`《${deleted.title}》已从书库删除。`);
                qc.setQueryData<Book[]>(["books"], (prev) =>
                  (prev || []).filter((item) => item.id !== deleted.id),
                );
                void qc.invalidateQueries({ queryKey: ["books"] });
              }}
            />
          ))
        ) : books.data && books.data.length > 0 ? (
          <div className="library-empty-guide" data-testid="library-search-miss">
            <StateView
              kind="empty"
              title="没有找到匹配的小说"
              description="尝试修改搜索内容或文件格式筛选。"
              data-testid="library-search-miss-state"
              primaryAction={
                hasActiveFilter
                  ? {
                      label: "清除筛选",
                      onClick: () => {
                        setSearch("");
                        setFormats({ TXT: true, DOCX: true, EPUB: true });
                      },
                      variant: "secondary",
                      testId: "library-clear-filters",
                    }
                  : undefined
              }
            />
          </div>
        ) : (
          <div className="library-empty-guide" data-testid="library-empty-guide">
            <StateView
              kind="empty"
              title="还没有导入小说"
              description="支持 TXT、DOCX 和 EPUB。导入后即可识别章节并开始分析。"
              data-testid="library-empty-state"
              primaryAction={{
                label: "导入第一本小说",
                onClick: () => input.current?.click(),
                testId: "library-empty-import",
              }}
            />
            <div className="drop-hint">也可以将文件拖到这里</div>
          </div>
        )}
        {visible.length > 0 && <div className="drop-hint">也可以将文件拖到这里导入</div>}
      </div>
    </section>
  );
}

function deleteErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === "BOOK_HAS_ACTIVE_TASKS") {
      return "这本书还有正在运行的分析任务，请先停止任务后再删除。";
    }
    if (error.code === "BOOK_NOT_FOUND" || error.status === 404) {
      return "这本书已经被删除或不存在。";
    }
    return error.message || "删除失败，书籍和分析数据均未发生变化。";
  }
  return "删除失败，书籍和分析数据均未发生变化。";
}

function BookRow({
  book,
  onDeleted,
}: {
  book: Book;
  onDeleted: (book: Book) => void;
}) {
  const fmt = fileFormat(book.source_file_name);
  const moreTriggerRef = useRef<HTMLButtonElement | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const deletingRef = useRef(false);
  const remove = useMutation({
    mutationFn: () => booksApi.delete(book.id),
    onSuccess: () => {
      setConfirmOpen(false);
      setDeleteError(null);
      onDeleted(book);
    },
    onError: (error) => {
      setDeleteError(deleteErrorMessage(error));
    },
    onSettled: () => {
      deletingRef.current = false;
    },
  });

  useEffect(() => {
    if (!confirmOpen) return;
    const id = window.setTimeout(() => {
      document
        .querySelector<HTMLButtonElement>(`[data-testid="book-delete-cancel-${book.id}"]`)
        ?.focus();
    }, 0);
    return () => window.clearTimeout(id);
  }, [confirmOpen, book.id]);

  const closeConfirm = () => {
    if (remove.isPending || deletingRef.current) return;
    setConfirmOpen(false);
    setDeleteError(null);
    window.setTimeout(() => moreTriggerRef.current?.focus(), 0);
  };

  const confirmDelete = () => {
    if (remove.isPending || deletingRef.current) return;
    deletingRef.current = true;
    remove.mutate();
  };

  return (
    <div className="book-row" data-testid={`book-row-${book.id}`}>
      <span className="cover" aria-hidden="true">
        SL
      </span>
      <span className="book-row-main">
        <b className="book-row-title" title={book.title}>
          {book.title}
        </b>
        <small className="book-row-filename" title={book.source_file_name}>
          {book.source_file_name}
        </small>
        <small className="book-row-meta" title={book.source_file_hash}>
          {fmt !== "OTHER" ? `${fmt} · ` : ""}
          导入于 {new Date(book.created_at).toLocaleDateString()}
        </small>
      </span>
      <div className="book-row-actions">
        <Link
          className="row-actions secondary book-row-open"
          to={`/books/${book.id}`}
          data-testid={`book-open-${book.id}`}
        >
          打开
        </Link>
        <div className="book-row-more" ref={(node) => {
          const trigger = node?.querySelector<HTMLButtonElement>(".overflow-menu-trigger");
          moreTriggerRef.current = trigger || null;
        }}>
          <OverflowMenu
            label="⋯"
            data-testid={`book-more-${book.id}`}
            items={[
              {
                id: "delete",
                label: "删除书籍",
                danger: true,
                testId: `book-delete-${book.id}`,
                onSelect: () => {
                  setDeleteError(null);
                  setConfirmOpen(true);
                },
              },
            ]}
          />
        </div>
      </div>

      <Dialog
        open={confirmOpen}
        onClose={closeConfirm}
        title={`删除《${book.title}》？`}
        data-testid={`book-delete-dialog-${book.id}`}
        className="book-delete-dialog"
        footer={
          <>
            <Button
              variant="secondary"
              disabled={remove.isPending}
              onClick={closeConfirm}
              data-testid={`book-delete-cancel-${book.id}`}
              autoFocus
            >
              取消
            </Button>
            {remove.error instanceof ApiError &&
            remove.error.code === "BOOK_HAS_ACTIVE_TASKS" ? (
              <Link
                className="sl-btn sl-btn--secondary secondary"
                to="/tasks"
                data-testid={`book-delete-goto-tasks-${book.id}`}
              >
                前往任务中心
              </Link>
            ) : null}
            <Button
              variant="danger"
              loading={remove.isPending}
              disabled={remove.isPending}
              onClick={confirmDelete}
              data-testid={`book-delete-confirm-${book.id}`}
              aria-label={`确认删除《${book.title}》`}
            >
              {remove.isPending ? "正在删除…" : "确认删除"}
            </Button>
          </>
        }
      >
        <p data-testid={`book-delete-warning-${book.id}`}>
          此操作将从 StoryLens 中永久删除这本书及其章节、场景和分析结果，删除后无法恢复。
        </p>
        <p className="muted" data-testid={`book-delete-original-note-${book.id}`}>
          不会删除你电脑中的原始 TXT、DOCX 或 EPUB 文件。
        </p>
        {deleteError ? (
          <p className="danger" role="alert" data-testid={`book-delete-error-${book.id}`}>
            {deleteError}
          </p>
        ) : null}
      </Dialog>
    </div>
  );
}
