import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  entitlementApi,
  maskLicenseCode,
  PRO_FEATURE_KEYS,
  type EntitlementSnapshot,
} from "../../services/entitlementApi";
import { openExternalUrl } from "../../services/openExternalUrl";
import { ApiError } from "../../services/apiClient";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import "./settings.css";

const FEATURE_LABELS: Record<(typeof PRO_FEATURE_KEYS)[number], string> = {
  whole_book_analysis: "整书分析",
  narrative_asset_library: "叙事资产库",
  story_lab: "故事实验台",
  cross_book_search: "跨书检索",
  advanced_export: "进阶导出",
};

export function LicenseSettingsCard() {
  const qc = useQueryClient();
  const entitlement = useQuery({
    queryKey: ["entitlements"],
    queryFn: entitlementApi.snapshot,
  });
  const [dialogOpen, setDialogOpen] = useState(false);
  const [code, setCode] = useState("");
  const [showFullCode, setShowFullCode] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [success, setSuccess] = useState<EntitlementSnapshot | null>(null);

  useEffect(() => {
    if (entitlement.data?.pro_active) {
      setSuccess(entitlement.data);
    }
  }, [entitlement.data]);

  const data = entitlement.data;
  const pro = Boolean(data?.pro_active);
  const buyUrl = data?.commerce?.afdian_product_url || "";

  const onBuy = async () => {
    const result = await openExternalUrl(buyUrl);
    if (!result.ok) {
      setMessage(result.message || "无法打开购买页。");
      setErrorCode("COMMERCE_URL_MISSING");
    }
  };

  const onActivate = async () => {
    setBusy(true);
    setMessage("");
    setErrorCode(null);
    try {
      const result = await entitlementApi.activate(code);
      setSuccess(result.entitlement);
      setMessage(result.user_message);
      setDialogOpen(false);
      setCode("");
      await qc.invalidateQueries({ queryKey: ["entitlements"] });
    } catch (error) {
      if (error instanceof ApiError) {
        setErrorCode(error.code);
        setMessage(error.message);
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
        <p>爱发电购买后，使用授权码在本机离线激活。</p>
      </header>

      <section className="settings-zone" data-testid="license-edition-zone">
        <h3>当前版本</h3>
        <p data-testid="license-edition-label">
          {pro ? "StoryLens Pro" : "StoryLens 免费版"}
        </p>
        {!pro && (
          <p className="zone-hint muted">
            整书分析、叙事资产库和故事实验台属于 StoryLens Pro 功能。
          </p>
        )}
      </section>

      {pro && data ? (
        <section className="settings-zone" data-testid="license-pro-active">
          <h3>StoryLens Pro 已激活</h3>
          <ul className="settings-license-summary">
            <li>授权范围：StoryLens {data.major_version ?? 1}.x</li>
            <li>授权编号：{data.license_id_masked}</li>
            <li>激活时间：{data.activated_at ? new Date(data.activated_at).toLocaleString() : "—"}</li>
          </ul>
          <p className="muted">专业版功能</p>
          <ul>
            {PRO_FEATURE_KEYS.map((key) => (
              <li key={key}>{FEATURE_LABELS[key]}</li>
            ))}
          </ul>
          <div className="settings-actions">
            <Button type="button" data-testid="license-copy-summary" onClick={() => void copySummary()}>
              复制授权摘要
            </Button>
          </div>
        </section>
      ) : (
        <section className="settings-zone" data-testid="license-free-actions">
          <div className="settings-actions">
            <Button
              variant="primary"
              data-testid="license-buy-pro"
              onClick={() => void onBuy()}
            >
              购买专业版
            </Button>
            <Button data-testid="license-open-activate" onClick={() => setDialogOpen(true)}>
              输入授权码
            </Button>
          </div>
        </section>
      )}

      {message && (
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
        {errorCode && (
          <p className="muted" data-testid="license-activate-error-code">
            {errorCode}
          </p>
        )}
      </Dialog>
    </article>
  );
}
