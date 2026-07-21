import { ApiError } from "./apiClient";

/**
 * Normalize model-invocations API payload to a stable array.
 * Null/undefined → []. Arrays pass through.
 * Error-shaped objects and other non-arrays throw (do not silently swallow).
 */
export function normalizeInvocations(data: unknown, runId: number): unknown[] {
  if (data == null) return [];
  if (Array.isArray(data)) return data;

  if (typeof data === "object") {
    const record = data as Record<string, unknown>;
    const detail = record.detail;
    const code =
      (typeof record.error_code === "string" && record.error_code) ||
      (typeof record.code === "string" && record.code) ||
      "INVOCATIONS_RESPONSE_INVALID";
    const message =
      (typeof detail === "string" && detail) ||
      (typeof record.message === "string" && record.message) ||
      `模型调用列表响应格式异常（Run #${runId}）`;
    const status =
      typeof record.status === "number" && Number.isFinite(record.status)
        ? record.status
        : 502;
    throw new ApiError(code, message, status, data);
  }

  throw new ApiError(
    "INVOCATIONS_RESPONSE_INVALID",
    `模型调用列表响应格式异常（Run #${runId}）`,
    502,
    data,
  );
}
