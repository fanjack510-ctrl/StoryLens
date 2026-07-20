import type { ReactNode } from "react";

export type BadgeTone = "neutral" | "info" | "success" | "warning" | "danger";

const TONE_CLASS: Record<BadgeTone, string> = {
  neutral: "sl-badge sl-badge--neutral badge neutral",
  info: "sl-badge sl-badge--info badge info",
  success: "sl-badge sl-badge--success badge success",
  warning: "sl-badge sl-badge--warning badge warning",
  danger: "sl-badge sl-badge--danger badge danger",
};

export type BadgeProps = {
  children: ReactNode;
  tone?: BadgeTone;
  /** Technical ids (provider / model) use mono + neutral. */
  mono?: boolean;
  className?: string;
  "data-testid"?: string;
};

export function UiBadge({
  children,
  tone = "neutral",
  mono = false,
  className = "",
  "data-testid": testId,
}: BadgeProps) {
  const classes = [TONE_CLASS[tone], mono ? "sl-badge--mono badge mono" : "", className]
    .filter(Boolean)
    .join(" ");
  return (
    <span className={classes} data-tone={tone} data-testid={testId}>
      {children}
    </span>
  );
}
