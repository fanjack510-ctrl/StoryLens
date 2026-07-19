import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { providersApi } from "../../services/providersApi";
import { analysisApi } from "../../services/analysisApi";
import { settingsApi } from "../../services/settingsApi";
import { analysisRecoveryApi } from "../../services/analysisRecoveryApi";
import {
  manualBoundaryEligibility,
  PROVIDER_ELIGIBILITY_MISSING,
} from "../../services/providerEligibility";
import { ApiError } from "../../services/apiClient";
import { useDeveloperModeStore } from "../../stores/developerModeStore";
import {
  DEFAULT_AI_SERVICE_ID,
  buildAiServiceViewModel,
} from "../../services/aiServiceViewModel";
import { BUDGET_ERROR_USER_COPY } from "../../services/budgetErrorCopy";
import {
  estimateFullPipelineRequests,
  fullPipelineRequestShortfall,
  requestOnlyShortfall,
  type CreateBudgetBlocker,
} from "../../services/budgetRecoveryMath";

function formatBudgetGaps(preflight: any): string {
  const dims: string[] = preflight?.exceeded_dimensions || [];
  if (!dims.length) return "";
  const required = {
    requests: preflight.worst_case_request_count,
    tokens: preflight.worst_case_total_tokens,
    estimated_cost: preflight.worst_case_cost,
  };
  const remaining = preflight.remaining || {};
  return dims.map((dim) => {
    if (dim === "requests") {
      return `请求不足：最坏需要${required.requests}次，当前剩余${remaining.requests}次。`;
    }
    if (dim === "tokens") {
      return `Token不足：最坏需要${required.tokens} Token，当前剩余${remaining.tokens} Token。`;
    }
    return `费用不足：最坏需要约${required.estimated_cost} CNY，当前剩余约${remaining.estimated_cost} CNY。`;
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
      <h3>本阶段仅生成场景边界候选</h3>
      <p>本阶段不会执行Scene Analysis。人工确认边界后，系统会根据最终Scene数量重新估算Scene Analysis预算。</p>
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
        本章完整分析最坏需要{worstCase}次云端请求，当前今日剩余{available}次，还差{shortfall}次。
        {costAndTokenOk ? "费用和Token预算充足。" : ""}
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

export function StartAnalysisDialog({ chapterId, onClose, onCreated }: { chapterId: number; onClose: () => void; onCreated?: (runId: number) => void }) {
  const developerMode = useDeveloperModeStore((s) => s.developerMode);
  const [mode, setMode] = useState(developerMode ? "local" : "cloud");
  const [provider, setProvider] = useState(developerMode ? "" : DEFAULT_AI_SERVICE_ID);
  const [consent, setConsent] = useState(false);
  const [message, setMessage] = useState("");
  const [preflight, setPreflight] = useState<any>(null);
  const [fullAdvisory, setFullAdvisory] = useState<any>(null);
  const [budgetDetailOpen, setBudgetDetailOpen] = useState(false);
  const [submitState, setSubmitState] = useState<"idle" | "checking" | "creating" | "created" | "failed">("idle");
  const clientRequestId = useRef(crypto.randomUUID());
  const dialogRef = useRef<HTMLDivElement>(null);
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
      (providers.data || []).find((p) => p.name === DEFAULT_AI_SERVICE_ID) ||
      (providers.data || []).find((p) => p.capabilities?.cloud) ||
      null,
    [providers.data],
  );

  const aiView = useMemo(
    () =>
      buildAiServiceViewModel({
        provider: developerMode ? selected || defaultProvider : defaultProvider,
        configuration: configuration.data,
        cloudEnabled: cloud.data?.enabled ?? true,
      }),
    [developerMode, selected, defaultProvider, configuration.data, cloud.data?.enabled],
  );

  useEffect(() => {
    if (developerMode) return;
    if (defaultProvider?.name && provider !== defaultProvider.name) {
      setProvider(defaultProvider.name);
    }
    if (mode !== "cloud") setMode("cloud");
  }, [developerMode, defaultProvider, provider, mode]);

  useEffect(() => {
    if (provider && !eligible.some((item) => item.name === provider)) {
      if (developerMode) setProvider("");
    }
  }, [eligible, provider, developerMode]);

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
  const fullPipelineShortfall = fullPipelineRequestShortfall({
    remainingRequests,
    fullWorstRequests: fullWorst,
  });

  const advisoryExceeded: string[] = fullAdvisory?.exceeded_dimensions || [];
  const tokenBlocked = advisoryExceeded.includes("tokens")
    || (typeof fullAdvisory?.worst_case_tokens === "number"
      && remainingTokens < fullAdvisory.worst_case_tokens);
  const costBlocked = advisoryExceeded.includes("estimated_cost")
    || (typeof fullAdvisory?.worst_case_cost === "number"
      && remainingCost + 1e-9 < fullAdvisory.worst_case_cost);
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
    if (!developerMode && !aiView.canStartAnalysis) {
      list.push({
        dimension: "provider",
        title: "Qwen 尚未连接",
        userMessage: "AI 服务尚未连接，请先完成连接测试。",
        required: null,
        available: null,
        shortfall: null,
        estimated: null,
        worstCase: null,
      });
    }
    if (fullPipelineShortfall > 0 && preflight) {
      list.push({
        dimension: "requests",
        title: "当前技术请求额度不足",
        userMessage: `本章完整分析最坏需要${fullWorst}次云端请求，当前今日剩余${remainingRequests}次，还差${fullPipelineShortfall}次。`,
        required: fullWorst,
        available: remainingRequests,
        shortfall: fullPipelineShortfall,
        estimated: fullExpected,
        worstCase: fullWorst,
      });
    }
    if (tokenBlocked && preflight) {
      const required = Number(fullAdvisory?.worst_case_tokens) || 0;
      list.push({
        dimension: "tokens",
        title: "当前 Token 额度不足",
        userMessage: `完整分析最坏约需 ${required} Token，当前剩余 ${remainingTokens}。`,
        required,
        available: remainingTokens,
        shortfall: Math.max(0, required - remainingTokens),
        estimated: Number(fullAdvisory?.estimated_tokens) || null,
        worstCase: required,
      });
    }
    if (costBlocked && preflight) {
      const required = Number(fullAdvisory?.worst_case_cost) || 0;
      list.push({
        dimension: "estimated_cost",
        title: "当前费用额度不足",
        userMessage: `完整分析最坏约需 ${required} CNY，当前剩余约 ${remainingCost} CNY。`,
        required,
        available: remainingCost,
        shortfall: Math.max(0, Math.round((required - remainingCost) * 1000) / 1000),
        estimated: Number(fullAdvisory?.estimated_cost) || null,
        worstCase: required,
      });
    }
    return list;
  }, [
    developerMode,
    aiView.apiKeyConfigured,
    aiView.canStartAnalysis,
    fullPipelineShortfall,
    preflight,
    fullWorst,
    remainingRequests,
    fullExpected,
    tokenBlocked,
    costBlocked,
    fullAdvisory,
    remainingTokens,
    remainingCost,
  ]);

  const requestOnly = requestOnlyShortfall(createBlockers);
  const busy = submitState === "checking" || submitState === "creating" || providers.isFetching;

  // Ordinary: do NOT hard-disable solely for request shortfall — show recovery panel instead.
  // Still disable for Stage-1 hard block, missing consent/connection, or cost/token hard blocks.
  const hardCreateBlocked = budgetBlocked || tokenBlocked || costBlocked
    || (!developerMode && (!aiView.canStartAnalysis || !consent));
  const effectiveSubmitDisabled = developerMode
    ? busy || budgetBlocked || (fullPipelineShortfall > 0 && !requestOnly)
    : busy || hardCreateBlocked || (fullPipelineShortfall > 0 && !requestOnly);

  const showRequestQuotaPanel = Boolean(requestOnly && consent && preflight && !budgetBlocked);

  const submitLabel = providers.isFetching && (submitState === "idle" || submitState === "failed")
    ? (developerMode ? "正在刷新Provider……" : "正在刷新服务状态……")
    : submitState === "checking"
      ? "正在检查预算……"
      : submitState === "creating"
        ? "正在创建任务……"
        : "创建任务";

  const submit = async (allowance?: {
    mode: "recommended_worst_case" | "estimated_usage";
    extra_requests: number;
  }) => {
    if (submitState === "checking" || submitState === "creating") return;
    if (!developerMode && !aiView.canStartAnalysis) {
      return setMessage("AI服务尚未连接，请前往设置完成配置。");
    }
    if ((mode === "cloud" || mode === "hybrid") && !consent) return setMessage("请先确认云端传输同意。");
    if (!provider) return setMessage(developerMode ? "请选择可用 Provider。" : "AI服务尚未连接。");
    if (budgetBlocked) return setMessage(formatBudgetGaps(preflight) || "当前Stage 1预算不足。");
    if ((tokenBlocked || costBlocked) && !allowance) {
      return setMessage("费用或Token预算不足，请先调整每日费用上限或等待额度恢复。");
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
        setSubmitState("failed");
        return setMessage(formatBudgetGaps(checked) || "当前Stage 1预算不足。");
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
      setSubmitState("created");
      setMessage(`任务已创建，Run ID：${run.run_id}。将在本章显示分析进度。`);
      onClose();
      if (onCreated) onCreated(run.run_id); else window.location.href = `/tasks?run_id=${run.run_id}`;
    } catch (error: any) {
      setSubmitState("failed");
      const dimGaps = formatBudgetGaps({
        exceeded_dimensions: error.exceededDimensions || error.detail?.exceeded_dimensions,
        worst_case_request_count: error.required?.requests,
        worst_case_total_tokens: error.required?.tokens,
        worst_case_cost: error.required?.estimated_cost,
        remaining: error.remaining,
      });
      const messages: Record<string, string> = {
        NO_MANUAL_BOUNDARY_PROVIDER: "当前没有可用于人工边界审阅的AI服务。",
        PROVIDER_UNHEALTHY: "当前AI服务健康检查失败，请前往设置查看连接状态。",
        PROVIDER_HEALTH_STALE: "AI服务健康状态已过期，请刷新状态或重新测试连接。",
        PROVIDER_NOT_CONNECTED: "AI服务尚未连接。",
        CLOUD_MASTER_SWITCH_OFF: "云端AI尚未开启。",
        BUDGET_NOT_AVAILABLE: "当前预算或价格配置不满足请求条件。",
        CLOUD_CONSENT_REQUIRED: "请确认当前章节正文将发送至云端模型服务。",
        PROVIDER_STATE_CHANGED: "服务状态已经变化，请刷新后重新确认。",
        FULL_PIPELINE_HARD_BUDGET_INSUFFICIENT:
          "费用或Token预算不足以覆盖完整分析。临时技术请求授权不能突破每日费用上限。",
        INSUFFICIENT_BUDGET_RESERVATION:
          dimGaps || BUDGET_ERROR_USER_COPY.INSUFFICIENT_BUDGET_RESERVATION,
        CLOUD_REQUEST_LIMIT_EXCEEDED: BUDGET_ERROR_USER_COPY.CLOUD_REQUEST_LIMIT_EXCEEDED,
        CLOUD_TOKEN_LIMIT_EXCEEDED: BUDGET_ERROR_USER_COPY.CLOUD_TOKEN_LIMIT_EXCEEDED,
        CLOUD_COST_LIMIT_EXCEEDED: BUDGET_ERROR_USER_COPY.CLOUD_COST_LIMIT_EXCEEDED,
        CLOUD_BUDGET_EXCEEDED: BUDGET_ERROR_USER_COPY.CLOUD_BUDGET_EXCEEDED,
      };
      const isNetwork = !("status" in (error || {}));
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
          <label>分析范围<select aria-label="分析范围"><option>当前章节</option><option disabled>全书（后续开放）</option></select></label>

          {!developerMode && (
            <div className="ai-service-summary" data-testid="start-analysis-ai-summary">
              {aiView.canStartAnalysis ? (
                <>
                  <p data-testid="start-analysis-ai-connected">
                    <b>{aiView.serviceDisplayName}</b>
                    {" · "}
                    {aiView.modelDisplayName}
                  </p>
                  <p className="ai-connected-label">已连接</p>
                  <Link
                    to="/settings?tab=ai&focus=api_key"
                    data-testid="start-analysis-reconfigure-qwen"
                    onClick={onClose}
                  >
                    配置阿里云百炼 · Qwen
                  </Link>
                </>
              ) : (
                <>
                  <p data-testid="start-analysis-ai-disconnected">AI服务尚未连接</p>
                  <Link
                    to="/settings?tab=ai&focus=api_key"
                    data-testid="start-analysis-goto-settings"
                    onClick={onClose}
                  >
                    配置阿里云百炼 · Qwen
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
              <label>执行模式<select aria-label="执行模式" value={mode} onChange={(event) => {
                setMode(event.target.value); setProvider(""); setMessage(""); setPreflight(null); void providers.refetch();
              }}><option value="local">本地</option><option value="cloud">云端</option><option value="hybrid">混合</option></select></label>
              <button type="button" disabled={providers.isFetching} onClick={async () => {
                await providers.refetch(); setMessage("Provider状态已刷新。");
              }}>{providers.isFetching ? "刷新中……" : "刷新Provider状态"}</button>
              <label>Provider<select aria-label="Provider" value={provider} onChange={(event) => setProvider(event.target.value)} data-testid="start-analysis-provider-select">
                <option value="">请选择</option>{eligible.map((item) => <option key={item.name} value={item.name}>
                  {item.name} · {item.default_model}{item.requires_boundary_review ? " · 云端 · 边界候选生成 · 需要人工确认" : ""}
                </option>)}
              </select></label>
              {selected?.requires_boundary_review && <p className="notice">该Provider只生成场景边界候选。候选完成后需要人工确认，确认后才会执行Scene Analysis。</p>}
            </>
          )}

          {(mode === "cloud" || mode === "hybrid") && preflight && (
            <>
              {(developerMode || budgetDetailOpen) && (
                <Stage1BudgetSummary preflight={preflight} budgetBlocked={budgetBlocked} />
              )}
              {showRequestQuotaPanel && requestOnly && (
                <RequestQuotaBlockPanel
                  required={requestOnly.required ?? fullWorst}
                  available={requestOnly.available ?? remainingRequests}
                  shortfall={requestOnly.shortfall ?? fullPipelineShortfall}
                  estimated={requestOnly.estimated ?? fullExpected}
                  worstCase={requestOnly.worstCase ?? fullWorst}
                  costAndTokenOk={costAndTokenOk}
                  detailOpen={budgetDetailOpen}
                  onToggleDetail={() => setBudgetDetailOpen((v) => !v)}
                  onCreateRecommended={createWithRecommended}
                  onCreateEstimated={createWithEstimated}
                  busy={busy}
                />
              )}
              <HardBudgetBlockers blockers={createBlockers} />
              <FullPipelineBudgetAdvisory
                advisory={fullAdvisory}
                preflight={preflight}
                usage={cloudUsage.data}
                budget={budgetSettings.data}
                detailOpen={developerMode || budgetDetailOpen || !showRequestQuotaPanel}
              />
            </>
          )}

          {developerMode && (
            <div className="advanced"><b>高级设置</b>{selected?.workflow_prompts ? <>
              <span>Boundary Candidate Prompt：{selected.workflow_prompts.boundary_candidate}</span>
              <span>Boundary Adjudication Prompt：{selected.workflow_prompts.boundary_adjudication}</span>
              <span>Scene Analysis Prompt：{selected.workflow_prompts.scene_analysis}</span>
              <span>Thinking：{selected.workflow_prompts.thinking ? "开启" : "关闭"}</span><span>边界确认：人工确认</span>
            </> : <span>任务协议由后端Provider能力配置决定</span>}</div>
          )}

          {developerMode && (mode === "cloud" || mode === "hybrid") && (
            <details className="provider-diagnostics">
              <summary>Provider诊断</summary>
              {providers.isError ? <p>Provider状态接口离线：{String(providers.error)}</p> :
                cloudDiagnostics.map(({ item, eligibility }) => <div key={item.name}>
                  <b>{item.name}</b><span>手动边界资格：{eligibility.status === "eligible" ? "可用" : eligibility.status === "blocked" ? "阻塞" : "未知"}</span>
                  <span>原始值：{typeof item.manual_boundary_candidate_eligible === "boolean" ? String(item.manual_boundary_candidate_eligible) : "missing"}</span>
                  <span>Schema：{item.capability_schema_version || "missing"}</span><span>检查时间：{item.evaluated_at || "missing"}</span>
                  <span>健康状态：{item.health_state || "unknown"}（{item.health_source || "unknown"}）</span>
                  <span>{eligibility.status === "unknown" ? PROVIDER_ELIGIBILITY_MISSING : eligibility.blockers.join("、") || "资格明确可用"}</span>
                </div>)}
            </details>
          )}

          {(mode === "cloud" || mode === "hybrid") && (
            <label className="consent">
              <input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} />
              我确认所选章节正文将发送到云端模型服务。
            </label>
          )}
          {message && <p className="notice">{message}</p>}
        </div>

        <footer className="modal-footer" data-testid="start-analysis-modal-footer">
          <button type="button" onClick={onClose}>取消</button>
          {!showRequestQuotaPanel && (
            <button
              type="button"
              className="primary"
              data-testid="start-analysis-submit"
              disabled={effectiveSubmitDisabled}
              onClick={() => void submit()}
            >
              {submitLabel}
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
        </footer>
      </div>
    </div>
  );
}
