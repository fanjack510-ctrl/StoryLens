/** User-facing mapping for scene-boundary API errors (CHG-041). */

import { ApiError } from "./apiClient";

export const SCENE_BOUNDARY_CONFLICT_CODE = "SCENE_REVISION_CONCURRENT_MODIFICATION";

const USER_MESSAGES: Record<string, string> = {
  SCENE_REVISION_CONCURRENT_MODIFICATION: "当前场景草稿已在其他窗口或操作中发生变化。请重新加载最新版本后继续。",
  SCENE_REVISION_NOT_CONFIRMED: "场景划分尚未确认，无法继续阅读旅程分析。",
  SCENE_REVISION_STALE: "场景划分已过期，请重新确认场景边界。",
  SCENE_REVISION_NOT_DRAFT: "仅草稿状态的场景划分可以拆分。请先创建草稿。",
  SCENE_PARTITION_GAP: "场景段落存在空隙，请检查分割线后重试。",
  SCENE_PARTITION_OVERLAP: "场景段落存在重叠，请检查分割线后重试。",
  SCENE_PARTITION_NO_JOURNEY_SCENE: "至少需要保留一个参与旅程分析的场景。",
  SCENE_PARTITION_EMPTY: "场景划分数据不完整，请重新打开草稿。",
  SCENE_PARTITION_CHAPTER_CHANGED: "章节正文已变化，请重新生成场景划分。",
  SCENE_SPLIT_INVALID_POSITION: "只能在同一场景的两个段落之间新增场景。",
  SCENE_SPLIT_EMPTY_SCENE: "该位置会产生空场景，无法拆分。",
  SCENE_BOUNDARY_ALREADY_EXISTS: "这里已经是场景边界。",
  SCENE_MERGE_INCLUDED_CONFLICT: "两侧场景的旅程参与状态不同，请先选择合并后是否参与旅程分析。",
  SCENE_CONFIRMED_JOURNEY_NOT_STARTED: "场景已确认，但阅读旅程任务尚未启动。",
  JOURNEY_TASK_ALREADY_ACTIVE: "阅读旅程任务已在进行中。",
};

export function sceneBoundaryErrorCode(error: unknown): string | undefined {
  if (error instanceof ApiError) {
    if (error.code && error.code !== "HTTP_ERROR") return error.code;
    const detail = error.detail;
    if (typeof detail === "object" && detail && "error_code" in detail) {
      const code = (detail as { error_code?: unknown }).error_code;
      if (typeof code === "string") return code;
    }
    const match = String(error.message || "").match(/\bSCENE_[A-Z0-9_]+\b|\bJOURNEY_[A-Z0-9_]+\b/);
    return match?.[0];
  }
  if (error instanceof Error) {
    const match = error.message.match(/\bSCENE_[A-Z0-9_]+\b|\bJOURNEY_[A-Z0-9_]+\b/);
    return match?.[0];
  }
  return undefined;
}

export function mapSceneBoundaryError(error: unknown): {
  code?: string;
  userMessage: string;
  isConflict: boolean;
} {
  const code = sceneBoundaryErrorCode(error);
  if (code && USER_MESSAGES[code]) {
    return {
      code,
      userMessage: USER_MESSAGES[code],
      isConflict: code === SCENE_BOUNDARY_CONFLICT_CODE,
    };
  }
  const fallback =
    error instanceof ApiError
      ? error.message
      : error instanceof Error
        ? error.message
        : "场景边界操作失败";
  // Never surface raw codes as the primary message.
  const sanitized = fallback.replace(/\bSCENE_[A-Z0-9_]+\b/g, "").replace(/\bJOURNEY_[A-Z0-9_]+\b/g, "").trim();
  return {
    code,
    userMessage: sanitized || "场景边界操作失败，请稍后重试。",
    isConflict: code === SCENE_BOUNDARY_CONFLICT_CODE,
  };
}
