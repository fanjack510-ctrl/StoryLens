/** Pause / Resume / Retry / Cancel action mirror (Phase 2A-P). */

import type { WholeBookRunViewStatus } from "../../contracts/keys";
import { canResume, isAllowedRunTransition } from "./runState";

export const MOCK_RUN_ACTIONS = ["pause", "resume", "retry", "cancel"] as const;
export type MockRunAction = (typeof MOCK_RUN_ACTIONS)[number];

export type MockRunActionRequest = {
  run_id: number;
  action: MockRunAction;
  operation_idempotency_key: string;
  expected_state?: WholeBookRunViewStatus | null;
  expected_version?: number | null;
  stage_key?: string | null;
  confirm_cancel?: boolean;
};

export type MockRunActionResult = {
  run_id: number;
  action: MockRunAction;
  requested: boolean;
  accepted: boolean;
  current_state: WholeBookRunViewStatus;
  idempotent_replay: boolean;
  detail_code?: string | null;
};

export function actionAllowedForState(
  action: MockRunAction,
  status: WholeBookRunViewStatus,
): boolean {
  if (action === "pause") return isAllowedRunTransition(status, "paused");
  if (action === "resume") return canResume(status);
  if (action === "retry") return status === "failed";
  if (action === "cancel") return isAllowedRunTransition(status, "cancelled");
  return false;
}

export const LAB_UI_LABELS = {
  mockStartButton: "启动 Mock 验证运行",
  productionStillDisabled: "生产启动仍不可用",
  nonProductionBanner: "开发验证，不是真实分析",
  mockBadge: "mock / non-production",
} as const;
