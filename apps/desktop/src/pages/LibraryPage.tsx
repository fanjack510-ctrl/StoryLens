import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { booksApi } from "../services/booksApi";
import { ApiError } from "../services/apiClient";
import { ErrorState, Loading } from "../components/common/States";
import { QwenFirstLaunchBanner } from "../components/onboarding/QwenFirstLaunchBanner";
import { FirstLaunchWizard } from "../components/onboarding/FirstLaunchWizard";
import { useOnboardingStore } from "../stores/onboardingStore";
import { Button } from "../components/ui/Button";
import { PageHeader, PageSubtitle, PageTitle } from "../components/ui/PageHeader";
import { StateView } from "../components/ui/StateView";
import type { Book } from "../types";

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
    const msg = `${error.message} ${String(error.detail || "")}`.toLowerCase();
    if (error.status === 413 || /过大|too large|size/i.test(msg)) {
      return { title: "文件过大", tone: "danger" };
    }
    if (/编码|encoding/i.test(msg)) {
      return { title: "编码无法识别", tone: "danger" };
    }
    if (/格式|format|不支持/i.test(msg)) {
      return { title: "文件格式不支持", tone: "danger" };
    }
    if (/重复|duplicate|已存在/i.test(msg)) {
      return { title: "书籍可能已存在", tone: "warning" };
    }
  }
  return { title: "导入失败", tone: "danger" };
}

export function LibraryPage() {
  const onboardingStatus = useOnboardingStore((s) => s.status);
  const [searchParams] = useSearchParams();
  const input = useRef<HTMLInputElement>(null);
  const [search, setSearch] = useState("");
  const [formats, setFormats] = useState<Record<FormatOption, boolean>>({
    TXT: true,
    DOCX: true,
    EPUB: true,
  });
  const [sort, setSort] = useState<"recent" | "title">("recent");
  const [pendingFile, setPendingFile] = useState<File>();
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
      <QwenFirstLaunchBanner />
      <PageHeader className="library-title-compact">
        <div>
          <PageTitle>我的书库</PageTitle>
          <PageSubtitle>管理已导入的小说和分析项目</PageSubtitle>
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
            <p className="notice" role="status">
              章节识别结果可能不准确：文件较大但只识别出一个章节，标题格式可能未被识别。
            </p>
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
        className="panel library-main library-main-wide"
        data-testid="library-list"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
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
        {books.isLoading ? (
          <Loading />
        ) : books.error ? (
          <ErrorState error={books.error} />
        ) : visible.length > 0 ? (
          visible.map((book) => <BookRow key={book.id} book={book} />)
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

function BookRow({ book }: { book: Book }) {
  const fmt = fileFormat(book.source_file_name);
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
      <Link className="row-actions secondary book-row-open" to={`/books/${book.id}`}>
        打开
      </Link>
    </div>
  );
}
