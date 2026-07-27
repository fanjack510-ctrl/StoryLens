/**
 * Stable Mock Run error presentation — Phase 2A Error Contract.
 * Never show stack / full body / credentials.
 */

import {
  MOCK_RUN_ERROR_CODES,
  MOCK_RUN_ERROR_MESSAGES,
  type MockRunErrorCode,
} from "../contracts/errors";
import { MockRunClientError } from "./types";

const KNOWN = new Set<string>(MOCK_RUN_ERROR_CODES);

export function isMockRunErrorCode(value: string): value is MockRunErrorCode {
  return KNOWN.has(value);
}

export function messageForMockRunError(
  code: MockRunErrorCode | "NETWORK" | "DTO_INVALID" | "UNKNOWN",
): string {
  if (code === "NETWORK") {
    return "无法连接 Mock Lab 服务。网络失败时不会将运行标记为 failed。";
  }
  if (code === "DTO_INVALID") {
    return "Mock Lab 响应格式无效（fail-closed）。";
  }
  if (code === "UNKNOWN") {
    return "未知错误。已 fail-closed；不会开放正式运行入口。";
  }
  return MOCK_RUN_ERROR_MESSAGES[code];
}

/** Chinese UI labels for known Phase 2A codes (stable; no stack). */
export const MOCK_RUN_ERROR_UI_LABELS: Record<MockRunErrorCode, string> = {
  MOCK_LAB_DISABLED: "Mock Lab 已禁用",
  MOCK_LAB_ENVIRONMENT_NOT_ALLOWED: "当前环境不允许 Mock Lab",
  MOCK_LAB_LOOPBACK_REQUIRED: "需要本机回环访问",
  MOCK_LAB_REQUEST_MARKER_REQUIRED: "缺少 Lab 请求标记",
  MOCK_LAB_ENGINE_REQUIRED: "需要 Mock 引擎",
  MOCK_LAB_ENGINE_NOT_PRODUCTION_SAFE: "引擎未标记为非生产",
  MOCK_ENGINE_REQUIRED: "需要 Mock 整书引擎",
  MOCK_RUN_NOT_FOUND: "未找到 Mock Run",
  MOCK_RUN_ALREADY_ACTIVE: "已有活动中的 Mock Run",
  MOCK_RUN_STATE_CONFLICT: "运行状态冲突",
  MOCK_RUN_OPERATION_NOT_ALLOWED: "当前状态不允许此操作",
  MOCK_RUN_IDEMPOTENCY_CONFLICT: "幂等键冲突",
  MOCK_RUN_SNAPSHOT_INVALID: "Snapshot 无效",
  MOCK_RUN_CHECKPOINT_INVALID: "Checkpoint 无效",
  MOCK_RUN_ENGINE_VERSION_MISMATCH: "引擎版本不匹配",
  MOCK_RUN_BUDGET_EXCEEDED: "Mock 预算已超限",
  MOCK_RUN_CANCELLED: "Mock Run 已取消",
  MOCK_RUN_NOT_RECOVERABLE: "无法恢复",
  MOCK_RUN_NON_MOCK_TARGET: "目标不是 Mock Lab Run",
};

export function presentMockRunError(error: unknown): {
  code: string;
  title: string;
  message: string;
} {
  if (error instanceof MockRunClientError) {
    const code = error.code;
    const title =
      isMockRunErrorCode(code) ? MOCK_RUN_ERROR_UI_LABELS[code] : "请求失败";
    return {
      code,
      title,
      message: error.message || messageForMockRunError(code),
    };
  }
  if (error instanceof Error) {
    return {
      code: "UNKNOWN",
      title: "未知错误",
      message: messageForMockRunError("UNKNOWN"),
    };
  }
  return {
    code: "UNKNOWN",
    title: "未知错误",
    message: messageForMockRunError("UNKNOWN"),
  };
}

export function toMockRunClientError(error: unknown): MockRunClientError {
  if (error instanceof MockRunClientError) return error;
  // ApiError-like
  if (
    error &&
    typeof error === "object" &&
    "code" in error &&
    "message" in error &&
    "status" in error
  ) {
    const e = error as {
      code: string;
      message: string;
      status: number;
      retryable?: boolean;
    };
    if (e.code === "BACKEND_OFFLINE" || e.status === 0) {
      return new MockRunClientError(
        messageForMockRunError("NETWORK"),
        "NETWORK",
        0,
        error,
        true,
      );
    }
    if (isMockRunErrorCode(e.code)) {
      return new MockRunClientError(
        e.message || messageForMockRunError(e.code),
        e.code,
        e.status,
        error,
        Boolean(e.retryable),
      );
    }
    return new MockRunClientError(
      e.message || messageForMockRunError("UNKNOWN"),
      "UNKNOWN",
      e.status,
      error,
      Boolean(e.retryable),
    );
  }
  if (error instanceof TypeError) {
    return new MockRunClientError(
      messageForMockRunError("NETWORK"),
      "NETWORK",
      0,
      error,
      true,
    );
  }
  return new MockRunClientError(
    messageForMockRunError("UNKNOWN"),
    "UNKNOWN",
    0,
    error,
    false,
  );
}
