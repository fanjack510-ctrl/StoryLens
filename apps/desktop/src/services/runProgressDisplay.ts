/** Format AnalysisRun progress for list UI. Never emit undefined/null/NaN. */

export function formatRunProgress(run: {
  total_scene_count?: number | null;
  completed_scene_count?: number | null;
  progress_current?: number | null;
  progress_total?: number | null;
}): string {
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
