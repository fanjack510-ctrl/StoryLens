import type { Book } from "../../types";
import {
  buildBookHomeChapterRows,
  type BookHomeChapterRow,
} from "../../services/bookHomeCatalog";
import type { Chapter, Run } from "../../types";

type Props = {
  book: Book | null | undefined;
  chapters: Chapter[] | null | undefined;
  runs: Run[] | null | undefined;
  loading: boolean;
  error: boolean;
  onRetry: () => void;
  onBackLibrary: () => void;
  onSelectChapter: (chapterId: number) => void;
  onReparse?: () => void;
};

/**
 * Book home / chapter directory for /books/:bookId without chapter=.
 * Never auto-opens chapter 1 or historical Journey.
 */
export function BookHomeCatalog({
  book,
  chapters,
  runs,
  loading,
  error,
  onRetry,
  onBackLibrary,
  onSelectChapter,
  onReparse,
}: Props) {
  const rows: BookHomeChapterRow[] = buildBookHomeChapterRows(chapters, runs);
  const title = book?.title || "书籍";

  if (loading) {
    return (
      <div className="book-home-catalog state" data-testid="book-home-catalog" data-state="loading">
        <strong>正在加载章节…</strong>
        <span className="secondary">{title}</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="book-home-catalog state" data-testid="book-home-catalog" data-state="error">
        <strong>章节目录加载失败</strong>
        <div className="chapter-result-error-actions">
          <button type="button" className="primary" data-testid="book-home-retry" onClick={onRetry}>
            重新加载
          </button>
          <button type="button" className="secondary" data-testid="book-home-back" onClick={onBackLibrary}>
            返回书库
          </button>
        </div>
      </div>
    );
  }

  if (!rows.length) {
    return (
      <div className="book-home-catalog state" data-testid="book-home-catalog" data-state="empty">
        <strong>尚未识别到章节</strong>
        <span className="secondary">可重新识别章节或查看导入诊断。</span>
        <div className="chapter-result-error-actions">
          {onReparse ? (
            <button type="button" className="primary" data-testid="book-home-reparse" onClick={onReparse}>
              重新识别章节
            </button>
          ) : null}
          <button type="button" className="secondary" data-testid="book-home-back" onClick={onBackLibrary}>
            返回书库
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="book-home-catalog" data-testid="book-home-catalog" data-state="ready">
      <header className="book-home-head">
        <h2 data-testid="book-home-title">{title}</h2>
        <p className="secondary" data-testid="book-home-meta">
          {book?.source_file_name ? `${book.source_file_name} · ` : ""}共 {rows.length} 章
        </p>
        <p className="secondary">请选择章节进入正文阅读。有历史分析时也不会自动打开结果。</p>
      </header>
      <div className="book-home-list" data-testid="book-home-chapter-list" role="list">
        {rows.map((row) => (
          <button
            key={row.id}
            type="button"
            role="listitem"
            className="book-home-chapter-item"
            data-testid={`book-home-chapter-${row.id}`}
            data-badge={row.badge}
            title={row.title}
            onClick={() => onSelectChapter(row.id)}
          >
            <span className="book-home-chapter-num">{row.numLabel}</span>
            <span className="book-home-chapter-title">{row.title}</span>
            <span className="book-home-chapter-badge">{row.badgeLabel}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
