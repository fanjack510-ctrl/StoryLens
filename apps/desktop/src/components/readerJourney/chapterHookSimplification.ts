/**
 * CHG-20260729-005 — ordinary-user chapter hook page simplification (presentation only).
 * Does NOT change hook recognition, persisted facts, or other lenses.
 */

import type {
  JourneySceneNode,
  ReaderJourneyVisualization,
} from "../../types/readerJourneyVisualization";
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
import { formatJourneySceneLabel, roleLabelZh } from "./journeyUiLabels";

export const CHAPTER_HOOK_TAB_LABEL = "钩子回收";

export const CHAPTER_HOOK_PAGE_BLURB =
  "钩子回收：查看本章提出了哪些问题、给出了哪些回应，以及留下了什么后续期待。";

export const CHAPTER_HOOK_EMPTY_TITLE = "本章未识别到明确的阅读钩子。";
export const CHAPTER_HOOK_EMPTY_NOTE =
  "这不一定代表章节存在问题；本章可能主要承担过渡、解释或情绪收束任务。";
export const CHAPTER_HOOK_LOW_CONFIDENCE_TITLE =
  "当前仅识别到较弱的阅读期待，暂无可靠钩子结论。";

export type ChapterHookNodeLabel =
  | "提出疑问"
  | "加深悬念"
  | "给出回应"
  | "留到下章";

export type ChapterPullLabel = "明确" | "较弱" | "暂无" | "无法判断";

export type ImportantHookResultLabel =
  | "已回应"
  | "部分回应"
  | "继续保留"
  | "暂无可靠判断";

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
  last_change_scene: number;
  result_label: ImportantHookResultLabel;
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

export type ChapterEndingPull = {
  status: ChapterPullLabel;
  left_behind: string | null;
  reader_wants: string | null;
  judgment: string | null;
  source: "derived" | "unavailable";
};

export type ChapterHookSceneInsight = {
  title: string;
  body: string;
  source: "derived" | "unavailable";
  node_label: ChapterHookNodeLabel | null;
};

export type ChapterHookTechRow = {
  loop_id: string;
  question: string;
  status: string;
  open_scene: number;
  development_scenes: number[];
  resolve_scene: number | null;
  payoff_types: string[];
  has_conflict: boolean;
  evidence_count: number;
  source: string;
  confidence: string;
};

export type ChapterHookEmptyKind = "none" | "low_confidence" | "has_content";

