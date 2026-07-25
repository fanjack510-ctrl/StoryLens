import { useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ErrorState, Loading } from "../components/common/States";
import { useProductEdition } from "../hooks/useProductEdition";
import { ApiError } from "../services/apiClient";
import { booksApi } from "../services/booksApi";
import { firstEvidenceHref } from "../services/proNativeOverviewDeepLink";
import {
  FIXTURE_CREATE_DEFAULTS,
  proNativeOverviewApi,
  type OverviewField,
  type PreflightBlockingError,
  type ProNativeOverviewPreflight,
} from "../services/proNativeOverviewApi";
import {
  isProNativeOverviewUiEnabled,
  WALKING_SKELETON_USER_NOTICE,
} from "../services/proNativeOverviewFlag";

const PAGE_TITLE = "Pro 原生全书概览";
const PAGE_SUBTITLE = "基于完整小说原文的原生整书概览（行走骨架）";
const MODE_LABEL = "原生整书";
const ENGINE_LABEL = "Fixture Development Mode";

const RESULT_FIELDS: Array<{ key: keyof ResultFieldMap; label: string }> = [
  { key: "protagonist", label: "主角" },
  { key: "protagonist_core_goal", label: "主角核心目标" },
  { key: "primary_conflict", label: "全书主要矛盾" },
  { key: "central_question", label: "核心悬念或核心问题" },
  { key: "key_turning_points", label: "关键转折" },
  { key: "ending_state", label: "结局状态" },
  { key: "logline", label: "一句话故事" },
  { key: "synopsis", label: "全书概要" },
];

type ResultFieldMap = {
  protagonist?: OverviewField | null;
  protagonist_core_goal?: OverviewField | null;
  primary_conflict?: OverviewField | null;
  central_question?: OverviewField | null;
  key_turning_points?: OverviewField | null;
  ending_state?: OverviewField | null;
  logline?: OverviewField | null;
  synopsis?: OverviewField | null;
};

function blockingMessage(item: PreflightBlockingError | string): string {
  if (typeof item === "string") return item;
  if (item.code && item.message) return `${item.code}：${item.message}`;
  return item.message || item.code || "阻塞错误";
}

