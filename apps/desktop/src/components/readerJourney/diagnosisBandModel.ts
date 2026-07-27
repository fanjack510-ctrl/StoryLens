/** Single diagnosis-band labels under the main Reader Journey chart. */

export type DiagnosisBandLabel =
  | "表现有效"
  | "未发现明显异常"
  | "辅助节拍"
  | "推进偏弱"
  | "剧情停滞"
  | "空转"
  | "节奏偏慢"
  | "节奏偏快"
  | "好奇不足"
  | "张力不足"
  | "情绪不足"
  | "张力过载"
  | "悬念建立"
  | "悬念不足"
  | "回应延迟"
  | "空悬念"
  | "明确回应"
  | "突然揭晓"
  | "表达不清"
  | "场景可能切得过细"
  | "数据不足"
  | "旧版数据"
  | "多项风险";

const CODE_TO_LABEL: Record<string, DiagnosisBandLabel> = {
  plot_stagnation: "剧情停滞",
  empty_fast_pacing: "空转",
  weak_progress: "推进偏弱",
  pacing_too_slow: "节奏偏慢",
  pacing_too_fast: "节奏偏快",
  weak_curiosity: "好奇不足",
  weak_tension: "张力不足",
  weak_emotional_investment: "情绪不足",
  suspended_tension: "张力不足",
  tension_overload: "张力过载",
  weak_hook: "悬念不足",
  empty_hook: "空悬念",
  delayed_payoff: "回应延迟",
  abrupt_reveal: "突然揭晓",
  effective_payoff: "明确回应",
  unclear_expression: "表达不清",
  scene_boundary_anomaly: "场景可能切得过细",
  low_confidence: "数据不足",
  information_overload: "张力过载",
};

export type SceneDiagnosisLike = {
  scene_ordinal: number;
  primary_diagnosis?: string | null;
  secondary_diagnoses?: string[];
  positive_mechanism?: string | null;
  data_quality_issue?: string | null;
  reading_momentum?: number | null;
  plot_progress?: number | null;
  role?: string | null;
  node_type?: string | null;
  include_in_main_curve?: boolean | null;
  /** When true, missing diagnosis maps to 旧版数据 instead of 未发现明显异常. */
  legacyUncalibrated?: boolean | null;
  /** When scores themselves are missing / unusable. */
  insufficientData?: boolean | null;
};

export function mapDiagnosisCodeToBandLabel(
  code: string | null | undefined,
): DiagnosisBandLabel | null {
  if (!code) return null;
  if ((Object.values(CODE_TO_LABEL) as string[]).includes(code)) {
    return code as DiagnosisBandLabel;
  }
  return CODE_TO_LABEL[code] ?? null;
}

/** Stable internal code check — never compare localized band labels. */
export function isSceneBoundaryAnomalyDiagnosis(diag: SceneDiagnosisLike): boolean {
  return (
    diag.data_quality_issue === "scene_boundary_anomaly" ||
    diag.primary_diagnosis === "scene_boundary_anomaly"
  );
}

function isBeatDiag(diag: SceneDiagnosisLike): boolean {
  if (diag.role === "beat") return true;
  if (diag.node_type === "beat") return true;
  if (diag.include_in_main_curve === false) return true;
  return false;
}

/**
 * Map scene diagnosis → band label.
 * Missing primary_diagnosis must NOT become 「正常」.
 */
export function primaryBandLabelForScene(diag: SceneDiagnosisLike): DiagnosisBandLabel {
  // Beat defaults to 辅助节拍 (not 正常 / 场景切分 as primary band copy).
  if (isBeatDiag(diag)) return "辅助节拍";

  if (diag.insufficientData) return "数据不足";
  if (diag.data_quality_issue === "scene_boundary_anomaly") return "场景可能切得过细";
  if (diag.data_quality_issue) return "数据不足";

  const secondary = diag.secondary_diagnoses ?? [];
  if (secondary.length >= 2 && diag.primary_diagnosis) return "多项风险";

  const mapped = mapDiagnosisCodeToBandLabel(diag.primary_diagnosis);
  if (mapped) return mapped;

  const positive = mapDiagnosisCodeToBandLabel(diag.positive_mechanism);
  if (positive === "明确回应") return "明确回应";

  if (
    typeof diag.plot_progress === "number" &&
    typeof diag.reading_momentum === "number" &&
    diag.plot_progress >= 70 &&
    diag.reading_momentum >= 70
  ) {
    return "表现有效";
  }

  if (diag.legacyUncalibrated && !diag.primary_diagnosis) {
    return "旧版数据";
  }

  if (!diag.primary_diagnosis) {
    return "未发现明显异常";
  }

  // Unknown code: do not invent 「正常」.
  return "未发现明显异常";
}

export function secondaryBandLabels(diag: SceneDiagnosisLike): DiagnosisBandLabel[] {
  const labels: DiagnosisBandLabel[] = [];
  for (const code of diag.secondary_diagnoses ?? []) {
    const mapped = mapDiagnosisCodeToBandLabel(code);
    if (mapped && !labels.includes(mapped)) labels.push(mapped);
  }
  return labels;
}
