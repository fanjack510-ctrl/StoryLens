/** Single diagnosis band under the main Reader Journey chart. */

import { useState } from "react";
import {
  formatReadingResistanceLabel,
  READING_RESISTANCE_HOVER,
} from "./journeyUiLabels";
import {
  primaryBandLabelForScene,
  secondaryBandLabels,
  type DiagnosisBandLabel,
  type SceneDiagnosisLike,
} from "./diagnosisBandModel";
import {
  isHookPayoffLens,
} from "./hookPayoffLensModel";
import type { ObservationLensId } from "./observationLenses";
import { compositeRoleFitLabel } from "./observationLenses";
import {
  ordinaryHookSceneBandLabel,
  type ChapterHookSimplificationModel,
} from "./chapterHookSimplification";

const RESISTANCE_BANDS = new Set<DiagnosisBandLabel>([
  "推进偏弱",
  "剧情停滞",
  "空转",
  "节奏偏慢",
  "悬念不足",
  "空悬念",
  "回应延迟",
  "多项风险",
]);

function ordinaryDiagnosisLabel(label: DiagnosisBandLabel): string {
  if (label === "推进偏弱") return formatReadingResistanceLabel("推进较弱");
  if (label === "回应延迟" || label === "空悬念" || label === "悬念不足") {
    return formatReadingResistanceLabel("回应不足");
  }
  if (label === "节奏偏慢" || label === "空转") {
    return formatReadingResistanceLabel("过渡偏长");
  }
  if (RESISTANCE_BANDS.has(label)) return formatReadingResistanceLabel(label);
  return label;
}

type Props = {
  diagnoses: SceneDiagnosisLike[];
  selectedSceneOrdinal: number | null;
  onSelectScene: (ordinal: number) => void;
  observationLens?: ObservationLensId | null;
  /** Single Hook presentation source — required for ordinary hook_payoff band labels. */
  hookPresentation?: ChapterHookSimplificationModel | null;
};

export function JourneyDiagnosisBand({
  diagnoses,
  selectedSceneOrdinal,
  onSelectScene,
  observationLens = null,
  hookPresentation = null,
}: Props) {
  const [expandedOrdinal, setExpandedOrdinal] = useState<number | null>(null);
  const hookPayoff = isHookPayoffLens(observationLens);

  if (!diagnoses.length) return null;

  return (
    <div
      className="journey-diagnosis-band"
      data-testid="journey-diagnosis-band"
      data-lens={observationLens ?? undefined}
      data-chapter-hook-mode={hookPresentation?.chapter_hook_mode}
      role="list"
      aria-label="场景诊断带"
    >
      {diagnoses.map((diag) => {
        const isComposite = observationLens === "composite";
        let rawLabel: DiagnosisBandLabel | string;
        if (hookPayoff && hookPresentation) {
          rawLabel = ordinaryHookSceneBandLabel(hookPresentation, diag.scene_ordinal);
        } else if (hookPayoff) {
          // Fail closed: never fall back to score/diagnosis 「明确回应」 without presentation.
          rawLabel = "—";
        } else if (isComposite) {
          rawLabel = compositeRoleFitLabel(diag.reading_momentum, diag.scene_role ?? diag.role);
        } else {
          rawLabel = primaryBandLabelForScene(diag);
        }
        const label =
          isComposite || (hookPayoff && hookPresentation)
            ? String(rawLabel)
            : ordinaryDiagnosisLabel(rawLabel as DiagnosisBandLabel);
        const secondary = hookPayoff
          ? []
          : secondaryBandLabels(diag);
        const selected = selectedSceneOrdinal === diag.scene_ordinal;
        const expanded = expandedOrdinal === diag.scene_ordinal;
        const resistanceHover =
          !hookPayoff && RESISTANCE_BANDS.has(rawLabel as DiagnosisBandLabel)
            ? READING_RESISTANCE_HOVER
            : `场景${String(diag.scene_ordinal).padStart(2, "0")}：${label}`;
        return (
          <button
            key={diag.scene_ordinal}
            type="button"
            role="listitem"
            className={`journey-diagnosis-band-item ${selected ? "selected" : ""}`}
            data-testid={`journey-diagnosis-band-s${diag.scene_ordinal}`}
            data-primary-label={label}
            data-scene-action={
              hookPresentation?.scene_rows.find((r) => r.scene_ordinal === diag.scene_ordinal)
                ?.scene_action
            }
            title={resistanceHover}
            onClick={() => {
              onSelectScene(diag.scene_ordinal);
              setExpandedOrdinal((prev) =>
                prev === diag.scene_ordinal ? null : diag.scene_ordinal,
              );
            }}
          >
            <span className="journey-diagnosis-band-ordinal">
              {String(diag.scene_ordinal).padStart(2, "0")}
            </span>
            <span className="journey-diagnosis-band-label">{label}</span>
            {expanded && secondary.length > 0 && (
              <span
                className="journey-diagnosis-band-secondary"
                data-testid={`journey-diagnosis-band-secondary-s${diag.scene_ordinal}`}
              >
                {hookPayoff ? `其他诊断：${secondary.join(" · ")}` : secondary.join(" · ")}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
