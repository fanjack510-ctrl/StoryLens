/**
 * Shared ordinary-user Bailian (Qwen) setup.
 * FirstLaunchWizard and SettingsAiServiceTab must call only these helpers.
 */

import type { QueryClient } from "@tanstack/react-query";
import {
  type AnalysisModePresetId,
  writeStoredAnalysisMode,
} from "./analysisModePresets";
import { mapTransportOrHttpError } from "./aiServiceViewModel";
import { api } from "./apiClient";
import { mapConnectionError, redactSecrets } from "./userFacingErrors";

export type RecommendedQwenSetupStatus = {
  ok: boolean;
  user_message: string;
  persisted: boolean;
  credential_configured: boolean;
  provider_enabled: boolean;
  cloud_enabled: boolean;
  provider_eligible: boolean;
  selected_provider_id: string;
  connection_status: string;
  analysis_mode: string | null;
  blockers: string[];
  needs_cloud_consent: boolean;
  error_code?: string | null;
};

export type ConfigureRecommendedQwenInput = {
  apiKey: string;
  analysisMode: Exclude<AnalysisModePresetId, "CUSTOM">;
  cloudBodyConsent: boolean;
  /** false = connectivity probe only; does not claim configuration saved */
  persist: boolean;
  qc?: QueryClient;
};

const SETUP_PATH = "/api/v1/desktop/ai-setup/recommended-qwen";

export async function fetchRecommendedQwenStatus(): Promise<RecommendedQwenSetupStatus> {
  return api<RecommendedQwenSetupStatus>(SETUP_PATH);
}

export async function configureRecommendedQwenService(
  input: ConfigureRecommendedQwenInput,
): Promise<RecommendedQwenSetupStatus> {
  const body = {
    api_key: input.apiKey.trim() ? input.apiKey.trim() : null,
    analysis_mode: input.analysisMode,
    cloud_body_consent: input.cloudBodyConsent,
    persist: input.persist,
  };
  try {
    const result = await api<RecommendedQwenSetupStatus>(SETUP_PATH, {
      method: "POST",
      body: JSON.stringify(body),
    });
    if (result.ok && result.persisted && result.analysis_mode) {
      writeStoredAnalysisMode(result.analysis_mode as AnalysisModePresetId);
    }
    if (input.qc) {
      await invalidateAiQueries(input.qc);
    }
    return result;
  } catch (error: any) {
    const mapped = mapTransportOrHttpError(error);
    return {
      ok: false,
      user_message: mapConnectionError({
        code: mapped.rawCode,
        status: error?.status,
        message: redactSecrets(error?.message || mapped.userLabel),
      }),
      persisted: false,
      credential_configured: false,
      provider_enabled: false,
      cloud_enabled: false,
      provider_eligible: false,
      selected_provider_id: "aliyun_qwen_plus",
      connection_status: "unconfigured",
      analysis_mode: null,
      blockers: [mapped.rawCode || "request_failed"],
      needs_cloud_consent: false,
      error_code: mapped.rawCode,
    };
  }
}

export async function repairRecommendedQwenSetup(input: {
  cloudBodyConsent?: boolean | null;
  qc?: QueryClient;
}): Promise<RecommendedQwenSetupStatus> {
  try {
    const result = await api<RecommendedQwenSetupStatus>(`${SETUP_PATH}/repair`, {
      method: "POST",
      body: JSON.stringify({
        cloud_body_consent: input.cloudBodyConsent ?? null,
      }),
    });
    if (input.qc) {
      await invalidateAiQueries(input.qc);
    }
    return result;
  } catch (error: any) {
    return {
      ok: false,
      user_message: mapConnectionError({
        code: error?.code,
        status: error?.status,
        message: redactSecrets(error?.message || "修复失败"),
      }),
      persisted: false,
      credential_configured: false,
      provider_enabled: false,
      cloud_enabled: false,
      provider_eligible: false,
      selected_provider_id: "aliyun_qwen_plus",
      connection_status: "unconfigured",
      analysis_mode: null,
      blockers: [error?.code || "repair_failed"],
      needs_cloud_consent: Boolean(error?.code === "CLOUD_CONSENT_REQUIRED"),
      error_code: error?.code || "REPAIR_FAILED",
    };
  }
}

export async function invalidateAiQueries(qc: QueryClient) {
  await Promise.all([
    qc.invalidateQueries({ queryKey: ["providers"] }),
    qc.invalidateQueries({ queryKey: ["cloud"] }),
    qc.invalidateQueries({ queryKey: ["cloud-usage"] }),
    qc.invalidateQueries({ queryKey: ["cloud-budget"] }),
    qc.invalidateQueries({ queryKey: ["provider-config"] }),
    qc.invalidateQueries({ queryKey: ["recommended-qwen-setup"] }),
  ]);
}

/** @deprecated Prefer configureRecommendedQwenService — kept for advanced diagnostics only */
export async function persistProviderConnected(providerId: string, qc: QueryClient) {
  const { providersApi } = await import("./providersApi");
  const { settingsApi } = await import("./settingsApi");
  if (!(await settingsApi.cloud()).enabled) {
    await settingsApi.setCloud(true);
  }
  await providersApi.action(providerId, "enable");
  await providersApi.action(providerId, "connect");
  const latest = await providersApi.configuration(providerId);
  qc.setQueryData(["provider-config", providerId], latest);
}

/** @deprecated Use configureRecommendedQwenService({ persist: true }) */
export async function saveAiServiceConfiguration(input: {
  providerId: string;
  apiKey: string;
  analysisMode: AnalysisModePresetId;
  cloudBodyConsent: boolean;
  qc: QueryClient;
}): Promise<{ ok: boolean; userMessage: string; rawDiagnostic?: string; testErrorCode?: string | null }> {
  const mode = input.analysisMode === "CUSTOM" ? "BALANCED" : input.analysisMode;
  const result = await configureRecommendedQwenService({
    apiKey: input.apiKey,
    analysisMode: mode,
    cloudBodyConsent: input.cloudBodyConsent,
    persist: true,
    qc: input.qc,
  });
  return {
    ok: result.ok && result.persisted,
    userMessage: result.user_message,
    testErrorCode: result.error_code || null,
  };
}

/** @deprecated Use configureRecommendedQwenService({ persist: false }) */
export async function testAiServiceConnection(
  _providerId: string,
  qc: QueryClient,
): Promise<{ ok: boolean; userMessage: string; rawDiagnostic?: string; testErrorCode?: string | null }> {
  const result = await configureRecommendedQwenService({
    apiKey: "",
    analysisMode: "BALANCED",
    cloudBodyConsent: false,
    persist: false,
    qc,
  });
  return {
    ok: result.ok,
    userMessage: result.user_message,
    testErrorCode: result.error_code || null,
  };
}
