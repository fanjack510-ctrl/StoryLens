export type WholeBookPartialResultNoticeProps = {
  available: boolean;
  completedModules: readonly string[];
  failedModules?: readonly string[];
  cancelled?: boolean;
};

export function WholeBookPartialResultNotice({
  available,
  completedModules,
  failedModules = [],
  cancelled = false,
}: WholeBookPartialResultNoticeProps) {
  if (!available && completedModules.length === 0) {
    return null;
  }

  return (
    <aside
      className="wb-partial-notice"
      data-testid="whole-book-partial-result-notice"
      role="status"
      aria-live="polite"
    >
      <strong>部分结果</strong>
      {available ? (
        <p>
          已有模块结果可提前查看。后续阶段失败不会抹掉已完成模块；取消也不会删除已产生的候选结果。
        </p>
      ) : (
        <p>当前无部分结果入口。</p>
      )}
      <p>
        已完成模块：
        {completedModules.length > 0 ? completedModules.join(", ") : "无"}
      </p>
      {failedModules.length > 0 ? (
        <p className="wb-run-ux__warn">
          失败模块：{failedModules.join(", ")}（其他已完成模块仍保留）
        </p>
      ) : null}
      {cancelled ? (
        <p>运行已取消；已产生候选结果保留，不等于删除书籍或 Snapshot。</p>
      ) : null}
    </aside>
  );
}
