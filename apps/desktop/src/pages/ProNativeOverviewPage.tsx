import { useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ErrorState, Loading } from "../components/common/States";
import { ProNativeOverviewResult } from "../components/proNativeOverview/ProNativeOverviewResult";
import { ApiError } from "../services/apiClient";
import { booksApi } from "../services/booksApi";
import {
  newClientRequestId,
  proNativeOverviewApi,
  resolveCreateBinding,
  type PreflightBlockingError,
  type ProNativeOverviewPreflight,
  type RunStatusResponse,
} from "../services/proNativeOverviewApi";
import {
  isProNativeOverviewUiEnabled,
  resolveEnginePresentation,
  WALKING_SKELETON_USER_NOTICE,
  type EnginePresentation,
} from "../services/proNativeOverviewFlag";
import {
  buildStageList,
  overviewStageLabel,
} from "../services/proNativeOverviewStages";

const PAGE_TITLE = "原生全书概览";
const PAGE_SUBTITLE =
  "直接分析完整小说原文，不需要提前完成全部单章分析。StoryLens 功能免费；第三方模型 API 费用由用户账户承担。";
const MODE_LABEL = "原生整书";

function blockingMessage(item: PreflightBlockingError | string): string {
  if (typeof item === "string") return item;
  if (item.code && item.message) return `${item.code}：${item.message}`;
  return item.message || item.code || "阻塞错误";
}

function formatMoney(value: number | null | undefined, currency = "CNY"): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return `${Number(value).toFixed(4)} ${currency}`;
}

function formatTokens(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return String(value);
}

function mapUiErrorCode(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === "BACKEND_OFFLINE" || error.status === 0) return "API_UNAVAILABLE";
    if (error.code === "PRO_LICENSE_REQUIRED") return "PRO_REQUIRED";
    if (error.code === "BOOK_CONTENT_EMPTY") return "BOOK_EMPTY";
    if (
      error.code.includes("DISABLED") ||
      error.code === "FEATURE_DISABLED" ||
      error.status === 404
    ) {
      return error.code.includes("DISABLED") || error.code === "FEATURE_DISABLED"
        ? "FEATURE_DISABLED"
        : error.code;
    }
    // Preserve frozen overview wire codes for recovery UI (STEP 2.4).
    if (
      error.code.startsWith("PROVIDER_") ||
      error.code.startsWith("PRIVATE_ENGINE_") ||
      error.code === "EVIDENCE_INVALID" ||
      error.code === "CITATION_INVALID" ||
      error.code === "MATERIALIZATION_FAILED" ||
      error.code === "RUN_FAILED" ||
      error.code === "SNAPSHOT_CHANGED"
    ) {
      return error.code;
    }
    return error.code || "HTTP_ERROR";
  }
  if (error instanceof Error && /fetch|network|Failed to fetch/i.test(error.message)) {
    return "API_UNAVAILABLE";
  }
  return "UNKNOWN";
}

function ErrorPanel({
  code,
  message,
  onRetry,
}: {
  code: string;
  message: string;
  onRetry?: () => void;
}) {
  const titles: Record<string, string> = {
    PRO_REQUIRED: "需要 Pro 授权",
    FEATURE_DISABLED: "功能未启用",
    BOOK_EMPTY: "书籍内容为空",
    RUN_FAILED: "运行失败",
    OVERVIEW_NOT_READY: "概览尚未就绪",
    EVIDENCE_MISSING: "缺少证据",
    EVIDENCE_INVALID: "证据无效",
    CITATION_INVALID: "引用无效",
    MATERIALIZATION_FAILED: "结果落库失败",
    API_UNAVAILABLE: "分析服务不可用",
    PROVIDER_TIMEOUT: "模型响应超时",
    PROVIDER_RATE_LIMITED: "模型请求过于频繁",
    PROVIDER_UNAVAILABLE: "模型服务暂不可用",
    PROVIDER_OUTPUT_INVALID: "模型输出无法解析",
    PROVIDER_OUTPUT_EMPTY: "模型返回为空",
    PROVIDER_NOT_CONFIGURED: "尚未配置模型",
    PRIVATE_ENGINE_UNAVAILABLE: "分析引擎不可用",
    PRIVATE_ENGINE_INCOMPATIBLE: "分析引擎不兼容",
    SNAPSHOT_CHANGED: "书籍内容已变更",
  };
  return (
    <section
      className="notice"
      data-testid="pro-native-overview-error"
      data-error-code={code}
    >
      <h2>{titles[code] || "出错了"}</h2>
      <p>{message}</p>
      <p className="muted">错误码：{code}</p>
      {onRetry ? (
        <button type="button" className="secondary" data-testid="pro-native-overview-retry" onClick={onRetry}>
          重试
        </button>
      ) : null}
    </section>
  );
}

