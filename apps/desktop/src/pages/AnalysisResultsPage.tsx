import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { analysisApi } from "../services/analysisApi";
import { Badge, Empty, ErrorState, Loading } from "../components/common/States";
import { hasUsableJourneyVisualization, hasChartSafeJourneyNodes } from "../components/readerJourney/hasUsableJourneyVisualization";
import { formatJourneyStatus } from "../components/readerJourney/journeyUiLabels";
import { ReaderJourneySyncWorkspace } from "../components/readerJourney/ReaderJourneySyncWorkspace";
import { StateView } from "../components/ui/StateView";
import { formatSceneDisplayLabel } from "../services/formatSceneDisplayLabel";
import { resolveRunResultsViewState } from "../services/runResultsGuard";
import type { ReaderJourneyPreflight, ReaderJourneyProgress, ReaderJourneyResult, SceneResultItem } from "../types";
import {
  EVIDENCE_GROUP_LABELS,
  STRUCTURE_FIELD_SECTIONS,
  formatBoundarySource,
  formatFunctionTags,
  formatRunStatusForResults,
  formatSceneSummary,
} from "./sceneResultLabels";
import "./analysisResults.css";

type Tab = "structure" | "evidence" | "history" | "overview" | "journey";

function fieldSummary(field?: { summary: string; evidence_paragraph_ids: string[] }): string {
  if (!field || !field.summary?.trim()) return "无";
  return field.summary.trim();
}

function failedStageLabel(stage?: string | null): string {
  if (stage === "reader_journey_scene_profiles") return "Scene Reader Journey Profile";
  if (stage === "reader_journey_chapter_synthesis") return "Chapter Reader Journey Synthesis";
  return stage || "未知阶段";
}

function resumeBlockLabel(reason?: string | null, blocked?: boolean): string | null {
  if (!blocked && !reason) return null;
  if (reason === "offline_replay_required") return "请先离线重放";
  if (reason === "contract_outdated") return "请升级Reader Journey契约后恢复";
  if (reason === "planner_outdated") return "请升级批次规划后恢复";
  if (reason === "preflight_loading") return "正在重新计算恢复计划";
  if (blocked) return "请按恢复预检重试";
  return null;
}

