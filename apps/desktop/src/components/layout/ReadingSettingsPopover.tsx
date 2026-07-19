import { useEffect, useId, useRef, useState } from "react";
import { useUiStore } from "../../stores/uiStore";

type Props = {
  className?: string;
};

export function ReadingSettingsPopover({ className = "" }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const panelId = useId();
  const {
    fontSize,
    lineHeight,
    contentWidth,
    showParagraphIds,
    setReading,
    setContentWidth,
    setShowParagraphIds,
  } = useUiStore();

  useEffect(() => {
    if (!open) return;
    const onDoc = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  return (
    <div
      className={`reading-settings-popover ${className}`.trim()}
      ref={rootRef}
      data-testid="reading-settings"
    >
      <button
        type="button"
        className="secondary"
        data-testid="reading-settings-trigger"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
      >
        阅读设置
      </button>
      {open && (
        <div className="reading-settings-panel" id={panelId} data-testid="reading-settings-panel">
          <div className="reading-settings-row">
            <span>字号</span>
            <button
              type="button"
              data-testid="reading-font-decrease"
              onClick={() => setReading(Math.max(14, fontSize - 1), lineHeight)}
            >
              A−
            </button>
            <span data-testid="reading-font-size">{fontSize}px</span>
            <button
              type="button"
              data-testid="reading-font-increase"
              onClick={() => setReading(fontSize + 1, lineHeight)}
            >
              A＋
            </button>
          </div>
          <div className="reading-settings-row">
            <span>行距</span>
            <button
              type="button"
              data-testid="reading-line-height"
              onClick={() => setReading(fontSize, lineHeight === 1.9 ? 2.2 : 1.9)}
            >
              {lineHeight}
            </button>
          </div>
          <label className="reading-settings-row">
            <span>正文宽度</span>
            <select
              data-testid="reading-content-width"
              value={contentWidth}
              onChange={(event) =>
                setContentWidth(event.target.value as "narrow" | "normal" | "wide")
              }
            >
              <option value="narrow">较窄</option>
              <option value="normal">标准</option>
              <option value="wide">加宽</option>
            </select>
          </label>
          <label className="reading-settings-row">
            <span>显示段落 ID</span>
            <input
              type="checkbox"
              data-testid="reading-show-paragraph-ids"
              checked={showParagraphIds}
              onChange={(event) => setShowParagraphIds(event.target.checked)}
            />
          </label>
        </div>
      )}
    </div>
  );
}
