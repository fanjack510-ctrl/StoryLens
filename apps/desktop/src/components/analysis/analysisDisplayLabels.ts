/** User-facing labels for analysis workflow UI. Raw enums stay for business logic. */

const ANALYSIS_STATUS_LABELS: Record<string, string> = {
  queued: "等待开始",
  preparing: "正在准备章节",
  boundary_generation: "正在识别场景边界",
  boundary_review: "等待边界确认",
  scene_analysis: "正在分析场景",
  reader_journey: "正在生成阅读旅程",
  paused: "分析已暂停",
  failed: "分析未完成",
  completed: "分析完成",
  succeeded: "分析完成",
  running: "正在分析本章",
  cancelled: "任务已取消",
};

const ANALYSIS_STAGE_LABELS: Record<string, string> = {
  preparing: "准备章节",
  boundary_generation: "识别场景边界",
  boundary_review_generation: "识别场景边界",
  boundary_review: "确认场景边界",
  scene_analysis: "分析场景",
  scene_analysis_budget: "分析场景",
  reader_journey: "生成读者旅程",
  completed: "完成",
};

const FAILURE_REASON_LABELS: Record<string, string> = {
  PROVIDER_UNHEALTHY: "AI 服务连接失败",
  PROVIDER_NOT_CONNECTED: "AI 服务连接失败",
  PROVIDER_HEALTH_STALE: "AI 服务连接失败",
  credential_invalid: "凭据失效",
  CREDENTIAL_INVALID: "凭据失效",
  CLOUD_BUDGET_EXCEEDED: "预算不足",
  CLOUD_REQUEST_LIMIT_EXCEEDED: "预算不足",
  CLOUD_TOKEN_LIMIT_EXCEEDED: "预算不足",
  CLOUD_COST_LIMIT_EXCEEDED: "预算不足",
  INSUFFICIENT_BUDGET_RESERVATION: "预算不足",
  STRUCTURAL_PARSE_ERROR: "返回结果格式异常",
  SCHEMA_VALIDATION_FAILED: "返回结果格式异常",
  LOCAL_SERVICE_DOWN: "本地服务中断",
  NETWORK_ERROR: "本地服务中断",
};

const PRIORITY_LABELS: Record<string, string> = {
  high: "高置信度",
  medium: "中置信度",
  low: "低置信度",
};

const DECISION_LABELS: Record<string, string> = {
  pending: "待处理",
  accept: "已接受",
  accepted: "已接受",
  reject: "已拒绝",
  rejected: "已拒绝",
  manually_added: "人工新增",
};

const REVIEW_STATUS_LABELS: Record<string, string> = {
  in_review: "审阅中",
  pending: "审阅中",
  confirmed: "已完成",
  draft: "草稿",
};

const MANUAL_REASON_LABELS: Record<string, string> = {
  location_change: "地点变化",
  time_jump: "时间跳跃",
  viewpoint_change: "视角变化",
  primary_goal_reset: "人物目标重置",
  explicit_scene_separator: "明确的场景分隔",
  other_manual_boundary: "其他人工边界",
};

function clean(value: unknown): string | null {
  if (value == null) return null;
  const text = String(value).trim();
  if (!text || text === "undefined" || text === "null" || text === "NaN") return null;
  return text;
}

export function formatAnalysisStatus(raw: unknown): string {
  const key = clean(raw);
  if (!key) return "未知状态";
  return ANALYSIS_STATUS_LABELS[key] || "未知状态";
}

export function formatAnalysisStage(raw: unknown): string {
  const key = clean(raw);
  if (!key) return "—";
  if (ANALYSIS_STAGE_LABELS[key]) return ANALYSIS_STAGE_LABELS[key];
  if (key.startsWith("reader_journey")) return "生成读者旅程";
  if (key.startsWith("scene_analysis")) return "分析场景";
  if (key.startsWith("boundary")) return "场景边界";
  return "进行中";
}

export function formatAnalysisFailureReason(raw: unknown): string {
  const key = clean(raw);
  if (!key) return "未知错误";
  return FAILURE_REASON_LABELS[key] || "未知错误";
}

export function formatReviewPriority(raw: unknown): string {
  const key = clean(raw);
  if (!key) return "—";
  return PRIORITY_LABELS[key] || key;
}

export function formatBoundaryDecision(raw: unknown): string {
  const key = clean(raw);
  if (!key) return "—";
  return DECISION_LABELS[key] || key;
}

export function formatReviewStatus(raw: unknown): string {
  const key = clean(raw);
  if (!key) return "审阅中";
  return REVIEW_STATUS_LABELS[key] || "审阅中";
}

export function formatManualReasonType(raw: unknown): string {
  const key = clean(raw);
  if (!key) return "";
  return MANUAL_REASON_LABELS[key] || key;
}

export function formatCny(amount: unknown, fallback = "暂无法估算"): string {
  if (typeof amount !== "number" || !Number.isFinite(amount)) return fallback;
  return `约 ${amount} 元`;
}

export function formatTokenCount(amount: unknown, fallback = "暂无法估算"): string {
  if (typeof amount !== "number" || !Number.isFinite(amount)) return fallback;
  return amount.toLocaleString("zh-CN");
}

export function formatConfidencePercent(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return `${Math.round(value * 100)}%`;
}
