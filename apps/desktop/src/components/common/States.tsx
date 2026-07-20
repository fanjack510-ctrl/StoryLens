export const Loading = () => <div className="state">正在载入…</div>;
export const Empty = ({ text = "暂无数据" }: { text?: string }) => (
  <div className="state">
    <strong>{text}</strong>
    <span>可以从左侧操作开始。</span>
  </div>
);
export const ErrorState = ({
  error,
  retry,
}: {
  error: Error;
  retry?: () => void;
}) => (
  <div className="state error" data-testid="error-state" role="alert">
    <strong>无法读取数据</strong>
    <span>{error.message}</span>
    {retry && <button onClick={retry}>重试</button>}
  </div>
);
export const Badge = ({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: string;
}) => <span className={`badge ${tone}`}>{children}</span>;
