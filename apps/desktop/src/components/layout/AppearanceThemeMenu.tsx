import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  appearanceThemeLabel,
  type AppearanceTheme,
} from "../../lib/appearanceTheme";
import { useUiStore } from "../../stores/uiStore";

const OPTIONS: AppearanceTheme[] = ["light", "dark"];

/**
 * Compact Header appearance control — current theme visible, menu to switch.
 * Persists via useUiStore → localStorage (same SSOT as bootstrap script).
 */
export function AppearanceThemeMenu() {
  const theme = useUiStore((s) => s.theme);
  const setTheme = useUiStore((s) => s.setTheme);
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const menuId = useId();
  const [coords, setCoords] = useState<{ top: number; right: number }>({ top: 0, right: 0 });

  useEffect(() => {
    if (!open) return;
    const update = () => {
      const el = triggerRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      setCoords({
        top: Math.round(rect.bottom + 6),
        right: Math.round(Math.max(8, window.innerWidth - rect.right)),
      });
    };
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    const onPointer = (event: MouseEvent) => {
      const target = event.target as Node | null;
      if (!target) return;
      if (triggerRef.current?.contains(target)) return;
      if (panelRef.current?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onPointer);
    };
  }, [open]);

  const select = (next: AppearanceTheme) => {
    setTheme(next);
    setOpen(false);
    triggerRef.current?.focus();
  };

  return (
    <div className="appearance-theme-menu" data-testid="appearance-theme-menu">
      <button
        type="button"
        ref={triggerRef}
        className={`theme-toggle-btn appearance-theme-trigger${open ? " is-open" : ""}`}
        data-testid="appearance-theme-trigger"
        data-theme-current={theme}
        aria-label="切换界面主题"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        title="切换界面主题"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="appearance-theme-trigger-icon" aria-hidden="true">
          {theme === "dark" ? "☾" : "☀"}
        </span>
        <span className="appearance-theme-trigger-label">{appearanceThemeLabel(theme)}</span>
        <span className="appearance-theme-trigger-caret" aria-hidden="true">
          ▾
        </span>
      </button>
      {open
        ? createPortal(
            <div
              ref={panelRef}
              id={menuId}
              className="appearance-theme-panel"
              data-testid="appearance-theme-panel"
              role="menu"
              aria-label="界面主题"
              style={{ top: coords.top, right: coords.right }}
            >
              {OPTIONS.map((option) => {
                const selected = option === theme;
                return (
                  <button
                    key={option}
                    type="button"
                    role="menuitemradio"
                    className={selected ? "is-selected" : undefined}
                    data-testid={`appearance-theme-option-${option}`}
                    aria-checked={selected}
                    onClick={() => select(option)}
                  >
                    <span aria-hidden="true">{option === "dark" ? "☾" : "☀"}</span>
                    <span>{appearanceThemeLabel(option)}</span>
                    {selected ? <span className="appearance-theme-check">✓</span> : null}
                  </button>
                );
              })}
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}