function formatFieldValue(value: unknown): string {
  if (value == null || value === "") return "";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function isInsufficient(field: OverviewField | null | undefined): boolean {
  if (!field) return true;
  if (field.status === "insufficient_evidence") return true;
  const text = formatFieldValue(field.value).trim();
  return !text;
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
    API_UNAVAILABLE: "分析服务不可用",
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

function OverviewFieldCard({
  bookId,
  label,
  fieldKey,
  field,
  evidenceIndex,
}: {
  bookId: number;
  label: string;
  fieldKey: string;
  field: OverviewField | null | undefined;
  evidenceIndex: Parameters<typeof firstEvidenceHref>[2];
}) {
  const insufficient = isInsufficient(field);
  const href = firstEvidenceHref(bookId, field?.evidence_refs, evidenceIndex);
  const confidence =
    typeof field?.confidence === "number" ? field.confidence.toFixed(2) : "—";

  return (
    <article
      className="pro-native-overview-field"
      data-testid={`pro-native-overview-field-${fieldKey}`}
      data-status={field?.status || "missing"}
    >
      <header>
        <h3>{label}</h3>
        <p className="muted">置信度：{confidence}</p>
      </header>
      {insufficient ? (
        <p data-testid={`pro-native-overview-field-${fieldKey}-insufficient`}>
          暂未能可靠判断
        </p>
      ) : (
        <p data-testid={`pro-native-overview-field-${fieldKey}-value`}>
          {formatFieldValue(field?.value)}
        </p>
      )}
      {href ? (
        <Link
          className="secondary"
          to={href}
          data-testid={`pro-native-overview-evidence-${fieldKey}`}
        >
          Evidence
        </Link>
      ) : (
        <button
          type="button"
          className="secondary"
          disabled
          data-testid={`pro-native-overview-evidence-${fieldKey}-missing`}
          title="缺少可跳转证据"
        >
          Evidence
        </button>
      )}
    </article>
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
  const blocking = preflight.blocking_errors || [];
  const canStart =
    blocking.length === 0 &&
    preflight.license_allowed !== false &&
    (preflight.paragraph_count ?? 0) > 0;

  return (
    <section data-testid="pro-native-overview-preflight">
      <h2>启动前检查</h2>
      <ul>
        <li>章节数：{preflight.chapter_count}</li>
        <li>段落数：{preflight.paragraph_count}</li>
        <li>字符数：{preflight.character_count}</li>
        <li>模式：{MODE_LABEL}</li>
        <li>Engine：{ENGINE_LABEL}</li>
        <li>
          授权：
          {preflight.license_allowed ? "已允许（Pro）" : "未授权 / 不允许"}
        </li>
      </ul>
      <p className="notice" data-testid="pro-native-overview-walking-notice">
        {WALKING_SKELETON_USER_NOTICE}
      </p>
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

export function ProNativeOverviewPage() {
  const params = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const bookId = Number(params.bookId || 0);
  const runId = searchParams.get("run_id");
  const edition = useProductEdition();
  const isPro = edition.loaded && edition.is_pro;
  const flagOn = isProNativeOverviewUiEnabled();
  const [startError, setStartError] = useState<string | null>(null);

  const book = useQuery({
    queryKey: ["book", bookId],
    queryFn: () => booksApi.detail(bookId),
    enabled: bookId > 0 && flagOn,
  });

  const preflight = useQuery({
    queryKey: ["pro-native-overview-preflight", bookId],
    queryFn: () => proNativeOverviewApi.preflight(bookId),
    enabled: bookId > 0 && flagOn && isPro && !runId,
    retry: false,
  });

  const runQuery = useQuery({
    queryKey: ["pro-native-overview-run", runId],
    queryFn: () => proNativeOverviewApi.getRun(runId!),
    enabled: Boolean(runId) && flagOn && isPro,
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
    enabled:
      Boolean(runId) &&
      flagOn &&
      isPro &&
      runQuery.data?.status === "completed",
    retry: false,
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      const pf = preflight.data;
      const clientRequestId =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `overview-${Date.now()}`;
      return proNativeOverviewApi.createRun(bookId, {
        provider_id: FIXTURE_CREATE_DEFAULTS.provider_id,
        model_id: FIXTURE_CREATE_DEFAULTS.model_id,
        client_request_id: clientRequestId,
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
          message="Pro 原生全书概览功能未启用（UI feature flag 关闭）。"
        />
        {backLink}
      </section>
    );
  }

  if (!isPro) {
    return (
      <section className="pro-native-overview-page" data-testid="pro-native-overview-upgrade">
        <h1>{PAGE_TITLE}</h1>
        <p className="muted">{PAGE_SUBTITLE}</p>
        <ErrorPanel
          code="PRO_REQUIRED"
          message="Pro 原生全书概览为 StoryLens Pro 功能。激活专业版授权后可使用。此入口与「章节聚合洞察」不同。"
        />
        <button type="button" className="primary" onClick={() => navigate("/settings")}>
          查看授权说明
        </button>
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

  return (
    <section className="pro-native-overview-page" data-testid="pro-native-overview-page">
      <header className="pro-native-overview-header">
        <div>
          <h1>{PAGE_TITLE}</h1>
          <p className="muted">{PAGE_SUBTITLE}</p>
          <p className="muted">{book.data?.title || `书籍 #${bookId}`}</p>
          <p className="muted" data-testid="pro-native-overview-product-distinction">
            本页是「Pro 原生全书概览」，不是「章节聚合洞察」。
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
        <section data-testid="pro-native-overview-progress">
          <h2>运行进度</h2>
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
            <>
              <ul>
                <li data-testid="pro-native-overview-status">状态：{run.status}</li>
                <li data-testid="pro-native-overview-stage">
                  阶段：{run.current_stage || "—"}
                </li>
                <li data-testid="pro-native-overview-window-progress">
                  窗口进度：
                  {run.progress?.completed_windows ?? 0} / {run.progress?.total_windows ?? 0}
                  {typeof run.progress?.percent === "number"
                    ? `（${run.progress.percent}%）`
                    : ""}
                </li>
                <li data-testid="pro-native-overview-retryable">
                  可重试：{run.retryable ? "是" : "否"}
                </li>
                {run.error ? (
                  <li data-testid="pro-native-overview-run-error">错误：{run.error}</li>
                ) : null}
              </ul>
              <button
                type="button"
                className="secondary"
                data-testid="pro-native-overview-refresh"
                onClick={() => {
                  void runQuery.refetch();
                  if (runCompleted) void overviewQuery.refetch();
                }}
              >
                刷新
              </button>
            </>
          ) : null}
        </section>
      ) : null}

      {runFailed ? (
        <ErrorPanel
          code="RUN_FAILED"
          message={run?.error || run?.error_code || "原生全书概览运行失败"}
          onRetry={
            run?.retryable
              ? () => {
                  void runQuery.refetch();
                }
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
        <section data-testid="pro-native-overview-result">
          <h2>概览结果</h2>
          <p className="muted">
            Engine：{overviewQuery.data.engine_version || ENGINE_LABEL} ·{" "}
            {WALKING_SKELETON_USER_NOTICE}
          </p>
          {RESULT_FIELDS.map(({ key, label }) => (
            <OverviewFieldCard
              key={key}
              bookId={bookId}
              label={label}
              fieldKey={key}
              field={overviewQuery.data.overview?.[key]}
              evidenceIndex={overviewQuery.data.evidence_index}
            />
          ))}
        </section>
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
