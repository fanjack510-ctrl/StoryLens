/** Resolve Reader Journey pane gate from confirmed revision + journey binding (CHG-041 R2). */

export type SceneJourneyGateKind =
  | "need_confirm"
  | "confirmed_no_journey"
  | "stale_journey"
  | "running"
  | "ready"
  | "failed";

export type SceneJourneyGate = {
  kind: SceneJourneyGateKind;
  title: string;
  description: string;
  primaryLabel: string;
  primaryTestId: string;
};

export function resolveSceneJourneyGate(args: {
  awaitingConfirmation: boolean;
  confirmedRevisionId: number | null | undefined;
  confirmedSource?: string | null;
  journeyStatus?: string | null;
  journeySceneRevisionId?: number | null;
  journeyResultStatus?: string | null;
}): SceneJourneyGate {
  const confirmedId = args.confirmedRevisionId ?? null;
  const journeyRev = args.journeySceneRevisionId ?? null;
  const status = (args.journeyStatus || "").toLowerCase();
  const running =
    status === "queued" ||
    status === "running" ||
    status === "scene_profiles_running" ||
    status === "chapter_synthesis_running" ||
    status === "pending";

  if (args.awaitingConfirmation || confirmedId == null) {
    return {
      kind: "need_confirm",
      title: "阅读旅程尚未开始",
      description: "请先确认场景边界，StoryLens 将按照确认后的场景进行旅程分析。",
      primaryLabel: "去确认场景",
      primaryTestId: "reader-journey-go-confirm-scenes",
    };
  }

  if (journeyRev != null && journeyRev !== confirmedId) {
    return {
      kind: "stale_journey",
      title: "当前阅读旅程基于旧场景版本",
      description: "场景划分已更新，需要按当前确认版本重新生成阅读旅程。",
      primaryLabel: "按当前场景重新生成",
      primaryTestId: "reader-journey-regenerate",
    };
  }

  if (journeyRev === confirmedId && running) {
    return {
      kind: "running",
      title: "正在生成阅读旅程",
      description: "已按确认后的场景划分开始生成。",
      primaryLabel: "查看阅读旅程进度",
      primaryTestId: "reader-journey-view-progress",
    };
  }

  if (journeyRev === confirmedId && status === "succeeded") {
    return {
      kind: "ready",
      title: "阅读旅程已就绪",
      description: "可查看当前确认场景对应的阅读旅程结果。",
      primaryLabel: "查看阅读旅程",
      primaryTestId: "reader-journey-view-result",
    };
  }

  if (journeyRev === confirmedId && (status === "failed" || status === "cancelled")) {
    return {
      kind: "failed",
      title: "阅读旅程生成失败",
      description: "场景划分仍然有效，可重新尝试生成阅读旅程。",
      primaryLabel: "重新尝试生成阅读旅程",
      primaryTestId: "reader-journey-retry-generate",
    };
  }

  return {
    kind: "confirmed_no_journey",
    title: "场景划分已确认，尚未生成阅读旅程",
    description: "确认后的场景划分已保存，可开始生成阅读旅程。",
    primaryLabel: "生成阅读旅程",
    primaryTestId: "reader-journey-generate",
  };
}
