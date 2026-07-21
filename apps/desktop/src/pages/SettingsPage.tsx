import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useAdvancedSettingsStore } from "../stores/advancedSettingsStore";
import { useDeveloperModeStore } from "../stores/developerModeStore";
import { SettingsAiServiceTab } from "../components/settings/SettingsAiServiceTab";
import { SettingsUsageCostTab } from "../components/settings/SettingsUsageCostTab";
import { SettingsDataStorageTab } from "../components/settings/SettingsDataStorageTab";
import { SettingsPrivacyUpdateTab } from "../components/settings/SettingsPrivacyUpdateTab";
import { SettingsAppearanceTab } from "../components/settings/SettingsAppearanceTab";
import { SettingsAdvancedTab } from "../components/settings/SettingsAdvancedTab";
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
  { id: "appearance", label: "外观" },
];

/** Map legacy / hidden tab ids without dropping deep-link compatibility. */
export function normalizeSettingsTab(raw: string | null, showDeveloper: boolean): TabId {
  if (raw === "general") return "appearance";
  if (raw === "budget") return "cost";
  // Membership UI not productized — redirect away from empty placeholder tab.
  if (raw === "license") return "ai";
  if (raw === "advanced") return showDeveloper ? "advanced" : "ai";
  if (
    raw === "ai" ||
    raw === "cost" ||
    raw === "data" ||
    raw === "privacy" ||
    raw === "appearance"
  ) {
    return raw;
  }
  return "ai";
}

export function SettingsPage() {
  const showAdvanced = useAdvancedSettingsStore((s) => s.showAdvancedSettings);
  const developerMode = useDeveloperModeStore((s) => s.developerMode);
  const showDeveloper = showAdvanced || developerMode;
  const [searchParams, setSearchParams] = useSearchParams();
  const [tab, setTab] = useState<TabId>(() =>
    normalizeSettingsTab(searchParams.get("tab"), showDeveloper),
  );

  useEffect(() => {
    setTab(normalizeSettingsTab(searchParams.get("tab"), showDeveloper));
  }, [searchParams, showDeveloper]);

  const tabs = showDeveloper
    ? [...BASE_TABS, { id: "advanced" as const, label: "开发者设置" }]
    : BASE_TABS;

  const activeTab = tab === "advanced" && !showDeveloper ? "ai" : tab;
  const focus = searchParams.get("focus");

  const selectTab = (id: TabId) => {
    const next = normalizeSettingsTab(id, showDeveloper);
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
        {activeTab === "appearance" && <SettingsAppearanceTab />}
        {activeTab === "advanced" && showDeveloper && <SettingsAdvancedTab />}
      </div>
    </section>
  );
}
