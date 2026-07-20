import type { ButtonHTMLAttributes, ReactNode } from "react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "small" | "default" | "large";

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  primary: "sl-btn sl-btn--primary primary",
  secondary: "sl-btn sl-btn--secondary secondary",
  ghost: "sl-btn sl-btn--ghost ghost",
  danger: "sl-btn sl-btn--danger danger-btn",
};

const SIZE_CLASS: Record<ButtonSize, string> = {
  small: "sl-btn--sm",
  default: "",
  large: "sl-btn--lg",
};

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  children: ReactNode;
};

/** Shared button — wraps existing .primary/.secondary/.ghost classes without changing callers. */
export function Button({
  variant = "primary",
  size = "default",
  loading = false,
  disabled,
  className = "",
  children,
  type = "button",
  ...rest
}: ButtonProps) {
  const classes = [VARIANT_CLASS[variant], SIZE_CLASS[size], className]
    .filter(Boolean)
    .join(" ");
  return (
    <button
      type={type}
      className={classes}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      data-variant={variant}
      {...rest}
    >
      {children}
    </button>
  );
}
