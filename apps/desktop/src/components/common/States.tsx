import type { ReactNode } from "react";
import { StateView } from "../ui/StateView";
import { UiBadge, type BadgeTone } from "../ui/Badge";
import { ApiError } from "../../services/apiClient";
import { mapTaskCenterError } from "../../services/taskCenterErrors";

export const Loading = () => (
  <StateView kind="loading" title="正在载入…" data-testid="loading-state" />
);

export const Empty = ({ text = "暂无数据" }: { text?: string }) => (
  <StateView
    kind="empty"
    title={text}
    description="可以从左侧操作开始。"
    data-testid="empty-state"
  />
);

export const ErrorState = ({
  error,
  retry,
  classifyTaskErrors = false,
  title: titleOverride,
}: {
  error: Error;
  retry?: () => void;
  /** When true, 422/5xx keep business copy instead of "local service offline". */
  classifyTaskErrors?: boolean;
  /** A caller that already knows what went wrong supplies the heading. Without this the
   *  import panel printed its own title and then this component's generic one right under
   *  it, so a duplicate import read 「书籍可能已存在 / 无法读取数据 / 该文件已导入」 — a true
   *  heading, a meaningless one, and the real message. */
  title?: string;
}) => {
  const mapped = classifyTaskErrors ? mapTaskCenterError(error) : null;
  const title = titleOverride || mapped?.title || "无法读取数据";
  const description = mapped?.message || error.message;
  const requestId =
    mapped?.requestId ||
    (error instanceof ApiError ? error.requestId : undefined);
  return (
    <StateView
      kind="error"
      title={title}
      description={
        requestId ? `${description}\nrequest_id: ${requestId}` : description
      }
      data-testid="error-state"
      primaryAction={
        retry
          ? { label: "重试", onClick: retry, testId: "error-state-retry" }
          : undefined
      }
    />
  );
};

const LEGACY_TONE: Record<string, BadgeTone> = {
  neutral: "neutral",
  info: "info",
  success: "success",
  succeeded: "success",
  ok: "success",
  warning: "warning",
  warn: "warning",
  danger: "danger",
  failed: "danger",
  error: "danger",
  demo: "info",
};

export const Badge = ({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: string;
}) => {
  const mapped = LEGACY_TONE[tone] || "neutral";
  const mono = tone === "mono" || tone === "neutral-mono";
  return (
    <UiBadge tone={mapped} mono={mono} className={tone !== mapped ? tone : undefined}>
      {children}
    </UiBadge>
  );
};
