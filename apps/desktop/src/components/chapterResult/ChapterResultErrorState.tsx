type Props = {
  onRetry: () => void;
  onReading: () => void;
  independentHref: string;
};

export function ChapterResultErrorState({ onRetry, onReading, independentHref }: Props) {
  return (
    <div className="chapter-result-error" data-testid="chapter-result-error">
      <h2>分析结果暂时无法加载</h2>
      <p>章节正文仍然可用。可重试加载，或打开独立结果页。</p>
      <div className="chapter-result-error-actions">
        <button type="button" className="primary" data-testid="chapter-result-retry" onClick={onRetry}>
          重试加载
        </button>
        <button type="button" className="secondary" data-testid="chapter-result-back-reading" onClick={onReading}>
          返回正文阅读
        </button>
        <a className="secondary" data-testid="chapter-result-open-independent" href={independentHref}>
          打开独立结果页
        </a>
      </div>
    </div>
  );
}
