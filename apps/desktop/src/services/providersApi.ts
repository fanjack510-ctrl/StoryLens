import { api } from "./apiClient";
import type { Provider } from "../types";
export const providersApi = {
  list: () => api<Provider[]>("/api/v1/model-providers"),
  cloud: () => api<any>("/api/v1/settings/cloud"),
  setCloud: (enabled: boolean) =>
    api("/api/v1/settings/cloud", {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    }),
  configuration: (name: string) =>
    api<any>(`/api/v1/model-providers/${name}/configuration`),
  save: (name: string, value: any) =>
    api<any>(`/api/v1/model-providers/${name}/configuration`, {
      method: "PUT",
      body: JSON.stringify(value),
    }),
  action: (name: string, action: string) =>
    api(`/api/v1/model-providers/${name}/${action}`, { method: "POST" }),
  deleteCredentials: (name: string) =>
    api(`/api/v1/model-providers/${name}/credentials`, { method: "DELETE" }),
  transportDiagnostic: (name: string) =>
    api<any>(`/api/v1/model-providers/${name}/transport-diagnostic`, { method: "POST" }),
  connectionTestPreflight: (name: string) =>
    api<any>(`/api/v1/model-providers/${name}/test/preflight`, { method: "POST" }),
  connect: (name: string) =>
    api<any>(`/api/v1/model-providers/${name}/connect`, { method: "POST" }),
  testConnection: (name: string, maxOutputTokens = 32) =>
    api<any>(`/api/v1/model-providers/${name}/test`, {
      method: "POST",
      body: JSON.stringify({
        confirmed: true,
        test_type: "minimal_json",
        max_output_tokens: maxOutputTokens,
      }),
    }),
  routing: () => api<any[]>("/api/v1/model-routing/preview"),
  localStatus: () => api<any>("/api/v1/local-model/status"),
  startLocal: (profile: string) =>
    api<any>("/api/v1/local-model/start", {
      method: "POST",
      body: JSON.stringify({ profile, acknowledge_gpu_load: true }),
    }),
  stopLocal: () => api<any>("/api/v1/local-model/stop", { method: "POST" }),
};
