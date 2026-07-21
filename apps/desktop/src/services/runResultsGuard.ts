import type { RunResults } from "../types";

export type RunResultsViewState =
  | { kind: "loading" }
  | { kind: "error"; error: Error }
  | { kind: "missing" }
  | { kind: "incomplete"; reason: string }
  | { kind: "failed"; status: string; run: RunResults["run"]; chapter: RunResults["chapter"] }
  | { kind: "completed"; data: RunResults };

function hasRunShape(value: unknown): value is RunResults["run"] {
  if (value == null || typeof value !== "object") return false;
  const run = value as Record<string, unknown>;
  return typeof run.id === "number" && typeof run.status === "string";
}

function hasChapterShape(value: unknown): value is RunResults["chapter"] {
  if (value == null || typeof value !== "object") return false;
  const chapter = value as Record<string, unknown>;
  return typeof chapter.id === "number" && typeof chapter.book_id === "number";
}

/**
 * Map raw /results query into explicit UI states.
 * Incomplete payloads are not treated as completed via optional chaining.
 */
export function resolveRunResultsViewState(args: {
  isLoading: boolean;
  error: unknown;
  data: unknown;
}): RunResultsViewState {
  if (args.isLoading) return { kind: "loading" };
  if (args.error) {
    const error =
      args.error instanceof Error ? args.error : new Error(String(args.error));
    return { kind: "error", error };
  }
  if (args.data == null) return { kind: "missing" };

  if (typeof args.data !== "object") {
    return { kind: "incomplete", reason: "分析结果响应格式无效" };
  }

  const payload = args.data as Partial<RunResults>;
  if (!hasRunShape(payload.run)) {
    return { kind: "incomplete", reason: "分析结果缺少运行状态（run.status）" };
  }
  if (!hasChapterShape(payload.chapter)) {
    return { kind: "incomplete", reason: "分析结果缺少章节信息" };
  }
  if (!Array.isArray(payload.scenes)) {
    return { kind: "incomplete", reason: "分析结果缺少场景列表" };
  }
  if (payload.summary == null || typeof payload.summary !== "object") {
    return { kind: "incomplete", reason: "分析结果缺少摘要信息" };
  }

  const data = payload as RunResults;
  if (data.run.status !== "succeeded") {
    return {
      kind: "failed",
      status: data.run.status,
      run: data.run,
      chapter: data.chapter,
    };
  }

  return { kind: "completed", data };
}
