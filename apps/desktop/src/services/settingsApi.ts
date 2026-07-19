import { api } from "./apiClient";
export const settingsApi = {
  dashboard: () => api<any>("/api/v1/dashboard/summary"),
  diagnostics: () => api<any>("/api/v1/system/diagnostics"),
  get: () => api<any>("/api/v1/settings/desktop"),
  save: (value: any) =>
    api("/api/v1/settings/desktop", {
      method: "PUT",
      body: JSON.stringify(value),
    }),
  cloud: () => api<any>("/api/v1/settings/cloud"),
  setCloud: (enabled: boolean) =>
    api("/api/v1/settings/cloud", { method: "PUT", body: JSON.stringify({ enabled }) }),
  cloudBudget: () => api<any>("/api/v1/settings/cloud-budget"),
  saveCloudBudget: (value: any) =>
    api<any>("/api/v1/settings/cloud-budget", {
      method: "PUT",
      body: JSON.stringify(value),
    }),
  cloudUsage: () => api<any>("/api/v1/cloud-usage/summary"),
  cloudPricing: () => api<any>("/api/v1/cloud-pricing/status"),
};
