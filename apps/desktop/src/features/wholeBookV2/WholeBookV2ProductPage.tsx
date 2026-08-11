import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ErrorState, Loading } from "../../components/common/States";
import { ApiError } from "../../services/apiClient";
import { isWholeBookFreeProductEnabled } from "../../services/wholeBookFreeProductFlag";
import { isWholeBookRealProviderEnabled } from "../../services/wholeBookRealProviderFlag";
import { settingsApi } from "../../services/settingsApi";
import {
  compareLimitsToEstimate,
  formatLimitGapsMessage,
  mapWholeBookStartError,
} from "../../services/wholeBookStartLimits";
import {
  newWholeBookClientRequestId,
  wholeBookFreeProductApi,
  type WholeBookPrepareResponse,
  type WholeBookRunRecord,
} from "../../services/wholeBookFreeProductApi";
import { getWholeBookV2, getWholeBookV2Progress } from "./api";
import { V2_PROGRESS_LABELS } from "./contracts";
import { WholeBookV2ReportView } from "./presentation/WholeBookV2ReportView";
import type { ModuleKey } from "./presentation/modules";
import "./formal.css";

const PAGE_TITLE = "全书分析";
const PAGE_DESCRIPTION =
  "从完整原文出发，分析全书总览、故事、人物、悬念、节奏、章节与综合诊断。";
const PREPARE_EXPLANATION =
  "StoryLens 将读取整本小说原文，生成 Whole-Book V2 完整分析报告。分析结果可以回到原文核对。";
const PREPARE_BULLETS = [
  "分析使用您配置的大模型 API；模型费用由模型服务商收取。",
  "原始小说不会上传到 StoryLens 官方服务器。",
  "当前分析以完整原文为事实源，不依赖已有单章分析。",
];
const CONSENT_TEXT = "我已了解本次分析会调用我配置的大模型 API，并可能产生模型费用。";
const REANALYSE_CONSENT_TEXT =
  "我已了解重新分析会调用我配置的大模型 API，并可能产生模型费用。";

type PageMode =
  | "prepare"
  | "reanalyse-confirm"
  | "running"
  | "completed-v2"
  | "legacy"
  | "failed";

type RunningSubview = "progress" | "old-result";

function isActiveRun(status: string | null | undefined): boolean {
  return status === "running" || status === "paused" || status === "recoverable";
}

function isCompletedRun(status: string | null | undefined): boolean {
  return status === "completed";
}

function isFailedRun(status: string | null | undefined): boolean {
  return status === "failed" || status === "cancelled" || status === "canceled";
}

function isLegacyV2Error(err: unknown): boolean {
  if (!(err instanceof ApiError)) return false;
  if (err.status === 404) return true;
  if (err.code === "WHOLE_BOOK_V2_RESULT_NOT_FOUND") return true;
  if (err.message.includes("WHOLE_BOOK_V2")) return true;
  return false;
}

function resolveActiveRun(prepare: WholeBookPrepareResponse): WholeBookRunRecord | null {
  if (prepare.active_run && isActiveRun(prepare.active_run.status)) {
    return prepare.active_run;
  }
  if (prepare.latest_run && isActiveRun(prepare.latest_run.status)) {
    return prepare.latest_run;
  }
  if (prepare.recoverable_run && isActiveRun(prepare.recoverable_run.status)) {
    return prepare.recoverable_run;
  }
  return null;
}

function resolveCompletedV2Run(prepare: WholeBookPrepareResponse): WholeBookRunRecord | null {
  // CHG-084: only backend-gated real_provider completed rows — never fall back to scaffold.
  if (prepare.completed_v2_run && isCompletedRun(prepare.completed_v2_run.status)) {
    return prepare.completed_v2_run;
  }
  return null;
}

function resolveLatestFailedRun(prepare: WholeBookPrepareResponse): WholeBookRunRecord | null {
  if (prepare.latest_failed_run && isFailedRun(prepare.latest_failed_run.status)) {
    return prepare.latest_failed_run;
  }
  if (prepare.latest_run && isFailedRun(prepare.latest_run.status)) {
    return prepare.latest_run;
  }
  return null;
}

