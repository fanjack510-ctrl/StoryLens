/** 「AI 与模型」：一屏，一套配置。
 *
 *  改版前这一页叠着**两套互不相干的服务商配置**：一套是通用的（服务商下拉 + 各家表单），
 *  另一套是只为通义千问写的一键配置旧路径。它们各有自己的 API Key、同意勾选、保存与验证
 *  按钮、状态显示。于是用户看到的是——上面「AI服务」写死 `阿里云百炼（推荐）`，下面「当前
 *  默认服务」却是 DeepSeek。
 *
 *  所以按钮不是「多」，是**成对重复**。合成一套之后，7 个按钮自然降到 1 主 + 1 次，
 *  不需要专门去减。
 *
 *  版面是「左标签右控件」的行式表单：一行一件事，行与行之间只有一条细线。设置页不是给人
 *  从头读到尾的，是给人**找一件事改一件事**的——左边一列稳定的标签，正是让眼睛能沿着它
 *  往下扫。
 *
 *  两条贯穿始终：
 *
 *  **一件事只有一个说法。** 一个服务商、一个密钥、一个状态、一个主按钮。
 *
 *  **说不出就说不出。** 状态、可用性、拦路原因全部由后端给（INV-P4），客户端不自己拼文案，
 *  也不在拿不到数据时编一个像样的默认值。
 */
import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchAiConnection } from "../../services/aiConnection";
import { providersApi } from "../../services/providersApi";
import { settingsApi } from "../../services/settingsApi";
import {
  DEFAULT_ANALYSIS_MODE,
  readStoredAnalysisMode,
  writeStoredAnalysisMode,
  type AnalysisModePresetId,
} from "../../services/analysisModePresets";
import { AdvancedBudgetGate } from "./AdvancedBudgetGate";
import { Loading } from "../common/States";
import "./settings.css";

type ModelTier = {
  id: string;
  label: string;
  hint?: string;
  pricing_known?: boolean;
  recommended?: boolean;
};

const DEPTH_OPTIONS: Array<{ id: AnalysisModePresetId; label: string }> = [
  { id: "FAST", label: "快速 · 省钱" },
  { id: "BALANCED", label: "均衡 · 推荐" },
  { id: "QUALITY", label: "高质量 · 更慢更贵" },
];

/** 一行：左边标签与说明，右边控件。 */
function Row({
  label,
  hint,
  children,
  testId,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
  testId?: string;
}) {
  return (
    <div className="ai-row" data-testid={testId}>
      <div className="ai-row-label">
        <b>{label}</b>
        {hint ? <span>{hint}</span> : null}
      </div>
      <div className="ai-row-control">{children}</div>
    </div>
  );
}

function toneOf(state: string): "ok" | "warn" | "idle" {
  if (state === "connected") return "ok";
  if (state === "unconfigured") return "idle";
  return "warn";
}

