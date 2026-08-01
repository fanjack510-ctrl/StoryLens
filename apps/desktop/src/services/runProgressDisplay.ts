/** Format AnalysisRun progress for list UI. Never emit undefined/null/NaN. */

const JOURNEY_ACTIVE = new Set([
  "starting",
  "queued",
  "running",
  "scene_profiles_running",
  "chapter_synthesis_running",
  "summary_running",
  "phase_analysis_running",
]);

export function formatRunProgress(run: {
  total_scene_count?: number | null;
  completed_scene_count?: number | null;
  progress_current?: number | null;
  progress_total?: number | null;
  journey_status?: string | null;
  journey_completed_scene_count?: number | null;
  journey_total_scene_count?: number | null;
  effective_status?: string | null;
  journey_retryable?: boolean | null;
  journey_error_code?: string | null;
}): string {
  const journeyStatus = String(run.journey_status || "");
  const effective = String(run.effective_status || "");
  const errorCode = String(run.journey_error_code || "");
  const journeyTotal =
    typeof run.journey_total_scene_count === "number" &&
    Number.isFinite(run.journey_total_scene_count) &&
    run.journey_total_scene_count > 0
      ? run.journey_total_scene_count
      : null;
  const journeyCompleted =
    typeof run.journey_completed_scene_count === "number" &&
    Number.isFinite(run.journey_completed_scene_count)
      ? run.journey_completed_scene_count
      : 0;

  if (errorCode === "WAITING_SCENE_ANALYSIS" || effective === "scene_analysis") {
    if (journeyTotal != null) {
      return `场景分析：${journeyCompleted} / ${journeyTotal}`;
    }
    return "正在分析场景";
  }

  if (JOURNEY_ACTIVE.has(journeyStatus) || effective === "journey_running") {
    if (journeyTotal != null) {
      return `阅读旅程：${journeyCompleted} / ${journeyTotal}`;
    }
    return "阅读旅程进行中";
  }

  // CHG-015: only true interrupt / lease-partial states show 已中断.
  if (
    errorCode === "JOURNEY_INTERRUPTED" ||
    journeyStatus === "scene_profiles_partial" ||
    journeyStatus === "budget_blocked" ||
    journeyStatus === "aborted_by_limit"
  ) {
    return "阅读旅程已中断";
  }

  if (journeyStatus === "failed" || effective === "journey_failed") {
    return "阅读旅程生成失败";
  }

  if (journeyStatus === "succeeded" && journeyTotal != null) {
    return `阅读旅程：${journeyTotal} / ${journeyTotal}`;
  }

  const totalScenes = run.total_scene_count;
  if (typeof totalScenes === "number" && Number.isFinite(totalScenes) && totalScenes > 0) {
    const completed =
      typeof run.completed_scene_count === "number" && Number.isFinite(run.completed_scene_count)
        ? run.completed_scene_count
        : 0;
    return `场景分析：${completed} / ${totalScenes}`;
  }

  const current = run.progress_current;
  const total = run.progress_total;
  if (
    typeof current === "number" &&
    typeof total === "number" &&
    Number.isFinite(current) &&
    Number.isFinite(total) &&
    total > 0
  ) {
    return `${current}/${total}`;
  }

  return "等待进度";
}
