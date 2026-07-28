import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ErrorState, Loading } from "../components/common/States";
import { ApiError } from "../services/apiClient";
import { isWholeBookFixturePreviewEnabled } from "../services/wholeBookFixturePreviewFlag";
import { isWholeBookFreeProductEnabled } from "../services/wholeBookFreeProductFlag";
import { isWholeBookRealProviderEnabled } from "../services/wholeBookRealProviderFlag";
import {
  BOOK_OVERVIEW_CLAIM_LABELS,
  BOOK_OVERVIEW_CLAIM_ORDER,
} from "../services/wholeBookFoundationApi";
import { openEvidenceInReader } from "../services/wholeBookFreeEvidenceDeepLink";
import {
  WHOLE_BOOK_FREE_MODULES,
  wholeBookFreeProductApi,
  newWholeBookClientRequestId,
  type BookOverviewResultRow,
  type EvidenceSourceDetail,
  type NarrativeAssetRow,
  type NarrativeEntityRow,
  type NarrativeEvidenceRow,
  type WholeBookModuleKey,
  type WholeBookPrepareResponse,
  type WholeBookProgressResponse,
  type WholeBookRunRecord,
} from "../services/wholeBookFreeProductApi";
import {
  buildWholeBookFreeStageList,
  wholeBookFreeStageLabel,
  wholeBookFreeStatusLabel,
} from "../services/wholeBookFreeProductStages";
import styles from "./WholeBookFreeProductPage.module.css";

const MODE_USER_LABEL = "原生全书分析";
const PREPARE_TITLE = "开始全书分析";
const PREPARE_EXPLANATION =
  "StoryLens 将读取整本小说原文，识别全书主线信息、主要人物和关键事件。分析结果可以回到原文核对。";
const PREPARE_BULLETS = [
  "分析使用您配置的大模型 API；模型费用由模型服务商收取，StoryLens 不收取本次 Token 费用。",
  "原始小说不会上传到 StoryLens 官方服务器。",
  "当前分析以完整原文为事实源，不依赖已有单章分析。",
];
const CONSENT_TEXT =
  "我已了解本次分析会调用我配置的大模型 API，并可能产生模型费用。";
const FIXTURE_BANNER_TEXT =
  "测试数据 · 不会调用真实模型 · 结果不代表真实分析质量";
const FIXTURE_PAGE_BANNER =
  "当前为测试数据预览，不会调用真实模型，结果不代表本书的真实分析。";

function formatMoneyRange(min: string | null | undefined, max: string | null | undefined): string {
  if (!min && !max) return "当前模型缺少价格配置";
  if (min && max && min !== max) return `约 ¥${min}～¥${max}`;
  const v = min || max;
  return v ? `约 ¥${v}` : "当前模型缺少价格配置";
}

