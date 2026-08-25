import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  entitlementApi,
  maskLicenseCode,
} from "../../services/entitlementApi";
import {
  ENTITLEMENTS_QUERY_KEY,
} from "../../services/productEdition";
import {
  FREE_FEATURE_LINES,
  PAID_FEATURE_LINES,
} from "../../services/capabilityCatalog";
import { openExternalUrl } from "../../services/openExternalUrl";
import { ApiError } from "../../services/apiClient";
import { useProductEdition } from "../../hooks/useProductEdition";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import "./settings.css";

export function LicenseSettingsCard() {
  const qc = useQueryClient();
  const edition = useProductEdition();
  const entitlement = useQuery({
    queryKey: ENTITLEMENTS_QUERY_KEY,
    queryFn: entitlementApi.snapshot,
  });
  const [dialogOpen, setDialogOpen] = useState(false);
  const [code, setCode] = useState("");
  const [showFullCode, setShowFullCode] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [errorCode, setErrorCode] = useState<string | null>(null);

  const data = entitlement.data;
  const pro = edition.loaded ? edition.is_pro : Boolean(data?.pro_active);
  const buyUrl = data?.commerce?.afdian_product_url || "";

  const onBuy = async () => {
    const result = await openExternalUrl(buyUrl);
    if (!result.ok) {
      setMessage(result.message || "专业版购买地址尚未配置。");
      setErrorCode(result.code || "COMMERCE_URL_MISSING");
    }
  };

  const onActivate = async () => {
    setBusy(true);
    setMessage("");
    setErrorCode(null);
    try {
      const result = await entitlementApi.activate(code);
      // Instant global identity update — no page refresh.
      qc.setQueryData(ENTITLEMENTS_QUERY_KEY, result.entitlement);
      await qc.invalidateQueries({ queryKey: ENTITLEMENTS_QUERY_KEY });
      setDialogOpen(false);
      setCode("");
      setErrorCode(null);
      setMessage(result.user_message || "StoryLens Pro 已激活。");
    } catch (error) {
      if (error instanceof ApiError) {
        setErrorCode(error.code);
        setMessage(
          error.code === "LICENSE_KEY_UNSUPPORTED" && data?.license_trust_mode === "development"
            ? "这是正式购买授权码，当前开发模式不能验证。请在 StoryLens 正式版或本地网页正式模式中激活；原有授权没有变化。"
            : error.message,
        );
      } else {
        setErrorCode("LICENSE_ACTIVATE_FAILED");
        setMessage(error instanceof Error ? error.message : "激活失败");
      }
    } finally {
      setBusy(false);
    }
  };

  const copySummary = async () => {
    const text = [
      "StoryLens Pro",
      `授权编号：${data?.license_id_masked || "—"}`,
      `范围：StoryLens ${data?.major_version ?? 1}.x`,
      `激活时间：${data?.activated_at || "—"}`,
    ].join("\n");
    try {
      await navigator.clipboard?.writeText(text);
      setMessage("授权摘要已复制。");
    } catch {
      setMessage(text);
    }
  };

  return (
    <article className="settings-panel settings-module" data-testid="settings-panel-license">
      <header className="settings-panel-header">
        <h2>授权与专业版</h2>
        <p>免费版可完成分析；StoryLens Pro 解锁知识沉淀、跨书能力和结构化 PDF。</p>
      </header>

      <section className="settings-zone" data-testid="license-edition-zone">
        <h3>当前版本</h3>
        <p data-testid="license-edition-label">{edition.product_line_name}</p>
        {!pro && (
          <p className="zone-hint muted">
            免费版没有试用倒计时，可继续使用下面这些完整基础能力。
          </p>
        )}
        {!pro && data?.license_issuance_message && (
          <p className="zone-hint muted" data-testid="license-issuance-message">
            {data.license_issuance_message}
          </p>
        )}
        {edition.user_error_message ? (
          <p className="zone-hint muted" data-testid="license-edition-read-error">
            {edition.user_error_message}
          </p>
        ) : null}
      </section>

      {pro && data ? (
        <section className="settings-zone" data-testid="license-pro-active">
          <h3 data-testid="license-pro-status-heading">专业版已激活</h3>
          <ul className="settings-license-summary" data-testid="license-pro-details">
            <li>授权范围：StoryLens {data.major_version ?? 1}.x</li>
            <li>授权编号：{data.license_id_masked}</li>
            <li>
              激活时间：
              {data.activated_at ? new Date(data.activated_at).toLocaleString() : "—"}
            </li>
          </ul>
          <p className="muted">专业版能力</p>
          <ul data-testid="license-pro-capabilities">
            {PAID_FEATURE_LINES.map((capability) => (
              <li key={capability.key} data-testid={`license-capability-${capability.key}`}>
                <span>{capability.label}</span>
                <span className="capability-active" data-testid="capability-active">
                  已解锁
                </span>
              </li>
            ))}
          </ul>
          <div className="settings-actions">
            <Button type="button" data-testid="license-copy-summary" onClick={() => void copySummary()}>
              复制授权摘要
            </Button>
            <Button type="button" data-testid="license-view-product" onClick={() => void onBuy()}>
              查看爱发电商品
            </Button>
            <Button type="button" data-testid="license-replace-code" onClick={() => setDialogOpen(true)}>
              更换授权码
            </Button>
          </div>
        </section>
      ) : (
        <section className="settings-zone" data-testid="license-free-actions">
          <div className="settings-edition-grid">
            <section data-testid="license-free-includes">
              <h3>免费版包含</h3>
              <ul className="settings-feature-list">
                {FREE_FEATURE_LINES.map((capability) => (
                  <li key={capability.label}>
                    <b>{capability.label}</b>
                    <span>{capability.line}</span>
                  </li>
                ))}
              </ul>
            </section>
            <section data-testid="license-pro-includes">
              <h3>StoryLens Pro 额外解锁</h3>
              <ul className="settings-feature-list" data-testid="license-free-capabilities">
            {PAID_FEATURE_LINES.map((capability) => (
              <li key={capability.key}>
                    <b>{capability.label}</b>
                    <span>{capability.line}</span>
              </li>
            ))}
          </ul>
            </section>
          </div>

          <div className="settings-purchase-flow" data-testid="license-purchase-flow">
            <h3>购买后 3 步启用</h3>
            <ol>
              <li><b>1</b><span>前往爱发电购买 StoryLens Pro</span></li>
              <li><b>2</b><span>在爱发电订单中复制以 SLP1- 开头的授权码</span></li>
              <li><b>3</b><span>回到这里粘贴授权码，本机立即离线激活</span></li>
            </ol>
            <p className="muted">授权码仅用于本机校验；激活后无需保持联网。</p>
          </div>
          <div className="settings-actions">
            <Button
              variant="primary"
              data-testid="license-buy-pro"
              onClick={() => void onBuy()}
            >
              前往爱发电购买
            </Button>
            <Button data-testid="license-open-activate" onClick={() => setDialogOpen(true)}>
              我已有授权码
            </Button>
          </div>
        </section>
      )}

      {message && !dialogOpen && (
        <p role="status" data-testid="license-message" data-error-code={errorCode || undefined}>
          {message}
        </p>
      )}

      <Dialog
        open={dialogOpen}
        onClose={() => !busy && setDialogOpen(false)}
        title="激活专业版"
        data-testid="license-activate-dialog"
      >
        <label className="settings-field">
          <span>授权码</span>
          <textarea
            value={code}
            data-testid="license-code-input"
            rows={3}
            placeholder="粘贴 SLP1- 开头的授权码"
            onChange={(e) => setCode(e.target.value)}
            disabled={busy}
          />
          <small className="field-hint">
            {showFullCode ? code : maskLicenseCode(code || "SLP1-••••••••")}
          </small>
          <small className="field-hint">授权码来自爱发电订单的自动发货内容。</small>
          <button
            type="button"
            className="linkish"
            data-testid="license-toggle-code-preview"
            onClick={() => setShowFullCode((v) => !v)}
          >
            {showFullCode ? "隐藏授权码" : "显示完整授权码"}
          </button>
        </label>
        <div className="settings-actions">
          <Button
            variant="primary"
            data-testid="license-activate-submit"
            disabled={busy || !code.trim()}
            onClick={() => void onActivate()}
          >
            {busy ? "正在激活…" : "激活专业版"}
          </Button>
        </div>
        {errorCode && message ? (
          <div className="settings-license-error" role="alert" data-testid="license-activate-error">
            <b>激活未完成</b>
            <span>{message}</span>
            <small data-testid="license-activate-error-code">{errorCode}</small>
          </div>
        ) : null}
      </Dialog>
    </article>
  );
}
