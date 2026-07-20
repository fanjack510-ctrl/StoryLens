import { useEffect, type ReactNode } from "react";

export type DialogProps = {
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  open?: boolean;
  onClose?: () => void;
  wide?: boolean;
  /** Extra class on the dialog panel */
  className?: string;
  "data-testid"?: string;
};

/**
 * Shared dialog shell. Does not replace complex analysis dialogs in phase 1;
 * Esc / backdrop click keep existing caller-controlled close behavior.
 */
export function Dialog({
  title,
  children,
  footer,
  open = true,
  onClose,
  wide = false,
  className = "",
  "data-testid": testId = "sl-dialog",
}: DialogProps) {
  useEffect(() => {
    if (!open || !onClose) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="sl-dialog-backdrop modal-backdrop"
      data-testid={`${testId}-backdrop`}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose?.();
      }}
    >
      <div
        className={`sl-dialog modal ${wide ? "sl-dialog--wide" : ""} ${className}`.trim()}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${testId}-title`}
        data-testid={testId}
      >
        <header className="sl-dialog__header">
          <h2 className="sl-dialog__title" id={`${testId}-title`}>
            {title}
          </h2>
          {onClose && (
            <button
              type="button"
              className="sl-dialog__close"
              aria-label="关闭"
              data-testid={`${testId}-close`}
              onClick={onClose}
            >
              ×
            </button>
          )}
        </header>
        <div className="sl-dialog__body">{children}</div>
        {footer != null && <footer className="sl-dialog__footer">{footer}</footer>}
      </div>
    </div>
  );
}
