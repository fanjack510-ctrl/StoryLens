/** Single diagnosis band under the main Reader Journey chart. */

import { useState } from "react";
import {
  primaryBandLabelForScene,
  secondaryBandLabels,
  type SceneDiagnosisLike,
} from "./diagnosisBandModel";
import {
  isHookPayoffLens,
  otherDiagnosesForHookPayoffLens,
  primaryBandLabelForHookPayoffLens,
} from "./hookPayoffLensModel";
import type { ObservationLensId } from "./observationLenses";

type Props = {
  diagnoses: SceneDiagnosisLike[];
  selectedSceneOrdinal: number | null;
  onSelectScene: (ordinal: number) => void;
  observationLens?: ObservationLensId | null;
};

export function JourneyDiagnosisBand({
  diagnoses,
  selectedSceneOrdinal,
  onSelectScene,
  observationLens = null,
}: Props) {
  const [expandedOrdinal, setExpandedOrdinal] = useState<number | null>(null);
  const hookPayoff = isHookPayoffLens(observationLens);

  if (!diagnoses.length) return null;

  return (
    <div
      className="journey-diagnosis-band"
      data-testid="journey-diagnosis-band"
      data-lens={observationLens ?? undefined}
      role="list"
      aria-label="场景诊断带"
    >
      {diagnoses.map((diag) => {
        const label = hookPayoff
          ? primaryBandLabelForHookPayoffLens(diag)
          : primaryBandLabelForScene(diag);
        const secondary = hookPayoff
          ? otherDiagnosesForHookPayoffLens(diag)
          : secondaryBandLabels(diag);
        const selected = selectedSceneOrdinal === diag.scene_ordinal;
        const expanded = expandedOrdinal === diag.scene_ordinal;
        return (
          <button
            key={diag.scene_ordinal}
            type="button"
            role="listitem"
            className={`journey-diagnosis-band-item ${selected ? "selected" : ""}`}
            data-testid={`journey-diagnosis-band-s${diag.scene_ordinal}`}
            data-primary-label={label}
            title={`S${diag.scene_ordinal}：${label}`}
            onClick={() => {
              onSelectScene(diag.scene_ordinal);
              setExpandedOrdinal((prev) =>
                prev === diag.scene_ordinal ? null : diag.scene_ordinal,
              );
            }}
          >
            <span className="journey-diagnosis-band-ordinal">S{diag.scene_ordinal}</span>
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
