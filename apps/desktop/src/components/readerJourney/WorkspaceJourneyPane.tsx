import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { ReaderJourneyResult } from "../../types";
import { analysisApi } from "../../services/analysisApi";
import {
  hasChartSafeJourneyNodes,
  hasUsableJourneyVisualization,
} from "./hasUsableJourneyVisualization";
import { ReaderJourneySyncWorkspace } from "./ReaderJourneySyncWorkspace";
import type { WorkspaceMainState } from "../../services/resolveWorkspaceLayout";

type Props = {
  bookId: number;
  chapterId: number | null;
  chapterTitle?: string;
  analysisRunId: number;
  journey: ReaderJourneyResult | null | undefined;
  mainContentState: WorkspaceMainState;
  onRetry: () => void;
  onReading: () => void;
  onViewScene?: () => void;
};

function JourneyActions({
  onReading,
  onViewScene,
}: {
  onReading: () => void;
  onViewScene?: () => void;
}) {
  return (
    <div className="chapter-result-error-actions">
      <button type="button" className="secondary" onClick={onReading}>
        返回正文阅读
      </button>
      {onViewScene ? (
        <button type="button" className="secondary" onClick={onViewScene}>
          查看场景结果
        </button>
      ) : null}
    </div>
  );
}

/**
 * Journey content for the unified Book workspace MainContentPane.
 * Restores compare / journey / text-only modes via ReaderJourneySyncWorkspace.
 */
