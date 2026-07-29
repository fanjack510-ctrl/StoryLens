/**
 * CHG-20260729-005 — ordinary-user chapter hook page simplification (presentation only).
 * Does NOT change hook recognition, persisted facts, or other lenses.
 */

import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";
import {
  getNarrativeLoops,
  type NarrativeLoopPayoff,
  type NarrativeLoopView,
} from "./narrativeLoopView";
import { shortPlainTitle } from "./readerJourneyLensExplanation";
import {
  resolveHookMainStatus,
  type HookMainStatus,
} from "./hookResolutionModel";

export const CHAPTER_HOOK_TAB_LABEL = "钩子回收";

export const CHAPTER_HOOK_PAGE_BLURB =
  "钩子回收：查看本章提出了哪些问题、给出了哪些回应，以及留下了什么后续期待。";

export type ChapterHookNodeLabel =
  | "提出疑问"
  | "加深悬念"
  | "给出回应"
  | "留到下章";

export type ChapterPullLabel = "明确" | "较弱" | "暂无" | "无法判断";

export type ChapterHookNodeJudgment = {
  short_label: ChapterHookNodeLabel | null;
  full_reason: string | null;
  related_hook_ids: string[];
  source: "derived" | "unavailable";
  confidence: "high" | "medium" | "low";
};

export type ImportantChapterHook = {
  loop_id: string;
  reader_question: string;
  open_scene: number;
  resolve_scene: number | null;
  role: "提出" | "回应" | "保留" | "牵引";
  importance: number;
  main_status: HookMainStatus;
};

export type ChapterHookOverview = {
  raised: number;
  answered: number;
  carried: number;
  chapter_pull: ChapterPullLabel;
};

export type ChapterHookSceneRow = {
  scene_ordinal: number;
  short_label: ChapterHookNodeLabel | null;
  full_reason: string | null;
  related_hook_ids: string[];
  source: "derived" | "unavailable";
};

export type ChapterHookSimplificationModel = {
  empty: boolean;
  max_scene: number;
  overview: ChapterHookOverview;
  important_hooks: ImportantChapterHook[];
  scene_rows: ChapterHookSceneRow[];
  page_blurb: string;
  summary_line: string;
};

function openSceneOf(loop: NarrativeLoopView): number {
  return (
    loop.open_from_scene ??
    loop.hook?.[0]?.scene_ordinal ??
    loop.developments?.[0]?.scene_ordinal ??
    1
  );
}

function entityPayoffs(loop: NarrativeLoopView): NarrativeLoopPayoff[] {
  return (loop.payoffs || []).filter(
    (p) =>
      p &&
      p.source_type !== "score_inferred" &&
      String(p.type || "") !== "score_inferred",
  );
}

function loopImportance(loop: NarrativeLoopView, openScene: number): number {
  const strength =
    typeof loop.hook?.[0]?.strength === "number" ? loop.hook[0].strength! : 50;
  const status = resolveHookMainStatus(loop).main_status;
  let score = strength;
  const q = `${loop.question || ""} ${loop.information_gap || ""}`;
  if (/主角|目标|追查|为什么|是谁|怎么/.test(q)) score += 18;
  if (/冲突|危险|反转|真相|门外|信/.test(q)) score += 12;
  if (status === "unresolved") score += 10;
  if (status === "partial") score += 4;
  // Prefer earlier setup slightly for stable ties after importance.
  score += Math.max(0, 6 - openScene * 0.15);
  return score;
}

