import { useEffect, useState } from "react";
import { providersApi } from "../../services/providersApi";
import { credentialStateLabel } from "./providerDisplayLabels";
import "./providers.css";

export function AliyunForm({
  provider,
  onSaved,
}: {
  provider: string;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<any>({
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
  });
  const [state, setState] = useState<any>();
  const [show, setShow] = useState(false);
  const [msg, setMsg] = useState("");
  useEffect(() => {
    providersApi
      .configuration(provider)
      .then((v) => {
        setState(v);
        setForm((f: any) => ({ ...f, ...v, api_key: "" }));
      })
      .catch(() => {});
  }, [provider]);
  const change = (key: string, value: any) =>
    setForm((f: any) => ({ ...f, [key]: value }));
  const save = async (connect = false) => {
    try {
      await providersApi.save(provider, {
        ...form,
        base_url: form.base_url || null,
        api_key: form.api_key || null,
        disconnected: !connect,
      });
      setMsg(connect ? "已安全保存并连接" : "配置已安全保存");
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

  return (
    <div className="provider-form providers-aliyun-form">
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

      <details className="providers-form-section" data-testid="provider-advanced-params">
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

      {msg && <p className="notice">{msg}</p>}
      <div className="form-actions">
        <button type="button" className="primary" onClick={() => save(false)}>
          保存配置
        </button>
        <button type="button" onClick={() => save(true)}>保存并连接</button>
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
          onClick={() =>
            providersApi
              .action(provider, form.enabled ? "disable" : "enable")
              .then(onSaved)
          }
        >
          {form.enabled ? "停用" : "启用"}
        </button>
        <button type="button" className="danger" onClick={remove}>
          删除凭据
        </button>
      </div>
      <p className="privacy">
        真实连接测试可能产生少量费用，页面加载和保存配置均不会自动测试或发送正文。
      </p>
    </div>
  );
}