export function WorkspaceJourneyPane({
  bookId,
  chapterId,
  chapterTitle = "本章",
  analysisRunId,
  journey,
  mainContentState,
  onRetry,
  onReading,
  onViewScene,
}: Props) {
  const [syncTab, setSyncTab] = useState<"structure" | "evidence" | "history" | "overview" | "journey">(
    "journey",
  );

  const results = useQuery({
    queryKey: ["run-results", analysisRunId],
    queryFn: () => analysisApi.results(analysisRunId),
    enabled: Number.isFinite(analysisRunId) && mainContentState === "ready",
    retry: false,
  });

  const scenes = useMemo(() => results.data?.scenes ?? [], [results.data?.scenes]);

  if (mainContentState === "loading" || mainContentState === "idle") {
    return (
      <div className="workspace-journey-pane state" data-testid="workspace-journey-pane" data-state="loading">
        <strong>正在加载阅读旅程…</strong>
        <span className="secondary">
          book {bookId}
          {chapterId ? ` · chapter ${chapterId}` : ""} · run {analysisRunId}
        </span>
      </div>
    );
  }

  if (mainContentState === "pending_generation") {
    return (
      <div
        className="workspace-journey-pane state"
        data-testid="workspace-journey-pane"
        data-state="pending_generation"
      >
        <strong>正在生成阅读旅程</strong>
        <span>可继续在「场景分析」查看已完成的 Scene，后台不会中断。</span>
        {onViewScene ? (
          <button type="button" className="secondary" onClick={onViewScene}>
            查看场景结果
          </button>
        ) : null}
      </div>
    );
  }

  if (mainContentState === "scope_mismatch") {
    return (
      <div
        className="workspace-journey-pane state"
        data-testid="workspace-journey-pane"
        data-state="scope_mismatch"
      >
        <strong>当前分析结果与本章节不匹配</strong>
        <span>系统不会自动回退到其他 Run。</span>
        <button type="button" className="secondary" onClick={onReading}>
          返回正文阅读
        </button>
      </div>
    );
  }

  if (mainContentState === "request_error") {
    return (
      <div
        className="workspace-journey-pane state"
        data-testid="workspace-journey-pane"
        data-state="request_error"
      >
        <strong>阅读旅程加载失败</strong>
        <div className="chapter-result-error-actions">
          <button type="button" className="primary" data-testid="workspace-journey-retry" onClick={onRetry}>
            重新加载
          </button>
          <button type="button" className="secondary" onClick={onReading}>
            返回正文阅读
          </button>
        </div>
      </div>
    );
  }

  if (mainContentState === "unavailable") {
    return (
      <div
        className="workspace-journey-pane state"
        data-testid="workspace-journey-pane"
        data-state="unavailable"
      >
        <strong>当前章节尚未生成阅读旅程</strong>
        <button type="button" className="secondary" onClick={onReading}>
          返回正文阅读
        </button>
      </div>
    );
  }

  const chartSafe = Boolean(journey && hasChartSafeJourneyNodes(journey));

  if (mainContentState === "invalid_artifact") {
    return (
      <div
        className="workspace-journey-pane"
        data-testid="workspace-journey-pane"
        data-state="invalid_artifact"
        data-book-id={bookId}
        data-chapter-id={chapterId ?? undefined}
        data-analysis-run={analysisRunId}
      >
        <div className="shell-banner" data-testid="workspace-journey-integrity-banner">
          <strong>阅读旅程结果校验未通过</strong>
          <span>检测到分析内容可能不属于当前正文，已停止展示不可信结果。</span>
        </div>
        <details data-testid="workspace-journey-tech-details">
          <summary>查看技术详情</summary>
          <p className="secondary">
            error_code=
            {(journey as { integrity?: { error_code?: string } } | null)?.integrity?.error_code ||
              (journey as { integrity_status?: string } | null)?.integrity_status ||
              "DATA_INTEGRITY_FAILED"}
            {" · "}
            analysis_run_id={analysisRunId}
            {journey?.journey_run_id ? ` · journey_run_id=${journey.journey_run_id}` : ""}
          </p>
        </details>
        <JourneyActions onReading={onReading} onViewScene={onViewScene} />
      </div>
    );
  }

  if (!journey || !hasUsableJourneyVisualization(journey) || !journey.visualization) {
    return (
      <div
        className="workspace-journey-pane state"
        data-testid="workspace-journey-pane"
        data-state="unavailable"
      >
        <strong>当前章节尚未生成阅读旅程</strong>
        <button type="button" className="secondary" onClick={onReading}>
          返回正文阅读
        </button>
      </div>
    );
  }

  if (!chartSafe) {
    return (
      <div
        className="workspace-journey-pane state"
        data-testid="workspace-journey-pane"
        data-state="unavailable"
      >
        <strong>阅读旅程曲线暂不可绘制</strong>
        <span>当前可视化缺少可用于图表的数值节点，其余结构未作为污染结论处理。</span>
        <JourneyActions onReading={onReading} onViewScene={onViewScene} />
      </div>
    );
  }

  if (!chapterId) {
    return (
      <div
        className="workspace-journey-pane state"
        data-testid="workspace-journey-pane"
        data-state="unavailable"
      >
        <strong>缺少章节上下文，无法打开正文对照</strong>
        <JourneyActions onReading={onReading} onViewScene={onViewScene} />
      </div>
    );
  }

  const integrityStatus =
    (journey as { integrity_status?: string } | null)?.integrity_status ||
    (journey as { integrity?: { status?: string } } | null)?.integrity?.status ||
    null;
  const legacyWarning =
    (journey as { integrity?: { legacy_warning?: string } } | null)?.integrity?.legacy_warning ||
    (integrityStatus === "legacy_unverified"
      ? "旧版分析尚未完成来源校验，仅供参考。"
      : null);
  const partialWarning =
    integrityStatus === "partially_trusted"
      ? "部分分析结果未通过校验，受影响内容已单独隐藏。"
      : null;

  return (
    <div
      className="workspace-journey-pane"
      data-testid="workspace-journey-pane"
      data-state="ready"
      data-integrity={integrityStatus || undefined}
      data-book-id={bookId}
      data-chapter-id={chapterId}
      data-analysis-run={analysisRunId}
    >
      {legacyWarning ? (
        <div className="shell-banner" data-testid="workspace-journey-legacy-banner">
          <strong>{legacyWarning}</strong>
        </div>
      ) : null}
      {partialWarning ? (
        <div className="shell-banner" data-testid="workspace-journey-partial-banner">
          <strong>{partialWarning}</strong>
        </div>
      ) : null}
      <ReaderJourneySyncWorkspace
        chapterId={chapterId}
        chapterTitle={chapterTitle}
        scenes={scenes}
        visualization={journey.visualization}
        tab={syncTab}
        onTabChange={setSyncTab}
        variant="workspace"
      />
    </div>
  );
}
