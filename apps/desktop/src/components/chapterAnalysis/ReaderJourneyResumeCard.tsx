import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { analysisApi } from "../../services/analysisApi";
import { settingsApi } from "../../services/settingsApi";
import { getOrCreateJourneyClientRequestId } from "../../services/chapterJourneyComposition";
import type { ReaderJourneyPreflight, Run } from "../../types";
import "./chapterAnalysis.css";

type Props = {
  run: Run;
  /** Existing recoverable journey run id, if any. */
  existingJourneyRunId?: number | null;
  onViewSceneAnalysis: () => void;
  onViewTaskDetails: () => void;
  onStarted: (journeyRunId: number) => void;
};

type UsageSnapshot = {
  remaining_requests?: number;
  remaining_tokens?: number;
  remaining_estimated_cost?: number;
};

/**
 * Scene Analysis complete, Reader Journey missing/recoverable.
 * Uses production preflight + create/resume APIs; does not re-run boundary/scene analysis.
 */
export function ReaderJourneyResumeCard({
  run,
  existingJourneyRunId,
  onViewSceneAnalysis,
  onViewTaskDetails,
  onStarted,
}: Props) {
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [preflight, setPreflight] = useState<ReaderJourneyPreflight | null>(null);
  const [preflightLoading, setPreflightLoading] = useState(true);

  const usageQuery = useQuery({
    queryKey: ["cloud-usage"],
    queryFn: settingsApi.cloudUsage,
  });
  const usage = usageQuery.data as UsageSnapshot | undefined;

  useEffect(() => {
    let cancelled = false;
    setPreflightLoading(true);
    void analysisApi
      .readerJourneyPreflight(run.id, { cloud_consent: false })
      .then((data) => {
        if (!cancelled) {
          setPreflight(data);
          setError(undefined);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message || "预算预检失败");
      })
      .finally(() => {
        if (!cancelled) setPreflightLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [run.id]);

  const resumeId =
    existingJourneyRunId || preflight?.existing_journey_run_id || null;
  const withinBudget = preflight?.within_budget !== false;
  const blockers = preflight?.blockers || [];
  const exceeded = preflight?.exceeded_dimensions || [];

  const startOrResume = async () => {
    if (busy) return;
    if (!consent) {
      setError("请先确认云端分析同意后再继续。");
      return;
    }
    if (preflight && !preflight.within_budget) {
      setError(
        `额度不足，无法满足 Reservation。缺口维度：${
          exceeded.length ? exceeded.join("、") : "请求/Token/费用"
        }。请先调整云端预算后再继续生成阅读旅程。`,
      );
      return;
    }
    if (preflight && !preflight.eligible) {
      setError(blockers.join("；") || "当前不满足阅读旅程启动条件。");
      return;
    }
    setBusy(true);
    setError(undefined);
    try {
      const clientRequestId = getOrCreateJourneyClientRequestId(run.id);
      const accepted = resumeId
        ? await analysisApi.resumeReaderJourney(resumeId, {
            client_request_id: clientRequestId,
            cloud_consent: true,
          })
        : await analysisApi.createReaderJourney(run.id, {
            client_request_id: clientRequestId,
            cloud_consent: true,
          });
      if (accepted.creation_blocked_reason && !accepted.journey_run_id) {
        setError(accepted.creation_blocked_reason);
        return;
      }
      onStarted(accepted.journey_run_id);
    } catch (err) {
      setError((err as Error).message || "启动阅读旅程失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      className="reader-journey-resume-card"
      data-testid="reader-journey-resume-card"
      data-run-id={run.id}
    >
      <header>
        <h2 data-testid="reader-journey-resume-title">Scene分析已完成</h2>
        <p data-testid="reader-journey-resume-body">
          阅读旅程尚未生成。可以继续使用当前 Scene 分析结果生成旅程图，不会重新执行场景边界和 Scene
          分析。
        </p>
      </header>

      <dl className="reader-journey-resume-meta" data-testid="reader-journey-resume-meta">
        <div>
          <dt>AnalysisRun</dt>
          <dd>#{run.id}</dd>
        </div>
        <div>
          <dt>Scene Analysis</dt>
          <dd data-testid="reader-journey-resume-scene-count">
            {run.completed_scene_count ?? 0}/{run.total_scene_count ?? 0}
          </dd>
        </div>
        {preflightLoading ? (
          <div>
            <dt>预算预检</dt>
            <dd data-testid="reader-journey-resume-preflight-loading">加载中…</dd>
          </div>
        ) : null}
        {preflight ? (
          <>
            <div>
              <dt>预计请求</dt>
              <dd data-testid="reader-journey-resume-expected-requests">
                {preflight.expected_requests}
                {typeof preflight.worst_case_requests === "number"
                  ? `（最坏 ${preflight.worst_case_requests}）`
                  : ""}
              </dd>
            </div>
            <div>
              <dt>预计 Token</dt>
              <dd data-testid="reader-journey-resume-expected-tokens">
                {preflight.estimated_tokens}
              </dd>
            </div>
            <div>
              <dt>预计费用</dt>
              <dd data-testid="reader-journey-resume-expected-cost">
                {preflight.estimated_cost} {preflight.currency || "CNY"}
              </dd>
            </div>
            <div>
              <dt>当前剩余请求</dt>
              <dd data-testid="reader-journey-resume-remaining-requests">
                {typeof usage?.remaining_requests === "number"
                  ? usage.remaining_requests
                  : "—"}
              </dd>
            </div>
            <div>
              <dt>当前剩余 Token</dt>
              <dd data-testid="reader-journey-resume-remaining-tokens">
                {typeof usage?.remaining_tokens === "number" ? usage.remaining_tokens : "—"}
              </dd>
            </div>
            <div>
              <dt>当前剩余费用</dt>
              <dd data-testid="reader-journey-resume-remaining-cost">
                {typeof usage?.remaining_estimated_cost === "number"
                  ? `${usage.remaining_estimated_cost} CNY`
                  : "—"}
              </dd>
            </div>
            <div>
              <dt>Reservation</dt>
              <dd
                data-testid="reader-journey-resume-within-budget"
                data-ok={withinBudget ? "true" : "false"}
              >
                {withinBudget ? "满足" : "不足"}
                {exceeded.length ? ` · 缺口：${exceeded.join("、")}` : ""}
              </dd>
            </div>
          </>
        ) : null}
      </dl>

      {!withinBudget && preflight && (
        <p className="notice error" data-testid="reader-journey-resume-budget-gap">
          额度不足，请先在设置中调整云端请求/Token/费用限额后再继续。不会创建 ReaderJourneyRun，也不会重跑
          Scene Analysis。
        </p>
      )}

      <label className="reader-journey-resume-consent" data-testid="reader-journey-resume-consent">
        <input
          type="checkbox"
          checked={consent}
          onChange={(e) => setConsent(e.target.checked)}
          data-testid="reader-journey-resume-consent-input"
        />
        我了解将使用当前 AnalysisRun 的云端模型配置生成阅读旅程（不会重新切分 Scene）。
      </label>

      {error && (
        <p className="notice error" data-testid="reader-journey-resume-error">
          {error}
        </p>
      )}

      <div className="reader-journey-resume-actions">
        <button
          type="button"
          className="primary"
          data-testid="reader-journey-resume-continue"
          disabled={busy || preflightLoading || (!!preflight && !withinBudget)}
          onClick={() => void startOrResume()}
        >
          {busy ? "正在启动…" : resumeId ? "继续生成阅读旅程" : "继续生成阅读旅程"}
        </button>
        <button
          type="button"
          className="secondary"
          data-testid="reader-journey-resume-view-scene"
          onClick={onViewSceneAnalysis}
        >
          查看Scene分析
        </button>
        <button
          type="button"
          className="ghost"
          data-testid="reader-journey-resume-task-details"
          onClick={onViewTaskDetails}
        >
          查看任务详情
        </button>
      </div>
    </section>
  );
}
