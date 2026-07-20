import type { QueryClient } from "@tanstack/react-query";
import {
  applyPresetToCloudBudget,
  applyPresetToProviderConfig,
  type AnalysisModePresetId,
  writeStoredAnalysisMode,
} from "./analysisModePresets";
import {
  DEFAULT_AI_SERVICE_DISPLAY_NAME,
  mapTransportOrHttpError,
  serviceDisplayNameFor,
} from "./aiServiceViewModel";
import { mapConnectionError, redactSecrets } from "./userFacingErrors";
import { providersApi } from "./providersApi";
import { settingsApi } from "./settingsApi";

export async function persistProviderConnected(providerId: string, qc: QueryClient) {
  if (!(await settingsApi.cloud()).enabled) {
    await settingsApi.setCloud(true);
  }
  await providersApi.action(providerId, "enable");
  await providersApi.action(providerId, "connect");
  const latest = await providersApi.configuration(providerId);
  qc.setQueryData(["provider-config", providerId], latest);
}

export type SaveAiServiceInput = {
  providerId: string;
  apiKey: string;
  analysisMode: AnalysisModePresetId;
  cloudBodyConsent: boolean;
  qc: QueryClient;
};

export async function saveAiServiceConfiguration(input: SaveAiServiceInput): Promise<{
  ok: boolean;
  userMessage: string;
  rawDiagnostic?: string;
  testErrorCode?: string | null;
}> {
  const { providerId, apiKey, analysisMode, cloudBodyConsent, qc } = input;
  if (!cloudBodyConsent) {
    return { ok: false, userMessage: "请先确认云端正文发送说明。" };
  }
  if (!apiKey) {
    const cfg = await providersApi.configuration(providerId);
    if (cfg.credential_state !== "configured") {
      return { ok: false, userMessage: "请填写 API Key 后再保存。" };
    }
  }

  try {
    const existing = await providersApi.configuration(providerId);
    let providerPayload: Record<string, unknown> = {
      ...existing,
      display_name: serviceDisplayNameFor(providerId) || DEFAULT_AI_SERVICE_DISPLAY_NAME,
      api_key: apiKey || null,
      enabled: true,
      disconnected: false,
      allow_auto_route: false,
    };

    const currentBudget = await settingsApi.cloudBudget();
    let budgetPayload: Record<string, unknown> = { ...currentBudget };

    if (analysisMode !== "CUSTOM") {
      providerPayload = applyPresetToProviderConfig(providerPayload, analysisMode);
      budgetPayload = applyPresetToCloudBudget(budgetPayload, analysisMode);
      writeStoredAnalysisMode(analysisMode);
    } else {
      writeStoredAnalysisMode("CUSTOM");
    }

    await settingsApi.saveCloudBudget({ ...budgetPayload, currency: "CNY" });
    await providersApi.save(providerId, providerPayload);
    await settingsApi.setCloud(true);

    const transport = await providersApi.transportDiagnostic(providerId);
    const rawDiagnostic = JSON.stringify(transport, null, 2);
    if (transport.overall_status === "ok" || transport.overall_status === "healthy") {
      await persistProviderConnected(providerId, qc);
      await invalidateAiQueries(qc);
      return { ok: true, userMessage: "保存成功，连接正常。", rawDiagnostic };
    }
    const mapped = mapTransportOrHttpError({
      code: transport.error_code || "TRANSPORT_FAILED",
      message: transport.user_action_hint || transport.overall_status,
    });
    await invalidateAiQueries(qc);
    return {
      ok: false,
      userMessage: mapConnectionError({ code: mapped.rawCode, message: mapped.userLabel }),
      rawDiagnostic,
      testErrorCode: mapped.rawCode,
    };
  } catch (error: any) {
    const mapped = mapTransportOrHttpError(error);
    return {
      ok: false,
      userMessage: mapConnectionError({
        code: mapped.rawCode,
        status: error?.status,
        message: redactSecrets(error?.message || mapped.userLabel),
      }),
      rawDiagnostic: JSON.stringify(
        {
          code: error?.code,
          status: error?.status,
          message: redactSecrets(error?.message || ""),
          requestId: error?.requestId,
        },
        null,
        2,
      ),
      testErrorCode: mapped.rawCode,
    };
  }
}

export async function testAiServiceConnection(
  providerId: string,
  qc: QueryClient,
): Promise<{ ok: boolean; userMessage: string; rawDiagnostic?: string; testErrorCode?: string | null }> {
  try {
    const transport = await providersApi.transportDiagnostic(providerId);
    const rawDiagnostic = JSON.stringify(transport, null, 2);
    if (transport.overall_status === "ok" || transport.overall_status === "healthy") {
      await persistProviderConnected(providerId, qc);
      await invalidateAiQueries(qc);
      return { ok: true, userMessage: "连接测试成功。", rawDiagnostic };
    }
    const mapped = mapTransportOrHttpError({
      code: transport.error_code || "TRANSPORT_FAILED",
      message: transport.user_action_hint || transport.overall_status,
    });
    return {
      ok: false,
      userMessage: mapConnectionError({ code: mapped.rawCode, message: mapped.userLabel }),
      rawDiagnostic,
      testErrorCode: mapped.rawCode,
    };
  } catch (error: any) {
    const mapped = mapTransportOrHttpError(error);
    return {
      ok: false,
      userMessage: mapConnectionError({
        code: mapped.rawCode,
        status: error?.status,
        message: error?.message,
      }),
      rawDiagnostic: JSON.stringify(
        { code: error?.code, status: error?.status, message: error?.message },
        null,
        2,
      ),
      testErrorCode: mapped.rawCode,
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
  ]);
}
