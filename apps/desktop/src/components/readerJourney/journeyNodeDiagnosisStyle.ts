/** Node color/shape from diagnosis for Reader Journey v2 chart. */

export type DiagnosisSeverityVisual = "ok" | "mild" | "clear" | "severe" | "beat";

export type NodeVisualStyle = {
  colorToken: string;
  colorZh: string;
  shape: "filled_circle" | "hollow_circle" | "triangle" | "diamond" | "square_dot";
  severity: DiagnosisSeverityVisual;
  cssClass: string;
};

export type DiagnosisFamily =
  | "ok"
  | "plot"
  | "pacing"
  | "tension"
  | "hook_payoff"
  | "multi"
  | "data_quality";

const FAMILY_COLOR: Record<DiagnosisFamily, { token: string; zh: string }> = {
  ok: { token: "var(--journey-node-ok, #2f9e44)", zh: "绿色" },
  plot: { token: "var(--journey-node-plot, #f59f00)", zh: "黄色" },
  pacing: { token: "var(--journey-node-pacing, #1c7ed6)", zh: "蓝色" },
  tension: { token: "var(--journey-node-tension, #f76707)", zh: "橙色" },
  hook_payoff: { token: "var(--journey-node-hook, #9c36b5)", zh: "紫色" },
  multi: { token: "var(--journey-node-multi, #e03131)", zh: "红色" },
  data_quality: { token: "var(--journey-node-muted, #868e96)", zh: "灰色" },
};

const PLOT_CODES = new Set([
  "plot_stagnation",
  "weak_progress",
  "empty_fast_pacing",
  "推进偏弱",
  "剧情停滞",
  "空转",
]);
const PACING_CODES = new Set([
  "pacing_too_slow",
  "pacing_too_fast",
  "节奏偏慢",
  "节奏偏快",
]);
const TENSION_CODES = new Set([
  "weak_curiosity",
  "weak_tension",
  "weak_emotional_investment",
  "suspended_tension",
  "tension_overload",
  "information_overload",
  "好奇不足",
  "紧张不足",
  "情绪不足",
  "张力过载",
]);
const HOOK_CODES = new Set([
  "weak_hook",
  "empty_hook",
  "delayed_payoff",
  "abrupt_reveal",
  "effective_payoff",
  "钩子建立",
  "钩子不足",
  "兑现延迟",
  "空钩子",
  "有效兑现",
  "突然揭晓",
]);
const QUALITY_CODES = new Set([
  "scene_boundary_anomaly",
  "low_confidence",
  "unclear_expression",
  "切分异常",
  "表达不清",
]);

export function diagnosisFamily(
  primary: string | null | undefined,
  secondary: string[] = [],
): DiagnosisFamily {
  const codes = [primary, ...secondary].filter(Boolean) as string[];
  if (!codes.length) return "ok";
  if (codes.some((c) => QUALITY_CODES.has(c)) && codes.length === 1) return "data_quality";
  const families = new Set<DiagnosisFamily>();
  for (const code of codes) {
    if (PLOT_CODES.has(code)) families.add("plot");
    else if (PACING_CODES.has(code)) families.add("pacing");
    else if (TENSION_CODES.has(code)) families.add("tension");
    else if (HOOK_CODES.has(code)) families.add("hook_payoff");
    else if (QUALITY_CODES.has(code)) families.add("data_quality");
    else if (code === "多项风险" || code === "low_confidence") families.add("multi");
  }
  if (families.size >= 2) return "multi";
  if (families.has("plot")) return "plot";
  if (families.has("pacing")) return "pacing";
  if (families.has("tension")) return "tension";
  if (families.has("hook_payoff")) return "hook_payoff";
  if (families.has("data_quality")) return "data_quality";
  if (families.has("multi")) return "multi";
  return "ok";
}

export function severityFromDiagnosis(
  primary: string | null | undefined,
  secondary: string[] = [],
  options: {
    isBeat?: boolean;
    confidence?: number | null;
    dataQualityIssue?: string | null;
  } = {},
): DiagnosisSeverityVisual {
  const isBeat = Boolean(options.isBeat);
  const confidence = options.confidence;
  const dataQualityIssue = options.dataQualityIssue;
  if (isBeat || dataQualityIssue || (typeof confidence === "number" && confidence < 0.45)) {
    return "beat";
  }
  const codes = [primary, ...secondary].filter(Boolean) as string[];
  if (!codes.length || primary === "正常" || primary === "推进增强" || primary === "有效兑现") {
    return "ok";
  }
  const severe = new Set([
    "plot_stagnation",
    "empty_fast_pacing",
    "tension_overload",
    "empty_hook",
    "剧情停滞",
    "空转",
    "张力过载",
    "空钩子",
    "多项风险",
  ]);
  const clear = new Set([
    "weak_progress",
    "delayed_payoff",
    "pacing_too_slow",
    "pacing_too_fast",
    "推进偏弱",
    "兑现延迟",
    "节奏偏慢",
    "节奏偏快",
  ]);
  if (codes.some((c) => severe.has(c))) return "severe";
  if (codes.some((c) => clear.has(c))) return "clear";
  return "mild";
}

export function resolveNodeVisualStyle(input: {
  primaryDiagnosis?: string | null;
  secondaryDiagnoses?: string[];
  isBeat?: boolean;
  confidence?: number | null;
  dataQualityIssue?: string | null;
}): NodeVisualStyle {
  const secondary = input.secondaryDiagnoses ?? [];
  const severity = severityFromDiagnosis(input.primaryDiagnosis, secondary, {
    isBeat: Boolean(input.isBeat),
    confidence: input.confidence,
    dataQualityIssue: input.dataQualityIssue,
  });
  const family =
    severity === "beat"
      ? "data_quality"
      : diagnosisFamily(input.primaryDiagnosis, secondary);
  const color = FAMILY_COLOR[family];
  let shape: NodeVisualStyle["shape"] = "filled_circle";
  if (severity === "beat") shape = "square_dot";
  else if (severity === "mild") shape = "hollow_circle";
  else if (severity === "clear") shape = "triangle";
  else if (severity === "severe") shape = "diamond";
  return {
    colorToken: color.token,
    colorZh: color.zh,
    shape,
    severity,
    cssClass: `journey-node-sev-${severity} journey-node-fam-${family}`,
  };
}
