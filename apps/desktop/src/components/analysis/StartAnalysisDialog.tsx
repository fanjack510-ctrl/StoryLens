import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { providersApi } from "../../services/providersApi";
import { analysisApi } from "../../services/analysisApi";
import { settingsApi } from "../../services/settingsApi";
import { analysisRecoveryApi } from "../../services/analysisRecoveryApi";
import {
  manualBoundaryEligibility,
  PROVIDER_ELIGIBILITY_MISSING,
} from "../../services/providerEligibility";
import { ApiError } from "../../services/apiClient";
import { existingRunDetailsFromError } from "../../services/runLifecycle";
import { useDeveloperModeStore } from "../../stores/developerModeStore";
import {
  DEFAULT_AI_SERVICE_ID,
  buildAiServiceViewModel,
} from "../../services/aiServiceViewModel";
import { invalidateAiQueries } from "../../services/aiServiceConfig";
import { BUDGET_ERROR_USER_COPY } from "../../services/budgetErrorCopy";
import {
  estimateFullPipelineRequests,
  estimatedRequestShortfall,
  fullPipelineRequestShortfall,
  requestOnlyShortfall,
  type CreateBudgetBlocker,
} from "../../services/budgetRecoveryMath";
import { trackAnalysisStarted } from "../../services/telemetry/analysisRunTelemetry";
import { formatCny, formatTokenCount } from "./analysisDisplayLabels";
import {
  ordinaryModeOptions,
  readStoredAnalysisMode,
  writeStoredAnalysisMode,
  type AnalysisModePresetId,
} from "../../services/analysisModePresets";
import { serviceDisplayNameFor } from "../../services/aiServiceViewModel";

const MODE_CARD_HINT: Record<"FAST" | "BALANCED" | "QUALITY", string> = {
  FAST: "速度优先，适合初步拆解",
  BALANCED: "推荐，兼顾成本和质量",
  QUALITY: "适合关键章节和最终分析",
};

const EXECUTION_HINTS: Record<string, string> = {
  local: "在本机运行模型，不发送正文到云端。",
  cloud: "使用云端 AI 生成边界候选，需人工确认后继续。",
  hybrid: "部分步骤本地执行，关键步骤使用云端 AI。",
};

function formatProviderDisplayName(item: {
  name: string;
  display_name?: string;
  capabilities?: { region?: string; profile_name?: string };
}): string {
  if (item.name.startsWith("local_")) return "本地模型";
  const base =
    item.display_name ||
    (item.name.includes("qwen")
      ? serviceDisplayNameFor(item.name, "阿里云百炼")
      : item.name);
  return base;
}

function formatProviderOptionLabel(
  item: {
    name: string;
    display_name?: string;
    default_model?: string;
    requires_boundary_review?: boolean;
    capabilities?: { region?: string; profile_name?: string };
  },
  peers: Array<{ name: string; display_name?: string }> = [],
): string {
  const base = formatProviderDisplayName(item);
  const sameNameCount = peers.filter((p) => formatProviderDisplayName(p) === base).length;
  if (sameNameCount <= 1) return base;
  const region = item.capabilities?.region;
  if (region) return `${base} · ${region}`;
  const profile = item.capabilities?.profile_name;
  if (profile && profile !== item.name) return `${base} · ${profile}`;
  return base;
}

function formatProviderStatusHint(item: {
  connected?: boolean;
  healthy?: boolean;
  requires_boundary_review?: boolean;
} | null | undefined): string | null {
  if (!item) return null;
  const connected = item.connected || item.healthy ? "已连接" : "未连接";
  if (item.requires_boundary_review) {
    return `${connected} · 需要人工确认场景边界`;
  }
  return connected;
}

function formatBudgetGaps(preflight: any): string {
  const dims: string[] = preflight?.exceeded_dimensions || [];
  if (!dims.length) return "";
  const required = {
    requests: preflight.expected_request_count,
    tokens: preflight.estimated_total_tokens,
    estimated_cost: preflight.estimated_cost,
  };
  const remaining = preflight.remaining || {};
  return dims.map((dim) => {
    if (dim === "requests") {
      return `请求不足：预计需要${required.requests}次，当前剩余${remaining.requests}次。`;
    }
    if (dim === "tokens") {
      return `Token不足：预计需要${required.tokens} Token，当前剩余${remaining.tokens} Token。`;
    }
    return `费用不足：预计需要约${required.estimated_cost} CNY，当前剩余约${remaining.estimated_cost} CNY。`;
  }).join("\n");
}

const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function Stage1BudgetSummary({ preflight, budgetBlocked }: { preflight: any; budgetBlocked: boolean }) {
  const currency = preflight.currency || "CNY";
  const cards = [
    { label: "段落数", value: preflight.paragraph_count },
    { label: "Transition数", value: preflight.transition_count },
    { label: "Detection批次", value: preflight.detection_batch_count },
    { label: "Adjudication批次", value: preflight.adjudication_batch_count_estimated },
    { label: "预计请求", value: preflight.expected_request_count },
    { label: "最坏请求", value: preflight.worst_case_request_count },
    { label: "预计Token", value: preflight.estimated_total_tokens },
    { label: "最坏Token", value: preflight.worst_case_total_tokens },
    { label: "预计费用", value: `${preflight.estimated_cost} ${currency}` },
    { label: "最坏费用", value: `${preflight.worst_case_cost} ${currency}` },
    { label: "剩余请求", value: preflight.remaining?.requests },
    { label: "剩余Token", value: preflight.remaining?.tokens },
    { label: "剩余费用", value: preflight.remaining?.estimated_cost },
  ];
  return (
    <div className="budget-preview" data-testid="stage1-budget-preview">
      <h3>本阶段仅识别场景边界</h3>
      <p>本阶段不会执行 Scene Analysis。人工确认边界后，系统会根据最终 Scene 数量重新估算 Scene Analysis 预算。</p>
      <dl className="budget-summary-grid" data-testid="stage1-budget-grid">
        {cards.map((card) => (
          <div key={card.label} className="budget-summary-card">
            <dt>{card.label}</dt>
            <dd>{card.value}</dd>
          </div>
        ))}
        <div className="budget-summary-card budget-summary-card--status">
          <dt>是否可执行</dt>
          <dd>{budgetBlocked ? "否" : "是"}</dd>
        </div>
      </dl>
      {budgetBlocked && <pre data-testid="stage1-budget-gap">{formatBudgetGaps(preflight)}</pre>}
    </div>
  );
}

