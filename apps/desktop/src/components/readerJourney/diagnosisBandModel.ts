/** Single diagnosis-band labels under the main Reader Journey chart. */

export type DiagnosisBandLabel =
  | "正常"
  | "推进增强"
  | "推进偏弱"
  | "剧情停滞"
  | "空转"
  | "节奏偏慢"
  | "节奏偏快"
  | "好奇不足"
  | "紧张不足"
  | "情绪不足"
  | "张力过载"
  | "钩子建立"
  | "钩子不足"
  | "兑现延迟"
  | "空钩子"
  | "有效兑现"
  | "突然揭晓"
  | "表达不清"
  | "切分异常"
  | "多项风险";

const CODE_TO_LABEL: Record<string, DiagnosisBandLabel> = {
  plot_stagnation: "剧情停滞",
  empty_fast_pacing: "空转",
  weak_progress: "推进偏弱",
  pacing_too_slow: "节奏偏慢",
  pacing_too_fast: "节奏偏快",
  weak_curiosity: "好奇不足",
  weak_tension: "紧张不足",
  weak_emotional_investment: "情绪不足",
  suspended_tension: "紧张不足",
  tension_overload: "张力过载",
  weak_hook: "钩子不足",
  empty_hook: "空钩子",
  delayed_payoff: "兑现延迟",
  abrupt_reveal: "突然揭晓",
  effective_payoff: "有效兑现",
  unclear_expression: "表达不清",
  scene_boundary_anomaly: "切分异常",
  low_confidence: "表达不清",
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

export function primaryBandLabelForScene(diag: SceneDiagnosisLike): DiagnosisBandLabel {
  if (diag.data_quality_issue) return "切分异常";
  const secondary = diag.secondary_diagnoses ?? [];
  if (secondary.length >= 2 && diag.primary_diagnosis) return "多项风险";
  const mapped = mapDiagnosisCodeToBandLabel(diag.primary_diagnosis);
  if (mapped) return mapped;
  const positive = mapDiagnosisCodeToBandLabel(diag.positive_mechanism);
  if (positive === "有效兑现") return "有效兑现";
  if (
    typeof diag.plot_progress === "number" &&
    typeof diag.reading_momentum === "number" &&
    diag.plot_progress >= 70 &&
    diag.reading_momentum >= 70
  ) {
    return "推进增强";
  }
  if (!diag.primary_diagnosis) return "正常";
  return "正常";
}

export function secondaryBandLabels(diag: SceneDiagnosisLike): DiagnosisBandLabel[] {
  const labels: DiagnosisBandLabel[] = [];
  for (const code of diag.secondary_diagnoses ?? []) {
    const mapped = mapDiagnosisCodeToBandLabel(code);
    if (mapped && !labels.includes(mapped)) labels.push(mapped);
  }
  return labels;
}
