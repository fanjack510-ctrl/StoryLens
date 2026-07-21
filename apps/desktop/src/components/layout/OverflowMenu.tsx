import { useEffect, useId, useRef, useState, type ReactNode } from "react";

export type OverflowMenuItem = {
  id: string;
  label: string;
  onSelect: () => void;
  disabled?: boolean;
  group?: string;
  testId?: string;
  /** Visual tone for destructive actions; does not change onSelect. */
  danger?: boolean;
};

type Props = {
  label?: string;
  items: OverflowMenuItem[];
  className?: string;
  "data-testid"?: string;
  children?: ReactNode;
};

export function OverflowMenu({
  label = "更多",
  items,
  className = "",
  "data-testid": testId = "overflow-menu",
  children,
}: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    const onDoc = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const groups = items.reduce<Record<string, OverflowMenuItem[]>>((acc, item) => {
    const key = item.group || "";
    (acc[key] ||= []).push(item);
    return acc;
  }, {});

  return (
    <div className={`overflow-menu ${className}`.trim()} ref={rootRef} data-testid={testId}>
      <button
        type="button"
        className="overflow-menu-trigger"
        data-testid={`${testId}-trigger`}
        aria-label={label === "⋯" ? "更多" : label}
        aria-expanded={open}
        aria-controls={menuId}
        aria-haspopup="menu"
        onClick={() => setOpen((value) => !value)}
      >
        {label}
      </button>
      {open && (
        <div className="overflow-menu-panel" id={menuId} role="menu" data-testid={`${testId}-panel`}>
          {children}
          {Object.entries(groups).map(([group, groupItems]) => (
            <div key={group || "_"} className="overflow-menu-group">
              {group ? <div className="overflow-menu-group-label">{group}</div> : null}
              {groupItems.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  role="menuitem"
                  disabled={item.disabled}
                  className={item.danger ? "overflow-menu-item danger" : "overflow-menu-item"}
                  data-testid={item.testId || `overflow-item-${item.id}`}
                  onClick={() => {
                    item.onSelect();
                    setOpen(false);
                  }}
                >
                  {item.label}
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
