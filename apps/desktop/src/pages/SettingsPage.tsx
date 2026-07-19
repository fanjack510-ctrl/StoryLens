import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useDeveloperModeStore } from "../stores/developerModeStore";
import { SettingsGeneralTab } from "../components/settings/SettingsGeneralTab";
import { SettingsAiServiceTab } from "../components/settings/SettingsAiServiceTab";
import { SettingsBudgetPrivacyTab } from "../components/settings/SettingsBudgetPrivacyTab";
import { SettingsAdvancedTab } from "../components/settings/SettingsAdvancedTab";

type TabId = "general" | "ai" | "budget" | "advanced";

const BASE_TABS: Array<{ id: TabId; label: string }> = [
  { id: "general", label: "通用" },
  { id: "ai", label: "AI服务" },
  { id: "budget", label: "预算与隐私" },
];

function tabFromSearch(raw: string | null): TabId {
  if (raw === "ai" || raw === "budget" || raw === "advanced" || raw === "general") return raw;
  return "general";
}

export function SettingsPage() {
  const developerMode = useDeveloperModeStore((s) => s.developerMode);
  const [searchParams] = useSearchParams();
  const [tab, setTab] = useState<TabId>(() => tabFromSearch(searchParams.get("tab")));

  useEffect(() => {
    const next = tabFromSearch(searchParams.get("tab"));
    if (next === "advanced" && !developerMode) {
      setTab("ai");
      return;
    }
    setTab(next);
  }, [searchParams, developerMode]);

  const tabs = developerMode
    ? [...BASE_TABS, { id: "advanced" as const, label: "高级设置" }]
    : BASE_TABS;

  const activeTab = !developerMode && tab === "advanced" ? "general" : tab;
  const focus = searchParams.get("focus");

  return (
    <section className="page settings-page" data-testid="settings-page">
      <div className="page-title settings-page-title">
        <div>
          <h1>设置</h1>
          <p>外观偏好、AI 服务与预算隐私。</p>
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
        {activeTab === "general" && <SettingsGeneralTab />}
        {activeTab === "ai" && (
          <SettingsAiServiceTab
            autoOpenWizard={focus === "api_key"}
            focusField={focus === "api_key" ? "api_key" : undefined}
          />
        )}
        {activeTab === "budget" && <SettingsBudgetPrivacyTab />}
        {activeTab === "advanced" && developerMode && <SettingsAdvancedTab />}
      </div>
    </section>
  );
}