function resolveNonRealCompletedRun(prepare: WholeBookPrepareResponse): WholeBookRunRecord | null {
  if (
    prepare.non_real_completed_v2_run &&
    isCompletedRun(prepare.non_real_completed_v2_run.status)
  ) {
    return prepare.non_real_completed_v2_run;
  }
  return null;
}

function ProductUnavailable() {
  return (
    <section className="wbv2-state" data-testid="whole-book-v2-unavailable">
      <h1>{PAGE_TITLE}</h1>
      <p>正式全书分析入口未启用。</p>
      <p className="muted">
        <Link to="/library">返回书库</Link>
      </p>
    </section>
  );
}

type LimitsState = {
  max_provider_calls: string;
  max_input_tokens: string;
  max_output_tokens: string;
  max_cost_budget_cny: string;
};

function LimitsInputs({
  limits,
  onLimitsChange,
  limitGaps,
}: {
  limits: LimitsState;
  onLimitsChange: (next: LimitsState) => void;
  limitGaps: ReturnType<typeof compareLimitsToEstimate>;
}) {
  return (
    <>
      <div className="wbv2-limits">
        <label>
          最大调用次数
          <input
            value={limits.max_provider_calls}
            onChange={(e) => onLimitsChange({ ...limits, max_provider_calls: e.target.value })}
          />
        </label>
        <label>
          最大输入 tokens
          <input
            value={limits.max_input_tokens}
            onChange={(e) => onLimitsChange({ ...limits, max_input_tokens: e.target.value })}
          />
        </label>
        <label>
          最大输出 tokens
          <input
            value={limits.max_output_tokens}
            onChange={(e) => onLimitsChange({ ...limits, max_output_tokens: e.target.value })}
          />
        </label>
        <label>
          费用上限（元）
          <input
            value={limits.max_cost_budget_cny}
            onChange={(e) => onLimitsChange({ ...limits, max_cost_budget_cny: e.target.value })}
          />
        </label>
      </div>
      {limitGaps.length > 0 ? (
        <p className="wbv2-warning">{formatLimitGapsMessage(limitGaps)}</p>
      ) : null}
    </>
  );
}

