import { api } from "./apiClient";

/** The switchable cloud vendors, served by the backend so the client stops naming them. */
export type CloudProviderOption = {
  name: string;
  display_name: string;
  base_url?: string;
  models?: string[];
};
export type ActiveCloudProviderResponse = {
  provider_name: string;
  options?: CloudProviderOption[];
};
import type { ConfigRuntimeProfile } from "./aiServiceConfig";

export const settingsApi = {
  dashboard: () => api<any>("/api/v1/dashboard/summary"),
  diagnostics: () => api<any>("/api/v1/system/diagnostics"),
  configProfile: () => api<ConfigRuntimeProfile>("/api/v1/settings/config-profile"),
  runtime: () => api<any>("/api/v1/runtime"),
  openDataDirectory: () =>
    api<{ ok: boolean; path: string }>("/api/v1/system/open-data-directory", { method: "POST" }),
  get: () => api<any>("/api/v1/settings/desktop"),
  save: (value: any) =>
    api("/api/v1/settings/desktop", {
      method: "PUT",
      body: JSON.stringify(value),
    }),
  cloud: () => api<any>("/api/v1/settings/cloud"),
  setCloud: (enabled: boolean) =>
    api("/api/v1/settings/cloud", { method: "PUT", body: JSON.stringify({ enabled }) }),
  /** 「分析时允许把正文发给当前服务商」。与服务商无关——以前只有通义千问那条路径能写。 */
  setCloudBodyConsent: (accepted: boolean) =>
    api<{ accepted: boolean }>("/api/v1/desktop/ai-connection/consent", {
      method: "PUT",
      body: JSON.stringify({ accepted }),
    }),
  activeCloudProvider: () =>
    api<ActiveCloudProviderResponse>("/api/v1/settings/active-cloud-provider"),
  setActiveCloudProvider: (provider_name: string) =>
    api<ActiveCloudProviderResponse>("/api/v1/settings/active-cloud-provider", {
      method: "PUT",
      body: JSON.stringify({ provider_name }),
    }),
  cloudBudget: () => api<any>("/api/v1/settings/cloud-budget"),
  saveCloudBudget: (value: any) =>
    api<any>("/api/v1/settings/cloud-budget", {
      method: "PUT",
      body: JSON.stringify(value),
    }),
  cloudUsage: () => api<any>("/api/v1/cloud-usage/summary"),
  cloudPricing: () => api<any>("/api/v1/cloud-pricing/status"),
};