export type ChapterHookSimplificationModel = {
  empty: boolean;
  empty_kind: ChapterHookEmptyKind;
  empty_title: string | null;
  empty_note: string | null;
  max_scene: number;
  overview: ChapterHookOverview;
  important_hooks: ImportantChapterHook[];
  scene_rows: ChapterHookSceneRow[];
  ending_pull: ChapterEndingPull;
  tech_rows: ChapterHookTechRow[];
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
  if (/主角|目标|追查|为什么|是谁|怎么|身份/.test(q)) score += 18;
  if (/冲突|危险|反转|真相|门外|信|旧案/.test(q)) score += 12;
  if (status === "unresolved") score += 10;
  if (status === "partial") score += 4;
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

/** Safe fallback when question cannot be cleaned into a reader question. */
function safeHookSummary(loop: NarrativeLoopView): string {
  const q = readerQuestionOf(loop);
  if (q) return q;
  const gap = String(loop.information_gap || "").trim();
  if (gap && !isInternalNoise(gap)) return shortPlainTitle(gap, 18);
  const summary = String(loop.hook?.[0]?.summary || "").trim();
  if (summary && !isInternalNoise(summary)) return shortPlainTitle(summary, 18);
  return "暂无可靠判断";
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
  // Ordinary node label「留到下章」only on the final scene.
  if (scene !== maxScene) return false;
  const info = resolveHookMainStatus(loop);
  if (info.main_status === "resolved") return false;
  const open = openSceneOf(loop);
  if (open > scene) return false;
  return info.main_status === "unresolved" || info.main_status === "partial";
}

function truncateZh(text: string, max: number): string {
  const chars = Array.from(text);
  return chars.length <= max ? text : chars.slice(0, max).join("");
}

function zhLen(text: string): number {
  return Array.from(text).length;
}

function resultLabelOf(status: HookMainStatus): ImportantHookResultLabel {
  if (status === "resolved") return "已回应";
  if (status === "partial") return "部分回应";
  if (status === "unresolved") return "继续保留";
  return "暂无可靠判断";
}

function lastChangeSceneOf(
  loop: NarrativeLoopView,
  info: ReturnType<typeof resolveHookMainStatus>,
  maxScene: number,
): number {
  const points: number[] = [openSceneOf(loop)];
  for (const d of loop.developments || []) {
    if (typeof d.scene_ordinal === "number") points.push(d.scene_ordinal);
  }
  for (const p of entityPayoffs(loop)) {
    if (typeof p.scene_ordinal === "number") points.push(p.scene_ordinal);
  }
  if (info.resolve_scene != null) points.push(info.resolve_scene);
  const lastReal = Math.max(...points.filter((n) => Number.isFinite(n)), openSceneOf(loop));
  // Only treat chapter-end as a change when the hook is still unresolved and
  // its last real activity is already near the chapter end (carry-forward).
  if (info.main_status === "unresolved" && isNearChapterEnd(lastReal, maxScene)) {
    return maxScene;
  }
  return lastReal;
}

function isStillActiveNearChapterEnd(
  loop: NarrativeLoopView,
  maxScene: number,
): boolean {
  const info = resolveHookMainStatus(loop);
  if (info.main_status === "resolved") return false;
  const open = openSceneOf(loop);
  if (open > maxScene) return false;
  const last = lastChangeSceneOf(loop, info, maxScene);
  // Prefer hooks whose last activity (or raise) sits in the final 1–2 scenes.
  return isNearChapterEnd(last, maxScene) || isNearChapterEnd(open, maxScene);
}

/**
 * Deterministic per-scene ordinary label.
 * Priority: 给出回应 > 留到下章 > 加深悬念 > 提出疑问
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

  if (answerLoops.length && !topRaise) {
    label = "给出回应";
    related = answerLoops;
    reason = "本场景对已有问题给出了有效信息（部分或完整回应）。";
    confidence = "high";
  } else if (answerLoops.length && topRaise) {
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
  }

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
      const q = readerQuestionOf(loop) ?? (safeHookSummary(loop) !== "暂无可靠判断" ? safeHookSummary(loop) : null);
      if (!q || q === "暂无可靠判断") return null;
      if (isInternalNoise(q)) return null;
      const importance = loopImportance(loop, open);
      // Drop very low-value noise.
      if (importance < 40 && info.main_status === "resolved") return null;
      let role: ImportantChapterHook["role"] = "提出";
      if (info.main_status === "resolved") role = "回应";
      else if (info.main_status === "partial") role = "回应";
      else if (info.main_status === "unresolved") {
        role = isNearChapterEnd(maxScene, maxScene) ? "牵引" : "保留";
      }
      return {
        loop_id: loop.loop_id,
        reader_question: q,
        open_scene: open,
        resolve_scene: info.resolve_scene,
        last_change_scene: lastChangeSceneOf(loop, info, maxScene),
        result_label: resultLabelOf(info.main_status),
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

  return scored.slice(0, Math.min(Math.max(limit, 0), 3));
}

export function deriveChapterPullLabel(
  loops: NarrativeLoopView[],
  maxScene: number,
): ChapterPullLabel {
  if (!loops.length) return "无法判断";
  // Only last 1–2 scenes' still-active important hooks count as ending pull.
  const endLoops = loops.filter((loop) => isStillActiveNearChapterEnd(loop, maxScene));
  if (!endLoops.length) {
    return "暂无";
  }
  const strong = endLoops.filter((loop) => {
    const q = readerQuestionOf(loop);
    const imp = loopImportance(loop, openSceneOf(loop));
    return Boolean(q) && imp >= 60;
  });
  if (strong.length >= 1) return "明确";
  if (endLoops.length >= 1) return "较弱";
  return "暂无";
}

export function deriveChapterEndingPullV1(
  loops: NarrativeLoopView[],
  maxScene: number,
): ChapterEndingPull {
  const readable = loops.filter((l) => readerQuestionOf(l) || safeHookSummary(l) !== "暂无可靠判断");
  if (!loops.length) {
    return {
      status: "无法判断",
      left_behind: null,
      reader_wants: null,
      judgment: "暂无可靠判断",
      source: "unavailable",
    };
  }
  const candidates = readable
    .map((loop) => {
      if (!isStillActiveNearChapterEnd(loop, maxScene)) return null;
      const info = resolveHookMainStatus(loop);
      if (info.main_status === "resolved") return null;
      const last = lastChangeSceneOf(loop, info, maxScene);
      return { loop, info, importance: loopImportance(loop, openSceneOf(loop)), last };
    })
    .filter((x): x is NonNullable<typeof x> => x != null)
    .sort((a, b) => {
      if (b.importance !== a.importance) return b.importance - a.importance;
      if (b.last !== a.last) return b.last - a.last;
      return a.loop.loop_id.localeCompare(b.loop.loop_id);
    });

  const status = deriveChapterPullLabel(readable, maxScene);
  if (!candidates.length) {
    return {
      status: status === "无法判断" ? "无法判断" : "暂无",
      left_behind: null,
      reader_wants: null,
      judgment: "暂无可靠判断",
      source: status === "无法判断" ? "unavailable" : "derived",
    };
  }

  const top = candidates[0];
  const q = safeHookSummary(top.loop);
  const left = truncateZh(`章末仍留下疑问：${q}`, 48);
  const wants = truncateZh(`读者接下来最想知道：${q}`, 48);
  let judgment: string;
  if (status === "明确") {
    judgment = "牵引明确，并与本章核心疑问形成强化。";
  } else if (status === "较弱") {
    judgment = "牵引较弱，跨章期待尚不清晰。";
  } else {
    judgment = "暂无可靠判断";
  }
  const combined = `${left}${wants}${judgment}`;
  if (zhLen(combined) > 120) {
    return {
      status,
      left_behind: truncateZh(left, 40),
      reader_wants: truncateZh(wants, 40),
      judgment: truncateZh(judgment, 40),
      source: "derived",
    };
  }
  return {
    status,
    left_behind: left,
    reader_wants: wants,
    judgment,
    source: "derived",
  };
}

export function deriveChapterHookSceneInsightV1(input: {
  visualization: ReaderJourneyVisualization;
  sceneOrdinal: number;
  node?: JourneySceneNode | null;
}): ChapterHookSceneInsight {
  const { visualization, sceneOrdinal, node } = input;
  const loops = getNarrativeLoops(visualization);
  const maxScene = maxSceneOf(visualization);
  const readable = loops.filter((l) => readerQuestionOf(l));
  const important = selectImportantChapterHooks(readable.length ? readable : loops, maxScene, 3);
  const judgment = deriveChapterHookNodeLabelV1({
    sceneOrdinal,
    maxScene,
    loops: readable.length ? readable : loops,
    topImportantLoopId: important[0]?.loop_id ?? null,
  });
  const role =
    node?.scene_role != null
      ? roleLabelZh(node.scene_role)
      : node?.role != null
        ? roleLabelZh(node.role)
        : "场景";
  const title = `${formatJourneySceneLabel(sceneOrdinal)} · 钩子洞察`;

  if (judgment.source === "unavailable" || !judgment.short_label) {
    return {
      title,
      body: "本场景暂无可靠的钩子洞察。",
      source: "unavailable",
      node_label: null,
    };
  }

  const related = (readable.length ? readable : loops).filter((l) =>
    judgment.related_hook_ids.includes(l.loop_id),
  );
  const q =
    related.map((l) => readerQuestionOf(l) || safeHookSummary(l)).find(Boolean) ||
    "相关阅读期待";

  let body: string;
  switch (judgment.short_label) {
    case "提出疑问":
      body = `本场景提出了「${q}」这一读者问题，打开了后续阅读期待，但尚未给出明确答案。`;
      break;
    case "加深悬念":
      body = `本场景没有直接回答「${q}」，而是补充了新的证据或风险，使已有疑问更值得追问。`;
      break;
    case "给出回应":
      body = `本场景对「${q}」给出了有效信息，形成部分或完整回应；若仍有残留疑问，会继续带动后续阅读。`;
      break;
    case "留到下章":
      body = `本场景将近章末，将「${q}」明确留给下一章，形成跨章继续阅读的牵引。`;
      break;
    default:
      body = "本场景暂无可靠的钩子洞察。";
  }

  // Keep 60–160 chars preference; truncate hard at 160.
  if (zhLen(body) < 40) {
    body = `${body}（场景角色：${role}）`;
  }
  body = truncateZh(body, 160);

  return {
    title,
    body,
    source: "derived",
    node_label: judgment.short_label,
  };
}

function buildTechRows(loops: NarrativeLoopView[]): ChapterHookTechRow[] {
  return loops.map((loop) => {
    const info = resolveHookMainStatus(loop);
    const evidence = [
      ...(info.evidence_paragraph_ids || []),
      ...(loop.evidence || []),
    ];
    return {
      loop_id: loop.loop_id,
      question: safeHookSummary(loop),
      status: String(loop.display_status || loop.status || "open"),
      open_scene: openSceneOf(loop),
      development_scenes: (loop.developments || [])
        .map((d) => d.scene_ordinal)
        .filter((n): n is number => typeof n === "number"),
      resolve_scene: info.resolve_scene,
      payoff_types: entityPayoffs(loop).map((p) => String(p.type || "")),
      has_conflict: info.has_conflict,
      evidence_count: evidence.length,
      source: loop.primary_relation?.grade ? String(loop.primary_relation.grade) : "derived",
      confidence: info.has_conflict ? "low" : "medium",
    };
  });
}

export function buildChapterHookSimplificationModel(
  visualization: ReaderJourneyVisualization,
): ChapterHookSimplificationModel {
  const loops = getNarrativeLoops(visualization);
  const maxScene = maxSceneOf(visualization);
  const readable = loops.filter((l) => readerQuestionOf(l));
  const weakOnly =
    loops.length > 0 &&
    readable.length === 0 &&
    loops.every((l) => loopImportance(l, openSceneOf(l)) < 55);

  const important = selectImportantChapterHooks(
    readable.length ? readable : loops,
    maxScene,
    3,
  );
  const topId = important[0]?.loop_id ?? null;

  const raised = readable.filter((l) => {
    const open = openSceneOf(l);
    return open >= 1 && open <= maxScene;
  }).length;
  const answered = readable.filter((l) => {
    const info = resolveHookMainStatus(l);
    return info.main_status === "resolved" || info.main_status === "partial";
  }).length;
  const carried = readable.filter(
    (l) => resolveHookMainStatus(l).main_status === "unresolved",
  ).length;

  const ending_pull = deriveChapterEndingPullV1(readable.length ? readable : loops, maxScene);
  const chapter_pull = ending_pull.status;

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

  let empty_kind: ChapterHookEmptyKind = "has_content";
  let empty_title: string | null = null;
  let empty_note: string | null = null;
  if (loops.length === 0) {
    empty_kind = "none";
    empty_title = CHAPTER_HOOK_EMPTY_TITLE;
    empty_note = CHAPTER_HOOK_EMPTY_NOTE;
  } else if (readable.length === 0) {
    empty_kind = "low_confidence";
    empty_title = CHAPTER_HOOK_LOW_CONFIDENCE_TITLE;
    empty_note = CHAPTER_HOOK_EMPTY_NOTE;
  } else if (weakOnly) {
    empty_kind = "low_confidence";
    empty_title = CHAPTER_HOOK_LOW_CONFIDENCE_TITLE;
    empty_note = CHAPTER_HOOK_EMPTY_NOTE;
  }

  const overview: ChapterHookOverview = {
    raised,
    answered,
    carried,
    chapter_pull,
  };

  const summary_line =
    empty_kind !== "has_content"
      ? empty_title || CHAPTER_HOOK_EMPTY_TITLE
      : `本章提出 ${overview.raised} 个重要问题，回应 ${overview.answered} 个，继续保留 ${overview.carried} 个；章末牵引：${overview.chapter_pull}。`;

  return {
    empty: empty_kind !== "has_content",
    empty_kind,
    empty_title,
    empty_note,
    max_scene: maxScene,
    overview,
    important_hooks: empty_kind === "has_content" ? important : [],
    scene_rows: empty_kind === "has_content" ? scene_rows : [],
    ending_pull,
    tech_rows: buildTechRows(loops),
    page_blurb: CHAPTER_HOOK_PAGE_BLURB,
    summary_line,
  };
}