function PreparePanel({
  prepare,
  consented,
  onConsent,
  canStart,
  starting,
  onStart,
  actionError,
  limits,
  onLimitsChange,
  limitGaps,
}: {
  prepare: WholeBookPrepareResponse;
  consented: boolean;
  onConsent: (v: boolean) => void;
  canStart: boolean;
  starting: boolean;
  onStart: () => void;
  actionError: string | null;
  limits: LimitsState;
  onLimitsChange: (next: LimitsState) => void;
  limitGaps: ReturnType<typeof compareLimitsToEstimate>;
}) {
  const est = prepare.estimate;
  return (
    <section className="wbv2-prepare" data-testid="whole-book-v2-prepare">
      <h2>开始全书分析</h2>
      <p>{PREPARE_EXPLANATION}</p>
      <ul>
        {PREPARE_BULLETS.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      {est ? (
        <p data-testid="whole-book-v2-estimate">
          预估调用 {est.estimated_provider_calls ?? "—"} 次 · 费用{" "}
          {est.estimated_cost_min_cny && est.estimated_cost_max_cny
            ? `约 ¥${est.estimated_cost_min_cny}～¥${est.estimated_cost_max_cny}`
            : "—"}
        </p>
      ) : null}
      <LimitsInputs limits={limits} onLimitsChange={onLimitsChange} limitGaps={limitGaps} />
      <label className="wbv2-consent">
        <input type="checkbox" checked={consented} onChange={(e) => onConsent(e.target.checked)} />
        {CONSENT_TEXT}
      </label>
      {actionError ? <p className="wbv2-error">{actionError}</p> : null}
      <button type="button" disabled={!canStart} onClick={onStart}>
        {starting ? "创建中…" : "开始全书分析"}
      </button>
    </section>
  );
}

function ReanalyseConfirmPanel({
  prepare,
  consented,
  onConsent,
  forceFull,
  onForceFull,
  canConfirm,
  confirming,
  onCancel,
  onConfirm,
  actionError,
  limits,
  onLimitsChange,
  limitGaps,
}: {
  prepare: WholeBookPrepareResponse;
  consented: boolean;
  onConsent: (v: boolean) => void;
  forceFull: boolean;
  onForceFull: (v: boolean) => void;
  canConfirm: boolean;
  confirming: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  actionError: string | null;
  limits: LimitsState;
  onLimitsChange: (next: LimitsState) => void;
  limitGaps: ReturnType<typeof compareLimitsToEstimate>;
}) {
  const est = prepare.estimate;
  const provider = est?.provider_name ?? prepare.active_provider_name ?? "—";
  const model = est?.model_name ?? prepare.active_model_name ?? "—";

  return (
    <section className="wbv2-reanalyse-confirm" data-testid="whole-book-v2-reanalyse-confirm">
      <h2>确认重新分析 V2</h2>
      <p>
        重新分析会创建新的 V2 分析任务。当前分析结果不会立即删除。新分析成功后将显示最新结果。
      </p>
      <dl className="wbv2-reanalyse-meta">
        <div>
          <dt>模型服务商</dt>
          <dd>{provider}</dd>
        </div>
        <div>
          <dt>模型</dt>
          <dd>{model}</dd>
        </div>
        <div>
          <dt>章节</dt>
          <dd>{prepare.chapter_count}</dd>
        </div>
        <div>
          <dt>字数</dt>
          <dd>{prepare.character_count.toLocaleString()}</dd>
        </div>
        {est ? (
          <>
            <div>
              <dt>预计窗口</dt>
              <dd>{est.estimated_windows ?? "—"}</dd>
            </div>
            <div>
              <dt>预计调用</dt>
              <dd>{est.estimated_provider_calls ?? "—"}</dd>
            </div>
            <div>
              <dt>预计 tokens</dt>
              <dd>
                {est.estimated_input_tokens ?? "—"} 输入 / {est.estimated_output_tokens ?? "—"} 输出
              </dd>
            </div>
            <div>
              <dt>预计费用</dt>
              <dd>
                {est.estimated_cost_min_cny && est.estimated_cost_max_cny
                  ? `约 ¥${est.estimated_cost_min_cny}～¥${est.estimated_cost_max_cny}`
                  : "—"}
              </dd>
            </div>
          </>
        ) : null}
        {prepare.context_safe != null ? (
          <div>
            <dt>上下文安全</dt>
            <dd>{prepare.context_safe ? "是" : "否"}</dd>
          </div>
        ) : null}
      </dl>
      <LimitsInputs limits={limits} onLimitsChange={onLimitsChange} limitGaps={limitGaps} />
      <label className="wbv2-consent">
        <input
          type="checkbox"
          data-testid="whole-book-v2-force-full"
          checked={forceFull}
          onChange={(e) => onForceFull(e.target.checked)}
        />
        强制重新分析全部 AI 中间结果
      </label>
      <label className="wbv2-consent">
        <input type="checkbox" checked={consented} onChange={(e) => onConsent(e.target.checked)} />
        {REANALYSE_CONSENT_TEXT}
      </label>
      {actionError ? <p className="wbv2-error">{actionError}</p> : null}
      <div className="wbv2-reanalyse-actions">
        <button type="button" className="wbv2-btn-secondary" onClick={onCancel} disabled={confirming}>
          取消
        </button>
        <button type="button" disabled={!canConfirm} onClick={onConfirm}>
          {confirming ? "创建任务中…" : "确认开始重新分析"}
        </button>
      </div>
    </section>
  );
}

function ProgressPanel({ runId }: { runId: number }) {
  const progressQuery = useQuery({
    queryKey: ["whole-book-v2-progress", runId],
    queryFn: () => getWholeBookV2Progress(runId),
    refetchInterval: 2000,
  });

  if (progressQuery.isLoading) {
    return (
      <section className="wbv2-state">
        <h1>读取 V2 进度…</h1>
        <Loading />
      </section>
    );
  }
  if (progressQuery.isError || !progressQuery.data) {
    return <ErrorState error={progressQuery.error ?? new Error("进度不可用")} />;
  }

  const p = progressQuery.data;
  const stageLabel = V2_PROGRESS_LABELS[p.current_stage] || p.current_action;

  return (
    <section className="wbv2-state" data-testid="whole-book-v2-progress">
      <h1>{p.overall_percent.toFixed(0)}%</h1>
      <p>
        {stageLabel} · 阶段 {p.stage_percent.toFixed(0)}%
      </p>
      <p>{p.current_action}</p>
      <p>
        第 {p.current_chapter}/{p.total_chapters} 章 · 窗口 {p.current_window}/{p.total_windows}
      </p>
      <p>
        调用 {p.provider_calls_completed}/{p.provider_calls_estimated} · 已用 {p.elapsed_seconds}s
        {p.estimated_remaining_seconds > 0 ? ` · 预计剩余 ${p.estimated_remaining_seconds}s` : ""}
      </p>
      <p>
        {p.provider} · {p.model}
      </p>
    </section>
  );
}

function RunningWithOldBanner({
  subview,
  onSubviewChange,
}: {
  subview: RunningSubview;
  onSubviewChange: (v: RunningSubview) => void;
}) {
  return (
    <div className="wbv2-reanalyse-running-banner" data-testid="whole-book-v2-reanalyse-running-banner">
      <p>新的 V2 分析正在进行</p>
      <div className="wbv2-reanalyse-running-actions">
        <button
          type="button"
          className={subview === "progress" ? "active" : ""}
          onClick={() => onSubviewChange("progress")}
        >
          查看分析进度
        </button>
        <button
          type="button"
          className={subview === "old-result" ? "active" : ""}
          onClick={() => onSubviewChange("old-result")}
        >
          查看当前旧结果
        </button>
      </div>
    </div>
  );
}

function LegacyNotice({ onReanalyze }: { onReanalyze: () => void }) {
  return (
    <section className="wbv2-state wbv2-legacy" data-testid="whole-book-v2-legacy-notice">
      <h1>旧版分析结果</h1>
      <p>这是旧版全书分析结果，需要重新分析以生成 V2 完整结果。</p>
      <button type="button" onClick={onReanalyze}>
        重新分析
      </button>
    </section>
  );
}

function WholeBookV2ProductPageEnabled() {
  const { bookId: bookIdParam } = useParams();
  const bookId = Number(bookIdParam);
  const queryClient = useQueryClient();
  const realProviderFlagOn = isWholeBookRealProviderEnabled();
  const [activeModule, setActiveModule] = useState<ModuleKey>("overview");
  const [consented, setConsented] = useState(false);
  const [reanalyseConsented, setReanalyseConsented] = useState(false);
  const [forceFullReanalysis, setForceFullReanalysis] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [modeOverride, setModeOverride] = useState<PageMode | null>(null);
  const [runningSubview, setRunningSubview] = useState<RunningSubview>("progress");
  const [limits, setLimits] = useState<LimitsState>({
    max_provider_calls: "",
    max_input_tokens: "",
    max_output_tokens: "",
    max_cost_budget_cny: "",
  });
  const createRequestIdRef = useRef<string | null>(null);
  const reanalysePreviousRunIdRef = useRef<number | null>(null);

  const activeCloudQuery = useQuery({
    queryKey: ["active-cloud-provider"],
    queryFn: settingsApi.activeCloudProvider,
    refetchOnMount: "always",
    staleTime: 0,
  });
  const activeProviderName = activeCloudQuery.data?.provider_name ?? "unknown";

  const prepareQuery = useQuery({
    queryKey: ["whole-book-v2-prepare", bookId, activeProviderName],
    queryFn: () => wholeBookFreeProductApi.prepare(bookId),
    enabled: bookId > 0 && Boolean(activeCloudQuery.data?.provider_name),
    retry: false,
    refetchInterval: (query) => {
      const prepare = query.state.data;
      if (!prepare) return false;
      const active = resolveActiveRun(prepare);
      return active ? 3000 : false;
    },
  });

  const prepare = prepareQuery.data;
  const activeRun = prepare ? resolveActiveRun(prepare) : null;
  const completedV2Run = prepare ? resolveCompletedV2Run(prepare) : null;
  const latestFailedRun = prepare ? resolveLatestFailedRun(prepare) : null;
  const nonRealCompletedRun = prepare ? resolveNonRealCompletedRun(prepare) : null;
  const activeRunId = activeRun?.run_id ?? null;
  const displayV2RunId =
    completedV2Run?.run_id ??
    (latestFailedRun ? nonRealCompletedRun?.run_id ?? null : nonRealCompletedRun?.run_id ?? null);
  const hasOldResultWhileRunning = activeRunId != null && displayV2RunId != null;

  const v2ResultQuery = useQuery({
    queryKey: ["whole-book-v2-result", displayV2RunId],
    queryFn: () => getWholeBookV2(displayV2RunId!),
    enabled: displayV2RunId != null,
    retry: false,
  });

  const invalidateAll = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ["whole-book-v2-prepare", bookId] });
    if (displayV2RunId != null) {
      await queryClient.invalidateQueries({ queryKey: ["whole-book-v2-result", displayV2RunId] });
    }
    if (activeRunId != null) {
      await queryClient.invalidateQueries({ queryKey: ["whole-book-v2-progress", activeRunId] });
    }
  }, [activeRunId, bookId, displayV2RunId, queryClient]);

  const createMutation = useMutation({
    mutationFn: (opts?: { reanalyse?: boolean; previousRunId?: number | null }) => {
      createRequestIdRef.current = newWholeBookClientRequestId("wb-v2");
      const isReanalyse = Boolean(opts?.reanalyse);
      return wholeBookFreeProductApi.createRun(bookId, {
        client_request_id: createRequestIdRef.current,
        estimate_id: prepareQuery.data?.estimate?.estimate_id ?? null,
        max_provider_calls: limits.max_provider_calls ? Number(limits.max_provider_calls) : null,
        max_input_tokens: limits.max_input_tokens ? Number(limits.max_input_tokens) : null,
        max_output_tokens: limits.max_output_tokens ? Number(limits.max_output_tokens) : null,
        max_cost_budget_cny: limits.max_cost_budget_cny || null,
        reanalyse: isReanalyse,
        force_full_reanalysis: isReanalyse ? forceFullReanalysis : false,
        previous_run_id: isReanalyse ? (opts?.previousRunId ?? null) : null,
      });
    },
    onSuccess: () => {
      createRequestIdRef.current = null;
      reanalysePreviousRunIdRef.current = null;
      setActionError(null);
      setModeOverride(null);
      setRunningSubview("progress");
      setReanalyseConsented(false);
      setForceFullReanalysis(false);
      void invalidateAll();
    },
    onError: (err) => {
      createRequestIdRef.current = null;
      if (err instanceof ApiError) {
        setActionError(mapWholeBookStartError(err.code, err.message, err.detail));
        return;
      }
      setActionError("创建分析任务失败");
    },
  });

  const resumeMutation = useMutation({
    mutationFn: (runId: number) => wholeBookFreeProductApi.resumeFailedRun(bookId, runId),
    onSuccess: () => {
      setActionError(null);
      setModeOverride(null);
      setRunningSubview("progress");
      void invalidateAll();
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setActionError(mapWholeBookStartError(err.code, err.message, err.detail));
        return;
      }
      setActionError("继续分析失败");
    },
  });

  useEffect(() => {
    const rec = prepareQuery.data?.recommended_limits;
    if (!rec) return;
    setLimits((prev) => ({
      max_provider_calls:
        prev.max_provider_calls || (rec.max_provider_calls != null ? String(rec.max_provider_calls) : ""),
      max_input_tokens:
        prev.max_input_tokens || (rec.max_input_tokens != null ? String(rec.max_input_tokens) : ""),
      max_output_tokens:
        prev.max_output_tokens || (rec.max_output_tokens != null ? String(rec.max_output_tokens) : ""),
      max_cost_budget_cny: prev.max_cost_budget_cny || rec.max_cost_budget_cny || "10.00",
    }));
  }, [prepareQuery.data?.recommended_limits]);

  useEffect(() => {
    if (!activeRun && modeOverride === null) {
      setRunningSubview("progress");
    }
  }, [activeRun, modeOverride]);

  if (bookId <= 0) {
    return <ErrorState error={new Error("无效的书籍 ID")} />;
  }

  if (prepareQuery.isLoading || activeCloudQuery.isLoading) {
    return (
      <section className="wbv2-state" data-testid="whole-book-v2-formal-page">
        <h1>准备全书分析…</h1>
        <Loading />
      </section>
    );
  }

  if (prepareQuery.isError) {
    const err = prepareQuery.error;
    const offline =
      err instanceof ApiError &&
      (err.code === "BACKEND_OFFLINE" || /无法连接本地分析服务/.test(err.message));
    return (
      <ErrorState
        error={
          offline
            ? new Error("本地分析服务暂时不可用。请点击重新连接。")
            : err instanceof Error
              ? err
              : new Error("准备失败")
        }
        retry={() => void prepareQuery.refetch()}
      />
    );
  }

  if (!prepare) {
    return <ErrorState error={new Error("准备数据不可用")} />;
  }

  const pageMode: PageMode = (() => {
    if (modeOverride === "reanalyse-confirm") return "reanalyse-confirm";
    if (activeRun) {
      if (isFailedRun(activeRun.status)) return "failed";
      return "running";
    }
    // New run failed → never auto-restore scaffold as "分析完成".
    if (latestFailedRun && !completedV2Run) return "failed";
    if (!completedV2Run && !activeRun && !nonRealCompletedRun) return "prepare";
    if (completedV2Run) {
      if (v2ResultQuery.isSuccess && v2ResultQuery.data) return "completed-v2";
      if (v2ResultQuery.isError && isLegacyV2Error(v2ResultQuery.error)) return "legacy";
      if (v2ResultQuery.isLoading || v2ResultQuery.isFetching) return "completed-v2";
      if (v2ResultQuery.isError) return "failed";
      return "legacy";
    }
    if (nonRealCompletedRun) return "legacy";
    return "prepare";
  })();

  const limitGaps = compareLimitsToEstimate(prepare.estimate, limits);
  const canStart =
    consented &&
    realProviderFlagOn &&
    Boolean(prepare.run_creation_enabled) &&
    Boolean(prepare.provider_available !== false) &&
    limitGaps.length === 0 &&
    !createMutation.isPending;

  const canConfirmReanalyse =
    reanalyseConsented &&
    realProviderFlagOn &&
    Boolean(prepare.run_creation_enabled) &&
    Boolean(prepare.provider_available !== false) &&
    limitGaps.length === 0 &&
    !createMutation.isPending;

  const resumable = prepare.resumable_checkpoint;
  const canResumeFailed =
    Boolean(resumable?.can_resume) &&
    Boolean(resumable?.run_id) &&
    realProviderFlagOn &&
    !resumeMutation.isPending &&
    !createMutation.isPending;

  const openReanalyseConfirm = () => {
    setActionError(null);
    setReanalyseConsented(false);
    setForceFullReanalysis(false);
    setModeOverride("reanalyse-confirm");
  };

  const cancelReanalyseConfirm = () => {
    setActionError(null);
    setModeOverride(null);
  };

  const confirmReanalyse = () => {
    const previousRunId =
      completedV2Run?.run_id ?? nonRealCompletedRun?.run_id ?? displayV2RunId;
    reanalysePreviousRunIdRef.current = previousRunId;
    createMutation.mutate({ reanalyse: true, previousRunId });
  };

  const showRunningProgress =
    pageMode === "running" && (runningSubview === "progress" || !hasOldResultWhileRunning);
  const showOldResultWhileRunning =
    pageMode === "running" && hasOldResultWhileRunning && runningSubview === "old-result";

  return (
    <div className="wbv2-product" data-testid="whole-book-v2-formal-page">
      <header className="wbv2-product-header">
        <p className="muted">
          <Link to={`/books/${bookId}`}>← 返回书籍</Link>
        </p>
        <h1>{PAGE_TITLE}</h1>
        <p className="muted">{PAGE_DESCRIPTION}</p>
        <p>
          {prepare.book_title} · {prepare.chapter_count} 章 · {prepare.character_count} 字
        </p>
      </header>

      {pageMode === "prepare" && (
        <PreparePanel
          prepare={prepare}
          consented={consented}
          onConsent={setConsented}
          canStart={canStart}
          starting={createMutation.isPending}
          onStart={() => createMutation.mutate(undefined)}
          actionError={actionError}
          limits={limits}
          onLimitsChange={setLimits}
          limitGaps={limitGaps}
        />
      )}

      {pageMode === "reanalyse-confirm" && (
        <ReanalyseConfirmPanel
          prepare={prepare}
          consented={reanalyseConsented}
          onConsent={setReanalyseConsented}
          forceFull={forceFullReanalysis}
          onForceFull={setForceFullReanalysis}
          canConfirm={canConfirmReanalyse}
          confirming={createMutation.isPending}
          onCancel={cancelReanalyseConfirm}
          onConfirm={confirmReanalyse}
          actionError={actionError}
          limits={limits}
          onLimitsChange={setLimits}
          limitGaps={limitGaps}
        />
      )}

      {pageMode === "running" && hasOldResultWhileRunning && (
        <RunningWithOldBanner subview={runningSubview} onSubviewChange={setRunningSubview} />
      )}

      {showRunningProgress && activeRunId != null && <ProgressPanel runId={activeRunId} />}

      {pageMode === "legacy" && <LegacyNotice onReanalyze={openReanalyseConfirm} />}

      {pageMode === "failed" && (
        <section className="wbv2-state" data-testid="whole-book-v2-failed">
          <h1>分析失败</h1>
          <p>
            阶段：{latestFailedRun?.current_stage_code || activeRun?.current_stage_code || "—"}
          </p>
          <p>
            错误码：
            {latestFailedRun?.failure_code ||
              activeRun?.failure_code ||
              (v2ResultQuery.error instanceof ApiError ? v2ResultQuery.error.code : null) ||
              "—"}
          </p>
          <p>
            {latestFailedRun?.failure_message_safe ||
              activeRun?.failure_message_safe ||
              (v2ResultQuery.error instanceof Error
                ? v2ResultQuery.error.message
                : "全书分析任务失败，可重新分析。")}
          </p>
          {canResumeFailed && (
            <>
              <p className="muted" data-testid="whole-book-v2-resume-hint">
                {resumable?.message ||
                  `已完成 ${resumable?.completed_windows ?? "—"}/${resumable?.total_windows ?? "—"} 个分析窗口，将从失败阶段继续，不会重复已成功的窗口调用。`}
              </p>
              <button
                type="button"
                data-testid="whole-book-v2-resume"
                disabled={resumeMutation.isPending}
                onClick={() => resumeMutation.mutate(Number(resumable!.run_id))}
              >
                {resumeMutation.isPending ? "继续中…" : "继续分析"}
              </button>
            </>
          )}
          <button type="button" onClick={openReanalyseConfirm}>
            {canResumeFailed ? "重新分析全部" : "重新分析"}
          </button>
          {actionError && <p className="wbv2-error">{actionError}</p>}
        </section>
      )}

      {(pageMode === "completed-v2" || showOldResultWhileRunning) && v2ResultQuery.data && (
        <WholeBookV2ReportView
          data={v2ResultQuery.data}
          activeModule={activeModule}
          onModuleChange={setActiveModule}
          mode="formal"
          bookId={bookId}
          showReanalyzeButton={pageMode === "completed-v2" && !activeRun}
          onReanalyzeClick={openReanalyseConfirm}
          analysisStatusLabel={showOldResultWhileRunning ? "当前旧结果" : undefined}
        />
      )}

      {(pageMode === "completed-v2" || showOldResultWhileRunning) &&
        !v2ResultQuery.data &&
        v2ResultQuery.isLoading && (
          <section className="wbv2-state">
            <h1>加载 V2 报告…</h1>
            <Loading />
          </section>
        )}

      {pageMode === "failed" && (completedV2Run || nonRealCompletedRun) && v2ResultQuery.data && (
        <WholeBookV2ReportView
          data={v2ResultQuery.data}
          activeModule={activeModule}
          onModuleChange={setActiveModule}
          mode="formal"
          bookId={bookId}
          showReanalyzeButton
          onReanalyzeClick={openReanalyseConfirm}
          analysisStatusLabel="当前旧结果"
          headerBanner={
            <div className="wbv2-error-banner">
              {nonRealCompletedRun && !completedV2Run
                ? "最新分析失败。当前旧结果不是完整真实 V2 分析，需要重新分析。"
                : "新的分析任务失败。您可以查看当前旧结果，或再次尝试重新分析。"}
            </div>
          }
        />
      )}
    </div>
  );
}

export function WholeBookV2ProductPage() {
  if (!isWholeBookFreeProductEnabled()) {
    return <ProductUnavailable />;
  }
  return <WholeBookV2ProductPageEnabled />;
}