function RequestQuotaBlockPanel({
  required,
  available,
  shortfall,
  estimated,
  worstCase,
  costAndTokenOk,
  detailOpen,
  onToggleDetail,
  onCreateRecommended,
  onCreateEstimated,
  busy,
}: {
  required: number;
  available: number;
  shortfall: number;
  estimated: number;
  worstCase: number;
  costAndTokenOk: boolean;
  detailOpen: boolean;
  onToggleDetail: () => void;
  onCreateRecommended: () => void;
  onCreateEstimated: () => void;
  busy: boolean;
}) {
  return (
    <div
      className="create-budget-block-panel"
      data-testid="create-request-quota-block"
      data-required={required}
      data-available={available}
      data-shortfall={shortfall}
      data-estimated={estimated}
      data-worst-case={worstCase}
    >
      <h3 data-testid="create-request-quota-title">当前技术请求额度不足</h3>
      <p data-testid="create-request-quota-body">
        本阶段预计需要{estimated}次云端请求，当前今日剩余{available}次，还差{shortfall}次。
        {costAndTokenOk ? "费用和Token预算充足。" : ""}
        {worstCase > estimated
          ? `（最坏情况约${worstCase}次，仅作风险提示，不作为启动硬门槛。）`
          : ""}
      </p>
      <dl className="budget-summary-grid" data-testid="create-request-quota-metrics">
        <div className="budget-summary-card">
          <dt>required</dt>
          <dd>{required}</dd>
        </div>
        <div className="budget-summary-card">
          <dt>available</dt>
          <dd>{available}</dd>
        </div>
        <div className="budget-summary-card">
          <dt>shortfall</dt>
          <dd>{shortfall}</dd>
        </div>
        <div className="budget-summary-card">
          <dt>estimated</dt>
          <dd>{estimated}</dd>
        </div>
        <div className="budget-summary-card">
          <dt>worst_case</dt>
          <dd>{worstCase}</dd>
        </div>
      </dl>
      <div className="create-budget-block-actions">
        <button
          type="button"
          className="primary"
          data-testid="create-with-recommended-allowance"
          disabled={busy || !costAndTokenOk}
          onClick={onCreateRecommended}
        >
          {busy ? "正在创建任务……" : "按推荐额度创建任务"}
        </button>
        <button
          type="button"
          className="secondary"
          data-testid="create-with-estimated-allowance"
          disabled={busy || !costAndTokenOk}
          onClick={onCreateEstimated}
        >
          按预计用量创建
        </button>
        <button
          type="button"
          className="linkish"
          data-testid="create-budget-view-details"
          onClick={onToggleDetail}
        >
          {detailOpen ? "收起详细预算" : "查看详细预算"}
        </button>
      </div>
      <p className="hint" data-testid="create-request-quota-hint">
        「按推荐额度创建」仅为本次任务临时授权所需技术请求额度，不会永久修改每日请求设置，也不会提高每日费用上限。
      </p>
    </div>
  );
}

function FullPipelineBudgetAdvisory({
  advisory,
  preflight,
  usage,
  budget,
  detailOpen,
}: {
  advisory: any | null;
  preflight: any;
  usage: any;
  budget: any;
  detailOpen: boolean;
}) {
  const envelope = estimateFullPipelineRequests(preflight);
  const remainingRequests =
    typeof advisory?.remaining_requests === "number"
      ? advisory.remaining_requests
      : typeof preflight.remaining?.requests === "number"
        ? preflight.remaining.requests
        : Number(usage?.remaining_requests) || 0;
  const usedRequests = Number(usage?.request_count) || 0;
  const reservedRequests =
    Number(preflight.reserved?.requests ?? usage?.reserved_requests) || 0;
  const remainingTokens =
    typeof advisory?.remaining_tokens === "number"
      ? advisory.remaining_tokens
      : typeof preflight.remaining?.tokens === "number"
        ? preflight.remaining.tokens
        : Number(usage?.remaining_tokens) || 0;
  const remainingCost =
    typeof advisory?.remaining_cost === "number"
      ? advisory.remaining_cost
      : typeof preflight.remaining?.estimated_cost === "number"
        ? preflight.remaining.estimated_cost
        : Number(usage?.remaining_estimated_cost) || 0;
  const fullWorst = Number(advisory?.full_worst_requests) || envelope.full.worst;
  const fullExpected = Number(advisory?.full_expected_requests) || envelope.full.expected;
  const shortfall = fullPipelineRequestShortfall({
    remainingRequests,
    fullWorstRequests: fullWorst,
  });
  const dailyLimit = Number(budget?.cloud_daily_request_limit) || 0;
  const estimatedFullCost =
    typeof advisory?.worst_case_cost === "number"
      ? advisory.worst_case_cost
      : typeof preflight.worst_case_cost === "number"
        ? Math.round((preflight.worst_case_cost + envelope.sceneAnalysis.worst * 0.01) * 1000) / 1000
        : null;

  if (!detailOpen && shortfall <= 0) {
    return (
      <div
        className="budget-preview full-pipeline-budget"
        data-testid="full-pipeline-budget-preview"
        data-request-shortfall="0"
      >
        <h3>完整分析预算预检（创建前）</h3>
        <p>
          完整 Run 最坏约 {fullWorst} 次请求；今日剩余 {remainingRequests} 次。费用/Token 请以剩余值为准。
        </p>
      </div>
    );
  }

  if (!detailOpen) return null;

  return (
    <div
      className="budget-preview full-pipeline-budget"
      data-testid="full-pipeline-budget-preview"
      data-request-shortfall={shortfall > 0 ? "1" : "0"}
    >
      <h3>完整分析预算预检（创建前）</h3>
      <p>
        以下为完整章节分析估算（含边界、Scene Analysis、Reader Journey 与 retry/recovery 余量）。
      </p>
      <dl className="budget-summary-grid" data-testid="full-pipeline-budget-grid">
        <div className="budget-summary-card">
          <dt>Boundary 预计/最坏</dt>
          <dd>
            {advisory?.boundary_expected_requests ?? envelope.boundary.expected}/
            {advisory?.boundary_worst_requests ?? envelope.boundary.worst}
          </dd>
        </div>
        <div className="budget-summary-card">
          <dt>Scene Analysis 预计/最坏</dt>
          <dd>
            {advisory?.scene_analysis_expected_requests ?? envelope.sceneAnalysis.expected}/
            {advisory?.scene_analysis_worst_requests ?? envelope.sceneAnalysis.worst}
            <small>
              （估 {advisory?.estimated_scene_count ?? envelope.sceneAnalysis.estimatedScenes} Scene）
            </small>
          </dd>
        </div>
        <div className="budget-summary-card">
          <dt>Reader Journey 预计/最坏</dt>
          <dd>
            {advisory?.reader_journey_expected_requests ?? envelope.readerJourney.expected}/
            {advisory?.reader_journey_worst_requests ?? envelope.readerJourney.worst}
          </dd>
        </div>
        <div className="budget-summary-card">
          <dt>完整 Run 预计/最坏请求</dt>
          <dd>
            {fullExpected}/{fullWorst}
          </dd>
        </div>
        <div className="budget-summary-card">
          <dt>今日已用请求</dt>
          <dd>{usedRequests}</dd>
        </div>
        <div className="budget-summary-card">
          <dt>有效 Reservation</dt>
          <dd>{reservedRequests}</dd>
        </div>
        <div className="budget-summary-card">
          <dt>剩余请求 / Token / 费用</dt>
          <dd>
            {remainingRequests} / {remainingTokens} / {remainingCost} CNY
          </dd>
        </div>
        <div className="budget-summary-card">
          <dt>每日请求保护（高级）</dt>
          <dd>{dailyLimit || "—"}</dd>
        </div>
        {estimatedFullCost != null && (
          <div className="budget-summary-card">
            <dt>完整 Run 费用量级</dt>
            <dd>约 {estimatedFullCost} CNY（估算）</dd>
          </div>
        )}
      </dl>
    </div>
  );
}

