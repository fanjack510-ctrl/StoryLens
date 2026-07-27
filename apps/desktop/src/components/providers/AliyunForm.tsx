import { useEffect, useState } from "react";
import { providersApi } from "../../services/providersApi";
import { credentialStateLabel } from "./providerDisplayLabels";
import "./providers.css";

type ProviderFormState = {
  display_name: string;
  region: string;
  workspace_id: string;
  base_url: string;
  plus_model: string;
  max_model: string;
  flash_model: string;
  timeout_seconds: number;
  max_retries: number;
  enabled: boolean;
  disconnected: boolean;
  allow_auto_route: boolean;
  raw_logging_enabled: boolean;
  api_key: string;
};

/** Empty shell only — must never be saved before backend hydrate. */
const EMPTY_FORM: ProviderFormState = {
  display_name: "阿里云百炼",
  region: "cn-beijing",
  workspace_id: "",
  base_url: "",
  plus_model: "qwen3.7-plus",
  max_model: "qwen3.7-max",
  flash_model: "qwen3.6-flash",
  timeout_seconds: 300,
  max_retries: 3,
  enabled: false,
  disconnected: true,
  allow_auto_route: false,
  raw_logging_enabled: false,
  api_key: "",
};

export function AliyunForm({
  provider,
  onSaved,
}: {
  provider: string;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<ProviderFormState>(EMPTY_FORM);
  const [state, setState] = useState<any>();
  const [hydrated, setHydrated] = useState(false);
  const [show, setShow] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    let cancelled = false;
    setHydrated(false);
    setMsg("");
    providersApi
      .configuration(provider)
      .then((v) => {
        if (cancelled) return;
        setState(v);
        setForm({
          display_name: v.display_name || EMPTY_FORM.display_name,
          region: v.region || EMPTY_FORM.region,
          workspace_id: v.workspace_id || "",
          base_url: v.base_url || "",
          plus_model: v.plus_model || EMPTY_FORM.plus_model,
          max_model: v.max_model || EMPTY_FORM.max_model,
          flash_model: v.flash_model || EMPTY_FORM.flash_model,
          timeout_seconds: Number(v.timeout_seconds ?? EMPTY_FORM.timeout_seconds),
          max_retries: Number(v.max_retries ?? EMPTY_FORM.max_retries),
          enabled: Boolean(v.enabled),
          disconnected: Boolean(v.disconnected),
          allow_auto_route: Boolean(v.allow_auto_route),
          raw_logging_enabled: Boolean(v.raw_logging_enabled),
          api_key: "",
        });
        setHydrated(true);
      })
      .catch((e: any) => {
        if (cancelled) return;
        setHydrated(false);
        setMsg(`${e?.code || "ERROR"}：无法读取 Provider 配置，已阻止使用默认关闭值覆盖后端。`);
      });
    return () => {
      cancelled = true;
    };
  }, [provider]);

  const change = <K extends keyof ProviderFormState>(key: K, value: ProviderFormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const save = async (connect = false) => {
    if (!hydrated) {
      setMsg("配置尚未从后端加载完成，已阻止保存，以免用默认关闭值覆盖已保存配置。");
      return;
    }
    try {
      await providersApi.save(provider, {
        ...form,
        base_url: form.base_url || null,
        api_key: form.api_key || null,
        disconnected: !connect,
      });
      setMsg(connect ? "已安全保存并连接" : "配置已安全保存");
      const latest = await providersApi.configuration(provider);
      setState(latest);
      setForm((f) => ({
        ...f,
        enabled: Boolean(latest.enabled),
        disconnected: Boolean(latest.disconnected),
        api_key: "",
      }));
      onSaved();
    } catch (e: any) {
      setMsg(`${e.code || "ERROR"}：${e.message}`);
    }
  };
  const remove = async () => {
    if (confirm("确认删除此 Provider 的凭据？历史任务不会删除。")) {
      await providersApi.deleteCredentials(provider);
      setMsg("凭据已删除");
      onSaved();
    }
  };
  const credLabel = credentialStateLabel(state?.credential_state);
  const credTone =
    state?.credential_state === "configured"
      ? "ok"
      : state?.credential_state === "invalid"
        ? "danger"
        : "warn";

  if (!hydrated) {
    return (
      <div className="provider-form providers-aliyun-form" data-testid="provider-form-loading">
        <p className="notice">正在从后端加载 Provider 配置…</p>
        {msg && <p className="notice" role="status">{msg}</p>}
      </div>
    );
  }

  return (
    <div className="provider-form providers-aliyun-form" data-testid="provider-form-hydrated">
      <div className="providers-credential-line credential-line" data-testid="provider-credential-state">
        <b>凭据状态</b>
        <span className={`ai-status-badge ${credTone === "ok" ? "ok" : "warn"}`}>{credLabel}</span>
        <small>保存后不会回显 API Key</small>
        {state?.credential_state && (
          <code className="providers-tech-id" title="技术状态码">
            {state.credential_state}
          </code>
        )}
      </div>

      <section className="providers-form-section" data-testid="provider-basic-section">
        <h3>基本信息</h3>
        <div className="form-grid providers-form-grid">
          <label>
            配置名称
            <input
              value={form.display_name}
              onChange={(e) => change("display_name", e.target.value)}
            />
          </label>
          <label>
            地域
            <select
              value={form.region}
              onChange={(e) => change("region", e.target.value)}
            >
              <option value="cn-beijing">中国大陆 · 华北2（北京）</option>
            </select>
          </label>
          <label>
            API Key
            <div className="password">
              <input
                type={show ? "text" : "password"}
                value={form.api_key}
                onChange={(e) => change("api_key", e.target.value)}
                autoComplete="new-password"
                data-testid="provider-api-key-input"
                placeholder={
                  state?.credential_state === "configured"
                    ? "已配置；留空表示不修改"
                    : "输入后保存到Windows凭据管理器"
                }
              />
              <button type="button" onClick={() => setShow(!show)}>
                {show ? "隐藏" : "显示"}
              </button>
            </div>
          </label>
        </div>
      </section>

      <section className="providers-form-section" data-testid="provider-model-map-section">
        <h3>模型映射</h3>
        <p className="providers-advanced-note">任务路由使用的模型 ID（等宽显示）。</p>
        <div className="form-grid providers-form-grid">
          <label>
            Plus 模型
            <input
              className="providers-mono-input"
              value={form.plus_model}
              onChange={(e) => change("plus_model", e.target.value)}
            />
          </label>
          <label>
            Max 模型
            <input
              className="providers-mono-input"
              value={form.max_model}
              onChange={(e) => change("max_model", e.target.value)}
            />
          </label>
          <label>
            Flash 模型
            <input
              className="providers-mono-input"
              value={form.flash_model}
              onChange={(e) => change("flash_model", e.target.value)}
            />
          </label>
        </div>
      </section>

      <details className="providers-form-section" open data-testid="provider-advanced-params">
        <summary>高级参数</summary>
        <p className="providers-advanced-note">
          普通用户无需修改。含 Base URL、Workspace ID、超时与路由开关。
        </p>
        <div className="form-grid providers-form-grid">
          <label>
            Workspace ID
            <input
              className="providers-mono-input"
              value={form.workspace_id}
              onChange={(e) => change("workspace_id", e.target.value)}
            />
          </label>
          <label>
            Base URL
            <input
              className="providers-mono-input"
              value={form.base_url}
              onChange={(e) => change("base_url", e.target.value)}
              placeholder="根据Workspace自动生成或手动填写"
            />
          </label>
          <label>
            超时
            <input
              type="number"
              value={form.timeout_seconds}
              onChange={(e) => change("timeout_seconds", Number(e.target.value))}
            />
          </label>
          <label>
            最大重试
            <input
              type="number"
              value={form.max_retries}
              onChange={(e) => change("max_retries", Number(e.target.value))}
            />
          </label>
        </div>
        <div className="checks providers-checks">
          <label>
            <input
              type="checkbox"
              checked={form.enabled}
              data-testid="provider-enabled-checkbox"
              onChange={(e) => change("enabled", e.target.checked)}
            />
            启用Provider
          </label>
          <label>
            <input
              type="checkbox"
              checked={form.allow_auto_route}
              onChange={(e) => change("allow_auto_route", e.target.checked)}
            />
            允许自动路由
          </label>
          <label>
            <input
              type="checkbox"
              checked={form.raw_logging_enabled}
              onChange={(e) => change("raw_logging_enabled", e.target.checked)}
            />
            保存云端原文（不推荐）
          </label>
        </div>
      </details>

      {msg && <p className="notice" role="status">{msg}</p>}
      <div className="form-actions">
        <button
          type="button"
          className="primary"
          data-testid="provider-save-config"
          disabled={!hydrated}
          onClick={() => void save(false)}
        >
          保存配置
        </button>
        <button
          type="button"
          data-testid="provider-save-connect"
          disabled={!hydrated}
          onClick={() => void save(true)}
        >
          保存并连接
        </button>
        <button
          type="button"
          onClick={() =>
            providersApi.action(provider, "disconnect").then(onSaved)
          }
        >
          断开
        </button>
        <button
          type="button"
          data-testid="provider-toggle-enable"
          onClick={() =>
            providersApi
              .action(provider, form.enabled ? "disable" : "enable")
              .then(async () => {
                const latest = await providersApi.configuration(provider);
                setState(latest);
                setForm((f) => ({ ...f, enabled: Boolean(latest.enabled) }));
                onSaved();
              })
          }
        >
          {form.enabled ? "停用" : "启用"}
        </button>
        <button type="button" className="danger" onClick={() => void remove()}>
          删除凭据
        </button>
      </div>
      <p className="privacy">
        真实连接测试可能产生少量费用，页面加载和保存配置均不会自动测试或发送正文。
      </p>
    </div>
  );
}
