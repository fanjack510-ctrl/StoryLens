import type { ReactNode } from "react";
import { StateView } from "../ui/StateView";
import { UiBadge, type BadgeTone } from "../ui/Badge";

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
}: {
  error: Error;
  retry?: () => void;
}) => (
  <StateView
    kind="error"
    title="无法读取数据"
    description={error.message}
    data-testid="error-state"
    primaryAction={
      retry
        ? { label: "重试", onClick: retry, testId: "error-state-retry" }
        : undefined
    }
  />
);

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
