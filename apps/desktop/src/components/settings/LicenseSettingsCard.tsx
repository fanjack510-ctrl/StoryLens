import { useEffect, useState } from "react";
import {
  isMockActivationAllowed,
  listVipFeatureDefinitions,
  MOCK_ACTIVATION_CODES,
} from "../../services/license";
import { licenseStatusLabel, useLicenseStore } from "../../stores/license";

/** VIP license settings card; wired via SettingsLicenseTab. Commerce remains 即将开放. */
export function LicenseSettingsCard() {
  const {
    status,
    editionLabel,
    license,
    usingMockService,
    commerceComingSoon,
    hydrated,
    busy,
    message,
    error,
    hydrate,
    activateLicense,
    refreshLicense,
    deactivateLicense,
  } = useLicenseStore();

  const [code, setCode] = useState("");
  const mockAllowed = isMockActivationAllowed();
  const vipFeatures = listVipFeatureDefinitions();

  useEffect(() => {
    if (!hydrated) {
      void hydrate();
    }
  }, [hydrated, hydrate]);

  return (
    <article className="settings-panel" data-testid="license-settings-card">
      <header className="settings-panel-header">
        <h2>VIP 授权</h2>
        <p>本地优先授权基础。真实购买与远程验签即将开放，当前不限制已有功能。</p>
      </header>

      <div className="settings-fields">
        <div className="settings-field" data-testid="license-edition">
          <span>当前版本</span>
          <strong>{editionLabel || "免费版"}</strong>
        </div>

        <div className="settings-field" data-testid="license-status">
          <span>授权状态</span>
          <strong>{licenseStatusLabel(status)}</strong>
        </div>

        {license && (
          <div className="settings-field" data-testid="license-meta">
            <span>授权信息</span>
            <small>
              ID：{license.license_id}
              {license.expires_at ? ` · 到期：${license.expires_at.slice(0, 10)}` : " · 无到期日"}
              {license.last_verified_at
                ? ` · 最近校验：${license.last_verified_at.slice(0, 10)}`
                : ""}
            </small>
          </div>
        )}

        {commerceComingSoon && (
          <p role="status" data-testid="license-coming-soon">
            购买 VIP：即将开放。本阶段不展示价格，也不跳转无效购买地址。
          </p>
        )}

        {usingMockService && mockAllowed && (
          <p className="muted" data-testid="license-mock-notice">
            开发 Mock 已启用（非真实付费授权）。可用码：
            {MOCK_ACTIVATION_CODES.ACTIVE}、{MOCK_ACTIVATION_CODES.EXPIRED}、
            {MOCK_ACTIVATION_CODES.OFFLINE_GRACE}、{MOCK_ACTIVATION_CODES.INVALID}
          </p>
        )}

        <label className="settings-field">
          <span>激活码</span>
          <input
            type="text"
            value={code}
            aria-label="激活码"
            data-testid="license-code-input"
            placeholder={mockAllowed ? "输入 Mock 激活码" : "即将开放"}
            disabled={!mockAllowed || busy}
            onChange={(e) => setCode(e.target.value)}
          />
        </label>
      </div>

      <div className="settings-actions">
        <button
          type="button"
          className="primary"
          data-testid="license-activate-button"
          disabled={!mockAllowed || busy || !code.trim()}
          onClick={() => void activateLicense(code)}
        >
          {busy ? "处理中…" : mockAllowed ? "激活（Mock）" : "激活（即将开放）"}
        </button>
        <button
          type="button"
          data-testid="license-refresh-button"
          disabled={!mockAllowed || busy}
          onClick={() => void refreshLicense()}
        >
          刷新授权
        </button>
        <button
          type="button"
          data-testid="license-deactivate-button"
          disabled={busy || status === "FREE"}
          onClick={() => void deactivateLicense()}
        >
          解除本机授权
        </button>
      </div>

      <section data-testid="license-vip-features">
        <h3>VIP 功能说明</h3>
        <p>以下能力已登记功能键，本阶段均为未启用或免费策略，不会锁定当前已有功能。</p>
        <ul>
          {vipFeatures.map((feature) => (
            <li key={feature.key}>
              <b>{feature.label}</b>
              <span> — {feature.description}</span>
              <small> （{feature.phaseAccess === "free" ? "免费可用" : "未启用"}）</small>
            </li>
          ))}
        </ul>
      </section>

      {message && (
        <p role="status" data-testid="license-message">
          {message}
        </p>
      )}
      {error && (
        <p role="alert" data-testid="license-error">
          {error}
        </p>
      )}
    </article>
  );
}
