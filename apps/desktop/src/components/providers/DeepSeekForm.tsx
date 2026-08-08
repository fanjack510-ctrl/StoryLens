import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { providersApi } from "../../services/providersApi";
import { settingsApi } from "../../services/settingsApi";
import { credentialStateLabel } from "./providerDisplayLabels";
import "./providers.css";

const DEEPSEEK_PROVIDER = "deepseek";
const MODEL_FLASH = "deepseek-v4-flash";
const MODEL_PRO = "deepseek-v4-pro";

type ProviderFormState = {
  display_name: string;
  base_url: string;
  plus_model: string;
  timeout_seconds: number;
  max_retries: number;
  enabled: boolean;
  disconnected: boolean;
  api_key: string;
};

const EMPTY_FORM: ProviderFormState = {
  display_name: "深度求索/DeepSeek",
  base_url: "https://api.deepseek.com",
  plus_model: MODEL_FLASH,
  timeout_seconds: 300,
  max_retries: 3,
  enabled: false,
  disconnected: true,
  api_key: "",
};

export function DeepSeekForm({ onSaved }: { onSaved: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ProviderFormState>(EMPTY_FORM);
  const [state, setState] = useState<any>();
  const [hydrated, setHydrated] = useState(false);
  const [show, setShow] = useState(false);
  const [msg, setMsg] = useState("");
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setHydrated(false);
    setMsg("");
    providersApi
      .configuration(DEEPSEEK_PROVIDER)
      .then((v) => {
        if (cancelled) return;
        setState(v);
        const model =
          v.plus_model === MODEL_PRO || v.plus_model === MODEL_FLASH
            ? v.plus_model
            : MODEL_FLASH;
        setForm({
          display_name: v.display_name || EMPTY_FORM.display_name,
          base_url: v.base_url || EMPTY_FORM.base_url,
          plus_model: model,
          timeout_seconds: Number(v.timeout_seconds ?? EMPTY_FORM.timeout_seconds),
          max_retries: Number(v.max_retries ?? EMPTY_FORM.max_retries),
          enabled: Boolean(v.enabled),
          disconnected: Boolean(v.disconnected),
          api_key: "",
        });
        setHydrated(true);
      })
      .catch((e: any) => {
        if (cancelled) return;
        setHydrated(false);
        setMsg(`${e?.code || "ERROR"}：无法读取 DeepSeek 配置。`);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const change = <K extends keyof ProviderFormState>(key: K, value: ProviderFormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const save = async (connect = false) => {
    if (!hydrated) {
      setMsg("配置尚未从后端加载完成，已阻止保存。");
      return;
    }
    try {
      await providersApi.save(DEEPSEEK_PROVIDER, {
        display_name: form.display_name,
        region: "",
        workspace_id: "",
        base_url: form.base_url || null,
        plus_model: form.plus_model,
        max_model: form.plus_model,
        flash_model: form.plus_model,
        timeout_seconds: form.timeout_seconds,
        max_retries: form.max_retries,
        enabled: connect ? true : form.enabled,
        disconnected: !connect,
        allow_auto_route: false,
        raw_logging_enabled: false,
        api_key: form.api_key || null,
      });
      await settingsApi.setActiveCloudProvider(DEEPSEEK_PROVIDER);
      setMsg(connect ? "已保存并设为当前云端 Provider" : "DeepSeek 配置已保存");
      const latest = await providersApi.configuration(DEEPSEEK_PROVIDER);
      setState(latest);
      setForm((f) => ({
        ...f,
        enabled: Boolean(latest.enabled),
        disconnected: Boolean(latest.disconnected),
        api_key: "",
      }));
      await queryClient.invalidateQueries({ queryKey: ["active-cloud-provider"] });
      await queryClient.invalidateQueries({ queryKey: ["whole-book-free-prepare"] });
      await queryClient.invalidateQueries({ queryKey: ["routing"] });
      onSaved();
    } catch (e: any) {
      setMsg(`${e.code || "ERROR"}：${e.message}`);
    }
  };

  const testConnection = async () => {
    if (testing) return;
    setTesting(true);
    setMsg("");
    try {
      // Prefer lightweight transport/health path — no long chat completion.
      await providersApi.transportDiagnostic(DEEPSEEK_PROVIDER);
      const modelLabel =
        form.plus_model === MODEL_PRO ? "DeepSeek V4 Pro" : "DeepSeek V4 Flash";
      setMsg(`✓ DeepSeek API 连接正常\n当前模型：${modelLabel}`);
      onSaved();
    } catch (e: any) {
      const code = String(e?.code || e?.status || "");
      if (code.includes("401") || code === "PROVIDER_AUTHENTICATION_FAILED") {
        setMsg("DeepSeek API Key 无效");
      } else if (code.includes("402") || code === "PROVIDER_INSUFFICIENT_BALANCE") {
        setMsg("DeepSeek API 余额不足");
      } else if (code.includes("429")) {
        setMsg("DeepSeek 请求过快，请稍后重试");
      } else if (code.includes("503")) {
        setMsg("DeepSeek 服务繁忙");
      } else if (code.includes("500")) {
        setMsg("DeepSeek 服务异常");
      } else {
        setMsg(`${code || "ERROR"}：${e?.message || "连接测试失败"}`);
      }
    } finally {
      setTesting(false);
    }
  };

  const remove = async () => {
    if (confirm("确认删除 DeepSeek 凭据？不会删除阿里云密钥或历史任务。")) {
      await providersApi.deleteCredentials(DEEPSEEK_PROVIDER);
      setMsg("DeepSeek 凭据已删除");
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
      <div className="provider-form providers-aliyun-form" data-testid="deepseek-form-loading">
        <p className="notice">正在从后端加载 DeepSeek 配置…</p>
        {msg && <p className="notice" role="status">{msg}</p>}
      </div>
    );
  }

  return (
    <div className="provider-form providers-aliyun-form" data-testid="deepseek-form-hydrated">
      <div className="providers-credential-line credential-line" data-testid="deepseek-credential-state">
        <b>凭据状态</b>
        <span className={`ai-status-badge ${credTone === "ok" ? "ok" : "warn"}`}>{credLabel}</span>
        <small>保存后不会回显 API Key；与阿里云密钥相互独立</small>
      </div>

      <label>
        API Key
        <div className="providers-key-row">
          <input
            data-testid="deepseek-api-key-input"
            type={show ? "text" : "password"}
            value={form.api_key}
            placeholder={state?.credential_state === "configured" ? "已保存（留空不修改）" : "sk-…"}
            onChange={(e) => change("api_key", e.target.value)}
          />
          <button type="button" onClick={() => setShow((v) => !v)}>
            {show ? "隐藏" : "显示"}
          </button>
        </div>
      </label>

      <fieldset className="providers-model-fieldset" data-testid="deepseek-model-radios">
        <legend>模型</legend>
        <label className="providers-radio">
          <input
            type="radio"
            name="deepseek-model"
            checked={form.plus_model === MODEL_FLASH}
            onChange={() => change("plus_model", MODEL_FLASH)}
          />
          <span>
            <b>DeepSeek V4 Flash</b>
            <small>推荐 · 性价比优先</small>
          </span>
        </label>
        <label className="providers-radio">
          <input
            type="radio"
            name="deepseek-model"
            checked={form.plus_model === MODEL_PRO}
            onChange={() => change("plus_model", MODEL_PRO)}
          />
          <span>
            <b>DeepSeek V4 Pro</b>
            <small>高质量 · 成本更高</small>
          </span>
        </label>
      </fieldset>

      <label>
        Base URL
        <input
          data-testid="deepseek-base-url"
          value={form.base_url}
          onChange={(e) => change("base_url", e.target.value)}
        />
      </label>

      <label className="providers-check">
        <input
          type="checkbox"
          checked={form.enabled}
          onChange={(e) => change("enabled", e.target.checked)}
        />
        启用 DeepSeek Provider
      </label>

      <div className="master-actions">
        <button type="button" data-testid="deepseek-save" onClick={() => save(false)}>
          保存配置
        </button>
        <button type="button" data-testid="deepseek-save-connect" onClick={() => save(true)}>
          保存并设为当前
        </button>
        <button
          type="button"
          data-testid="deepseek-test-connection"
          disabled={testing}
          onClick={testConnection}
        >
          {testing ? "诊断中…" : "测试连接"}
        </button>
        <button type="button" data-testid="deepseek-delete-creds" onClick={remove}>
          删除凭据
        </button>
      </div>
      {msg && (
        <p className="notice" role="status" data-testid="deepseek-form-message">
          {msg}
        </p>
      )}
      <p className="notice">费用为预估值，实际收费以 DeepSeek 官方账单为准。余额查询 UI 暂不提供。</p>
    </div>
  );
}