function OrdinaryBudgetSummary({
  preflight,
  estimatedFits,
  retryReserveTight,
}: {
  preflight: any;
  estimatedFits: boolean;
  retryReserveTight: boolean;
}) {
  return (
    <div className="ordinary-budget-summary" data-testid="start-analysis-budget-summary">
      <h3>预计本次用量</h3>
      <p data-testid="start-analysis-budget-estimate">
        约 {preflight.expected_request_count} 次请求
        {" · "}
        {formatTokenCount(preflight.estimated_total_tokens)} Token
        {" · "}
        {formatCny(preflight.estimated_cost)}
      </p>
      {estimatedFits && retryReserveTight && (
        <p className="hint" data-testid="start-analysis-retry-reserve-note">
          预计额度足够，暂无重试余量。
        </p>
      )}
      <p className="hint">本阶段仅识别场景边界；确认边界后将重新估算后续分析用量。</p>
    </div>
  );
}

function HardBudgetBlockers({ blockers }: { blockers: CreateBudgetBlocker[] }) {
  const hard = blockers.filter((b) => b.dimension !== "requests");
  if (!hard.length) return null;
  return (
    <div className="create-budget-hard-blockers" data-testid="create-hard-budget-blockers">
      {hard.map((b) => (
        <div key={b.dimension} data-testid={`create-blocker-${b.dimension}`}>
          <h3>{b.title}</h3>
          <p>{b.userMessage}</p>
          {b.required != null && (
            <p className="hint">
              required={b.required} · available={b.available} · shortfall={b.shortfall}
            </p>
          )}
          {(b.dimension === "api_key" || b.dimension === "provider") && (
            <Link to="/settings?tab=ai&focus=api_key">前往配置阿里云百炼 · Qwen</Link>
          )}
          {b.dimension === "estimated_cost" && (
            <Link to="/settings?tab=budget">调整每日费用上限</Link>
          )}
        </div>
      ))}
    </div>
  );
}

