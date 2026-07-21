import { useEffect, useId, useRef, useState } from "react";
import { useUiStore } from "../../stores/uiStore";
import { Button } from "../ui/Button";
import { Checkbox } from "../ui/Checkbox";

type Props = {
  className?: string;
};

const LINE_PRESETS = [
  { label: "紧凑", value: 1.6 },
  { label: "舒适", value: 1.9 },
  { label: "宽松", value: 2.2 },
] as const;

const WIDTH_PRESETS = [
  { label: "窄", value: "narrow" as const },
  { label: "适中", value: "normal" as const },
  { label: "宽", value: "wide" as const },
];

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
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const nearestLine = LINE_PRESETS.reduce((best, preset) =>
    Math.abs(preset.value - lineHeight) < Math.abs(best.value - lineHeight)
      ? preset
      : best,
  );

  return (
    <div
      className={`reading-settings-popover ${className}`.trim()}
      ref={rootRef}
      data-testid="reading-settings"
    >
      <Button
        type="button"
        variant="secondary"
        data-testid="reading-settings-trigger"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
      >
        阅读设置
      </Button>
      {open && (
        <div
          className="reading-settings-panel"
          id={panelId}
          role="dialog"
          aria-label="阅读设置"
          data-testid="reading-settings-panel"
        >
          <div className="reading-settings-heading">阅读设置</div>

          <div className="reading-settings-row">
            <span className="reading-settings-label">字号</span>
            <div className="reading-settings-stepper">
              <Button
                type="button"
                variant="secondary"
                size="small"
                data-testid="reading-font-decrease"
                aria-label="减小字号"
                onClick={() => setReading(Math.max(14, fontSize - 1), lineHeight)}
              >
                −
              </Button>
              <span data-testid="reading-font-size">{fontSize}px</span>
              <Button
                type="button"
                variant="secondary"
                size="small"
                data-testid="reading-font-increase"
                aria-label="增大字号"
                onClick={() => setReading(fontSize + 1, lineHeight)}
              >
                +
              </Button>
            </div>
          </div>

          <div className="reading-settings-row">
            <span className="reading-settings-label">行距</span>
            <div
              className="reading-settings-segment"
              data-testid="reading-line-height"
              role="group"
              aria-label="行距"
            >
              {LINE_PRESETS.map((preset) => (
                <button
                  key={preset.value}
                  type="button"
                  className={`reading-settings-chip${
                    nearestLine.value === preset.value ? " is-active" : ""
                  }`}
                  aria-pressed={nearestLine.value === preset.value}
                  onClick={() => setReading(fontSize, preset.value)}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>

          <div className="reading-settings-row">
            <span className="reading-settings-label">正文宽度</span>
            <div
              className="reading-settings-segment"
              data-testid="reading-content-width"
              role="group"
              aria-label="正文宽度"
            >
              {WIDTH_PRESETS.map((preset) => (
                <button
                  key={preset.value}
                  type="button"
                  className={`reading-settings-chip${
                    contentWidth === preset.value ? " is-active" : ""
                  }`}
                  aria-pressed={contentWidth === preset.value}
                  onClick={() => setContentWidth(preset.value)}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>

          <div className="reading-settings-row reading-settings-check">
            <Checkbox
              data-testid="reading-show-paragraph-ids"
              checked={showParagraphIds}
              onChange={(event) => setShowParagraphIds(event.target.checked)}
              label="显示段落 ID"
            />
          </div>
        </div>
      )}
    </div>
  );
}
