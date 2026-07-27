type Props = {
  onRetry: () => void;
  onReading: () => void;
  /** @deprecated Independent result pages are removed from the unified workspace. */
  independentHref?: string;
  title?: string;
  description?: string;
};

export function ChapterResultErrorState({
  onRetry,
  onReading,
  title = "阅读旅程加载失败",
  description = "章节正文仍然可用。可重新加载当前结果。",
}: Props) {
  return (
    <div className="chapter-result-error" data-testid="chapter-result-error">
      <h2>{title}</h2>
      <p>{description}</p>
      <div className="chapter-result-error-actions">
        <button type="button" className="primary" data-testid="chapter-result-retry" onClick={onRetry}>
          重新加载
        </button>
        <button type="button" className="secondary" data-testid="chapter-result-back-reading" onClick={onReading}>
          返回正文阅读
        </button>
      </div>
      <details data-testid="chapter-result-tech-details">
        <summary>查看技术详情</summary>
        <p className="secondary">request_error · 统一工作台内重试，不会打开独立结果页。</p>
      </details>
    </div>
  );
}
