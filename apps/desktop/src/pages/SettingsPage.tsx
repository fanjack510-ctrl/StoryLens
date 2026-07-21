import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useAdvancedSettingsStore } from "../stores/advancedSettingsStore";
import { SettingsAiServiceTab } from "../components/settings/SettingsAiServiceTab";
import { SettingsUsageCostTab } from "../components/settings/SettingsUsageCostTab";
import { SettingsDataStorageTab } from "../components/settings/SettingsDataStorageTab";
import { SettingsPrivacyUpdateTab } from "../components/settings/SettingsPrivacyUpdateTab";
import { SettingsLicenseTab } from "../components/settings/SettingsLicenseTab";
import { SettingsAppearanceTab } from "../components/settings/SettingsAppearanceTab";
import { SettingsAdvancedTab } from "../components/settings/SettingsAdvancedTab";
import "../components/settings/settings.css";

type TabId =
  | "ai"
  | "cost"
  | "data"
  | "privacy"
  | "license"
  | "appearance"
  | "advanced"
  | "general"
  | "budget";

const BASE_TABS: Array<{ id: TabId; label: string }> = [
  { id: "ai", label: "AI 服务" },
  { id: "cost", label: "使用额度" },
  { id: "data", label: "数据与存储" },
  { id: "privacy", label: "隐私与更新" },
  { id: "license", label: "授权与会员" },
  { id: "appearance", label: "外观" },
];

function normalizeTab(raw: string | null, showAdvanced: boolean): TabId {
  if (raw === "general") return "appearance";
  if (raw === "budget") return "cost";
  if (raw === "advanced") return showAdvanced ? "advanced" : "ai";
  if (
    raw === "ai" ||
    raw === "cost" ||
    raw === "data" ||
    raw === "privacy" ||
    raw === "license" ||
    raw === "appearance"
  ) {
    return raw;
  }
  return "ai";
}

export function SettingsPage() {
  const showAdvanced = useAdvancedSettingsStore((s) => s.showAdvancedSettings);
  const [searchParams] = useSearchParams();
  const [tab, setTab] = useState<TabId>(() =>
    normalizeTab(searchParams.get("tab"), showAdvanced),
  );

  useEffect(() => {
    setTab(normalizeTab(searchParams.get("tab"), showAdvanced));
  }, [searchParams, showAdvanced]);

  const tabs = showAdvanced
    ? [...BASE_TABS, { id: "advanced" as const, label: "高级设置" }]
    : BASE_TABS;

  const activeTab = tab === "advanced" && !showAdvanced ? "ai" : tab;
  const focus = searchParams.get("focus");

  return (
    <section className="page settings-page" data-testid="settings-page">
      <div className="page-title settings-page-title">
        <div>
          <h1>设置</h1>
          <p>配置 AI 服务、费用、数据与外观。多数技术项由软件自动处理。</p>
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
            onClick={() => setTab(item.id)}
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
        {activeTab === "advanced" && showAdvanced && <SettingsAdvancedTab />}
      </div>
    </section>
  );
}