function formatPercent(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Math.round(value * 1000) / 10}%`;
}

function overviewAvailabilityLabel(availability: string): string {
  if (availability === "available") return "可用";
  if (availability === "insufficient_evidence") return "当前证据不足";
  if (availability === "unavailable") return "当前分析不可用";
  return availability;
}

function highlightQuote(
  paragraphText: string,
  quoteText: string,
  startOffset: number,
  endOffset: number,
): { before: string; quote: string; after: string } {
  if (
    startOffset >= 0 &&
    endOffset > startOffset &&
    endOffset <= paragraphText.length &&
    paragraphText.slice(startOffset, endOffset) === quoteText
  ) {
    return {
      before: paragraphText.slice(0, startOffset),
      quote: quoteText,
      after: paragraphText.slice(endOffset),
    };
  }
  const idx = paragraphText.indexOf(quoteText);
  if (idx >= 0) {
    return {
      before: paragraphText.slice(0, idx),
      quote: quoteText,
      after: paragraphText.slice(idx + quoteText.length),
    };
  }
  return { before: paragraphText, quote: "", after: "" };
}

function isActiveRun(status: string | null | undefined): boolean {
  return status === "running" || status === "paused" || status === "recoverable";
}

function isCompletedRun(status: string | null | undefined): boolean {
  return status === "completed";
}

function ProductUnavailable() {
  return (
    <section className={styles.wholeBookFreeUnavailable} data-testid="whole-book-free-unavailable">
      <h1>全书分析</h1>
      <p>正式全书分析入口未启用。请设置 VITE_WHOLE_BOOK_FREE_PRODUCT_ENABLED=true 后重试。</p>
      <p className="muted">
        <Link to="/library">返回书库</Link>
      </p>
    </section>
  );
}

export function WholeBookFreeProductPage() {
  if (!isWholeBookFreeProductEnabled()) {
    return <ProductUnavailable />;
  }
  return <WholeBookFreeProductPageEnabled />;
}

function WholeBookFreeProductPageEnabled() {
  const { bookId: bookIdParam } = useParams();
  const bookId = Number(bookIdParam);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const fixturePreviewOn = isWholeBookFixturePreviewEnabled();
  const realProviderOn = isWholeBookRealProviderEnabled();

  const [activeModule, setActiveModule] = useState<WholeBookModuleKey>("overview");
  const [charactersTab, setCharactersTab] = useState<"characters" | "events">("characters");
  const [consented, setConsented] = useState(false);
  const [limits, setLimits] = useState({
    max_provider_calls: "",
    max_input_tokens: "",
    max_output_tokens: "",
    max_cost_budget_cny: "",
    auto_retry_enabled: false,
  });
  const [actionError, setActionError] = useState<string | null>(null);
  const [drawerSource, setDrawerSource] = useState<EvidenceSourceDetail | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerError, setDrawerError] = useState<string | null>(null);

  const prepareQuery = useQuery({
    queryKey: ["whole-book-free-prepare", bookId],
    queryFn: () => wholeBookFreeProductApi.prepare(bookId),
    enabled: bookId > 0,
    retry: false,
    refetchInterval: (query) => {
      const run = query.state.data?.latest_run;
      return run && isActiveRun(run.status) ? 3000 : false;
    },
  });

  const runId = prepareQuery.data?.latest_run?.run_id ?? prepareQuery.data?.recoverable_run?.run_id ?? null;
  const runStatus = prepareQuery.data?.latest_run?.status ?? prepareQuery.data?.recoverable_run?.status;

  const progressQuery = useQuery({
    queryKey: ["whole-book-free-progress", runId],
    queryFn: () => wholeBookFreeProductApi.getProgress(runId!),
    enabled: runId != null && isActiveRun(runStatus),
    refetchInterval: isActiveRun(runStatus) ? 2000 : false,
  });

  const stagesQuery = useQuery({
    queryKey: ["whole-book-free-stages", runId],
    queryFn: () => wholeBookFreeProductApi.listStages(runId!),
    enabled: runId != null && (isActiveRun(runStatus) || isCompletedRun(runStatus)),
  });

  const overviewQuery = useQuery({
    queryKey: ["whole-book-free-overview", runId],
    queryFn: () => wholeBookFreeProductApi.getOverview(runId!),
    enabled: runId != null && isCompletedRun(runStatus),
  });

  const entitiesQuery = useQuery({
    queryKey: ["whole-book-free-entities", runId],
    queryFn: () => wholeBookFreeProductApi.listEntities(runId!),
    enabled:
      runId != null &&
      isCompletedRun(runStatus) &&
      (activeModule === "characters_events" || activeModule === "overview"),
  });

  const assetsQuery = useQuery({
    queryKey: ["whole-book-free-assets", runId],
    queryFn: () => wholeBookFreeProductApi.listAssets(runId!, { asset_type: "event" }),
    enabled: runId != null && isCompletedRun(runStatus) && activeModule === "characters_events",
  });

  const evidencesQuery = useQuery({
    queryKey: ["whole-book-free-evidences", runId],
    queryFn: () => wholeBookFreeProductApi.listEvidences(runId!),
    enabled: runId != null && isCompletedRun(runStatus),
  });

  const capabilitiesQuery = useQuery({
    queryKey: ["whole-book-free-capabilities"],
    queryFn: () => wholeBookFreeProductApi.productCapabilities(),
  });

  useEffect(() => {
    const rec = prepareQuery.data?.recommended_limits;
    if (!rec) return;
    setLimits((prev) => ({
      max_provider_calls:
        prev.max_provider_calls ||
        (rec.max_provider_calls != null ? String(rec.max_provider_calls) : ""),
      max_input_tokens:
        prev.max_input_tokens ||
        (rec.max_input_tokens != null ? String(rec.max_input_tokens) : ""),
      max_output_tokens:
        prev.max_output_tokens ||
        (rec.max_output_tokens != null ? String(rec.max_output_tokens) : ""),
      max_cost_budget_cny: prev.max_cost_budget_cny || rec.max_cost_budget_cny || "",
      auto_retry_enabled: prev.auto_retry_enabled,
    }));
  }, [prepareQuery.data?.recommended_limits]);

  const invalidateAll = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ["whole-book-free-prepare", bookId] });
    if (runId != null) {
      await queryClient.invalidateQueries({ queryKey: ["whole-book-free-progress", runId] });
    }
  }, [bookId, queryClient, runId]);

  const createFormalMutation = useMutation({
    mutationFn: () =>
      wholeBookFreeProductApi.createRun(bookId, {
        client_request_id: newWholeBookClientRequestId(),
        estimate_id: prepareQuery.data?.estimate?.estimate_id ?? null,
        max_provider_calls: limits.max_provider_calls
          ? Number(limits.max_provider_calls)
          : null,
        max_input_tokens: limits.max_input_tokens ? Number(limits.max_input_tokens) : null,
        max_output_tokens: limits.max_output_tokens ? Number(limits.max_output_tokens) : null,
        max_cost_budget_cny: limits.max_cost_budget_cny || null,
        auto_retry_enabled: limits.auto_retry_enabled,
      }),
    onSuccess: () => void invalidateAll(),
    onError: (err) =>
      setActionError(err instanceof ApiError ? err.message : "创建分析任务失败"),
  });

  const createFixtureMutation = useMutation({
    mutationFn: () =>
      wholeBookFreeProductApi.createFixtureRun(bookId, {
        client_request_id: newWholeBookClientRequestId("wb-fixture"),
      }),
    onSuccess: () => void invalidateAll(),
    onError: (err) =>
      setActionError(err instanceof ApiError ? err.message : "Fixture 预览失败"),
  });

  const pauseMutation = useMutation({
    mutationFn: () => wholeBookFreeProductApi.pauseRun(runId!),
    onSuccess: () => void invalidateAll(),
  });

  const resumeMutation = useMutation({
    mutationFn: () => wholeBookFreeProductApi.resumeRun(runId!),
    onSuccess: () => void invalidateAll(),
  });

  const cancelMutation = useMutation({
    mutationFn: () => wholeBookFreeProductApi.cancelRun(runId!),
    onSuccess: () => void invalidateAll(),
  });

  const prepare = prepareQuery.data;
  const run = prepare?.latest_run ?? prepare?.recoverable_run ?? null;
  const progress = progressQuery.data;
  const resultOrigin = run?.result_origin ?? progress?.result_origin ?? null;
  const showFixtureBanner = resultOrigin === "fixture";

  const importantEntities = useMemo(() => {
    const overview = overviewQuery.data?.overview;
    const all = entitiesQuery.data?.entities ?? [];
    if (!overview?.important_entity_ids?.length) return [];
    const byId = new Map(all.map((e) => [e.entity_id, e]));
    return overview.important_entity_ids
      .map((id) => byId.get(id))
      .filter((e): e is NarrativeEntityRow => Boolean(e));
  }, [entitiesQuery.data?.entities, overviewQuery.data?.overview]);

  const keyEvents = useMemo(() => {
    const overview = overviewQuery.data?.overview;
    const all = assetsQuery.data?.assets ?? [];
    if (!overview?.key_event_asset_ids?.length) return [];
    const byId = new Map(all.map((a) => [a.asset_id, a]));
    const events = overview.key_event_asset_ids
      .map((id) => byId.get(id))
      .filter((a): a is NarrativeAssetRow => Boolean(a));
    const evidenceById = new Map(
      (evidencesQuery.data?.evidences ?? []).map((e) => [e.evidence_id, e]),
    );
    return [...events].sort((a, b) => {
      const ga =
        a.evidence_ids?.map((id) => evidenceById.get(id)?.global_paragraph_index ?? Infinity)[0] ??
        Infinity;
      const gb =
        b.evidence_ids?.map((id) => evidenceById.get(id)?.global_paragraph_index ?? Infinity)[0] ??
        Infinity;
      return ga - gb;
    });
  }, [assetsQuery.data?.assets, evidencesQuery.data?.evidences, overviewQuery.data?.overview]);

  const handleOpenEvidence = useCallback(
    async (evidenceId: number) => {
      setDrawerError(null);
      try {
        const resp = await wholeBookFreeProductApi.getEvidenceSource(evidenceId);
        setDrawerSource(resp.source);
        setDrawerOpen(true);
      } catch (err) {
        setDrawerError(err instanceof Error ? err.message : "加载 Evidence 失败");
      }
    },
    [],
  );

  const handleOpenInReader = useCallback(
    (source: EvidenceSourceDetail) => {
      setDrawerError(null);
      try {
        if (source.state === "stale") {
          setDrawerError("原文已发生变化，当前依据无法精确定位。");
          return;
        }
        const chapterId = source.chapter_index;
        const href = openEvidenceInReader(bookId, source, chapterId);
        navigate(href);
      } catch (err) {
        if (err instanceof Error && err.message === "EVIDENCE_MISSING") {
          setDrawerError("对应章节已不存在。");
          return;
        }
        setDrawerError(err instanceof Error ? err.message : "无法打开原文");
      }
    },
    [bookId, navigate],
  );

  if (!bookId || Number.isNaN(bookId)) {
    return <ErrorState error={new Error("无效的书籍 ID")} />;
  }

  if (prepareQuery.isLoading) {
    return <Loading />;
  }

  if (prepareQuery.isError) {
    const err =
      prepareQuery.error instanceof Error
        ? prepareQuery.error
        : new Error("无法加载全书分析页面");
    return <ErrorState error={err} retry={() => void prepareQuery.refetch()} />;
  }

  if (!prepare) {
    return <ErrorState error={new Error("准备数据不可用")} />;
  }

  const pageMode: "prepare" | "running" | "completed" | "failed" = (() => {
    if (!run) return "prepare";
    if (isCompletedRun(run.status)) return "completed";
    if (run.status === "failed" || run.status === "cancelled") return "failed";
    return "running";
  })();

  const canStartFormal =
    consented &&
    realProviderOn &&
    prepare.run_creation_enabled &&
    !createFormalMutation.isPending;

  return (
    <div className={styles.wholeBookFreePage} data-testid="whole-book-free-product-page">
      <header className={styles.wholeBookFreeHeader}>
        <p className="muted">
          <Link to={`/books/${bookId}`}>← 返回书籍</Link>
        </p>
        <h1 data-testid="whole-book-free-book-title">{prepare.book_title}</h1>
        <div className={styles.wholeBookFreeHeaderMeta}>
          <span data-testid="whole-book-free-chapter-count">{prepare.chapter_count} 章</span>
          <span data-testid="whole-book-free-word-count">{prepare.character_count} 字</span>
          <span data-testid="whole-book-free-status">
            状态：{wholeBookFreeStatusLabel(run?.status ?? "pending")}
          </span>
          <span data-testid="whole-book-free-mode">模式：{MODE_USER_LABEL}</span>
          {run?.started_at ? (
            <span data-testid="whole-book-free-started">开始：{run.started_at}</span>
          ) : null}
          {run?.completed_at || progress?.updated_at ? (
            <span data-testid="whole-book-free-updated">
              更新：{run?.completed_at ?? progress?.updated_at}
            </span>
          ) : null}
        </div>
        {run ? (
          <details className={styles.wholeBookFreeTechDetails} data-testid="whole-book-free-tech-details">
            <summary>技术详情</summary>
            <ul>
              <li>run_id: {run.run_id}</li>
              <li>snapshot_id: {run.snapshot_id ?? "—"}</li>
              <li>mode: {run.mode}</li>
              <li>engine_id: {run.engine_id}</li>
              <li>result_origin: {run.result_origin}</li>
            </ul>
          </details>
        ) : null}
      </header>

      {showFixtureBanner ? (
        <div className={styles.wholeBookFreeFixtureBanner} data-testid="whole-book-free-fixture-banner">
          {FIXTURE_PAGE_BANNER}
        </div>
      ) : null}

      <div className={styles.wholeBookFreeLayout}>
        <nav className={styles.wholeBookFreeNav} aria-label="全书分析模块" data-testid="whole-book-free-module-nav">
          {WHOLE_BOOK_FREE_MODULES.map((mod) => {
            const disabled = mod.status === "available" && pageMode !== "completed";
            const badge =
              mod.status === "planned"
                ? "开发中"
                : mod.status === "pro_planned"
                  ? "后续版本开放"
                  : null;
            return (
              <button
                key={mod.key}
                type="button"
                className={styles.wholeBookFreeNavButton}
                data-testid={`whole-book-free-module-${mod.key}`}
                data-active={activeModule === mod.key ? "true" : "false"}
                data-disabled={disabled ? "true" : "false"}
                disabled={disabled}
                onClick={() => setActiveModule(mod.key)}
              >
                {mod.label}
                {badge ? `（${badge}）` : ""}
              </button>
            );
          })}
        </nav>

        <main className={styles.wholeBookFreeContent}>
          {pageMode === "prepare" ? (
            <PreparePanel
              prepare={prepare}
              consented={consented}
              onConsentChange={setConsented}
              limits={limits}
              onLimitsChange={setLimits}
              canStartFormal={canStartFormal}
              realProviderOn={realProviderOn}
              fixturePreviewOn={fixturePreviewOn}
              actionError={actionError}
              startingFormal={createFormalMutation.isPending}
              startingFixture={createFixtureMutation.isPending}
              onStartFormal={() => {
                setActionError(null);
                createFormalMutation.mutate();
              }}
              onStartFixture={() => {
                setActionError(null);
                createFixtureMutation.mutate();
              }}
            />
          ) : null}

          {pageMode === "running" ? (
            <ProgressPanel
              progress={progress}
              stages={stagesQuery.data?.stages ?? []}
              run={run!}
              pausing={pauseMutation.isPending}
              resuming={resumeMutation.isPending}
              cancelling={cancelMutation.isPending}
              onPause={() => pauseMutation.mutate()}
              onResume={() => resumeMutation.mutate()}
              onCancel={() => cancelMutation.mutate()}
            />
          ) : null}

          {pageMode === "completed" && activeModule === "overview" ? (
            <OverviewPanel
              overview={overviewQuery.data?.overview ?? null}
              loading={overviewQuery.isLoading}
              evidences={evidencesQuery.data?.evidences ?? []}
              onOpenEvidence={(id) => void handleOpenEvidence(id)}
            />
          ) : null}

          {pageMode === "completed" && activeModule === "characters_events" ? (
            <CharactersEventsPanel
              tab={charactersTab}
              onTabChange={setCharactersTab}
              entities={importantEntities}
              events={keyEvents}
              onOpenEvidence={(id) => void handleOpenEvidence(id)}
            />
          ) : null}

          {activeModule === "structure" ? (
            <PlannedModulePanel label="故事结构" data-testid="whole-book-free-structure-planned" />
          ) : null}

          {activeModule === "chapter_functions" ? (
            <PlannedModulePanel label="章节功能" data-testid="whole-book-free-chapter-functions-planned" />
          ) : null}

          {activeModule === "pro_depth" ? (
            <section data-testid="whole-book-free-pro-planned">
              <h2>Pro 深度分析</h2>
              <p>后续版本开放</p>
            </section>
          ) : null}
        </main>
      </div>

      {drawerOpen && drawerSource ? (
        <EvidenceDrawerPanel
          source={drawerSource}
          onClose={() => setDrawerOpen(false)}
          onOpenInReader={() => handleOpenInReader(drawerSource)}
          error={drawerError}
        />
      ) : null}

      {capabilitiesQuery.data ? (
        <div hidden data-testid="whole-book-free-capabilities-loaded">
          {capabilitiesQuery.data.capabilities.length}
        </div>
      ) : null}
    </div>
  );
}

function PreparePanel({
  prepare,
  consented,
  onConsentChange,
  limits,
  onLimitsChange,
  canStartFormal,
  realProviderOn,
  fixturePreviewOn,
  actionError,
  startingFormal,
  startingFixture,
  onStartFormal,
  onStartFixture,
}: {
  prepare: WholeBookPrepareResponse;
  consented: boolean;
  onConsentChange: (v: boolean) => void;
  limits: {
    max_provider_calls: string;
    max_input_tokens: string;
    max_output_tokens: string;
    max_cost_budget_cny: string;
    auto_retry_enabled: boolean;
  };
  onLimitsChange: (v: typeof limits) => void;
  canStartFormal: boolean;
  realProviderOn: boolean;
  fixturePreviewOn: boolean;
  actionError: string | null;
  startingFormal: boolean;
  startingFixture: boolean;
  onStartFormal: () => void;
  onStartFixture: () => void;
}) {
  const est = prepare.estimate;
  return (
    <section className={styles.wholeBookFreePrepare} data-testid="whole-book-free-prepare">
      <h2>{PREPARE_TITLE}</h2>
      <p>{PREPARE_EXPLANATION}</p>
      <ul>
        {PREPARE_BULLETS.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>

      <section data-testid="whole-book-free-cost-estimate">
        <h3>费用预估</h3>
        {est ? (
          <ul>
            <li>预计窗口数：{est.estimated_windows ?? "—"}</li>
            <li>预计模型调用数：{est.estimated_provider_calls ?? "—"}</li>
            <li>预计输入 Token：{est.estimated_input_tokens ?? "—"}</li>
            <li>预计输出 Token：{est.estimated_output_tokens ?? "—"}</li>
            <li>
              预计模型调用费用：
              {est.price_known
                ? formatMoneyRange(est.estimated_cost_min_cny, est.estimated_cost_max_cny)
                : "当前模型缺少价格配置"}
            </li>
            <li>
              Provider / 模型：{est.provider_name ?? "—"} / {est.model_name ?? "—"}
            </li>
          </ul>
        ) : (
          <p className="muted">费用预估暂不可用。</p>
        )}
        <p className="muted">
          由模型服务商收取，实际费用以模型服务商账单为准。价格未知时需设置调用次数和 Token 上限。
        </p>
      </section>

      <section data-testid="whole-book-free-limits">
        <h3>调用限制</h3>
        <div className={styles.wholeBookFreeLimitsGrid}>
          <label>
            最大模型调用次数
            <input
              type="number"
              value={limits.max_provider_calls}
              onChange={(e) => onLimitsChange({ ...limits, max_provider_calls: e.target.value })}
            />
          </label>
          <label>
            最大输入 Token
            <input
              type="number"
              value={limits.max_input_tokens}
              onChange={(e) => onLimitsChange({ ...limits, max_input_tokens: e.target.value })}
            />
          </label>
          <label>
            最大输出 Token
            <input
              type="number"
              value={limits.max_output_tokens}
              onChange={(e) => onLimitsChange({ ...limits, max_output_tokens: e.target.value })}
            />
          </label>
          <label>
            最高费用预算（CNY）
            <input
              type="text"
              value={limits.max_cost_budget_cny}
              onChange={(e) => onLimitsChange({ ...limits, max_cost_budget_cny: e.target.value })}
            />
          </label>
        </div>
        <label>
          <input
            type="checkbox"
            checked={limits.auto_retry_enabled}
            onChange={(e) => onLimitsChange({ ...limits, auto_retry_enabled: e.target.checked })}
          />
          启用自动重试（默认关闭；失败后不会自动无限重试）
        </label>
      </section>

      <label className="consent" data-testid="whole-book-free-consent">
        <input
          type="checkbox"
          checked={consented}
          data-testid="whole-book-free-consent-checkbox"
          onChange={(e) => onConsentChange(e.target.checked)}
        />
        <span>{CONSENT_TEXT}</span>
      </label>

      {!realProviderOn ? (
        <p data-testid="whole-book-free-real-provider-disabled">
          真实模型 Provider 尚未启用，暂不可开始正式分析。
        </p>
      ) : null}

      <button
        type="button"
        className="primary"
        data-testid="whole-book-free-start-formal"
        disabled={!canStartFormal || startingFormal}
        onClick={onStartFormal}
      >
        {startingFormal ? "创建中…" : "开始全书分析"}
      </button>

      {fixturePreviewOn ? (
        <>
          <div className={styles.wholeBookFreeFixtureBanner} data-testid="whole-book-free-fixture-notice">
            {FIXTURE_BANNER_TEXT}
          </div>
          <button
            type="button"
            className="secondary"
            data-testid="whole-book-free-start-fixture"
            disabled={startingFixture}
            onClick={onStartFixture}
          >
            {startingFixture ? "加载测试数据…" : "使用测试数据预览页面"}
          </button>
        </>
      ) : null}

      {actionError ? <p className="error-text">{actionError}</p> : null}
    </section>
  );
}

function ProgressPanel({
  progress,
  stages,
  run,
  pausing,
  resuming,
  cancelling,
  onPause,
  onResume,
  onCancel,
}: {
  progress: WholeBookProgressResponse | undefined;
  stages: Array<{ stage_code: string; status: string }>;
  run: WholeBookRunRecord;
  pausing: boolean;
  resuming: boolean;
  cancelling: boolean;
  onPause: () => void;
  onResume: () => void;
  onCancel: () => void;
}) {
  const stageList = buildWholeBookFreeStageList(stages, run.current_stage_code, run.status);
  const p = progress;
  return (
    <section data-testid="whole-book-free-progress">
      <h2>分析进度</h2>
      <p data-testid="whole-book-free-overall-progress">
        完成：{formatPercent(p?.overall_progress ?? null)}
      </p>
      <ul>
        <li>
          窗口：{p?.completed_windows ?? 0} / {p?.total_windows ?? 0}
        </li>
        <li>
          调用：{p?.provider_calls_used ?? 0}
          {p?.provider_calls_limit != null ? ` / ${p.provider_calls_limit}` : ""}
        </li>
        <li>
          Token：输入 {p?.input_tokens_used ?? 0} · 输出 {p?.output_tokens_used ?? 0}
        </li>
        <li>当前预计费用：{p?.cost_used_cny ? `¥${p.cost_used_cny}` : "—"}</li>
        <li>当前阶段：{wholeBookFreeStageLabel(p?.current_stage ?? run.current_stage_code)}</li>
      </ul>

      <ol className={styles.wholeBookFreeStageList} data-testid="whole-book-free-stage-list">
        {stageList.map((stage) => (
          <li key={stage.key} data-state={stage.state} data-testid={`whole-book-free-stage-${stage.key}`}>
            {stage.label} — {stage.state}
          </li>
        ))}
      </ol>

      <div className="actions">
        {p?.can_pause ? (
          <button type="button" className="secondary" disabled={pausing} onClick={onPause}>
            暂停
          </button>
        ) : null}
        {p?.can_resume ? (
          <button type="button" className="secondary" disabled={resuming} onClick={onResume}>
            继续
          </button>
        ) : null}
        {p?.can_cancel ? (
          <button type="button" className="secondary" disabled={cancelling} onClick={onCancel}>
            取消
          </button>
        ) : null}
      </div>
    </section>
  );
}

function OverviewPanel({
  overview,
  loading,
  evidences,
  onOpenEvidence,
}: {
  overview: BookOverviewResultRow | null;
  loading: boolean;
  evidences: NarrativeEvidenceRow[];
  onOpenEvidence: (id: number) => void;
}) {
  if (loading) return <Loading />;
  if (!overview) return <p>总览尚未就绪。</p>;

  const claimByKey = new Map(overview.claims.map((c) => [c.claim_key, c]));

  return (
    <section data-testid="whole-book-free-overview">
      <h2>全书总览</h2>
      <ul className={styles.wholeBookFreeClaimList}>
        {BOOK_OVERVIEW_CLAIM_ORDER.map((claimKey) => {
          const claim = claimByKey.get(claimKey);
          const label = BOOK_OVERVIEW_CLAIM_LABELS[claimKey] ?? claimKey;
          return (
            <li
              key={claimKey}
              className={styles.wholeBookFreeClaimCard}
              data-testid={`whole-book-free-claim-${claimKey}`}
              data-availability={claim?.availability ?? "unavailable"}
            >
              <h3>{label}</h3>
              <p className="muted">{overviewAvailabilityLabel(claim?.availability ?? "unavailable")}</p>
              {claim?.availability === "insufficient_evidence" ? (
                <p data-testid="whole-book-free-insufficient-evidence">
                  当前证据不足：{claim.summary ?? "暂无足够证据。"}
                </p>
              ) : claim?.summary ? (
                <p>{claim.summary}</p>
              ) : (
                <p className="muted">暂无摘要</p>
              )}
              {claim?.confidence != null ? <p>置信度：{claim.confidence}</p> : null}
              {claim?.evidence_ids?.length ? (
                <p>Evidence 数量：{claim.evidence_ids.length}</p>
              ) : null}
              {claim?.evidence_ids?.length ? (
                <button
                  type="button"
                  className="secondary"
                  data-testid={`whole-book-free-claim-evidence-${claimKey}`}
                  onClick={() => onOpenEvidence(claim.evidence_ids[0])}
                >
                  查看依据
                </button>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function CharactersEventsPanel({
  tab,
  onTabChange,
  entities,
  events,
  onOpenEvidence,
}: {
  tab: "characters" | "events";
  onTabChange: (t: "characters" | "events") => void;
  entities: NarrativeEntityRow[];
  events: NarrativeAssetRow[];
  onOpenEvidence: (id: number) => void;
}) {
  return (
    <section data-testid="whole-book-free-characters-events">
      <h2>主要人物与关键事件</h2>
      <div className={styles.wholeBookFreeSubTabs}>
        <button
          type="button"
          data-active={tab === "characters"}
          onClick={() => onTabChange("characters")}
        >
          人物
        </button>
        <button type="button" data-active={tab === "events"} onClick={() => onTabChange("events")}>
          关键事件
        </button>
      </div>
      {tab === "characters" ? (
        <ul className={styles.wholeBookFreeEntityList} data-testid="whole-book-free-characters-list">
          {entities.length === 0 ? <li className="muted">暂无重要人物</li> : null}
          {entities.map((entity) => (
            <li key={entity.entity_id} data-testid={`whole-book-free-entity-${entity.entity_id}`}>
              <strong>{entity.canonical_name}</strong>
              {entity.aliases?.length ? (
                <span className="muted">
                  {" "}
                  别名：{entity.aliases.map((a) => a.name).join("、")}
                </span>
              ) : null}
              <p className="muted">
                事件 {entity.event_count} · Evidence {entity.evidence_count} · 置信度 {entity.confidence}
              </p>
              {entity.linked_evidences?.[0]?.evidence_id ? (
                <button
                  type="button"
                  className="secondary"
                  onClick={() => onOpenEvidence(entity.linked_evidences![0].evidence_id!)}
                >
                  查看依据
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <ul className={styles.wholeBookFreeEventList} data-testid="whole-book-free-events-list">
          {events.length === 0 ? <li className="muted">暂无关键事件</li> : null}
          {events.map((event) => (
            <li key={event.asset_id} data-testid={`whole-book-free-event-${event.asset_id}`}>
              <strong>{event.title}</strong>
              {event.summary ? <p>{event.summary}</p> : null}
              <p className="muted">
                {event.event_type ? `类型：${event.event_type} · ` : ""}
                Evidence {event.evidence_count} · 置信度 {event.confidence}
              </p>
              {event.evidence_ids?.[0] ? (
                <button
                  type="button"
                  className="secondary"
                  onClick={() => onOpenEvidence(event.evidence_ids![0])}
                >
                  查看依据
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function PlannedModulePanel({ label, "data-testid": testId }: { label: string; "data-testid": string }) {
  return (
    <section data-testid={testId}>
      <h2>{label}</h2>
      <p>开发中</p>
    </section>
  );
}

function EvidenceDrawerPanel({
  source,
  onClose,
  onOpenInReader,
  error,
}: {
  source: EvidenceSourceDetail;
  onClose: () => void;
  onOpenInReader: () => void;
  error: string | null;
}) {
  const parts = highlightQuote(
    source.paragraph_text,
    source.quote_text,
    source.start_offset,
    source.end_offset,
  );
  return (
    <aside
      className={styles.wholeBookFreeEvidenceDrawer}
      data-testid="whole-book-free-evidence-drawer"
      role="dialog"
      aria-label="Evidence"
    >
      <header>
        <h3>Evidence #{source.evidence_id}</h3>
        <button type="button" onClick={onClose}>
          关闭
        </button>
      </header>
      <p>
        [{source.chapter_index}] {source.chapter_title} · 段落 {source.paragraph_index}
      </p>
      <p className={styles.wholeBookFreeEvidenceParagraph} data-testid="whole-book-free-evidence-paragraph">
        {parts.before}
        {parts.quote ? <mark>{parts.quote}</mark> : null}
        {parts.after}
      </p>
      {error ? <p className="error-text">{error}</p> : null}
      <button type="button" className="primary" data-testid="whole-book-free-open-in-reader" onClick={onOpenInReader}>
        在原文中查看
      </button>
    </aside>
  );
}