export function AnalysisResultsPage() {
  const params = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const runId = Number(params.runId);
  const [selectedSceneId, setSelectedSceneId] = useState<number>();
  const [tab, setTabState] = useState<Tab>(() => {
    return searchParams.get("tab") === "reader-journey" ? "journey" : "structure";
  });
  const [highlight, setHighlight] = useState<string[]>([]);
  const [journeyPreflight, setJourneyPreflight] = useState<ReaderJourneyPreflight | null>(null);
  const [journeyConsent, setJourneyConsent] = useState(false);
  const [journeyRunId, setJourneyRunId] = useState<number>();
  const [journeyBusy, setJourneyBusy] = useState(false);
  const [journeyError, setJourneyError] = useState<string>();
  const [offlineReplayMessage, setOfflineReplayMessage] = useState<string>();
  const proseRef = useRef<HTMLDivElement>(null);

  const results = useQuery({
    queryKey: ["run-results", runId],
    queryFn: () => analysisApi.results(runId),
    enabled: Number.isFinite(runId),
  });

  const viewState = resolveRunResultsViewState({
    isLoading: results.isLoading,
    error: results.error,
    data: results.data,
  });
  const completedResults = viewState.kind === "completed" ? viewState.data : null;

  const scenes = useMemo(
    () => completedResults?.scenes ?? [],
    [completedResults],
  );
  const selected: SceneResultItem | undefined = useMemo(
    () => scenes.find((item) => item.scene.id === selectedSceneId) ?? scenes[0],
    [scenes, selectedSceneId],
  );

  useEffect(() => {
    if (selectedSceneId == null && scenes.length) {
      setSelectedSceneId(scenes[0].scene.id);
    }
  }, [scenes, selectedSceneId]);

  const sceneParagraphs = useQuery({
    queryKey: ["scene-paragraphs", selected?.scene.id],
    queryFn: () => analysisApi.sceneParagraphs(selected!.scene.id),
    enabled: !!selected,
  });

  const readerJourney = useQuery({
    queryKey: [
      "reader-journey",
      completedResults?.chapter?.book_id ?? null,
      completedResults?.chapter?.id ?? null,
      runId,
    ],
    queryFn: () =>
      analysisApi.readerJourney(runId, {
        bookId: completedResults?.chapter?.book_id,
        chapterId: completedResults?.chapter?.id,
      }),
    enabled:
      Number.isFinite(runId) &&
      completedResults != null &&
      completedResults.run.status === "succeeded" &&
      Boolean(completedResults.chapter?.id),
    placeholderData: undefined,
  });

  const journeyProgress = useQuery({
    queryKey: ["reader-journey-progress", journeyRunId],
    queryFn: () => analysisApi.readerJourneyProgress(journeyRunId!),
    enabled: !!journeyRunId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status || ["succeeded", "failed", "cancelled", "budget_blocked"].includes(status)) {
        return false;
      }
      return 1500;
    },
  });

  useEffect(() => {
    if (readerJourney.data?.journey_run_id) {
      setJourneyRunId(readerJourney.data.journey_run_id);
    }
  }, [readerJourney.data?.journey_run_id]);

  useEffect(() => {
    if (journeyProgress.data?.status === "succeeded") {
      readerJourney.refetch();
    }
  }, [journeyProgress.data?.status, readerJourney]);

  useEffect(() => {
    if (searchParams.get("tab") === "reader-journey") {
      setTabState("journey");
    }
  }, [searchParams]);

  const setTab = (next: Tab) => {
    setTabState(next);
    const params = new URLSearchParams(searchParams);
    if (next === "journey") {
      params.set("tab", "reader-journey");
    } else {
      params.delete("tab");
      params.delete("mode");
      params.delete("scene");
      params.delete("paragraph");
      params.delete("metric");
      params.delete("cluster");
    }
    setSearchParams(params, { replace: true });
  };

  const selectScene = (sceneId: number, options?: { keepTab?: boolean }) => {
    setSelectedSceneId(sceneId);
    setHighlight([]);
    if (!options?.keepTab && tab !== "journey") {
      setTab("structure");
    }
  };

  const locateEvidence = (paragraphId: string) => {
    setHighlight([paragraphId]);
    setTimeout(() => {
      const node = document.getElementById(`result-p-${paragraphId}`);
      node?.scrollIntoView?.({ behavior: "smooth", block: "center" });
    }, 0);
  };

  const download = async (format: "json" | "markdown") => {
    const url = analysisApi.resultsExportUrl(runId, format);
    const resp = await fetch(url);
    const blob = await resp.blob();
    const href = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.download = `run-${runId}-results.${format === "markdown" ? "md" : "json"}`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(href);
  };

  const loadJourneyPreflight = async () => {
    setJourneyError(undefined);
    try {
      const data = await analysisApi.readerJourneyPreflight(runId, { cloud_consent: journeyConsent });
      setJourneyPreflight(data);
      setTab("journey");
    } catch (error) {
      setJourneyError((error as Error).message);
    }
  };

  const startReaderJourney = async () => {
    if (journeyBusy) return;
    setJourneyBusy(true);
    setJourneyError(undefined);
    try {
      const accepted = await analysisApi.createReaderJourney(runId, {
        client_request_id: crypto.randomUUID(),
        cloud_consent: journeyConsent,
      });
      setJourneyRunId(accepted.journey_run_id);
      if (accepted.creation_blocked_reason || accepted.recovery_recommended) {
        setJourneyError(
          accepted.recovery_recommended
            ? "已存在可恢复的读者旅程任务，请使用「恢复失败任务」而不是新建"
            : "已存在进行中或可恢复的读者旅程任务，已定位到该任务",
        );
      }
      setTab("journey");
      await journeyProgress.refetch();
    } catch (error) {
      setJourneyError((error as Error).message);
    } finally {
      setJourneyBusy(false);
    }
  };

  const resumeReaderJourney = async () => {
    if (!journeyRunId || journeyBusy) return;
    if (journeyProgress.data?.offline_replay_available) {
      setJourneyError("请先使用离线重放恢复旧版契约结果，再考虑付费恢复");
      return;
    }
    const blockLabel = resumeBlockLabel(
      journeyProgress.data?.resume_block_reason,
      journeyProgress.data?.blind_resume_blocked,
    );
    if (blockLabel) {
      setJourneyError(blockLabel);
      return;
    }
    setJourneyBusy(true);
    setJourneyError(undefined);
    try {
      const accepted = await analysisApi.resumeReaderJourney(journeyRunId, {
        client_request_id: crypto.randomUUID(),
        cloud_consent: journeyConsent,
      });
      setJourneyRunId(accepted.journey_run_id);
      setJourneyPreflight(null);
      await journeyProgress.refetch();
    } catch (error) {
      setJourneyError((error as Error).message);
    } finally {
      setJourneyBusy(false);
    }
  };

  const offlineReplayReaderJourney = async () => {
    if (journeyBusy || !journeyRunId) return;
    setJourneyBusy(true);
    setJourneyError(undefined);
    setOfflineReplayMessage(undefined);
    // Invalidate create-time preflight so UI cannot keep showing completed scenes.
    setJourneyPreflight(null);
    setJourneyConsent(false);
    try {
      const result = await analysisApi.offlineReplayReaderJourney(journeyRunId, { confirmed: true });
      setOfflineReplayMessage(
        result.idempotent_replay
          ? "离线重放：Profile 已存在，无需重复写入"
          : `离线重放成功：已恢复 ${result.replayed_scene_ids.length} 个 Scene（零 HTTP / 零 Token）`,
      );
      await journeyProgress.refetch();
      await readerJourney.refetch();
    } catch (error) {
      setJourneyError((error as Error).message);
    } finally {
      setJourneyBusy(false);
    }
  };

  const semanticRecalibrateReaderJourney = async () => {
    if (journeyBusy || !journeyRunId) return;
    setJourneyBusy(true);
    setJourneyError(undefined);
    setOfflineReplayMessage(undefined);
    try {
      const result = await analysisApi.semanticRecalibrateReaderJourney(journeyRunId, {
        confirmed: true,
      });
      setOfflineReplayMessage(
        `语义校准完成：已重算 ${result.calibrated_profile_count} 个 Profile（零 HTTP / 零 Token）；剩余空 q_in=${result.empty_qin_remaining}`,
      );
      await journeyProgress.refetch();
      await readerJourney.refetch();
    } catch (error) {
      setJourneyError((error as Error).message);
    } finally {
      setJourneyBusy(false);
    }
  };

  const exportJourneyJson = async (journeyId: number) => {
    const resp = await fetch(analysisApi.readerJourneyExportUrl(journeyId));
    const blob = await resp.blob();
    const href = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.download = `reader-journey-${journeyId}.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(href);
  };

  const journeyData: ReaderJourneyResult | null | undefined = readerJourney.data;
  const journeyProg: ReaderJourneyProgress | undefined = journeyProgress.data;
  const hasActiveOrFailedJourney = Boolean(
    journeyProg &&
      ["queued", "scene_profiles_running", "chapter_synthesis_running", "scene_profiles_partial", "failed"].includes(
        journeyProg.status,
      ),
  );
  const recoverablePartialOrFailed = Boolean(
    journeyProg &&
      (journeyProg.status === "scene_profiles_partial" || journeyProg.status === "failed") &&
      (journeyProg.recovery_safe ||
        journeyProg.offline_replay_available ||
        journeyProg.retryable ||
        journeyProg.blind_resume_blocked),
  );
  const displayPreflight = journeyProg?.resume_preflight
    ? {
        scene_batch_count: journeyProg.resume_preflight.scene_batch_count,
        expected_requests: journeyProg.resume_preflight.expected_requests,
        worst_case_requests: journeyProg.resume_preflight.worst_case_requests,
        estimated_cost: journeyProg.resume_preflight.estimated_cost,
        currency: journeyProg.resume_preflight.currency || "CNY",
        within_budget: true,
        planner_version: journeyProg.resume_preflight.planner_version,
        batch_plan: journeyProg.resume_preflight.batch_plan,
        remaining_scenes: journeyProg.resume_preflight.remaining_scenes,
        is_resume: true as const,
      }
    : journeyPreflight
      ? { ...journeyPreflight, is_resume: false as const }
      : null;
  const resumeDisabledReason =
    journeyProg?.offline_replay_available
      ? "请先离线重放"
      : resumeBlockLabel(journeyProg?.resume_block_reason, journeyProg?.blind_resume_blocked) ||
        (journeyProg && journeyProg.recovery_safe === false && !journeyProg.resume_preflight
          ? "正在重新计算恢复计划"
          : null);
  const journeyHasVisualization = hasUsableJourneyVisualization(journeyData);
  const journeyChartSafe = hasChartSafeJourneyNodes(journeyData);
  const journeyEmptyVisualization = Boolean(
    journeyData?.status === "succeeded" &&
      journeyData.visualization &&
      !journeyHasVisualization,
  );
  const journeyStatusFailed = Boolean(
    (journeyData?.status &&
      ["failed", "scene_profiles_partial", "budget_blocked"].includes(journeyData.status)) ||
      (journeyProg?.status &&
        ["failed", "scene_profiles_partial", "budget_blocked"].includes(journeyProg.status)),
  );
  const showJourneySync = tab === "journey" && journeyChartSafe;
  const generateJourneyLabel = journeyHasVisualization
    ? "查看预测读者旅程"
    : recoverablePartialOrFailed
      ? "请先恢复剩余任务"
      : "生成读者旅程分析";
  const resumeButtonLabel = resumeDisabledReason || "恢复剩余任务";

  const openJourneyTab = () => setTab("journey");

  if (viewState.kind === "loading") return <Loading />;
  if (viewState.kind === "error") {
    return (
      <ErrorState error={viewState.error} retry={() => void results.refetch()} />
    );
  }
  if (viewState.kind === "missing") {
    return (
      <div className="state results-page-state" data-testid="results-page-missing">
        <strong>未找到分析结果</strong>
        <span>该运行可能尚不存在，或结果尚未生成。</span>
      </div>
    );
  }
  if (viewState.kind === "incomplete") {
    return (
      <div className="state results-page-state" data-testid="results-page-incomplete">
        <strong>分析结果数据不完整</strong>
        <span>{viewState.reason}</span>
      </div>
    );
  }
  if (viewState.kind === "failed") {
    return (
      <div className="state results-page-state" data-testid="results-page-failed">
        <strong>分析尚未完成</strong>
        <span>
          当前状态：{formatRunStatusForResults(viewState.status)}。请返回任务中心查看进度后再打开结果。
        </span>
      </div>
    );
  }

  const { summary, chapter, run, boundary_revision } = viewState.data;
  const analysis = selected?.analysis_artifact?.analysis ?? {};

  const exportBar = (
    <div className="export-bar journey-sync-export-bar">
      <button
        data-testid="generate-reader-journey"
        onClick={journeyHasVisualization ? openJourneyTab : loadJourneyPreflight}
        disabled={
          run.status !== "succeeded" ||
          recoverablePartialOrFailed ||
          (journeyHasVisualization ? false : journeyBusy)
        }
        title={
          recoverablePartialOrFailed
            ? "已有可恢复的读者旅程任务，请使用「恢复剩余任务」"
            : undefined
        }
      >
        {generateJourneyLabel}
      </button>
      <button data-testid="export-json" onClick={() => download("json")}>
        导出JSON
      </button>
      <button data-testid="export-markdown" onClick={() => download("markdown")}>
        导出Markdown
      </button>
      {journeyData?.status === "succeeded" && (
        <button
          data-testid="export-journey-json"
          onClick={() => exportJourneyJson(journeyData.journey_run_id)}
        >
          导出旅程JSON
        </button>
      )}
    </div>
  );

  const journeyTaskControls = (
    <div className="reader-journey-panel" data-testid="journey-panel">
      <p className="muted">
        本功能会基于已完成的场景分析，计算阅读节奏、读者问题、正反馈、钩子和风险，不会重新切分场景。
        新建分析默认使用 Reader Journey V2（真实正文分析）。
      </p>
      {journeyError && <div className="notice error">{journeyError}</div>}
      {(journeyProg?.status === "succeeded" || journeyData?.status === "succeeded") &&
        String(journeyProg?.scene_contract_version || journeyData?.scene_contract_version || "").startsWith(
          "1.",
        ) && (
          <div className="notice" data-testid="journey-legacy-reanalyze-hint">
            当前为旧版未校准分析。重新生成将创建新的 V2 分析并产生相应模型费用；旧结果保留只读，不会自动升级。
          </div>
        )}
      {offlineReplayMessage && (
        <div className="notice" data-testid="journey-offline-replay-success">
          {offlineReplayMessage}
        </div>
      )}
      {journeyProg?.offline_replay_available && (
        <div className="notice" data-testid="journey-old-contract-notice">
          {journeyProg.user_error_message ||
            "此运行使用旧版读者问题契约，可先执行零费用离线重放。"}
        </div>
      )}
      {displayPreflight && (
        <div
          className="journey-preflight"
          data-testid={displayPreflight.is_resume ? "journey-resume-preflight" : "journey-preflight"}
        >
          <dl>
            {displayPreflight.remaining_scenes != null && (
              <>
                <dt>剩余 Scene</dt>
                <dd>{displayPreflight.remaining_scenes}</dd>
              </>
            )}
            <dt>Scene批次</dt>
            <dd>{displayPreflight.scene_batch_count}</dd>
            <dt>预估请求</dt>
            <dd>{displayPreflight.expected_requests}</dd>
            <dt>最坏请求</dt>
            <dd>{displayPreflight.worst_case_requests}</dd>
            <dt>预估费用</dt>
            <dd>
              {displayPreflight.estimated_cost} {displayPreflight.currency}
            </dd>
            {"within_budget" in displayPreflight && displayPreflight.within_budget != null && (
              <>
                <dt>预算内</dt>
                <dd>{displayPreflight.within_budget ? "是" : "否"}</dd>
              </>
            )}
            {displayPreflight.planner_version && (
              <>
                <dt>规划器版本</dt>
                <dd>{displayPreflight.planner_version}</dd>
              </>
            )}
            {journeyProg?.scene_contract_version && (
              <>
                <dt>Scene契约</dt>
                <dd>{journeyProg.scene_contract_version}</dd>
              </>
            )}
          </dl>
          {!!displayPreflight.batch_plan?.length && (
            <ol data-testid="journey-batch-plan">
              {displayPreflight.batch_plan.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ol>
          )}
        </div>
      )}
      {recoverablePartialOrFailed &&
        !journeyProg?.resume_preflight &&
        !journeyProg?.offline_replay_available &&
        journeyProg?.recovery_safe !== false && (
          <div className="notice" data-testid="journey-preflight-recalculating">
            正在重新计算恢复计划
          </div>
        )}
      <label>
        <input
          type="checkbox"
          data-testid="journey-cloud-consent"
          checked={journeyConsent}
          onChange={(event) => setJourneyConsent(event.target.checked)}
        />
        同意向云端传输正文以生成读者旅程
      </label>
      <div className="journey-actions">
        {!hasActiveOrFailedJourney && (
          <button
            data-testid="start-reader-journey"
            disabled={!journeyConsent || journeyBusy || !journeyPreflight?.within_budget}
            onClick={startReaderJourney}
          >
            开始生成
          </button>
        )}
        {(journeyProg?.status === "scene_profiles_partial" || journeyProg?.status === "failed") && (
          <button
            data-testid="resume-reader-journey"
            disabled={
              !journeyConsent ||
              journeyBusy ||
              !!journeyProg.offline_replay_available ||
              !!journeyProg.blind_resume_blocked ||
              journeyProg.recovery_safe === false ||
              !journeyProg.resume_preflight
            }
            onClick={resumeReaderJourney}
          >
            {resumeButtonLabel}
          </button>
        )}
        {journeyProg?.offline_replay_available && (
          <button
            data-testid="offline-replay-reader-journey"
            disabled={journeyBusy}
            onClick={offlineReplayReaderJourney}
          >
            离线恢复已有Scene Profile（不产生费用）
          </button>
        )}
        {(journeyProg?.status === "succeeded" || journeyData?.status === "succeeded") && (
          <button
            data-testid="semantic-recalibrate-reader-journey"
            disabled={journeyBusy}
            onClick={semanticRecalibrateReaderJourney}
          >
            离线语义校准（重算问题链/诊断，零费用）
          </button>
        )}
        {(journeyProg?.status === "succeeded" || journeyData?.status === "succeeded") &&
          String(journeyProg?.scene_contract_version || journeyData?.scene_contract_version || "").startsWith(
            "1.",
          ) && (
            <button
              data-testid="force-new-v2-reader-journey"
              disabled={!journeyConsent || journeyBusy}
              onClick={async () => {
                if (journeyBusy) return;
                const ok = window.confirm(
                  "将创建新的 V2 真实正文分析并产生相应模型费用。旧版结果保留只读，不会自动升级。是否继续？",
                );
                if (!ok) return;
                setJourneyBusy(true);
                setJourneyError(undefined);
                try {
                  const accepted = await analysisApi.createReaderJourney(runId, {
                    client_request_id: crypto.randomUUID(),
                    cloud_consent: journeyConsent,
                    force_new_version: true,
                  });
                  setJourneyRunId(accepted.journey_run_id);
                  setTab("journey");
                  await journeyProgress.refetch();
                } catch (error) {
                  setJourneyError((error as Error).message);
                } finally {
                  setJourneyBusy(false);
                }
              }}
            >
              重新生成 V2 分析（产生模型费用）
            </button>
          )}
      </div>
      {(journeyProg?.status === "failed" || journeyProg?.status === "scene_profiles_partial") &&
        (journeyProg.status === "failed" ? (
          <StateView
            kind="error"
            data-testid="journey-failed"
            title="阅读旅程生成失败"
            description={
              <>
                <span>已完成的场景分析不会受到影响。</span>
                <details data-testid="journey-failed-tech">
                  <summary>技术详情</summary>
                  {journeyProg.failed_stage && (
                    <div>失败阶段：{failedStageLabel(journeyProg.failed_stage)}</div>
                  )}
                  {(journeyProg.user_error_message ||
                    journeyProg.root_error_message ||
                    journeyProg.root_error_code) && (
                    <div>
                      错误：
                      {journeyProg.user_error_message ||
                        journeyProg.root_error_message ||
                        journeyProg.root_error_code}
                    </div>
                  )}
                  {journeyProg.failed_scene_ordinal != null && (
                    <div data-testid="journey-failed-scene">
                      failed_scene：Scene {journeyProg.failed_scene_ordinal}
                      {journeyProg.failed_scene_id != null
                        ? ` (id=${journeyProg.failed_scene_id})`
                        : ""}
                    </div>
                  )}
                  {journeyProg.failed_invocation_id != null && (
                    <div data-testid="journey-failed-invocation">
                      failed_invocation_id：{journeyProg.failed_invocation_id}
                    </div>
                  )}
                  <div>
                    已完成 Profile：{journeyProg.completed_scene_count} / 剩余：
                    {journeyProg.remaining_scene_count}
                  </div>
                  <div>
                    规划器：{journeyProg.planner_version || "-"} · 契约：
                    {journeyProg.scene_contract_version || "-"}
                  </div>
                  <div data-testid="journey-usage-summary">
                    请求 {journeyProg.request_count ?? 0} · Token {journeyProg.total_tokens ?? 0} ·
                    费用 {journeyProg.estimated_cost ?? 0} {journeyProg.currency || "CNY"}
                  </div>
                  <div>
                    Reservation：{journeyProg.reservation_released ? "已释放" : "仍占用"}
                  </div>
                  <div>
                    是否可恢复：
                    {resumeDisabledReason
                      ? `否（${resumeDisabledReason}）`
                      : journeyProg.recovery_safe
                        ? "是"
                        : journeyProg.retryable
                          ? "是"
                          : "否"}
                  </div>
                </details>
              </>
            }
          />
        ) : (
          <div className="notice journey-failed" data-testid="journey-partial">
            <strong>部分完成</strong>
            <details data-testid="journey-partial-tech">
              <summary>技术详情</summary>
              {journeyProg.failed_stage && (
                <div>失败阶段：{failedStageLabel(journeyProg.failed_stage)}</div>
              )}
              {(journeyProg.user_error_message ||
                journeyProg.root_error_message ||
                journeyProg.root_error_code) && (
                <div>
                  错误：
                  {journeyProg.user_error_message ||
                    journeyProg.root_error_message ||
                    journeyProg.root_error_code}
                </div>
              )}
              <div>
                已完成 Profile：{journeyProg.completed_scene_count} / 剩余：
                {journeyProg.remaining_scene_count}
              </div>
            </details>
          </div>
        ))}
      {journeyProg && (
        <div data-testid="journey-progress">
          <div>
            状态：{formatJourneyStatus(journeyProg.status)}
            {" · "}
            {(journeyProg.total_scene_count ?? 0) > 0
              ? `已处理 ${journeyProg.completed_scene_count} / ${journeyProg.total_scene_count} 个场景`
              : "正在处理场景数据"}
          </div>
          <details data-testid="journey-progress-tech">
            <summary>技术详情</summary>
            <div>AnalysisRun #{journeyProg.analysis_run_id}</div>
            <div>JourneyRun #{journeyProg.journey_run_id}</div>
            <div>原始状态：{journeyProg.status}</div>
            {journeyProg.current_stage ? (
              <div>原始阶段：{journeyProg.current_stage}</div>
            ) : null}
          </details>
        </div>
      )}
    </div>
  );

  if (tab === "journey" && journeyStatusFailed && !showJourneySync) {
    return (
      <section className="workspace results-page results-page-journey-state">
        {exportBar}
        {journeyTaskControls}
      </section>
    );
  }

  if (tab === "journey" && journeyEmptyVisualization) {
    return (
      <section className="workspace results-page results-page-journey-state">
        <StateView
          kind="empty"
          data-testid="journey-empty-state"
          title="暂时没有可显示的阅读旅程"
          description="当前分析结果没有包含有效的场景或指标数据。"
        />
        {exportBar}
      </section>
    );
  }

  if (
    tab === "journey" &&
    journeyHasVisualization &&
    !journeyChartSafe &&
    !showJourneySync
  ) {
    return (
      <section className="workspace results-page results-page-journey-state">
        <StateView
          kind="error"
          data-testid="journey-integrity-blocked-state"
          title="阅读旅程结果校验未通过"
          description="检测到部分结论与当前正文不一致，图表详情已暂停展示。"
        />
        {exportBar}
      </section>
    );
  }

  if (showJourneySync && journeyData?.visualization) {
    return (
      <section className="workspace results-page results-page-journey-sync">
        <ReaderJourneySyncWorkspace
          chapterId={chapter.id}
          chapterTitle={chapter.display_title || chapter.title}
          scenes={scenes}
          visualization={journeyData.visualization}
          tab={tab}
          onTabChange={setTab}
          taskControls={journeyTaskControls}
          exportBar={exportBar}
          journeyRunId={journeyData.journey_run_id ?? null}
          analysisRunId={journeyData.analysis_run_id ?? null}
          providerName={journeyData.provider_name ?? null}
          modelName={journeyData.model_name ?? null}
        />
      </section>
    );
  }

  return (
    <section className="workspace results-page analysis-results-layout" data-testid="scene-analysis-results">
      <aside className="structure-pane" data-testid="scene-list">
        <div className="pane-head results-page-header">
          <div>
            <small>场景分析</small>
            <h2 data-testid="results-header">
              场景分析结果：Run #{run.id} · {summary.total_scene_count} 个场景
            </h2>
            <p>{chapter.display_title || chapter.title}</p>
          </div>
          <div className="results-page-status">
            <Badge tone="success">{formatRunStatusForResults(run.status)}</Badge>
          </div>
        </div>
        <div className="scene-nav-label">场景导航</div>
        <div className="scene-selector" data-testid="scene-nav">
          {scenes.map((item) => {
            const s = item.scene;
            const goal = fieldSummary(item.analysis_artifact?.analysis.goal);
            const revised =
              s.boundary_source === "user_added"
              || s.boundary_source === "user_accepted_model_conflict";
            return (
              <button
                key={s.id}
                data-testid={`scene-list-item-${s.ordinal}`}
                className={selected?.scene.id === s.id ? "selected" : ""}
                onClick={() => selectScene(s.id)}
              >
                <span className="scene-line">
                  <b>{formatSceneDisplayLabel(s)}</b>
                  {item.analysis_artifact?.offline_recovered && (
                    <Badge tone="warning">离线恢复</Badge>
                  )}
                  {revised && <Badge tone="neutral">人工修订</Badge>}
                </span>
                <small>
                  {s.start_paragraph_id} → {s.end_paragraph_id}
                  {s.is_single_paragraph ? "（单段）" : ""}
                </small>
                <small className="scene-goal">{goal === "无" ? "暂无目标摘要" : goal}</small>
                <small className="scene-tags">
                  {formatFunctionTags(item.analysis_artifact?.analysis.function_tags)}
                </small>
                <small>边界来源：{formatBoundarySource(s.boundary_source)}</small>
              </button>
            );
          })}
        </div>
      </aside>

      <article className="reader" ref={proseRef}>
        <header>
          <p className="eyebrow">场景正文</p>
          <h1>
            {selected ? formatSceneDisplayLabel(selected.scene) : "未选择场景"}
            {selected?.scene && (
              <small>
                {" "}
                {selected.scene.start_paragraph_id} → {selected.scene.end_paragraph_id}
              </small>
            )}
          </h1>
        </header>
        <div className="prose">
          {sceneParagraphs.isLoading ? (
            <Loading />
          ) : sceneParagraphs.error ? (
            <ErrorState error={sceneParagraphs.error as Error} />
          ) : (
            (sceneParagraphs.data?.paragraphs ?? []).map((p) => (
              <div
                id={`result-p-${p.id}`}
                key={p.id}
                data-testid={`paragraph-${p.id}`}
                className={`paragraph ${p.in_scene ? "in-scene" : ""} ${
                  highlight.includes(p.id) ? "highlight" : ""
                }`}
              >
                <button
                  title="复制段落ID"
                  onClick={() => navigator.clipboard?.writeText(p.id)}
                >
                  {p.id}
                </button>
                <p>{p.raw_text}</p>
              </div>
            ))
          )}
        </div>
      </article>

      <aside className="analysis-pane">
        <div className="tabs">
          <button
            data-testid="tab-structure"
            className={tab === "structure" ? "active" : ""}
            onClick={() => setTab("structure")}
          >
            场景结构
          </button>
          <button
            data-testid="tab-evidence"
            className={tab === "evidence" ? "active" : ""}
            onClick={() => setTab("evidence")}
          >
            证据
          </button>
          <button
            data-testid="tab-history"
            className={tab === "history" ? "active" : ""}
            onClick={() => setTab("history")}
          >
            历史
          </button>
          <button
            data-testid="tab-overview"
            className={tab === "overview" ? "active" : ""}
            onClick={() => setTab("overview")}
          >
            整章概览
          </button>
          <button
            data-testid="tab-journey"
            className={tab === "journey" ? "active" : ""}
            onClick={() => setTab("journey")}
          >
            读者旅程
          </button>
        </div>

        <div className="export-bar">
          <button
            data-testid="generate-reader-journey"
            onClick={journeyHasVisualization ? openJourneyTab : loadJourneyPreflight}
            disabled={
              run.status !== "succeeded" ||
              recoverablePartialOrFailed ||
              (journeyHasVisualization ? false : journeyBusy)
            }
            title={
              recoverablePartialOrFailed
                ? "已有可恢复的读者旅程任务，请使用「恢复剩余任务」"
                : undefined
            }
          >
            {generateJourneyLabel}
          </button>
          <button data-testid="export-json" onClick={() => download("json")}>
            导出JSON
          </button>
          <button data-testid="export-markdown" onClick={() => download("markdown")}>
            导出Markdown
          </button>
        </div>

        {!selected ? (
          <Empty text="没有可显示的场景" />
        ) : tab === "structure" ? (
          <div className="scene-structure analysis-results-body" data-testid="structure-panel">
            <div className="scene-title">
              <Badge tone="success">{formatSceneDisplayLabel(selected.scene)}</Badge>
              <h2>{selected.scene.scene_key}</h2>
              <p>
                {selected.scene.start_paragraph_id} → {selected.scene.end_paragraph_id}
              </p>
            </div>
            {!selected.analysis_artifact ? (
              <Empty text="该场景暂无分析结果" />
            ) : (
              <div className="results-structure-sections">
                <section className="analysis-result-section results-structure-section" data-testid="scene-summary-section">
                  <h3>场景摘要</h3>
                  <p>{formatSceneSummary(analysis)}</p>
                </section>
                {STRUCTURE_FIELD_SECTIONS.map(({ key, label, section }) => (
                  <section className="analysis-result-section results-structure-section" key={key}>
                    <h3>{section}</h3>
                    <div className="structure-field" data-testid={`structure-field-${key}`}>
                      <b>{label}</b>
                      <p>{fieldSummary(analysis[key] as any)}</p>
                    </div>
                  </section>
                ))}
                <section className="analysis-result-section results-structure-section">
                  <h3>关键动作</h3>
                  <div className="structure-field" data-testid="structure-field-key_actions">
                    <b>关键动作</b>
                    {(analysis.key_actions ?? []).length ? (
                      <ul>
                        {(analysis.key_actions ?? []).map((action, index) => (
                          <li key={index}>{action.summary?.trim() || "无"}</li>
                        ))}
                      </ul>
                    ) : (
                      <p>无</p>
                    )}
                  </div>
                </section>
                <section className="analysis-result-section results-structure-section">
                  <h3>功能标签</h3>
                  <div className="structure-field" data-testid="structure-field-function_tags">
                    <b>功能标签</b>
                    <p>{formatFunctionTags(analysis.function_tags)}</p>
                  </div>
                </section>
                <section className="analysis-result-section results-structure-section" data-testid="scene-evidence-preview">
                  <h3>证据</h3>
                  {(selected.evidence ?? []).length ? (
                    <div className="analysis-result-evidence-chips">
                      {(selected.evidence ?? []).slice(0, 8).map((item, index) => (
                        <button
                          key={`${item.field_path}-${item.paragraph_id}-${index}`}
                          type="button"
                          className="secondary"
                          data-testid={`structure-evidence-${item.paragraph_id}`}
                          onClick={() => {
                            setTab("evidence");
                            locateEvidence(item.paragraph_id);
                          }}
                        >
                          {item.paragraph_id}
                        </button>
                      ))}
                      <button type="button" className="ghost" onClick={() => setTab("evidence")}>
                        查看全部证据
                      </button>
                    </div>
                  ) : (
                    <p>暂无证据段落</p>
                  )}
                </section>
              </div>
            )}
            <details className="analysis-result-tech results-tech-details" data-testid="scene-tech-details">
              <summary>技术详情</summary>
              <dl className="structure-meta">
                <dt>运行编号</dt>
                <dd>#{run.id}</dd>
                <dt>服务商</dt>
                <dd>{selected.analysis_artifact?.provider || "—"}</dd>
                <dt>模型</dt>
                <dd>{selected.analysis_artifact?.model || "—"}</dd>
                <dt>提示词版本</dt>
                <dd>{selected.analysis_artifact?.prompt_version || "—"}</dd>
                <dt>结果工件</dt>
                <dd>#{selected.analysis_artifact?.id ?? "—"}</dd>
                <dt>分析时间</dt>
                <dd>
                  {selected.analysis_artifact?.created_at
                    ? new Date(selected.analysis_artifact.created_at).toLocaleString()
                    : "无"}
                </dd>
              </dl>
              <pre data-testid="scene-raw-json">
                {JSON.stringify(selected.analysis_artifact?.analysis ?? {}, null, 2)}
              </pre>
            </details>
          </div>
        ) : tab === "evidence" ? (
          <div className="scene-evidence" data-testid="evidence-panel">
            {EVIDENCE_GROUP_LABELS.map(({ group, label }) => {
              const items = (selected.evidence ?? []).filter((e) => e.group === group);
              if (!items.length) return null;
              return (
                <div className="evidence-group" key={group}>
                  <b>{label}</b>
                  {items.map((item) => (
                    <button
                      key={`${item.field_path}-${item.paragraph_id}`}
                      data-testid={`evidence-item-${item.paragraph_id}`}
                      className={`evidence-item ${item.in_scope ? "" : "error"}`}
                      onClick={() => locateEvidence(item.paragraph_id)}
                    >
                      {item.paragraph_id}
                      {!item.in_scope && <span className="danger">超出场景范围</span>}
                    </button>
                  ))}
                </div>
              );
            })}
            {(selected.illegal_evidence ?? []).length > 0 && (
              <div className="notice error" data-testid="evidence-illegal">
                检测到 {selected.illegal_evidence.length} 条超范围/缺失证据
              </div>
            )}
            {!selected.evidence?.length && !(selected.illegal_evidence ?? []).length && (
              <Empty text="该场景暂无证据条目" />
            )}
          </div>
        ) : tab === "history" ? (
          <div className="scene-history" data-testid="history-panel">
            <div className="history-item">
              <b>原始模型 Artifact</b>
              <p>#{selected.analysis_artifact?.id}</p>
              <small>
                {selected.analysis_artifact?.provider} · {selected.analysis_artifact?.model} ·{" "}
                {selected.analysis_artifact?.prompt_version}
              </small>
              {selected.analysis_artifact?.offline_recovered && (
                <Badge tone="warning">离线恢复结果</Badge>
              )}
            </div>
            <dl>
              <dt>Revision编号</dt>
              <dd>#{boundary_revision?.revision_number ?? "-"}</dd>
              <dt>修改时间</dt>
              <dd>
                {selected.analysis_artifact?.created_at
                  ? new Date(selected.analysis_artifact.created_at).toLocaleString()
                  : "无"}
              </dd>
              <dt>确认用户</dt>
              <dd>{boundary_revision?.confirmed_by ?? "无"}</dd>
            </dl>
            {!selected.revision && <p className="muted">暂无人工修订版本（只读结果）。</p>}
          </div>
        ) : tab === "overview" ? (
          <div className="chapter-overview" data-testid="overview-panel">
            <dl className="overview-stats">
              <dt>场景总数</dt>
              <dd>{summary.total_scene_count}</dd>
              <dt>覆盖率</dt>
              <dd>{summary.coverage_rate != null ? `${Math.round(summary.coverage_rate * 100)}%` : "-"}</dd>
              <dt>单段场景</dt>
              <dd>{summary.single_paragraph_scene_count}</dd>
              <dt>最长场景</dt>
              <dd>
                {summary.longest_scene_ordinal != null
                  ? `${formatSceneDisplayLabel({ ordinal: summary.longest_scene_ordinal })}（${summary.longest_scene_paragraph_count}段）`
                  : "-"}
              </dd>
              <dt>人工新增边界</dt>
              <dd>{summary.manual_added_boundary_count}</dd>
              <dt>模型接受边界</dt>
              <dd>{summary.model_accepted_boundary_count}</dd>
              <dt>人工接受冲突</dt>
              <dd>{summary.user_accepted_conflict_count}</dd>
              <dt>证据覆盖率</dt>
              <dd>{Math.round(summary.evidence_coverage_rate * 100)}%</dd>
            </dl>
            <ol className="scene-chain">
              {scenes.map((item) => (
                <li
                  key={item.scene.id}
                  data-testid={`overview-scene-${item.scene.ordinal}`}
                  onClick={() => selectScene(item.scene.id)}
                >
                  <b>
                    {formatSceneDisplayLabel(item.scene)}
                    {item.scene.is_single_paragraph ? "（单段）" : ""}
                  </b>
                  <small>
                    {item.scene.start_paragraph_id} → {item.scene.end_paragraph_id}
                  </small>
                  <span>目标：{fieldSummary(item.analysis_artifact?.analysis.goal)}</span>
                  <span>结果：{fieldSummary(item.analysis_artifact?.analysis.outcome)}</span>
                  <span>
                    悬念：{fieldSummary(item.analysis_artifact?.analysis.unresolved_question)}
                  </span>
                  <small>
                    {formatFunctionTags(item.analysis_artifact?.analysis.function_tags)}
                    {" · "}
                    {formatBoundarySource(item.scene.boundary_source)}
                  </small>
                </li>
              ))}
            </ol>
          </div>
        ) : (
          <>
            {journeyTaskControls}
            {journeyData?.status === "succeeded" && !journeyData.visualization ? (
              <>
                <p data-testid="journey-diagnosis">{journeyData.one_sentence_diagnosis}</p>
                {Array.isArray(journeyData.deterministic_statistics?.journey_nodes) && (
                  <section data-testid="journey-nodes">
                    <h3>旅程节点</h3>
                    <ol>
                      {journeyData.deterministic_statistics.journey_nodes.map((node) => (
                        <li key={node.scene_ordinal}>
                          Scene {node.scene_ordinal} · {node.role} · {node.paragraph_count}段
                          {node.primary_question ? ` · ${node.primary_question}` : ""}
                        </li>
                      ))}
                    </ol>
                  </section>
                )}
                <section data-testid="journey-phases">
                  <h3>阅读阶段（{journeyData.phases.length}）</h3>
                  <ol>
                    {journeyData.phases.map((phase) => (
                      <li key={phase.ordinal}>
                        <b>{phase.title}</b> Scene {phase.start_scene_ordinal}—{phase.end_scene_ordinal}
                        <small>{phase.primary_reader_question}</small>
                      </li>
                    ))}
                  </ol>
                </section>
                <section data-testid="journey-profiles">
                  <h3>Scene Profile（{journeyData.scene_profiles.length}）</h3>
                  {journeyData.scene_profiles.map((profile) => (
                    <article key={profile.scene_id} className="journey-profile-card">
                      <b>Scene {profile.scene_ordinal}</b>
                      <span>engagement {profile.engagement.engagement_score}</span>
                      <p>{profile.scene_value_summary}</p>
                      <small>问题入：{profile.reader_question_in.join("；") || "无"}</small>
                      <small>问题出：{profile.reader_question_out.join("；") || "无"}</small>
                      <small>payoff：{profile.payoffs.join("；") || "无"}</small>
                      <small>hook：{profile.hooks.join("；") || "无"}</small>
                      <small>risk：{profile.risk_points.join("；") || "无"}</small>
                      <small>Evidence：{profile.evidence_paragraph_ids.join(", ") || "无"}</small>
                    </article>
                  ))}
                </section>
                <button
                  data-testid="export-journey-json"
                  onClick={() => exportJourneyJson(journeyData.journey_run_id)}
                >
                  导出旅程JSON
                </button>
              </>
            ) : null}
          </>
        )}
      </aside>
    </section>
  );
}
