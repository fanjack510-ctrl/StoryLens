import type { InputHTMLAttributes, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

type FieldTone = { error?: boolean; className?: string };

export type InputProps = InputHTMLAttributes<HTMLInputElement> & FieldTone;

export function Input({ error, className = "", ...rest }: InputProps) {
  return (
    <input
      className={["sl-input", error ? "sl-input--error" : "", className].filter(Boolean).join(" ")}
      aria-invalid={error || undefined}
      {...rest}
    />
  );
}

export type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & FieldTone;

export function Textarea({ error, className = "", ...rest }: TextareaProps) {
  return (
    <textarea
      className={["sl-textarea", error ? "sl-input--error" : "", className].filter(Boolean).join(" ")}
      aria-invalid={error || undefined}
      {...rest}
    />
  );
}

export type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & FieldTone;

export function Select({ error, className = "", children, ...rest }: SelectProps) {
  return (
    <select
      className={["sl-select", error ? "sl-input--error" : "", className].filter(Boolean).join(" ")}
      aria-invalid={error || undefined}
      {...rest}
    >
      {children}
    </select>
  );
}
