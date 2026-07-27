/**
 * Mock Run action adapter — UI prototype only.
 * Shows future API request shapes; never hits production run control endpoints.
 */

import type { RunAllowedAction } from "../contracts/keys";
import type { WholeBookRunViewState } from "../contracts/runView";
import type { MockRunActionRequest, MockRunActionResult } from "./types";

function futurePath(
  action: MockRunActionRequest["action"],
  runId: number,
  stageKey?: string,
): string {
  switch (action) {
    case "pause":
      return `/api/v1/whole-book-runs/${runId}/pause`;
    case "resume":
      return `/api/v1/whole-book-runs/${runId}/resume`;
    case "cancel":
      return `/api/v1/whole-book-runs/${runId}/cancel`;
    case "retry":
      return `/api/v1/whole-book-runs/${runId}/stages/${stageKey ?? "{stage_key}"}/retry`;
    default:
      return `/api/v1/whole-book-runs/${runId}`;
  }
}

export function isActionAllowed(
  view: WholeBookRunViewState,
  action: RunAllowedAction,
  stageKey?: string,
): boolean {
  if (view.allowed_actions.includes(action)) {
    if (action !== "retry") return true;
  }
  if (action === "retry" && stageKey) {
    const stage = view.stages.find((s) => s.stage_key === stageKey);
    return Boolean(stage?.allowed_actions.includes("retry"));
  }
  return view.allowed_actions.includes(action);
}

/**
 * Apply a mock control action against an in-memory view state.
 * Completes only when allowed_actions (backend/fixture) contains the action.
 */
export function applyMockRunAction(
  view: WholeBookRunViewState,
  action: MockRunActionRequest["action"],
  options?: { stage_key?: string; confirmCancel?: boolean },
): { result: MockRunActionResult; next: WholeBookRunViewState } {
  const request: MockRunActionRequest = {
    action,
    run_id: view.run_id,
    stage_key: options?.stage_key,
    future_path: futurePath(action, view.run_id, options?.stage_key),
  };

  if (!isActionAllowed(view, action, options?.stage_key)) {
    return {
      result: {
        ok: false,
        action,
        message: `当前 allowed_actions 不包含 ${action}，无法执行`,
        request_preview: request,
      },
      next: view,
    };
  }

  if (action === "cancel" && !options?.confirmCancel) {
    return {
      result: {
        ok: false,
        action,
        message: "取消需要二次确认；已完成候选结果会保留，不会删除书籍或 Snapshot",
        request_preview: request,
      },
      next: view,
    };
  }

  const next: WholeBookRunViewState = {
    ...view,
    updated_at: new Date().toISOString(),
    stages: view.stages.map((s) => ({ ...s })),
    completed_modules: [...view.completed_modules],
    available_modules: [...view.available_modules],
    failed_modules: [...view.failed_modules],
    allowed_actions: [...view.allowed_actions],
    module_statuses: { ...view.module_statuses },
  };

  switch (action) {
    case "pause": {
      next.status = "paused";
      next.allowed_actions = ["resume", "cancel", "view_partial_results"];
      if (next.current_stage) {
        next.stages = next.stages.map((s) =>
          s.stage_key === next.current_stage
            ? { ...s, status: "paused", allowed_actions: ["resume", "cancel"] }
            : s,
        );
      }
      return {
        result: {
          ok: true,
          action,
          message: "已暂停（Mock）。已完成模块不受影响。",
          next_status: "paused",
          request_preview: request,
        },
        next,
      };
    }
    case "resume": {
      if (view.status !== "paused" && view.status !== "interrupted") {
        return {
          result: {
            ok: false,
            action,
            message: "仅 paused / interrupted 可恢复；已完成 Stage 不会重跑",
            request_preview: request,
          },
          next: view,
        };
      }
      next.status = "running";
      next.allowed_actions = ["pause", "cancel", "view_partial_results"];
      next.stages = next.stages.map((s) => {
        if (s.status === "completed" || s.status === "skipped") return s;
        if (s.status === "paused" || s.status === "interrupted") {
          return { ...s, status: "running", allowed_actions: ["pause", "cancel"] };
        }
        return s;
      });
      return {
        result: {
          ok: true,
          action,
          message: "已恢复（Mock）。已完成 Stage 不会重跑。",
          next_status: "running",
          request_preview: request,
        },
        next,
      };
    }
    case "retry": {
      const stageKey = options?.stage_key;
      const failed = next.stages.find(
        (s) => s.stage_key === stageKey && s.status === "failed",
      );
      if (!failed || !stageKey) {
        return {
          result: {
            ok: false,
            action,
            message: "重试必须指定失败的 Stage，不允许整书无差别重跑",
            request_preview: request,
          },
          next: view,
        };
      }
      const failedOrder = failed.order;
      next.status = "running";
      next.current_stage = stageKey;
      next.blocking_issue = null;
      next.stages = next.stages.map((s) => {
        if (s.stage_key === stageKey) {
          return {
            ...s,
            status: "running",
            attempt_count: s.attempt_count + 1,
            error_code: null,
            error_message: null,
            allowed_actions: ["pause", "cancel"],
          };
        }
        // Downstream may become stale / pending again (not auto-completed).
        if (s.order > failedOrder && s.status !== "completed") {
          return {
            ...s,
            status: "pending",
            warnings: [
              ...s.warnings,
              "上游阶段重试后，本阶段可能需要重新执行",
            ],
            allowed_actions: [],
          };
        }
        return s;
      });
      next.allowed_actions = ["pause", "cancel", "view_partial_results"];
      // Completed modules remain visible.
      return {
        result: {
          ok: true,
          action,
          message: `已针对失败阶段 ${failed.display_name} 发起重试（Mock）。下游阶段可能重新失效。`,
          next_status: "running",
          request_preview: request,
        },
        next,
      };
    }
    case "cancel": {
      next.status = "cancelled";
      next.allowed_actions = next.partial_results_available
        ? ["view_partial_results"]
        : [];
      next.stages = next.stages.map((s) => {
        if (s.status === "completed" || s.status === "skipped") return s;
        if (s.status === "running" || s.status === "paused" || s.status === "pending") {
          return { ...s, status: "cancelled", allowed_actions: [] };
        }
        return { ...s, allowed_actions: [] };
      });
      return {
        result: {
          ok: true,
          action,
          message:
            "运行已取消（Mock）。已产生的候选结果会保留；不等于删除书籍或 Snapshot。",
          next_status: "cancelled",
          request_preview: request,
        },
        next,
      };
    }
    default:
      return {
        result: {
          ok: false,
          action,
          message: "未知操作",
          request_preview: request,
        },
        next: view,
      };
  }
}

export const mockRunActionAdapter = {
  apply: applyMockRunAction,
  isAllowed: isActionAllowed,
  previewRequest(
    view: WholeBookRunViewState,
    action: MockRunActionRequest["action"],
    stageKey?: string,
  ): MockRunActionRequest {
    return {
      action,
      run_id: view.run_id,
      stage_key: stageKey,
      future_path: futurePath(action, view.run_id, stageKey),
    };
  },
};