export function AiConnectionPanel({ focusApiKey = false }: { focusApiKey?: boolean }) {
  const qc = useQueryClient();
  const [apiKey, setApiKey] = useState("");
  const [editingKey, setEditingKey] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [baseUrl, setBaseUrl] = useState("");
  const [baseUrlDirty, setBaseUrlDirty] = useState(false);
  const [busy, setBusy] = useState<"save" | "verify" | "disconnect" | "delete" | "cloud" | null>(
    null,
  );
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);
  const [depth, setDepth] = useState<AnalysisModePresetId>(() => {
    const stored = readStoredAnalysisMode();
    return stored === "CUSTOM" ? DEFAULT_ANALYSIS_MODE : stored;
  });

  const connection = useQuery({
    queryKey: ["ai-connection"],
    queryFn: fetchAiConnection,
    refetchOnMount: "always",
    staleTime: 0,
  });
  const active = useQuery({
    queryKey: ["active-cloud-provider"],
    queryFn: settingsApi.activeCloudProvider,
    refetchOnMount: "always",
    staleTime: 0,
  });

  const options = active.data?.options ?? [];
  const selectedId = active.data?.provider_name || options[0]?.name || "";
  const selected = options.find((o) => o.name === selectedId);
  const tiers = ((selected as { model_tiers?: ModelTier[] } | undefined)?.model_tiers ??
    []) as ModelTier[];

  const configuration = useQuery({
    queryKey: ["provider-config", selectedId],
    queryFn: () => providersApi.configuration(selectedId),
    enabled: Boolean(selectedId),
  });

  const [model, setModel] = useState("");
  useEffect(() => {
    if (configuration.data?.plus_model) setModel(String(configuration.data.plus_model));
  }, [configuration.data?.plus_model]);
  useEffect(() => {
    // 用户改过就不要再被后台刷新覆盖——正在输入的地址被悄悄改回去，比报错还难查。
    if (!baseUrlDirty) setBaseUrl(String(configuration.data?.base_url || ""));
  }, [configuration.data?.base_url, baseUrlDirty]);

  useEffect(() => {
    if (focusApiKey) {
      setEditingKey(true);
      document.querySelector<HTMLInputElement>('[data-testid="ai-api-key-input"]')?.focus();
    }
  }, [focusApiKey]);

  const status = connection.data;
  const tone = toneOf(status?.connection_state || "unconfigured");
  const keySaved = Boolean(status?.credential_configured);

  const refreshAll = async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ["ai-connection"] }),
      qc.invalidateQueries({ queryKey: ["active-cloud-provider"] }),
      qc.invalidateQueries({ queryKey: ["provider-config", selectedId] }),
      qc.invalidateQueries({ queryKey: ["whole-book-v2-prepare"] }),
      qc.invalidateQueries({ queryKey: ["routing"] }),
    ]);
  };

  const switchProvider = async (next: string) => {
    if (busy || next === selectedId) return;
    setBusy("save");
    setMessage("");
    setFailed(false);
    try {
      await settingsApi.setActiveCloudProvider(next);
      setApiKey("");
      setEditingKey(false);
      await refreshAll();
    } catch (error: unknown) {
      setFailed(true);
      setMessage(error instanceof Error ? error.message : "切换服务商失败");
    } finally {
      setBusy(null);
    }
  };

  /**
   * 先传输诊断、再打一次真实的最小调用。
   *
   * 只做传输诊断不够：写「验证快照」的是真实调用，而分析前的预检读的正是那份快照。少了它，
   * 距离上一次真实探测 24 小时后，「分析本章」会永久变灰（PROVIDER_HEALTH_STALE），
   * 而设置页里没有任何按钮能解开——诊断证明的是管子通，不是服务商能用。
   */
  const verify = async ({ silent = false }: { silent?: boolean } = {}) => {
    if (!silent && busy) return;
    if (!silent) {
      setBusy("verify");
      setMessage("");
      setFailed(false);
    }
    try {
      await providersApi.transportDiagnostic(selectedId);
      await providersApi.testConnection(selectedId, 32);
      if (!silent) setMessage("连接正常。");
    } catch (error: unknown) {
      setFailed(true);
      const code = String((error as { code?: string })?.code || "");
      setMessage(
        code === "PROVIDER_AUTHENTICATION_FAILED" || code.includes("401")
          ? "API Key 无效"
          : code === "PROVIDER_INSUFFICIENT_BALANCE" || code.includes("402")
            ? "服务商账户余额不足"
            : code.includes("429")
              ? "请求过快，稍后再试"
              : error instanceof Error
                ? error.message
                : "验证失败",
      );
    } finally {
      if (!silent) {
        setBusy(null);
        await refreshAll();
      }
    }
  };

  /** 保存与验证合成一个动作：保存完不验证，等于让人自己去点第二下。 */
  const save = async () => {
    if (busy || !configuration.data) return;
    setBusy("save");
    setMessage("");
    setFailed(false);
    try {
      const current = configuration.data;
      await providersApi.save(selectedId, {
        display_name: current.display_name,
        region: current.region || "",
        workspace_id: current.workspace_id || "",
        base_url: baseUrl.trim() || null,
        plus_model: model || current.plus_model,
        max_model: model || current.plus_model,
        flash_model: model || current.plus_model,
        timeout_seconds: current.timeout_seconds ?? 300,
        max_retries: current.max_retries ?? 3,
        enabled: true,
        disconnected: false,
        allow_auto_route: Boolean(current.allow_auto_route),
        raw_logging_enabled: Boolean(current.raw_logging_enabled),
        api_key: apiKey || null,
      });
      await settingsApi.setActiveCloudProvider(selectedId);
      writeStoredAnalysisMode(depth);
      setApiKey("");
      setEditingKey(false);
      setBaseUrlDirty(false);
      await verify({ silent: true });
      setMessage("已保存并验证。");
    } catch (error: unknown) {
      setFailed(true);
      setMessage(error instanceof Error ? error.message : "保存失败");
    } finally {
      setBusy(null);
      await refreshAll();
    }
  };

  const disconnect = async () => {
    if (busy) return;
    setBusy("disconnect");
    setMessage("");
    setFailed(false);
    try {
      await providersApi.action(selectedId, "disconnect");
      setMessage("已断开。配置和密钥都还在，随时可以重新连接。");
    } catch (error: unknown) {
      setFailed(true);
      setMessage(error instanceof Error ? error.message : "断开失败");
    } finally {
      setBusy(null);
      await refreshAll();
    }
  };

  const removeCredential = async () => {
    if (busy) return;
    const name = status?.display_name || selectedId;
    if (!confirm(`确认删除本机保存的 ${name} 密钥？不影响已完成的分析。`)) return;
    setBusy("delete");
    setMessage("");
    setFailed(false);
    try {
      await providersApi.deleteCredentials(selectedId);
      setMessage("密钥已从本机删除。");
    } catch (error: unknown) {
      setFailed(true);
      setMessage(error instanceof Error ? error.message : "删除失败");
    } finally {
      setBusy(null);
      await refreshAll();
    }
  };

  const toggleCloud = async () => {
    if (busy || !status) return;
    setBusy("cloud");
    setMessage("");
    setFailed(false);
    try {
      await settingsApi.setCloud(!status.cloud_enabled);
    } catch (error: unknown) {
      setFailed(true);
      setMessage(error instanceof Error ? error.message : "切换失败");
    } finally {
      setBusy(null);
      await refreshAll();
    }
  };

  const budgetBlocked = useMemo(
    () => (status?.blockers || []).some((b) => b.includes("budget")),
    [status?.blockers],
  );

  if (connection.isLoading || active.isLoading) {
    return (
      <article className="settings-panel">
        <Loading />
      </article>
    );
  }

  return (
    <article className="settings-panel ai-panel" data-testid="settings-panel-ai-service">
      <header className="ai-panel-head">
        <h2>AI与模型设置</h2>
        <p>配置 AI 服务和模型，开始智能写作与分析</p>
      </header>

      <Row label="AI 服务商" hint="选择要使用的 AI 服务商" testId="ai-provider-row">
        <select
          className="ai-input"
          data-testid="ai-provider-select"
          value={selectedId}
          disabled={Boolean(busy)}
          onChange={(e) => void switchProvider(e.target.value)}
        >
          {options.map((o) => (
            <option key={o.name} value={o.name}>
              {o.display_name || o.name}
            </option>
          ))}
        </select>
      </Row>

      {tiers.length > 0 && (
        <Row label="模型选择" hint="决定质量与成本" testId="ai-model-row">
          <div className="ai-tier-list" data-testid="ai-model-tiers">
            {tiers.map((tier) => (
              <label key={tier.id} className="ai-tier" data-disabled={!tier.pricing_known}>
                <input
                  type="radio"
                  name="ai-model-tier"
                  value={tier.id}
                  checked={model === tier.id}
                  disabled={!tier.pricing_known || Boolean(busy)}
                  onChange={() => setModel(tier.id)}
                />
                <span className="ai-tier-body">
                  <span className="ai-tier-name">
                    {tier.label}
                    {tier.recommended && <em className="ai-pill">推荐</em>}
                  </span>
                  <span className="ai-tier-hint">
                    {tier.hint}
                    {/* 没有价格数据的档位选了会让服务商变成不合格。说出来，而不是让它看起来可选。 */}
                    {tier.pricing_known ? "" : "　暂无价格数据，不能选"}
                  </span>
                </span>
              </label>
            ))}
          </div>
        </Row>
      )}

      <Row
        label="API Key"
        hint={keySaved ? "API Key 已安全保存" : "只保存在本机，不会上传"}
        testId="ai-key-row"
      >
        <div className="ai-key-line">
          {keySaved && !editingKey ? (
            <>
              <input className="ai-input" readOnly value="••••••••••••••••••••" aria-label="API Key 已保存" />
              <button
                type="button"
                className="ai-btn-ghost"
                data-testid="ai-key-reset"
                onClick={() => {
                  setEditingKey(true);
                  setApiKey("");
                }}
              >
                重新设置
              </button>
            </>
          ) : (
            <>
              <input
                className="ai-input"
                data-testid="ai-api-key-input"
                type={showKey ? "text" : "password"}
                value={apiKey}
                autoComplete="new-password"
                placeholder="粘贴 API Key"
                onChange={(e) => setApiKey(e.target.value)}
              />
              <button
                type="button"
                className="ai-btn-ghost"
                onClick={() => setShowKey((v) => !v)}
              >
                {showKey ? "隐藏" : "显示"}
              </button>
              {keySaved && (
                <button
                  type="button"
                  className="ai-btn-ghost"
                  onClick={() => {
                    setEditingKey(false);
                    setApiKey("");
                  }}
                >
                  取消
                </button>
              )}
            </>
          )}
        </div>
      </Row>

      <Row label="分析深度" hint="设置 AI 分析的深度级别" testId="ai-depth-row">
        <select
          className="ai-input"
          data-testid="ai-analysis-depth"
          value={depth}
          disabled={Boolean(busy)}
          onChange={(e) => {
            const next = e.target.value as AnalysisModePresetId;
            setDepth(next);
            writeStoredAnalysisMode(next);
          }}
        >
          {DEPTH_OPTIONS.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </select>
      </Row>

      <Row label="连接状态" testId="ai-status-row">
        <div className="ai-status-line" data-tone={tone} data-testid="ai-connection-status">
          <div className="ai-status-text">
            <p className="ai-status-title" data-testid="ai-connection-label">
              <span className="ai-status-dot" aria-hidden />
              {busy === "verify" ? "正在验证…" : status?.ui_label || "尚未配置"}
            </p>
            <p className="ai-status-sub" data-testid="ai-connection-reason">
              {status?.model
                ? `${status.display_name} · ${status.model}`
                : "填入 API Key 后即可开始"}
            </p>
            {/* 拦路原因由后端翻译好，逐条列出。以前它们混在一句话里，看不出有几件事。 */}
            {(status?.blocker_labels?.length ?? 0) > 0 && (
              <ul className="ai-status-blockers" data-testid="ai-connection-blockers">
                {status!.blocker_labels.map((label) => (
                  <li key={label}>
                    {label}
                    {budgetBlocked && label.includes("预算") && (
                      <>
                        {" · "}
                        <Link to="/settings?tab=cost">调整额度</Link>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <button
            type="button"
            className="ai-btn-ghost"
            data-testid="ai-verify"
            disabled={Boolean(busy)}
            onClick={() => void verify()}
          >
            测试连接
          </button>
        </div>
      </Row>

      {message && (
        <p className={failed ? "ai-message bad" : "ai-message"} role="status" data-testid="ai-message">
          {message}
        </p>
      )}

      <div className="ai-footer">
        <button
          type="button"
          className="ai-btn-primary"
          data-testid="ai-save"
          disabled={Boolean(busy)}
          onClick={() => void save()}
        >
          {busy === "save" ? "正在保存…" : "保存设置"}
        </button>
        <button
          type="button"
          className="ai-advanced-toggle"
          data-testid="ai-advanced-toggle"
          aria-expanded={advancedOpen}
          onClick={() => setAdvancedOpen((v) => !v)}
        >
          高级设置 <span aria-hidden>{advancedOpen ? "⌃" : "⌄"}</span>
        </button>
      </div>

      {/* 高级设置里只放「少用但必须有」的动作。技术参数（接口地址、连接详情、诊断）在开发者
          设置里——那是它们本来该待的地方，这一页不需要再造一层技术区。 */}
      {advancedOpen && (
        <section className="ai-advanced" data-testid="ai-advanced">
          <div className="ai-switch-row">
            <div>
              <b>允许云端模型连接</b>
              <p>关闭后不删除任何配置，但所有云端分析都无法开始。本地模型不受影响。</p>
            </div>
            <button
              type="button"
              className="ai-btn-ghost"
              disabled={Boolean(busy)}
              data-testid="ai-cloud-switch"
              onClick={() => void toggleCloud()}
            >
              {status?.cloud_enabled ? "已开启 · 关闭" : "已关闭 · 开启"}
            </button>
          </div>

          <div className="ai-switch-row">
            <div>
              <b>断开连接</b>
              <p>配置和密钥都保留，随时可以重新连接。</p>
            </div>
            <button
              type="button"
              className="ai-btn-ghost"
              data-testid="ai-disconnect"
              disabled={Boolean(busy) || !keySaved}
              onClick={() => void disconnect()}
            >
              断开
            </button>
          </div>

          <div className="ai-switch-row">
            <div>
              <b>删除本机密钥</b>
              <p>从本机钥匙串移除 API Key。不可撤销，但不影响已完成的分析。</p>
            </div>
            <button
              type="button"
              className="ai-btn-danger"
              data-testid="ai-delete-credential"
              disabled={Boolean(busy) || !keySaved}
              onClick={() => void removeCredential()}
            >
              删除
            </button>
          </div>

          <AdvancedBudgetGate />

          <div className="ai-adv-field">
            <b>接口地址（Base URL）</b>
            <p>只有走代理或镜像时才需要改。留空使用服务商默认地址。</p>
            <input
              className="ai-input"
              data-testid="ai-base-url"
              value={baseUrl}
              placeholder="留空使用默认地址"
              onChange={(e) => {
                setBaseUrl(e.target.value);
                setBaseUrlDirty(true);
              }}
            />
            {baseUrlDirty && <p className="ai-adv-note">改完点上面的「保存设置」生效。</p>}
          </div>

          <div className="ai-switch-row">
            <div>
              <b>本地模型服务</b>
              <p>在本机跑模型，不经过云端，也不产生费用。启动会占用较多显存。</p>
            </div>
            <span className="ai-adv-actions">
              <button
                type="button"
                className="ai-btn-ghost"
                data-testid="ai-local-start"
                onClick={() => {
                  if (confirm("启动本地模型可能造成较高 GPU 负载，确认使用 safe 配置？")) {
                    void providersApi.startLocal("safe").then(refreshAll);
                  }
                }}
              >
                启动
              </button>
              <button
                type="button"
                className="ai-btn-ghost"
                data-testid="ai-local-stop"
                onClick={() => void providersApi.stopLocal().then(refreshAll)}
              >
                停止
              </button>
            </span>
          </div>
        </section>
      )}
    </article>
  );
}
