import type { ReactNode } from "react";
import { Button, type ButtonVariant } from "./Button";

export type StateViewKind = "loading" | "empty" | "error" | "info";

export type StateAction = {
  label: string;
  onClick: () => void;
  variant?: ButtonVariant;
  testId?: string;
  disabled?: boolean;
};

export type StateViewProps = {
  kind?: StateViewKind;
  title: ReactNode;
  description?: ReactNode;
  primaryAction?: StateAction;
  secondaryAction?: StateAction;
  mark?: ReactNode;
  className?: string;
  "data-testid"?: string;
};

const MARK: Record<StateViewKind, string> = {
  loading: "…",
  empty: "○",
  error: "!",
  info: "i",
};

export function StateView({
  kind = "info",
  title,
  description,
  primaryAction,
  secondaryAction,
  mark,
  className = "",
  "data-testid": testId = "state-view",
}: StateViewProps) {
  return (
    <div
      className={`sl-state state ${kind === "error" ? "error sl-state--error" : ""} ${className}`.trim()}
      data-testid={testId}
      role={kind === "error" ? "alert" : undefined}
    >
      <div className="sl-state__mark" aria-hidden="true">
        {mark ?? MARK[kind]}
      </div>
      <strong className="sl-state__title">{title}</strong>
      {description != null && <span className="sl-state__desc">{description}</span>}
      {(primaryAction || secondaryAction) && (
        <div className="sl-state__actions">
          {primaryAction && (
            <Button
              variant={primaryAction.variant || "primary"}
              onClick={primaryAction.onClick}
              disabled={primaryAction.disabled}
              data-testid={primaryAction.testId || `${testId}-primary`}
            >
              {primaryAction.label}
            </Button>
          )}
          {secondaryAction && (
            <Button
              variant={secondaryAction.variant || "secondary"}
              onClick={secondaryAction.onClick}
              disabled={secondaryAction.disabled}
              data-testid={secondaryAction.testId || `${testId}-secondary`}
            >
              {secondaryAction.label}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
