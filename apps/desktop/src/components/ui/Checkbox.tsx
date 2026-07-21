import type { InputHTMLAttributes, ReactNode } from "react";

export type CheckboxProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  label: ReactNode;
};

export function Checkbox({ label, className = "", id, ...rest }: CheckboxProps) {
  const inputId = id || rest.name;
  return (
    <label className={`sl-check ${className}`.trim()} htmlFor={inputId}>
      <input id={inputId} type="checkbox" {...rest} />
      <span>{label}</span>
    </label>
  );
}

export type RadioProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  label: ReactNode;
};

export function Radio({ label, className = "", id, ...rest }: RadioProps) {
  const inputId = id || `${rest.name}-${String(rest.value)}`;
  return (
    <label className={`sl-check ${className}`.trim()} htmlFor={inputId}>
      <input id={inputId} type="radio" {...rest} />
      <span>{label}</span>
    </label>
  );
}

export type SwitchProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  label?: ReactNode;
};

export function Switch({ label, className = "", ...rest }: SwitchProps) {
  const control = (
    <input
      type="checkbox"
      role="switch"
      className={`sl-switch settings-switch ${className}`.trim()}
      {...rest}
    />
  );
  if (!label) return control;
  return (
    <label className="settings-switch-row">
      <span>{label}</span>
      {control}
    </label>
  );
}