function EngineBadge({ engine }: { engine: EnginePresentation }) {
  return (
    <span
      data-testid="pro-native-overview-engine-badge"
      data-engine-kind={engine.kind}
    >
      {engine.label}
      {engine.engineId ? `（${engine.engineId}）` : ""}
    </span>
  );
}

function PreflightPanel({
  preflight,
  starting,
  onStart,
  startError,
}: {
  preflight: ProNativeOverviewPreflight;
  starting: boolean;
  onStart: () => void;
  startError: string | null;
}) {
  const [consented, setConsented] = useState(false);
  const binding = resolveCreateBinding(preflight);
  const engine = binding.engine;
  const currency = preflight.currency || "CNY";
  const blocking = preflight.blocking_errors || [];
  const canStart =
    blocking.length === 0 &&
    preflight.license_allowed !== false &&
    (preflight.paragraph_count ?? 0) > 0 &&
    consented;

  return (
    <section data-testid="pro-native-overview-preflight">
      <h2>启动前检查</h2>
      <ul>
        <li>章节数：{preflight.chapter_count}</li>
        <li>段落数：{preflight.paragraph_count}</li>
        <li>字符数：{preflight.character_count}</li>
        <li data-testid="pro-native-overview-preflight-windows">
          预估窗口：{preflight.estimated_windows ?? 0}
        </li>
        <li data-testid="pro-native-overview-preflight-tokens">
          预估 Token：{formatTokens(preflight.estimated_tokens)}
        </li>
        <li data-testid="pro-native-overview-preflight-cost">
          预估费用：{formatMoney(preflight.estimated_cost, currency)}
        </li>
        <li data-testid="pro-native-overview-preflight-provider">
          Provider：{binding.provider_id}
          {preflight.provider_configured === false ? "（未配置）" : ""}
        </li>
        <li data-testid="pro-native-overview-preflight-model">
          Model：{binding.model_id}
        </li>
        <li>模式：{MODE_LABEL}</li>
        <li data-testid="pro-native-overview-preflight-engine">
          Engine：<EngineBadge engine={engine} />
        </li>
        <li>
          授权：
          {preflight.license_allowed ? "已允许（Pro）" : "未授权 / 不允许"}
        </li>
      </ul>

      {engine.isFixture ? (
        <p className="notice" data-testid="pro-native-overview-walking-notice">
          {WALKING_SKELETON_USER_NOTICE}
        </p>
      ) : (
        <p className="notice" data-testid="pro-native-overview-formal-notice">
          当前绑定正式概览引擎，将按 Provider/Model 执行（非 Fixture 开发模式）。
        </p>
      )}

      {preflight.warnings?.length ? (
        <div data-testid="pro-native-overview-warnings">
          <h3>警告</h3>
          <ul>
            {preflight.warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {blocking.length ? (
        <div data-testid="pro-native-overview-blocking-errors">
          <h3>阻塞错误</h3>
          <ul>
            {blocking.map((item, index) => (
              <li key={index}>{blockingMessage(item)}</li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="muted">无阻塞错误</p>
      )}

      <label className="consent" data-testid="pro-native-overview-consent">
        <input
          type="checkbox"
          checked={consented}
          data-testid="pro-native-overview-consent-checkbox"
          onChange={(event) => setConsented(event.target.checked)}
        />
        <span>
          我确认启动「原生全书概览」，并了解预估 Token（
          {formatTokens(preflight.estimated_tokens)}）与费用（
          {formatMoney(preflight.estimated_cost, currency)}）将由第三方模型
          Provider 账户承担，以及当前 Engine 为 {engine.label}。
        </span>
      </label>

      {startError ? <p data-testid="pro-native-overview-start-error">{startError}</p> : null}
      <button
        type="button"
        className="primary"
        data-testid="pro-native-overview-start"
        disabled={!canStart || starting}
        onClick={onStart}
      >
        {starting ? "启动中…" : "开始原生全书概览"}
      </button>
    </section>
  );
}

function ProgressPanel({
  run,
  runId,
  onRefresh,
  onRetry,
  onResume,
  actionPending,
  actionError,
}: {
  run: RunStatusResponse;
  runId: string;
  onRefresh: () => void;
  onRetry: () => void;
  onResume: () => void;
  actionPending: boolean;
  actionError: string | null;
}) {
  const stages = buildStageList(run.current_stage, run.status);
  const currency = run.currency || "CNY";
  const engine = resolveEnginePresentation(run.engine_id, run.model);
  const completedWindows = run.progress?.completed_windows ?? 0;
  const totalWindows = run.progress?.total_windows ?? 0;
  const canRetry =
    Boolean(run.actions?.can_retry) || (run.status === "failed" && Boolean(run.retryable));
  const canResume =
    Boolean(run.actions?.can_resume) || run.status === "paused";

  return (
    <section data-testid="pro-native-overview-progress">
      <h2>运行进度</h2>
      <ul>
        <li data-testid="pro-native-overview-status">状态：{run.status}</li>
        <li data-testid="pro-native-overview-stage">
          阶段：{overviewStageLabel(run.current_stage)}
          {run.current_stage ? `（${run.current_stage}）` : ""}
        </li>
        <li data-testid="pro-native-overview-window-progress">
          窗口进度：{completedWindows} / {totalWindows}
        </li>
        {run.progress?.current_window_index != null ? (
          <li data-testid="pro-native-overview-current-window">
            当前窗口索引：{run.progress.current_window_index}
          </li>
        ) : null}
        {run.progress?.failed_window_index != null ? (
          <li data-testid="pro-native-overview-failed-window">
            失败窗口索引：{run.progress.failed_window_index}
          </li>
        ) : null}
        <li data-testid="pro-native-overview-tokens">
          Token：预估 {formatTokens(run.estimated_tokens)} / 实际{" "}
          {formatTokens(run.actual_tokens)}
        </li>
        <li data-testid="pro-native-overview-cost">
          费用：预估 {formatMoney(run.estimated_cost, currency)} / 实际{" "}
          {formatMoney(run.actual_cost, currency)}
        </li>
        <li data-testid="pro-native-overview-run-provider">
          Provider：{run.provider || "—"} · Model：{run.model || "—"}
        </li>
        <li data-testid="pro-native-overview-run-engine">
          Engine：<EngineBadge engine={engine} />
        </li>
        <li data-testid="pro-native-overview-retryable">
          可重试：{run.retryable || canRetry ? "是" : "否"}
        </li>
        <li data-testid="pro-native-overview-resumable">
          可恢复：{canResume ? "是" : "否"}
        </li>
        {run.error ? (
          <li data-testid="pro-native-overview-run-error">错误：{run.error}</li>
        ) : null}
      </ul>

      <div data-testid="pro-native-overview-stage-list">
        <h3>阶段列表</h3>
        <ol>
          {stages.map((stage) => (
            <li
              key={stage.key}
              data-testid={`pro-native-overview-stage-item-${stage.key}`}
              data-stage-state={stage.state}
            >
              {stage.label}
              {stage.state === "current" ? "（进行中）" : ""}
              {stage.state === "done" ? "（完成）" : ""}
            </li>
          ))}
        </ol>
      </div>

      {actionError ? (
        <p data-testid="pro-native-overview-action-error">{actionError}</p>
      ) : null}

      <div className="pro-native-overview-actions">
        <button
          type="button"
          className="secondary"
          data-testid="pro-native-overview-refresh"
          onClick={onRefresh}
        >
          刷新
        </button>
        {canRetry ? (
          <button
            type="button"
            className="primary"
            data-testid="pro-native-overview-retry-run"
            disabled={actionPending}
            onClick={onRetry}
          >
            {actionPending ? "重试中…" : "Retry 失败运行"}
          </button>
        ) : null}
        {canResume ? (
          <button
            type="button"
            className="primary"
            data-testid="pro-native-overview-resume-run"
            disabled={actionPending}
            onClick={onResume}
          >
            {actionPending ? "恢复中…" : "Resume 暂停运行"}
          </button>
        ) : null}
      </div>
      <p className="muted" data-testid="pro-native-overview-run-id">
        Run：{runId}
      </p>
    </section>
  );
}

export function ProNativeOverviewPage() {
  const params = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const bookId = Number(params.bookId || 0);
  const runId = searchParams.get("run_id");
  const flagOn = isProNativeOverviewUiEnabled();
  const [startError, setStartError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const book = useQuery({
    queryKey: ["book", bookId],
    queryFn: () => booksApi.detail(bookId),
    enabled: bookId > 0 && flagOn,
  });

  const preflight = useQuery({
    queryKey: ["pro-native-overview-preflight", bookId],
    queryFn: () => proNativeOverviewApi.preflight(bookId),
    enabled: bookId > 0 && flagOn && !runId,
    retry: false,
  });

  const runQuery = useQuery({
    queryKey: ["pro-native-overview-run", runId],
    queryFn: () => proNativeOverviewApi.getRun(runId!),
    enabled: Boolean(runId) && flagOn,
    retry: false,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status) return 1500;
      if (status === "completed" || status === "failed" || status === "cancelled") {
        return false;
      }
      return 1500;
    },
  });

  const overviewQuery = useQuery({
    queryKey: ["pro-native-overview-result", runId],
    queryFn: () => proNativeOverviewApi.getOverview(runId!),
    enabled: Boolean(runId) && flagOn && runQuery.data?.status === "completed",
    retry: false,
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      const pf = preflight.data;
      const binding = resolveCreateBinding(pf);
      return proNativeOverviewApi.createRun(bookId, {
        provider_id: binding.provider_id,
        model_id: binding.model_id,
        client_request_id: newClientRequestId(),
        consent: {
          estimated_tokens: pf?.estimated_tokens ?? 0,
          estimated_cost: pf?.estimated_cost ?? 0,
          currency: pf?.currency ?? "CNY",
          confirmed: true,
        },
      });
    },
    onSuccess: (created) => {
      setStartError(null);
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set("run_id", created.run_id);
          return next;
        },
        { replace: true },
      );
    },
    onError: (error) => {
      const code = mapUiErrorCode(error);
      setStartError(
        error instanceof Error ? `${code}：${error.message}` : String(error),
      );
    },
  });

  const retryMutation = useMutation({
    mutationFn: async () => {
      if (!runId) throw new Error("missing run_id");
      return proNativeOverviewApi.retryRun(runId, {
        client_request_id: newClientRequestId("overview-retry"),
        reason: "ui_retry",
      });
    },
    onSuccess: async () => {
      setActionError(null);
      await queryClient.invalidateQueries({ queryKey: ["pro-native-overview-run", runId] });
      await runQuery.refetch();
    },
    onError: (error) => {
      setActionError(
        error instanceof Error
          ? `${mapUiErrorCode(error)}：${error.message}`
          : String(error),
      );
    },
  });

  const resumeMutation = useMutation({
    mutationFn: async () => {
      if (!runId) throw new Error("missing run_id");
      return proNativeOverviewApi.resumeRun(runId, {
        client_request_id: newClientRequestId("overview-resume"),
      });
    },
    onSuccess: async () => {
      setActionError(null);
      await queryClient.invalidateQueries({ queryKey: ["pro-native-overview-run", runId] });
      await runQuery.refetch();
    },
    onError: (error) => {
      setActionError(
        error instanceof Error
          ? `${mapUiErrorCode(error)}：${error.message}`
          : String(error),
      );
    },
  });

  const backLink = useMemo(
    () => (
      <Link className="secondary" to={`/books/${bookId}`} data-testid="pro-native-overview-back">
        返回书籍
      </Link>
    ),
    [bookId],
  );

  if (!flagOn) {
    return (
      <section className="pro-native-overview-page" data-testid="pro-native-overview-feature-disabled">
        <h1>{PAGE_TITLE}</h1>
        <ErrorPanel
          code="FEATURE_DISABLED"
          message="原生全书概览功能未启用（UI feature flag 关闭）。正式版本启用前不可用。"
        />
        {backLink}
      </section>
    );
  }

  if (book.isLoading || (!runId && preflight.isLoading)) {
    return <Loading />;
  }

  if (!runId && preflight.isError) {
    const code = mapUiErrorCode(preflight.error);
    return (
      <section className="pro-native-overview-page" data-testid="pro-native-overview-page">
        <h1>{PAGE_TITLE}</h1>
        <ErrorPanel
          code={code === "BOOK_CONTENT_EMPTY" ? "BOOK_EMPTY" : code}
          message={
            preflight.error instanceof Error
              ? preflight.error.message
              : "Preflight 失败"
          }
          onRetry={() => void preflight.refetch()}
        />
        {backLink}
      </section>
    );
  }

  const run = runQuery.data;
  const runFailed = run?.status === "failed";
  const runCompleted = run?.status === "completed";
  const actionPending = retryMutation.isPending || resumeMutation.isPending;

  return (
    <section className="pro-native-overview-page" data-testid="pro-native-overview-page">
      <header className="pro-native-overview-header">
        <div>
          <h1>{PAGE_TITLE}</h1>
          <p className="muted">{PAGE_SUBTITLE}</p>
          <p className="muted">{book.data?.title || `书籍 #${bookId}`}</p>
          <p className="muted" data-testid="pro-native-overview-product-distinction">
            本页是「原生全书概览」，不是「章节聚合洞察」。
          </p>
        </div>
        {backLink}
      </header>

      {!runId && preflight.data ? (
        <PreflightPanel
          preflight={preflight.data}
          starting={createMutation.isPending}
          onStart={() => createMutation.mutate()}
          startError={startError}
        />
      ) : null}

      {runId ? (
        <>
          {runQuery.isLoading ? <Loading /> : null}
          {runQuery.isError ? (
            <ErrorPanel
              code={mapUiErrorCode(runQuery.error)}
              message={
                runQuery.error instanceof Error
                  ? runQuery.error.message
                  : "无法读取运行状态"
              }
              onRetry={() => void runQuery.refetch()}
            />
          ) : null}
          {run ? (
            <ProgressPanel
              run={run}
              runId={runId}
              onRefresh={() => {
                void runQuery.refetch();
                if (runCompleted) void overviewQuery.refetch();
              }}
              onRetry={() => retryMutation.mutate()}
              onResume={() => resumeMutation.mutate()}
              actionPending={actionPending}
              actionError={actionError}
            />
          ) : null}
        </>
      ) : null}

      {runFailed ? (
        <ErrorPanel
          code="RUN_FAILED"
          message={run?.error || run?.error_code || "原生全书概览运行失败"}
          onRetry={
            run?.retryable || run?.actions?.can_retry
              ? () => retryMutation.mutate()
              : undefined
          }
        />
      ) : null}

      {runCompleted && overviewQuery.isLoading ? <Loading /> : null}

      {runCompleted && overviewQuery.isError ? (
        <ErrorPanel
          code={
            mapUiErrorCode(overviewQuery.error) === "HTTP_ERROR"
              ? "OVERVIEW_NOT_READY"
              : mapUiErrorCode(overviewQuery.error)
          }
          message={
            overviewQuery.error instanceof Error
              ? overviewQuery.error.message
              : "Overview 尚未就绪"
          }
          onRetry={() => void overviewQuery.refetch()}
        />
      ) : null}

      {overviewQuery.data ? (
        <ProNativeOverviewResult bookId={bookId} data={overviewQuery.data} />
      ) : null}

      {createMutation.isError && !runId ? (
        <ErrorState
          error={
            createMutation.error instanceof Error
              ? createMutation.error
              : new Error(String(createMutation.error))
          }
        />
      ) : null}
    </section>
  );
}