export function StartAnalysisDialog({
  chapterId,
  onClose,
  onCreated,
}: {
  chapterId: number;
  onClose: () => void;
  onCreated?: (
    runId: number,
    meta?: { existing?: boolean; status?: string; taskType?: string },
  ) => void;
}) {
  const developerMode = useDeveloperModeStore((s) => s.developerMode);
  const [mode, setMode] = useState(developerMode ? "local" : "cloud");
  const [provider, setProvider] = useState(developerMode ? "" : DEFAULT_AI_SERVICE_ID);
  const [consent, setConsent] = useState(false);
  const [message, setMessage] = useState("");
  const [preflight, setPreflight] = useState<any>(null);
  const [fullAdvisory, setFullAdvisory] = useState<any>(null);
  const [budgetDetailOpen, setBudgetDetailOpen] = useState(false);
  const [analysisModePreset, setAnalysisModePreset] = useState<AnalysisModePresetId>(() =>
    readStoredAnalysisMode(),
  );
  const [submitState, setSubmitState] = useState<"idle" | "checking" | "creating" | "created" | "failed">("idle");
  const clientRequestId = useRef(crypto.randomUUID());
  const dialogRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();
  const providers = useQuery({
    queryKey: ["providers"], queryFn: providersApi.list, refetchOnMount: "always", staleTime: 0,
  });
  const cloud = useQuery({
    queryKey: ["cloud"],
    queryFn: providersApi.cloud,
    enabled: !developerMode,
  });
  const budgetSettings = useQuery({
    queryKey: ["cloud-budget"],
    queryFn: settingsApi.cloudBudget,
  });
  const cloudUsage = useQuery({
    queryKey: ["cloud-usage"],
    queryFn: settingsApi.cloudUsage,
  });
  const configuration = useQuery({
    queryKey: ["provider-config", DEFAULT_AI_SERVICE_ID],
    queryFn: () => providersApi.configuration(DEFAULT_AI_SERVICE_ID),
    enabled: !developerMode,
    refetchOnMount: "always",
    staleTime: 0,
  });
  const executionPlanQuery = useQuery({
    queryKey: ["analysis-execution-plan", analysisModePreset, DEFAULT_AI_SERVICE_ID],
    queryFn: () => analysisApi.executionPlan(analysisModePreset),
    refetchOnMount: "always",
    staleTime: 0,
  });
  const executionPlan = executionPlanQuery.data;
  const evaluated = useMemo(() => (providers.data || []).map((item) => ({
    item, eligibility: manualBoundaryEligibility(item),
  })), [providers.data]);
  const eligible = evaluated.filter(({ item, eligibility }) => mode === "local"
    ? !item.capabilities.cloud && item.eligible_for_automatic_analysis
    : item.capabilities.cloud && eligibility.status === "eligible").map(({ item }) => item);
  const selected = providers.data?.find((item) => item.name === provider);
  const cloudDiagnostics = evaluated.filter(({ item }) => item.capabilities.cloud);

  const defaultProvider = useMemo(
    () =>
      eligible.find((p) => p.name === DEFAULT_AI_SERVICE_ID) ||
      (eligible.length === 1 ? eligible[0] : null) ||
      (providers.data || []).find((p) => p.name === DEFAULT_AI_SERVICE_ID) ||
      (providers.data || []).find((p) => p.capabilities?.cloud) ||
      null,
    [eligible, providers.data],
  );

  const unavailableReason = useMemo(() => {
    if (executionPlan?.user_message && !executionPlan.can_start) {
      return executionPlan.user_message;
    }
    if (eligible.length > 0) return null;
    const target =
      (providers.data || []).find((p) => p.name === DEFAULT_AI_SERVICE_ID) ||
      (providers.data || []).find((p) => p.capabilities?.cloud);
    const blockers = target?.manual_selection_blockers || [];
    if (!target || blockers.includes("credential_missing")) return "尚未配置 API Key";
    if (blockers.includes("cloud_master_switch_off") || cloud.data?.enabled === false) {
      return "云端分析尚未开启";
    }
    if (blockers.includes("provider_disabled")) return "Provider 已停用";
    if (
      blockers.includes("credential_invalid") ||
      configuration.data?.credential_state === "invalid"
    ) {
      return "凭据已失效";
    }
    if (blockers.includes("provider_unhealthy") || blockers.includes("provider_health_stale")) {
      return "Provider暂时不可用，请重新验证连接";
    }
    if (blockers.includes("budget_unavailable")) return "当前额度不足";
    if (blockers.length) {
      const first = blockers[0];
      const mapped: Record<string, string> = {
        provider_not_configured: "尚未配置AI服务",
        provider_disconnected: "AI 服务尚未连接",
        boundary_candidates_not_supported: "当前服务不支持场景边界分析",
        pricing_unavailable: "计价配置不可用",
      };
      return mapped[first] || "当前无法开始分析";
    }
    return "当前无法开始分析";
  }, [
    eligible.length,
    providers.data,
    cloud.data?.enabled,
    configuration.data?.credential_state,
    executionPlan?.user_message,
    executionPlan?.can_start,
  ]);

  const aiView = useMemo(
    () =>
      buildAiServiceViewModel({
        provider: developerMode ? selected || defaultProvider : defaultProvider,
        configuration: configuration.data,
        cloudEnabled: cloud.data?.enabled ?? true,
        providerEligible:
          executionPlan?.can_start === true ||
          eligible.some((p) => p.name === (defaultProvider?.name || DEFAULT_AI_SERVICE_ID)),
      }),
    [
      developerMode,
      selected,
      defaultProvider,
      configuration.data,
      cloud.data?.enabled,
      eligible,
      executionPlan?.can_start,
    ],
  );

  // Backend ExecutionPlan is SSOT; developer mode may still pick any eligible provider.
  const planAllowsStart = executionPlan
    ? executionPlan.can_start
    : aiView.canStartAnalysis && eligible.length > 0;

  useEffect(() => {
    if (developerMode) {
      if (eligible.length === 1 && provider !== eligible[0].name) {
        setProvider(eligible[0].name);
      } else if (eligible.length === 0 && planAllowsStart && provider !== DEFAULT_AI_SERVICE_ID) {
        setProvider(DEFAULT_AI_SERVICE_ID);
      }
      // Cloud provider + stale local mode → coerce to cloud (RC2 CLOUD_MODE_REQUIRED).
      // Do not coerce while providers are still loading, or when a local-capable
      // provider is available for developer local mode (CHG-20260727-017).
      const selectedCaps = (providers.data || []).find((p) => p.name === provider)?.capabilities;
      if (selectedCaps?.cloud && mode === "local") {
        setMode("cloud");
      } else if (
        !provider &&
        planAllowsStart &&
        mode === "local" &&
        Array.isArray(providers.data) &&
        eligible.length === 0 &&
        (providers.data || []).some((p) => p.name === DEFAULT_AI_SERVICE_ID && p.capabilities?.cloud)
      ) {
        setMode("cloud");
      }
      return;
    }
    const preferred =
      eligible.find((p) => p.name === DEFAULT_AI_SERVICE_ID)?.name ||
      (eligible.length === 1 ? eligible[0].name : null) ||
      DEFAULT_AI_SERVICE_ID;
    if (preferred && provider !== preferred) {
      setProvider(preferred);
    }
    if (mode !== "cloud") setMode("cloud");
  }, [developerMode, eligible, provider, mode, planAllowsStart, providers.data]);

  useEffect(() => {
    if (provider && !eligible.some((item) => item.name === provider)) {
      if (developerMode) {
        if (eligible.length === 1) setProvider(eligible[0].name);
        else if (planAllowsStart) setProvider(DEFAULT_AI_SERVICE_ID);
        else setProvider("");
      }
    }
  }, [eligible, provider, developerMode, planAllowsStart]);

  useEffect(() => {
    setPreflight(null);
    setFullAdvisory(null);
    if ((mode !== "cloud" && mode !== "hybrid") || !provider || !selected || !consent) return;
    let cancelled = false;
    void (async () => {
      try {
        const result = await analysisApi.preflight({
          chapter_id: chapterId, provider, execution_mode: mode,
          analysis_mode: "assisted_boundary_review",
          cloud_consent: consent,
          capability_schema_version: selected.capability_schema_version,
          provider_state_version: selected.provider_state_version,
        });
        if (cancelled) return;
        setPreflight(result);
        try {
          const advisory = await analysisRecoveryApi.fullPipelinePreflight({
            chapter_id: chapterId,
            provider,
            execution_mode: mode,
            analysis_mode: "assisted_boundary_review",
            cloud_consent: consent,
            capability_schema_version: selected.capability_schema_version,
            provider_state_version: selected.provider_state_version,
          });
          if (!cancelled) setFullAdvisory(advisory);
        } catch {
          if (!cancelled) setFullAdvisory(null);
        }
      } catch (error) {
        if (!cancelled) setPreflight(null);
        if (!cancelled && error instanceof ApiError) setMessage(error.message);
      }
    })();
    return () => { cancelled = true; };
  }, [mode, provider, consent, chapterId, selected]);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previousOverflow; };
  }, []);

  useEffect(() => {
    const root = dialogRef.current;
    if (!root) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const focusables = () => Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE));
    const initial = focusables()[0];
    initial?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const nodes = focusables();
      if (!nodes.length) return;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previouslyFocused?.focus?.();
    };
  }, [onClose]);

  const budgetBlocked = Boolean(preflight && (!preflight.within_budget || (preflight.exceeded_dimensions || []).length));
  const envelope = useMemo(
    () => (preflight ? estimateFullPipelineRequests(preflight) : null),
    [preflight],
  );
  const remainingRequests = useMemo(() => {
    if (typeof fullAdvisory?.remaining_requests === "number") return fullAdvisory.remaining_requests;
    if (typeof preflight?.remaining?.requests === "number") return preflight.remaining.requests;
    return Number(cloudUsage.data?.remaining_requests) || 0;
  }, [fullAdvisory, preflight, cloudUsage.data]);
  const remainingTokens = useMemo(() => {
    if (typeof fullAdvisory?.remaining_tokens === "number") return fullAdvisory.remaining_tokens;
    if (typeof preflight?.remaining?.tokens === "number") return preflight.remaining.tokens;
    return Number(cloudUsage.data?.remaining_tokens) || 0;
  }, [fullAdvisory, preflight, cloudUsage.data]);
  const remainingCost = useMemo(() => {
    if (typeof fullAdvisory?.remaining_cost === "number") return fullAdvisory.remaining_cost;
    if (typeof preflight?.remaining?.estimated_cost === "number") return preflight.remaining.estimated_cost;
    return Number(cloudUsage.data?.remaining_estimated_cost) || 0;
  }, [fullAdvisory, preflight, cloudUsage.data]);

  const fullWorst = Number(fullAdvisory?.full_worst_requests) || envelope?.full.worst || 0;
  const fullExpected = Number(fullAdvisory?.full_expected_requests) || envelope?.full.expected || 0;
  const stage1Estimated = Number(preflight?.expected_request_count) || envelope?.boundary.expected || 0;
  // Hard gate shortfall: Stage-1 estimated only (never full-pipeline / worst-case).
  const stage1RequestShortfall = estimatedRequestShortfall({
    remainingRequests,
    estimatedRequests: stage1Estimated,
  });
  // Advisory-only: full worst headroom tip (does not hard-block create).
  const fullPipelineShortfall = fullPipelineRequestShortfall({
    remainingRequests,
    fullWorstRequests: fullWorst,
  });

  const stage1Dims: string[] = preflight?.exceeded_dimensions || [];
  const tokenBlocked = stage1Dims.includes("tokens")
    || (typeof preflight?.estimated_total_tokens === "number"
      && remainingTokens < preflight.estimated_total_tokens);
  const costBlocked = stage1Dims.includes("estimated_cost")
    || (typeof preflight?.estimated_cost === "number"
      && remainingCost + 1e-9 < preflight.estimated_cost);
  const costAndTokenOk = !tokenBlocked && !costBlocked;

  const createBlockers = useMemo((): CreateBudgetBlocker[] => {
    const list: CreateBudgetBlocker[] = [];
    if (!developerMode && !aiView.apiKeyConfigured) {
      list.push({
        dimension: "api_key",
        title: "尚未配置 API Key",
        userMessage: "请先配置阿里云百炼 · Qwen 的 API Key。",
        required: null,
        available: null,
        shortfall: null,
        estimated: null,
        worstCase: null,
      });
    }
    if (!developerMode && !planAllowsStart) {
      list.push({
        dimension: "provider",
        title: "Qwen 尚未连接",
        userMessage: unavailableReason || "AI 服务尚未连接，请先完成连接测试。",
        required: null,
        available: null,
        shortfall: null,
        estimated: null,
        worstCase: null,
      });
    }
    if (stage1RequestShortfall > 0 && preflight) {
      list.push({
        dimension: "requests",
        title: "当前技术请求额度不足",
        userMessage: `本阶段预计需要${stage1Estimated}次云端请求，当前今日剩余${remainingRequests}次，还差${stage1RequestShortfall}次。`,
        required: stage1Estimated,
        available: remainingRequests,
        shortfall: stage1RequestShortfall,
        estimated: stage1Estimated,
        worstCase: Number(preflight.worst_case_request_count) || fullWorst,
      });
    }
    if (tokenBlocked && preflight) {
      const required = Number(preflight.estimated_total_tokens) || 0;
      list.push({
        dimension: "tokens",
        title: "当前 Token 额度不足",
        userMessage: `本阶段预计约需 ${required} Token，当前剩余 ${remainingTokens}。`,
        required,
        available: remainingTokens,
        shortfall: Math.max(0, required - remainingTokens),
        estimated: required,
        worstCase: Number(preflight.worst_case_total_tokens) || null,
      });
    }
    if (costBlocked && preflight) {
      const required = Number(preflight.estimated_cost) || 0;
      list.push({
        dimension: "estimated_cost",
        title: "当前费用额度不足",
        userMessage: `本阶段预计约需 ${required} CNY，当前剩余约 ${remainingCost} CNY。`,
        required,
        available: remainingCost,
        shortfall: Math.max(0, Math.round((required - remainingCost) * 1000) / 1000),
        estimated: required,
        worstCase: Number(preflight.worst_case_cost) || null,
      });
    }
    return list;
  }, [
    developerMode,
    aiView.apiKeyConfigured,
    planAllowsStart,
    unavailableReason,
    stage1RequestShortfall,
    preflight,
    stage1Estimated,
    remainingRequests,
    fullWorst,
    tokenBlocked,
    costBlocked,
    remainingTokens,
    remainingCost,
  ]);

  const requestOnly = requestOnlyShortfall(createBlockers);
  const busy = submitState === "checking" || submitState === "creating" || providers.isFetching || executionPlanQuery.isFetching;

  // Ordinary: hard-disable only when Stage-1 estimated path cannot start.
  // Request-only shortfall shows recovery panel (temp auth); token/cost remain hard.
  // Developer: prefer eligible list, but do not ignore a backend plan that says can_start
  // (stale cached_failure must not strand a verified Settings configuration).
  const providerUnavailable = developerMode
    ? ((eligible.length === 0 && !planAllowsStart) || !provider)
    : !planAllowsStart || !provider;
  const hardCreateBlocked = tokenBlocked || costBlocked
    || (budgetBlocked && !requestOnly)
    || (!developerMode && (!planAllowsStart || !consent));
  const effectiveSubmitDisabled = developerMode
    ? busy || (budgetBlocked && !requestOnly) || providerUnavailable
    : busy || hardCreateBlocked || providerUnavailable;

  const showRequestQuotaPanel = Boolean(requestOnly && consent && preflight && costAndTokenOk);

  const submitLabel = providers.isFetching && (submitState === "idle" || submitState === "failed")
    ? (developerMode ? "正在刷新 Provider……" : "正在刷新服务状态……")
    : submitState === "checking"
      ? "正在检查预算……"
      : submitState === "creating"
        ? "正在创建任务……"
        : "创建分析任务";

  const submitDisabledReason = useMemo(() => {
    if (busy && (submitState === "checking" || submitState === "creating")) return null;
    if (providerUnavailable) {
      return unavailableReason || (developerMode ? "请选择可用 Provider" : "AI 服务尚未连接");
    }
    if (!developerMode && !planAllowsStart) {
      return unavailableReason || "AI 服务尚未连接";
    }
    if ((mode === "cloud" || mode === "hybrid") && !consent) {
      return "请先确认正文发送说明";
    }
    if (!provider) {
      return unavailableReason || (developerMode ? "请选择可用 Provider" : "AI 服务尚未连接");
    }
    if (stage1RequestShortfall > 0) return "当前技术请求额度不足";
    if (tokenBlocked) return "当前 Token 额度不足";
    if (costBlocked) return "当前费用额度不足";
    return null;
  }, [
    busy,
    submitState,
    providerUnavailable,
    developerMode,
    planAllowsStart,
    unavailableReason,
    mode,
    consent,
    provider,
    stage1RequestShortfall,
    tokenBlocked,
    costBlocked,
  ]);

  const handleAnalysisModeSelect = (id: AnalysisModePresetId) => {
    setAnalysisModePreset(id);
    writeStoredAnalysisMode(id);
  };

  const analysisModeCards = developerMode
    ? [...ordinaryModeOptions(), { id: "CUSTOM" as const, label: "自定义", shortLabel: "自定义", recommended: false }]
    : ordinaryModeOptions();

  const submit = async (allowance?: {
    mode: "recommended_worst_case" | "estimated_usage";
    extra_requests: number;
  }) => {
    if (submitState === "checking" || submitState === "creating") return;
    if (providerUnavailable) {
      return setMessage(unavailableReason || "当前没有可用的 AI 服务，请前往设置配置。");
    }
    if (!developerMode && !planAllowsStart) {
      return setMessage(unavailableReason || "AI服务尚未连接，请前往设置完成配置。");
    }
    if ((mode === "cloud" || mode === "hybrid") && !consent) return setMessage("请先确认云端传输同意。");
    if (!provider) {
      return setMessage(
        developerMode
          ? unavailableReason || "请选择可用 Provider。"
          : unavailableReason || "AI服务尚未连接。",
      );
    }
    if (
      !developerMode
      && !planAllowsStart
      && eligible.every((item) => item.name !== provider)
    ) {
      return setMessage(unavailableReason || "当前没有可用的 AI 服务，请前往设置配置。");
    }
    if (budgetBlocked && !allowance) return setMessage(formatBudgetGaps(preflight) || "当前Stage 1预算不足。");
    if ((tokenBlocked || costBlocked) && !allowance) {
      return setMessage("费用或Token预算不足，请先调整每日费用上限或等待额度恢复。");
    }
    if (stage1RequestShortfall > 0 && !allowance) {
      return setMessage(formatBudgetGaps(preflight) || "当前技术请求额度不足，请按推荐额度创建或提高每日请求保护。");
    }
    try {
      setSubmitState("checking");
      setMessage("正在检查服务、预算和章节范围……");
      const checked = mode === "cloud" || mode === "hybrid" ? await analysisApi.preflight({
        chapter_id: chapterId, provider, execution_mode: mode,
        analysis_mode: mode === "cloud" || mode === "hybrid" ? "assisted_boundary_review" : "automatic",
        cloud_consent: consent, capability_schema_version: selected!.capability_schema_version,
        provider_state_version: selected!.provider_state_version,
      }) : { eligible: true, provider_state_version: selected!.provider_state_version, within_budget: true };
      setPreflight(checked);
      if (!checked.eligible) throw Object.assign(new Error((checked.blockers || []).join("、")), { code: "NO_MANUAL_BOUNDARY_PROVIDER" });
      if (checked.within_budget === false) {
        const dims: string[] = checked.exceeded_dimensions || [];
        const requestOnlyGap = dims.length > 0 && dims.every((d) => d === "requests");
        if (!(allowance && requestOnlyGap)) {
          setSubmitState("failed");
          return setMessage(formatBudgetGaps(checked) || "当前Stage 1预算不足。");
        }
      }
      setSubmitState("creating");
      setMessage(allowance
        ? "正在按本次任务临时技术授权创建边界候选任务……"
        : "正在创建边界候选任务……");
      const payload: Record<string, unknown> = {
        provider_name: provider, execution_mode: mode, cloud_consent: consent,
        analysis_mode: mode === "cloud" || mode === "hybrid" ? "assisted_boundary_review" : "automatic",
        selected_provider: provider,
        capability_schema_version: selected!.capability_schema_version,
        provider_state_version: checked.provider_state_version,
        client_request_id: clientRequestId.current,
      };
      if (allowance && allowance.extra_requests > 0) {
        payload.run_temporary_request_allowance = {
          extra_requests: allowance.extra_requests,
          mode: allowance.mode,
        };
      }
      const run = await analysisApi.start(chapterId, payload);
      trackAnalysisStarted(mode);
      setSubmitState("created");
      setMessage(`任务已创建，Run ID：${run.run_id}。将在本章显示分析进度。`);
      onClose();
      if (onCreated) onCreated(run.run_id); else window.location.href = `/tasks?run_id=${run.run_id}`;
    } catch (error: any) {
      const existing = existingRunDetailsFromError(
        error instanceof ApiError
          ? { code: error.code, detail: error.detail }
          : { code: error?.code, detail: error?.detail || error?.details },
      );
      if (existing) {
        setSubmitState("created");
        setMessage("该章节已有分析任务，已为你打开现有任务。");
        onClose();
        if (onCreated) {
          onCreated(existing.existing_run_id, {
            existing: true,
            status: existing.existing_run_status,
            taskType: existing.existing_run_type,
          });
        } else {
          window.location.href = `/tasks?run_id=${existing.existing_run_id}`;
        }
        return;
      }
      setSubmitState("failed");
      const dimGaps = formatBudgetGaps({
        exceeded_dimensions: error.exceededDimensions || error.detail?.exceeded_dimensions,
        expected_request_count: error.required?.requests,
        estimated_total_tokens: error.required?.tokens,
        estimated_cost: error.required?.estimated_cost,
        remaining: error.remaining,
      });
      const messages: Record<string, string> = {
        NO_MANUAL_BOUNDARY_PROVIDER: "当前没有可用于人工边界审阅的AI服务。",
        PROVIDER_UNHEALTHY: "当前AI服务健康检查失败，请前往设置查看连接状态。",
        PROVIDER_HEALTH_STALE: "AI服务健康状态已过期，请刷新状态或重新测试连接。",
        PROVIDER_NOT_CONNECTED: "AI服务尚未连接。",
        CLOUD_MASTER_SWITCH_OFF: "云端AI尚未开启。",
        BUDGET_NOT_AVAILABLE: "当前无法计算本次分析费用",
        MODEL_PRICING_NOT_FOUND: "当前模型缺少计价信息",
        CLOUD_CONSENT_REQUIRED: "请确认当前章节正文将发送至云端模型服务。",
        CLOUD_MODE_REQUIRED: "云端 Provider 需要 cloud 或 hybrid 执行模式，请重试或检查设置。",
        PROVIDER_STATE_CHANGED: "服务状态已经变化，请刷新后重新确认。",
        ANALYSIS_RUN_EXISTS: "该章节已有相同 Provider 的运行记录。",
        FULL_PIPELINE_HARD_BUDGET_INSUFFICIENT:
          "费用或Token预算不足以覆盖完整分析。临时技术请求授权不能突破每日费用上限。",
        INSUFFICIENT_BUDGET_RESERVATION:
          dimGaps || BUDGET_ERROR_USER_COPY.INSUFFICIENT_BUDGET_RESERVATION,
        CLOUD_REQUEST_LIMIT_EXCEEDED: BUDGET_ERROR_USER_COPY.CLOUD_REQUEST_LIMIT_EXCEEDED,
        CLOUD_TOKEN_LIMIT_EXCEEDED: BUDGET_ERROR_USER_COPY.CLOUD_TOKEN_LIMIT_EXCEEDED,
        CLOUD_COST_LIMIT_EXCEEDED: BUDGET_ERROR_USER_COPY.CLOUD_COST_LIMIT_EXCEEDED,
        CLOUD_BUDGET_EXCEEDED: BUDGET_ERROR_USER_COPY.CLOUD_BUDGET_EXCEEDED,
      };
      const isNetwork =
        error instanceof ApiError
          ? error.status === 0 || error.code === "BACKEND_OFFLINE"
          : !(error && typeof error === "object" && "status" in error);
      const primary = isNetwork
        ? "无法连接StoryLens后端，请确认服务正在运行。"
        : messages[error.code] || error.message || "任务提交失败。";
      const hint = error.userActionHint || (error.code === "PROVIDER_STATE_CHANGED" ? "请刷新服务状态并重新确认后提交。" : "请展开诊断信息核对。");
      const raw = developerMode
        ? `\nHTTP ${error.status ?? "NETWORK"} · ${error.code || "NETWORK_ERROR"}${error.requestId ? ` · request_id ${error.requestId}` : ""}`
        : "";
      setMessage(`${primary}\n${hint}${raw}`);
      if (error.code === "PROVIDER_STATE_CHANGED") await providers.refetch();
    }
  };

  const createWithRecommended = () => {
    const extra = Math.max(1, fullPipelineShortfall);
    void submit({ mode: "recommended_worst_case", extra_requests: extra });
  };
  const createWithEstimated = () => {
    const estimatedShortfall = Math.max(0, fullExpected - remainingRequests);
    const extra = estimatedShortfall > 0 ? estimatedShortfall : Math.max(1, Math.ceil(fullPipelineShortfall / 2));
    void submit({ mode: "estimated_usage", extra_requests: extra });
  };

  return (
    <div className="modal-backdrop" data-testid="start-analysis-backdrop">
      <div
        ref={dialogRef}
        className="modal modal-start-analysis"
        role="dialog"
        aria-modal="true"
        aria-labelledby="start-analysis-title"
        data-testid="start-analysis-dialog"
        data-developer-mode={developerMode ? "1" : "0"}
      >
        <header className="modal-header">
          <h2 id="start-analysis-title">开始分析</h2>
          <button type="button" className="modal-close" aria-label="关闭" onClick={onClose}>×</button>
        </header>

        <div className="modal-body" data-testid="start-analysis-modal-body">
          <section className="start-analysis-section">
            <label className="start-analysis-field">
              <span className="start-analysis-field-label">分析范围</span>
              <select aria-label="分析范围">
                <option>当前章节</option>
                <option disabled>全书（后续开放）</option>
              </select>
            </label>
            <p className="hint">当前仅支持分析单个章节；全书分析将在后续版本开放。</p>
          </section>

          <section className="start-analysis-section">
            <span className="start-analysis-field-label">执行方式</span>
            {developerMode ? (
              <>
                <label className="start-analysis-field">
                  <select
                    aria-label="执行方式"
                    value={mode}
                    onChange={(event) => {
                      setMode(event.target.value);
                      setProvider("");
                      setMessage("");
                      setPreflight(null);
                      void providers.refetch();
                    }}
                  >
                    <option value="local">本地分析</option>
                    <option value="cloud">云端 AI</option>
                    <option value="hybrid">混合</option>
                  </select>
                </label>
                <p className="hint">{EXECUTION_HINTS[mode] || ""}</p>
              </>
            ) : (
              <div className="start-analysis-execution-static" data-testid="start-analysis-execution-static">
                <span className="start-analysis-execution-value">云端 AI</span>
                <p className="hint">章节正文将发送至云端模型进行场景边界识别与分析。</p>
              </div>
            )}
          </section>

          <section className="start-analysis-section">
            <div className="start-analysis-section-head">
              <span className="start-analysis-field-label">AI 服务</span>
              <button
                type="button"
                className="ghost"
                data-testid="start-analysis-refresh-status"
                disabled={providers.isFetching}
                onClick={async () => {
                  await invalidateAiQueries(queryClient);
                  await Promise.all([
                    providers.refetch(),
                    executionPlanQuery.refetch(),
                    configuration.refetch(),
                    cloud.refetch(),
                    cloudUsage.refetch(),
                    budgetSettings.refetch(),
                  ]);
                  setMessage(developerMode ? "Provider 状态已刷新。" : "服务状态已刷新。");
                }}
              >
                {providers.isFetching ? "刷新中……" : "刷新状态"}
              </button>
            </div>

            {!developerMode && (
              <div className="ai-service-summary" data-testid="start-analysis-ai-summary">
                {planAllowsStart ? (
                  <>
                    <p data-testid="start-analysis-ai-connected">
                      <b>{aiView.serviceDisplayName}</b>
                      {" · "}
                      {executionPlan?.selected_model || aiView.modelDisplayName}
                    </p>
                    <p className="ai-connected-label">已连接</p>
                    <Link
                      to="/settings?tab=ai&focus=api_key"
                      data-testid="start-analysis-reconfigure-qwen"
                      onClick={onClose}
                    >
                      去配置 AI 服务
                    </Link>
                  </>
                ) : (
                  <>
                    <p data-testid="start-analysis-ai-disconnected">
                      {unavailableReason || "AI 服务尚未连接"}
                    </p>
                    <Link
                      to="/settings?tab=ai&focus=api_key"
                      data-testid="start-analysis-goto-settings"
                      onClick={onClose}
                    >
                      去配置 AI 服务
                    </Link>
                  </>
                )}
                <p className="hint" data-testid="start-analysis-connection-label">
                  连接状态：{aiView.userStatusLabel}
                </p>
              </div>
            )}

            {developerMode && (
              <>
                {eligible.length === 0 && !planAllowsStart ? (
                  <div data-testid="start-analysis-no-provider">
                    <p>{unavailableReason || "当前没有可用 Provider"}</p>
                    <Link to="/settings?tab=ai&focus=api_key" onClick={onClose}>
                      去配置 AI 服务
                    </Link>
                  </div>
                ) : (
                  <label className="start-analysis-field">
                    <span className="sr-only">Provider</span>
                    <select
                      aria-label="Provider"
                      value={provider}
                      onChange={(event) => setProvider(event.target.value)}
                      data-testid="start-analysis-provider-select"
                    >
                      {(eligible.length > 1 || (eligible.length === 0 && planAllowsStart)) && (
                        <option value="">请选择</option>
                      )}
                      {(eligible.length > 0
                        ? eligible
                        : (providers.data || []).filter((p) => p.name === DEFAULT_AI_SERVICE_ID)
                      ).map((item) => (
                        <option key={item.name} value={item.name}>
                          {formatProviderOptionLabel(item, eligible.length ? eligible : [item])}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                {selected && (
                  <p className="hint" data-testid="start-analysis-provider-hint">
                    {formatProviderStatusHint(selected)}
                  </p>
                )}
                {selected?.requires_boundary_review && (
                  <p className="notice">
                    本次会先识别场景边界。确认边界后，StoryLens 会继续完成场景分析。
                  </p>
                )}
              </>
            )}
          </section>

          <section className="start-analysis-section" data-testid="start-analysis-mode-section">
            <span className="start-analysis-field-label">分析模式</span>
            <div className="analysis-mode-cards" role="radiogroup" aria-label="分析模式">
              {analysisModeCards.map((preset) => (
                <label
                  key={preset.id}
                  className={`analysis-mode-card ${analysisModePreset === preset.id ? "is-selected" : ""}`}
                  data-testid={`analysis-mode-${preset.id.toLowerCase()}`}
                >
                  <input
                    type="radio"
                    name="start-analysis-mode"
                    value={preset.id}
                    checked={analysisModePreset === preset.id}
                    onChange={() => handleAnalysisModeSelect(preset.id)}
                  />
                  <span>
                    <strong data-testid={`analysis-mode-label-${preset.id.toLowerCase()}`}>
                      {preset.recommended
                        ? `${preset.shortLabel} · 推荐`
                        : preset.shortLabel || preset.label}
                    </strong>
                    {preset.id !== "CUSTOM" && (
                      <small>{MODE_CARD_HINT[preset.id as "FAST" | "BALANCED" | "QUALITY"]}</small>
                    )}
                    {preset.id === "CUSTOM" && (
                      <small>使用设置中的自定义 Provider 与预算参数</small>
                    )}
                  </span>
                </label>
              ))}
            </div>
            <p className="hint" data-testid="start-analysis-mode-hint">
              {analysisModePreset === "CUSTOM"
                ? "自定义模式（开发者）"
                : MODE_CARD_HINT[analysisModePreset as "FAST" | "BALANCED" | "QUALITY"] ||
                  "分析模式影响设置中的模型与预算偏好，不改变本次任务的边界审阅流程。"}
            </p>
          </section>

          {(mode === "cloud" || mode === "hybrid") && preflight && consent && !developerMode && (
            <OrdinaryBudgetSummary
              preflight={preflight}
              estimatedFits={stage1RequestShortfall === 0 && !tokenBlocked && !costBlocked}
              retryReserveTight={fullPipelineShortfall > 0 || (Number(preflight?.worst_case_request_count) || 0) > remainingRequests}
            />
          )}

          {(mode === "cloud" || mode === "hybrid") && preflight && (
            <>
              {developerMode && (
                <Stage1BudgetSummary preflight={preflight} budgetBlocked={budgetBlocked} />
              )}
              {showRequestQuotaPanel && requestOnly && (
                <RequestQuotaBlockPanel
                  required={requestOnly.required ?? stage1Estimated}
                  available={requestOnly.available ?? remainingRequests}
                  shortfall={requestOnly.shortfall ?? stage1RequestShortfall}
                  estimated={requestOnly.estimated ?? stage1Estimated}
                  worstCase={requestOnly.worstCase ?? (Number(preflight?.worst_case_request_count) || fullWorst)}
                  costAndTokenOk={costAndTokenOk}
                  detailOpen={budgetDetailOpen}
                  onToggleDetail={() => setBudgetDetailOpen((v) => !v)}
                  onCreateRecommended={createWithRecommended}
                  onCreateEstimated={createWithEstimated}
                  busy={busy}
                />
              )}
              <HardBudgetBlockers blockers={createBlockers} />
              {(developerMode || budgetDetailOpen) && (
                <FullPipelineBudgetAdvisory
                  advisory={fullAdvisory}
                  preflight={preflight}
                  usage={cloudUsage.data}
                  budget={budgetSettings.data}
                  detailOpen={developerMode || budgetDetailOpen || !showRequestQuotaPanel}
                />
              )}
            </>
          )}

          {(mode === "cloud" || mode === "hybrid") && (
            <label className="consent start-analysis-consent">
              <input
                type="checkbox"
                checked={consent}
                onChange={(event) => setConsent(event.target.checked)}
              />
              <span>
                <strong>正文发送说明</strong>
                <br />
                我确认所选章节正文将发送至云端模型服务。
              </span>
            </label>
          )}

          {developerMode && (
            <details className="start-analysis-tech-details" data-testid="start-analysis-tech-details">
              <summary>技术详情</summary>
              <div className="advanced">
                <b>Provider</b>
                <span>ID：{selected?.name || provider || "—"}</span>
                <span>Model：{selected?.default_model || "—"}</span>
                {selected?.workflow_prompts ? (
                  <>
                    <span>Boundary Candidate Prompt：{selected.workflow_prompts.boundary_candidate}</span>
                    <span>Boundary Adjudication Prompt：{selected.workflow_prompts.boundary_adjudication}</span>
                    <span>Scene Analysis Prompt：{selected.workflow_prompts.scene_analysis}</span>
                    <span>Thinking：{selected.workflow_prompts.thinking ? "开启" : "关闭"}</span>
                    <span>边界确认：人工确认</span>
                  </>
                ) : (
                  <span>任务协议由后端 Provider 能力配置决定</span>
                )}
              </div>
              {(mode === "cloud" || mode === "hybrid") && (
                <div className="provider-diagnostics">
                  {providers.isError ? (
                    <p>Provider 状态接口离线：{String(providers.error)}</p>
                  ) : (
                    cloudDiagnostics.map(({ item, eligibility }) => (
                      <div key={item.name}>
                        <b>{item.name}</b>
                        <span>
                          手动边界资格：
                          {eligibility.status === "eligible"
                            ? "可用"
                            : eligibility.status === "blocked"
                              ? "阻塞"
                              : "未知"}
                        </span>
                        <span>
                          原始值：
                          {typeof item.manual_boundary_candidate_eligible === "boolean"
                            ? String(item.manual_boundary_candidate_eligible)
                            : "missing"}
                        </span>
                        <span>Schema：{item.capability_schema_version || "missing"}</span>
                        <span>检查时间：{item.evaluated_at || "missing"}</span>
                        <span>
                          健康状态：{item.health_state || "unknown"}（{item.health_source || "unknown"}）
                        </span>
                        <span>
                          {eligibility.status === "unknown"
                            ? PROVIDER_ELIGIBILITY_MISSING
                            : eligibility.blockers.join("、") || "资格明确可用"}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              )}
            </details>
          )}

          {message && <p className="notice">{message}</p>}
        </div>

        <footer className="modal-footer" data-testid="start-analysis-modal-footer">
          <button type="button" onClick={onClose}>取消</button>
          <div className="start-analysis-footer-actions">
            {!showRequestQuotaPanel && effectiveSubmitDisabled && submitDisabledReason && (
              <span className="start-analysis-disabled-reason" data-testid="start-analysis-disabled-reason">
                {submitDisabledReason}
              </span>
            )}
            <Link
              to="/settings?tab=cost"
              className="button-link"
              data-testid="start-analysis-adjust-quota"
              onClick={() => {
                try {
                  sessionStorage.setItem(
                    "storylens.startAnalysis.resumeChapterId",
                    String(chapterId),
                  );
                } catch {
                  /* ignore */
                }
              }}
            >
              调整额度
            </Link>
            {!showRequestQuotaPanel && (
              <button
                type="button"
                className="primary"
                data-testid="start-analysis-submit"
                disabled={effectiveSubmitDisabled}
                onClick={() => void submit()}
              >
                {busy ? submitLabel : "按当前额度开始"}
              </button>
            )}
            {showRequestQuotaPanel && (
              <button
                type="button"
                className="primary"
                data-testid="start-analysis-submit"
                disabled={busy || !costAndTokenOk}
                onClick={createWithRecommended}
              >
                {busy ? submitLabel : "按推荐额度创建任务"}
              </button>
            )}
          </div>
        </footer>
      </div>
    </div>
  );
}
