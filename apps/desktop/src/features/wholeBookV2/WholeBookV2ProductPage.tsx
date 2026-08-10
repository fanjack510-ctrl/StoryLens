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

function isActiveRun(status: string | null | undefined): boolean {
  return status === "running" || status === "paused" || status === "recoverable";
}

function isCompletedRun(status: string | null | undefined): boolean {
  return status === "completed";
}

function isLegacyV2Error(err: unknown): boolean {
  if (!(err instanceof ApiError)) return false;
  if (err.status === 404) return true;
  if (err.code === "WHOLE_BOOK_V2_RESULT_NOT_FOUND") return true;
  if (err.message.includes("WHOLE_BOOK_V2")) return true;
  return false;
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
  limits: {
    max_provider_calls: string;
    max_input_tokens: string;
    max_output_tokens: string;
    max_cost_budget_cny: string;
  };
  onLimitsChange: (next: typeof limits) => void;
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
      <div className="wbv2-limits">
        <label>
          最大调用次数
          <input
            value={limits.max_provider_calls}
            onChange={(e) => onLimitsChange({ ...limits, max_provider_calls: e.target.value })}
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
  const [actionError, setActionError] = useState<string | null>(null);
  const [limits, setLimits] = useState({
    max_provider_calls: "",
    max_input_tokens: "",
    max_output_tokens: "",
    max_cost_budget_cny: "",
  });
  const createRequestIdRef = useRef<string | null>(null);

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
      const run = query.state.data?.latest_run;
      return run && isActiveRun(run.status) ? 3000 : false;
    },
  });

  const runId =
    prepareQuery.data?.latest_run?.run_id ?? prepareQuery.data?.recoverable_run?.run_id ?? null;
  const runStatus =
    prepareQuery.data?.latest_run?.status ?? prepareQuery.data?.recoverable_run?.status;

  const v2ResultQuery = useQuery({
    queryKey: ["whole-book-v2-result", runId],
    queryFn: () => getWholeBookV2(runId!),
    enabled: runId != null && isCompletedRun(runStatus),
    retry: false,
  });

  const invalidateAll = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ["whole-book-v2-prepare", bookId] });
    if (runId != null) {
      await queryClient.invalidateQueries({ queryKey: ["whole-book-v2-result", runId] });
      await queryClient.invalidateQueries({ queryKey: ["whole-book-v2-progress", runId] });
    }
  }, [bookId, queryClient, runId]);

  const createMutation = useMutation({
    mutationFn: () => {
      if (!createRequestIdRef.current) {
        createRequestIdRef.current = newWholeBookClientRequestId("wb-v2");
      }
      return wholeBookFreeProductApi.createRun(bookId, {
        client_request_id: createRequestIdRef.current,
        estimate_id: prepareQuery.data?.estimate?.estimate_id ?? null,
        max_provider_calls: limits.max_provider_calls ? Number(limits.max_provider_calls) : null,
        max_input_tokens: limits.max_input_tokens ? Number(limits.max_input_tokens) : null,
        max_output_tokens: limits.max_output_tokens ? Number(limits.max_output_tokens) : null,
        max_cost_budget_cny: limits.max_cost_budget_cny || null,
      });
    },
    onSuccess: () => {
      createRequestIdRef.current = null;
      setActionError(null);
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
    return (
      <ErrorState
        error={prepareQuery.error instanceof Error ? prepareQuery.error : new Error("准备失败")}
        retry={() => void prepareQuery.refetch()}
      />
    );
  }

  const prepare = prepareQuery.data;
  if (!prepare) {
    return <ErrorState error={new Error("准备数据不可用")} />;
  }

  const run = prepare.latest_run ?? prepare.recoverable_run ?? null;
  const pageMode: "prepare" | "running" | "completed-v2" | "legacy" | "failed" = (() => {
    if (!run) return "prepare";
    if (isCompletedRun(run.status)) {
      if (v2ResultQuery.isSuccess && v2ResultQuery.data) return "completed-v2";
      if (v2ResultQuery.isError && isLegacyV2Error(v2ResultQuery.error)) return "legacy";
      if (v2ResultQuery.isLoading || v2ResultQuery.isFetching) return "completed-v2";
      if (v2ResultQuery.isError) return "failed";
      return "legacy";
    }
    if (run.status === "failed" || run.status === "cancelled" || run.status === "canceled") {
      return "failed";
    }
    return "running";
  })();

  const limitGaps = compareLimitsToEstimate(prepare.estimate, limits);
  const canStart =
    consented &&
    realProviderFlagOn &&
    Boolean(prepare.run_creation_enabled) &&
    Boolean(prepare.provider_available !== false) &&
    limitGaps.length === 0 &&
    !createMutation.isPending;

  const handleReanalyze = () => {
    void queryClient.resetQueries({ queryKey: ["whole-book-v2-result", runId] });
    void prepareQuery.refetch();
    createMutation.mutate();
  };

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
          onStart={() => createMutation.mutate()}
          actionError={actionError}
          limits={limits}
          onLimitsChange={setLimits}
          limitGaps={limitGaps}
        />
      )}

      {pageMode === "running" && runId != null && <ProgressPanel runId={runId} />}

      {pageMode === "legacy" && (
        <LegacyNotice onReanalyze={() => void handleReanalyze()} />
      )}

      {pageMode === "failed" && (
        <ErrorState
          error={
            v2ResultQuery.error instanceof Error
              ? v2ResultQuery.error
              : new Error(run?.status === "failed" ? "分析任务失败" : "无法加载 V2 结果")
          }
          retry={() => void prepareQuery.refetch()}
        />
      )}

      {pageMode === "completed-v2" && v2ResultQuery.data && (
        <WholeBookV2ReportView
          data={v2ResultQuery.data}
          activeModule={activeModule}
          onModuleChange={setActiveModule}
          mode="formal"
          bookId={bookId}
          onReanalyze={() => void handleReanalyze()}
        />
      )}

      {pageMode === "completed-v2" && !v2ResultQuery.data && v2ResultQuery.isLoading && (
        <section className="wbv2-state">
          <h1>加载 V2 报告…</h1>
          <Loading />
        </section>
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
