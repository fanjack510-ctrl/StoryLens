import type { WholeBookAnalysisMode } from "../../contracts/keys";
import { MODE_DISPLAY } from "../labels";
import { formatRatio } from "../labels";
import type { PreflightSourceCoverageDto } from "../../contracts/preflight";

export type WholeBookModeSelectorProps = {
  value: WholeBookAnalysisMode;
  supportedModes: readonly WholeBookAnalysisMode[];
  disabledReasons?: Partial<Record<WholeBookAnalysisMode, string>>;
  sourceCoverage?: PreflightSourceCoverageDto | null;
  onChange: (mode: WholeBookAnalysisMode) => void;
};

/**
 * Mode is not a Capability Key. supportedModes come from backend/preflight.
 */
export function WholeBookModeSelector({
  value,
  supportedModes,
  disabledReasons = {},
  sourceCoverage,
  onChange,
}: WholeBookModeSelectorProps) {
  const modes: WholeBookAnalysisMode[] = [
    "whole_book_native",
    "whole_book_enhanced",
  ];

  return (
    <section
      className="wb-run-ux__section"
      data-testid="whole-book-mode-selector"
      aria-labelledby="wb-mode-heading"
    >
      <h2 id="wb-mode-heading">分析模式</h2>
      <p className="wb-run-ux__hint">
        Native / Enhanced 是分析模式，不是不同订阅产品，也不是 Capability Key。
      </p>
      <div className="wb-mode-grid" role="radiogroup" aria-label="分析模式">
        {modes.map((mode) => {
          const meta = MODE_DISPLAY[mode];
          const supported = supportedModes.includes(mode);
          const reason =
            disabledReasons[mode] ||
            (!supported ? "当前 Preflight / Capability 不支持该模式" : undefined);
          const disabled = !supported;
          const selected = value === mode;
          return (
            <button
              key={mode}
              type="button"
              role="radio"
              aria-checked={selected}
              aria-disabled={disabled || undefined}
              disabled={disabled}
              title={disabled ? reason : meta.summary}
              className="wb-mode-card"
              data-testid={`mode-option-${mode}`}
              data-selected={selected ? "true" : "false"}
              data-disabled={disabled ? "true" : "false"}
              onClick={() => {
                if (!disabled) onChange(mode);
              }}
            >
              <span className="wb-mode-card__title">{meta.title}</span>
              <span className="wb-mode-card__summary">{meta.summary}</span>
              <ul className="wb-mode-card__bullets">
                {meta.bullets.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
              {disabled ? (
                <span className="wb-mode-card__reason" role="status">
                  不可用：{reason}
                </span>
              ) : null}
              <span className="wb-visually-hidden">
                模式键 {mode}
                {selected ? "，已选中" : ""}
                {disabled ? `，已禁用，原因：${reason}` : ""}
              </span>
            </button>
          );
        })}
      </div>
      {value === "whole_book_enhanced" && sourceCoverage ? (
        <div
          className="wb-mode-coverage"
          data-testid="enhanced-coverage"
          role="status"
        >
          <strong>增强覆盖率（估算）</strong>
          <ul>
            <li>
              Scene：{formatRatio(sourceCoverage.scene_coverage_ratio)}
            </li>
            <li>
              Reader Journey：
              {formatRatio(sourceCoverage.reader_journey_coverage_ratio)}
            </li>
            <li>
              章节分析：
              {formatRatio(sourceCoverage.chapter_analysis_coverage_ratio)}
            </li>
            <li>
              综合：
              {formatRatio(sourceCoverage.enhanced_asset_coverage_ratio)}
            </li>
          </ul>
          {sourceCoverage.enhanced_degraded ? (
            <p className="wb-run-ux__warn">
              增强资产不足时允许降级；完整正文仍是主来源。
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