function isInternalNoise(text: string): boolean {
  const t = text.trim();
  if (!t) return true;
  if (/^hook[_-]?\d+/i.test(t)) return true;
  if (/smoke[-_]?fake/i.test(t)) return true;
  if (/^ql[_-]/i.test(t) || /^loop[_-]/i.test(t)) return true;
  if (/^\{/.test(t) || /_id\b/.test(t)) return true;
  return false;
}

function readerQuestionOf(loop: NarrativeLoopView): string | null {
  const raw = String(loop.question || loop.information_gap || "").trim();
  if (!raw || isInternalNoise(raw)) return null;
  const cleaned = shortPlainTitle(raw, 18);
  if (!cleaned || isInternalNoise(cleaned)) return null;
  return cleaned;
}

function maxSceneOf(visualization: ReaderJourneyVisualization): number {
  let max = 1;
  for (const n of visualization.scene_nodes || []) {
    max = Math.max(max, n.scene_ordinal);
  }
  return Math.max(max, 1);
}

function isNearChapterEnd(sceneOrdinal: number, maxScene: number): boolean {
  if (maxScene <= 1) return true;
  if (maxScene <= 3) return sceneOrdinal === maxScene;
  return sceneOrdinal >= maxScene - 1;
}

function sceneHasRaise(loop: NarrativeLoopView, scene: number): boolean {
  return openSceneOf(loop) === scene;
}

function sceneHasDeepen(loop: NarrativeLoopView, scene: number): boolean {
  const open = openSceneOf(loop);
  if (scene <= open) return false;
  const inDev = (loop.developments || []).some((d) => d.scene_ordinal === scene);
  if (inDev) return true;
  // Hook entity on a later scene without payoff counts as deepen.
  const hookHit = (loop.hook || []).some((h) => h.scene_ordinal === scene);
  const payoffHit = entityPayoffs(loop).some((p) => p.scene_ordinal === scene);
  return hookHit && !payoffHit;
}

function sceneHasAnswer(loop: NarrativeLoopView, scene: number): boolean {
  const info = resolveHookMainStatus(loop);
  if (info.main_status === "unresolved") return false;
  if (info.resolve_scene === scene) return true;
  return entityPayoffs(loop).some((p) => p.scene_ordinal === scene);
}

function sceneHasCarryToNext(
  loop: NarrativeLoopView,
  scene: number,
  maxScene: number,
): boolean {
  if (!isNearChapterEnd(scene, maxScene)) return false;
  const info = resolveHookMainStatus(loop);
  if (info.main_status === "resolved") return false;
  // Must already be open before or at this scene, and still meaningful.
  const open = openSceneOf(loop);
  if (open > scene) return false;
  return info.main_status === "unresolved" || info.main_status === "partial";
}

/**
 * Deterministic per-scene ordinary label.
 * Priority: 给出回应 > 留到下章 > 加深悬念 > 提出疑问
 * Exception: raising the chapter's top important hook may promote 提出疑问.
 */
export function deriveChapterHookNodeLabelV1(input: {
  sceneOrdinal: number;
  maxScene: number;
  loops: NarrativeLoopView[];
  topImportantLoopId?: string | null;
}): ChapterHookNodeJudgment {
  const { sceneOrdinal, maxScene, loops, topImportantLoopId } = input;
  if (!loops.length) {
    return {
      short_label: null,
      full_reason: "当前节点暂无可靠判断",
      related_hook_ids: [],
      source: "unavailable",
      confidence: "low",
    };
  }

  const answerLoops = loops.filter((l) => sceneHasAnswer(l, sceneOrdinal));
  const carryLoops = loops.filter((l) => sceneHasCarryToNext(l, sceneOrdinal, maxScene));
  const deepenLoops = loops.filter((l) => sceneHasDeepen(l, sceneOrdinal));
  const raiseLoops = loops.filter((l) => sceneHasRaise(l, sceneOrdinal));

  const topRaise =
    topImportantLoopId &&
    raiseLoops.some((l) => l.loop_id === topImportantLoopId);

  let label: ChapterHookNodeLabel | null = null;
  let related: NarrativeLoopView[] = [];
  let reason: string | null = null;
  let confidence: "high" | "medium" | "low" = "medium";

  if (answerLoops.length && !(topRaise && !answerLoops.length)) {
    // Normal priority: answer wins unless we only have a top raise with no answer.
  }
  if (answerLoops.length && !topRaise) {
    label = "给出回应";
    related = answerLoops;
    reason = "本场景对已有问题给出了有效信息（部分或完整回应）。";
    confidence = "high";
  } else if (answerLoops.length && topRaise) {
    // Same scene both answers something and raises the chapter-core question:
    // still prefer 给出回应 per priority, unless the only answer is weak and top raise is unique.
    label = "给出回应";
    related = answerLoops;
    reason = "本场景对已有问题给出了有效信息；同时可能提出新问题。";
    confidence = "high";
  } else if (carryLoops.length) {
    label = "留到下章";
    related = carryLoops;
    reason = "临近章末，仍有明确跨章期待留给后续。";
    confidence = "high";
  } else if (deepenLoops.length) {
    label = "加深悬念";
    related = deepenLoops;
    reason = "本场景未直接回答，但强化了已有问题的风险或信息差。";
    confidence = "medium";
  } else if (raiseLoops.length) {
    label = "提出疑问";
    related = raiseLoops;
    reason = "本场景首次形成明确读者问题。";
    confidence = "high";
  } else if (topRaise) {
    label = "提出疑问";
    related = raiseLoops;
    reason = "本场景提出本章最重要的核心问题。";
    confidence = "high";
  }

  // Promote: if this scene first raises the single most important hook and
  // there is no answer here, ensure 提出疑问 (already handled). If answer also
  // exists on the same scene as the top raise only, keep 给出回应 unless the
  // top important hook is raised here and answers are for other loops only —
  // then prefer 提出疑问 for the chapter-core signal.
  if (
    topImportantLoopId &&
    raiseLoops.some((l) => l.loop_id === topImportantLoopId) &&
    answerLoops.length > 0 &&
    !answerLoops.some((l) => l.loop_id === topImportantLoopId)
  ) {
    label = "提出疑问";
    related = raiseLoops.filter((l) => l.loop_id === topImportantLoopId);
    reason = "本场景首次提出全章最重要的核心问题。";
    confidence = "high";
  }

  if (!label) {
    return {
      short_label: null,
      full_reason: "当前节点暂无可靠判断",
      related_hook_ids: [],
      source: "unavailable",
      confidence: "low",
    };
  }

  return {
    short_label: label,
    full_reason: reason,
    related_hook_ids: related.map((l) => l.loop_id),
    source: "derived",
    confidence,
  };
}

export function selectImportantChapterHooks(
  loops: NarrativeLoopView[],
  maxScene: number,
  limit = 3,
): ImportantChapterHook[] {
  const scored = loops
    .map((loop) => {
      const open = openSceneOf(loop);
      const info = resolveHookMainStatus(loop);
      const q = readerQuestionOf(loop);
      if (!q) return null;
      const importance = loopImportance(loop, open);
      let role: ImportantChapterHook["role"] = "提出";
      if (info.main_status === "resolved") role = "回应";
      else if (info.main_status === "partial") role = "回应";
      else if (info.main_status === "unresolved") {
        role = openSceneOf(loop) <= maxScene ? "保留" : "提出";
        if (isNearChapterEnd(maxScene, maxScene)) role = "牵引";
      }
      return {
        loop_id: loop.loop_id,
        reader_question: q,
        open_scene: open,
        resolve_scene: info.resolve_scene,
        role,
        importance,
        main_status: info.main_status,
      } satisfies ImportantChapterHook;
    })
    .filter((x): x is ImportantChapterHook => x != null);

  scored.sort((a, b) => {
    if (b.importance !== a.importance) return b.importance - a.importance;
    if (a.open_scene !== b.open_scene) return a.open_scene - b.open_scene;
    return a.loop_id.localeCompare(b.loop_id);
  });

  return scored.slice(0, Math.max(1, Math.min(limit, 3)));
}

export function deriveChapterPullLabel(
  loops: NarrativeLoopView[],
  maxScene: number,
): ChapterPullLabel {
  if (!loops.length) return "无法判断";
  const openAtEnd = loops.filter((loop) => {
    const info = resolveHookMainStatus(loop);
    if (info.main_status === "resolved") return false;
    const open = openSceneOf(loop);
    return open <= maxScene;
  });
  if (!openAtEnd.length) return "暂无";
  const strong = openAtEnd.filter((loop) => {
    const q = readerQuestionOf(loop);
    const imp = loopImportance(loop, openSceneOf(loop));
    return Boolean(q) && imp >= 60;
  });
  if (strong.length >= 1) return "明确";
  if (openAtEnd.length >= 1) return "较弱";
  return "暂无";
}

export function buildChapterHookSimplificationModel(
  visualization: ReaderJourneyVisualization,
): ChapterHookSimplificationModel {
  const loops = getNarrativeLoops(visualization);
  const maxScene = maxSceneOf(visualization);
  const important = selectImportantChapterHooks(loops, maxScene, 3);
  const topId = important[0]?.loop_id ?? null;

  let raised = 0;
  let answered = 0;
  let carried = 0;

  // Prefer counting readable reader questions opened in this chapter.
  const readable = loops.filter((l) => readerQuestionOf(l));
  raised = readable.filter((l) => {
    const open = openSceneOf(l);
    return open >= 1 && open <= maxScene;
  }).length;
  answered = readable.filter((l) => {
    const info = resolveHookMainStatus(l);
    return info.main_status === "resolved" || info.main_status === "partial";
  }).length;
  carried = readable.filter((l) => resolveHookMainStatus(l).main_status === "unresolved").length;

  const chapter_pull = deriveChapterPullLabel(readable, maxScene);

  const scene_rows: ChapterHookSceneRow[] = [];
  for (let s = 1; s <= maxScene; s += 1) {
    const j = deriveChapterHookNodeLabelV1({
      sceneOrdinal: s,
      maxScene,
      loops: readable.length ? readable : loops,
      topImportantLoopId: topId,
    });
    scene_rows.push({
      scene_ordinal: s,
      short_label: j.short_label,
      full_reason: j.full_reason,
      related_hook_ids: j.related_hook_ids,
      source: j.source,
    });
  }

  const overview: ChapterHookOverview = {
    raised,
    answered,
    carried,
    chapter_pull,
  };

  const summary_line =
    overview.raised === 0
      ? "本章未识别出明确的重要读者问题。"
      : `本章提出 ${overview.raised} 个重要问题，回应 ${overview.answered} 个，继续保留 ${overview.carried} 个；章末牵引：${overview.chapter_pull}。`;

  return {
    empty: readable.length === 0 && loops.length === 0,
    max_scene: maxScene,
    overview,
    important_hooks: important,
    scene_rows,
    page_blurb: CHAPTER_HOOK_PAGE_BLURB,
    summary_line,
  };
}
