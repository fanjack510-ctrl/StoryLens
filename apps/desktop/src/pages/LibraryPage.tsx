import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { booksApi } from "../services/booksApi";
import { Empty, ErrorState, Loading } from "../components/common/States";
import { QwenFirstLaunchBanner } from "../components/onboarding/QwenFirstLaunchBanner";
import { FirstLaunchWizard } from "../components/onboarding/FirstLaunchWizard";
import { useOnboardingStore } from "../stores/onboardingStore";

export function LibraryPage() {
  const onboardingStatus = useOnboardingStore((s) => s.status);
  const [searchParams] = useSearchParams();
  const input = useRef<HTMLInputElement>(null);
  const [search, setSearch] = useState("");
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
  const visible = books.data?.filter((book) =>
    (book.title + book.source_file_name).includes(search),
  );

  useEffect(() => {
    if (searchParams.get("import") === "1") {
      input.current?.click();
    }
  }, [searchParams]);

  return (
    <section className="page library-page-compact" data-testid="library-page">
      {onboardingStatus === "pending" && <FirstLaunchWizard />}
      <QwenFirstLaunchBanner />
      <div className="page-title library-title-compact">
        <div>
          <h1>我的书库</h1>
        </div>
        <button
          className="primary"
          data-testid="import-book"
          onClick={() => input.current?.click()}
        >
          导入小说
        </button>
        <input
          ref={input}
          hidden
          type="file"
          accept=".txt,.docx,.epub"
          onChange={(event) => accept(event.target.files)}
        />
      </div>

      {preview.isPending && (
        <div className="panel">
          <Loading />
        </div>
      )}
      {preview.error && <ErrorState error={preview.error} />}
      {preview.data && pendingFile && (
        <div className="panel import-preview">
          <h2>章节识别预览</h2>
          {preview.data.warning === "CHAPTER_DETECTION_SUSPECT" && (
            <p className="notice">
              该文件较大，但只识别出一个章节，章节标题格式可能未被识别。
            </p>
          )}
          <p>
            编码：{preview.data.encoding} · 文件：
            {(preview.data.byte_count / 1024 / 1024).toFixed(2)} MB
          </p>
          <p>
            候选 {preview.data.candidate_count} 个 · 最终{" "}
            {preview.data.final_chapter_count} 章
          </p>
          <ol>
            {preview.data.chapter_titles.slice(0, 20).map((title) => (
              <li key={title}>{title}</li>
            ))}
          </ol>
          <button
            type="button"
            onClick={() => {
              setPendingFile(undefined);
              preview.reset();
            }}
          >
            取消
          </button>
          <button
            type="button"
            className="primary"
            onClick={() => {
              upload.mutate(pendingFile);
              setPendingFile(undefined);
              preview.reset();
            }}
          >
            按当前结果继续导入
          </button>
        </div>
      )}

      <div className="library-filter-bar" data-testid="library-filter-bar">
        <label>
          搜索
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="书名或文件名"
            data-testid="library-search"
          />
        </label>
        <div className="library-filter-types">
          {["TXT", "DOCX", "EPUB"].map((type) => (
            <label key={type}>
              <input type="checkbox" defaultChecked /> {type}
            </label>
          ))}
        </div>
        <label>
          排序
          <select data-testid="library-sort">
            <option>最近导入</option>
            <option>书名</option>
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
          <div className="import-progress">
            <b>正在导入</b>
            <span>上传文件 → 文本提取 → 章节识别 → 段落编号 → 入库</span>
          </div>
        )}
        {upload.error && <ErrorState error={upload.error} />}
        {books.isLoading ? (
          <Loading />
        ) : books.error ? (
          <ErrorState error={books.error} />
        ) : (
          visible?.map((book) => (
            <Link
              className="book-row book-row-clickable"
              to={`/books/${book.id}`}
              key={book.id}
              data-testid={`book-row-${book.id}`}
            >
              <span className="cover">SL</span>
              <span className="book-row-main">
                <b>{book.title}</b>
                <small>{book.source_file_name}</small>
                <small className="book-row-meta" title={book.source_file_hash}>
                  导入于 {new Date(book.created_at).toLocaleDateString()}
                </small>
              </span>
              <span className="row-actions primary-link">打开</span>
            </Link>
          ))
        )}
        {!visible?.length && !books.isLoading && (
          <div className="library-empty-guide" data-testid="library-empty-guide">
            <Empty text="书库还是空的" />
            <p>导入第一本小说前，请先配置阿里云百炼 · Qwen。</p>
            <div className="settings-actions">
              <Link
                className="primary"
                to="/settings?tab=ai&focus=api_key"
                data-testid="library-empty-configure-qwen"
              >
                配置阿里云百炼 · Qwen
              </Link>
              <button
                type="button"
                className="secondary"
                data-testid="library-empty-import"
                onClick={() => input.current?.click()}
              >
                导入小说
              </button>
            </div>
          </div>
        )}
        <div className="drop-hint">也可以将文件拖到这里导入</div>
      </div>
    </section>
  );
}
