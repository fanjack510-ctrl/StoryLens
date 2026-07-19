import type { ReactNode } from "react";

type Props = {
  title?: ReactNode;
  primary?: ReactNode;
  secondary?: ReactNode;
  tertiary?: ReactNode;
  className?: string;
  "data-testid"?: string;
};

/** Compact page toolbar: at most one primary action in the primary slot. */
export function CompactToolbar({
  title,
  primary,
  secondary,
  tertiary,
  className = "",
  "data-testid": testId = "compact-toolbar",
}: Props) {
  return (
    <div className={`compact-toolbar ${className}`.trim()} data-testid={testId}>
      {title ? <div className="compact-toolbar-title">{title}</div> : null}
      <div className="compact-toolbar-actions">
        {secondary ? <div className="compact-toolbar-secondary">{secondary}</div> : null}
        {primary ? <div className="compact-toolbar-primary">{primary}</div> : null}
        {tertiary ? <div className="compact-toolbar-tertiary">{tertiary}</div> : null}
      </div>
    </div>
  );
}
