type Props = {
  message?: string;
};

export function ChapterResultLoadingState({
  message = "分析完成，正在加载结果",
}: Props) {
  return (
    <div className="chapter-result-loading" data-testid="chapter-result-loading">
      <p>{message}</p>
    </div>
  );
}
