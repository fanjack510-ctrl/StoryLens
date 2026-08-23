import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { SettingsAiServiceTab } from "../components/settings/SettingsAiServiceTab";
import { SettingsUsageCostTab } from "../components/settings/SettingsUsageCostTab";
import { SettingsDataStorageTab } from "../components/settings/SettingsDataStorageTab";
import { SettingsPrivacyUpdateTab } from "../components/settings/SettingsPrivacyUpdateTab";
import { SettingsAppearanceTab } from "../components/settings/SettingsAppearanceTab";
import { SettingsLicenseTab } from "../components/settings/SettingsLicenseTab";
import "../components/settings/settings.css";

type TabId =
  | "ai"
  | "cost"
  | "data"
  | "privacy"
  | "appearance"
  | "advanced"
  | "general"
  | "budget"
  | "license";

const BASE_TABS: Array<{ id: TabId; label: string }> = [
  { id: "ai", label: "AI与模型" },
  { id: "cost", label: "使用额度" },
  { id: "data", label: "数据与备份" },
  { id: "privacy", label: "隐私与更新" },
  { id: "license", label: "授权与专业版" },
  { id: "appearance", label: "外观" },
];

/** Map legacy / hidden tab ids without dropping deep-link compatibility. */
export function normalizeSettingsTab(raw: string | null): TabId {
  if (raw === "general") return "appearance";
  if (raw === "budget") return "cost";
  // 「开发者设置」已经删除。老链接不该 404，落回 AI 与模型。
  if (raw === "advanced") return "ai";
  if (
    raw === "ai" ||
    raw === "cost" ||
    raw === "data" ||
    raw === "privacy" ||
    raw === "appearance" ||
    raw === "license"
  ) {
    return raw;
  }
  return "ai";
}

export function SettingsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [tab, setTab] = useState<TabId>(() =>
    normalizeSettingsTab(searchParams.get("tab")),
  );

  useEffect(() => {
    setTab(normalizeSettingsTab(searchParams.get("tab")));
  }, [searchParams]);

  const tabs = BASE_TABS;
  const activeTab = tab === "advanced" ? "ai" : tab;
  const focus = searchParams.get("focus");

  const selectTab = (id: TabId) => {
    const next = normalizeSettingsTab(id);
    setTab(next);
    const params = new URLSearchParams(searchParams);
    params.set("tab", next);
    if (next !== "ai") params.delete("focus");
    setSearchParams(params, { replace: true });
  };

  return (
    <section className="page settings-page" data-testid="settings-page">
      <div className="page-title settings-page-title">
        <div>
          <h1>设置</h1>
          <p>管理模型、用量、数据、隐私与外观。</p>
        </div>
      </div>

      <nav className="settings-tabs" data-testid="settings-tabs" aria-label="设置分类">
        {tabs.map((item) => (
          <button
            key={item.id}
            type="button"
            className={activeTab === item.id ? "active" : ""}
            data-testid={`settings-tab-${item.id}`}
            aria-selected={activeTab === item.id}
            onClick={() => selectTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      <div className="settings-content" data-testid="settings-content">
        {activeTab === "ai" && (
          <SettingsAiServiceTab
            autoOpenWizard={focus === "api_key"}
            focusField={focus === "api_key" ? "api_key" : undefined}
          />
        )}
        {activeTab === "cost" && <SettingsUsageCostTab />}
        {activeTab === "data" && <SettingsDataStorageTab />}
        {activeTab === "privacy" && <SettingsPrivacyUpdateTab />}
        {activeTab === "license" && <SettingsLicenseTab />}
        {activeTab === "appearance" && <SettingsAppearanceTab />}
      </div>
    </section>
  );
}
