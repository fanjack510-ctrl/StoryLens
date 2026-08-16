/**
 * CHG-20260729-005 — ordinary-user chapter hook presentation (presentation only).
 * Single fact source for overview / scene actions / ending pull / right insight / diagnosis band.
 * Does NOT change hook recognition, persisted facts, or other lenses.
 */

import type {
  HookVocabulary,
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

export const CHAPTER_HOOK_EMPTY_TITLE = "本章未形成明确的阅读悬念。";
export const CHAPTER_HOOK_EMPTY_NOTE =
  "这不一定代表章节存在问题；本章可能主要承担过渡、说明、氛围营造或情绪收束任务。";
export const CHAPTER_HOOK_LOW_CONFIDENCE_TITLE =
  "当前仅识别到较弱的阅读期待，暂无可靠钩子结论。";

export const CHAPTER_HOOK_SCENE_NONE_INSIGHT =
  "本场景未识别到可靠的钩子提出、强化或回应。";
export const CHAPTER_HOOK_SCENE_UNCERTAIN_INSIGHT =
  "当前场景仅存在较弱的阅读期待信号，暂无可靠钩子结论。";

export type ChapterHookNodeLabel =
  | "提出疑问"
  | "加深悬念"
  | "给出回应"
  | "留到下章";

export type ChapterHookSceneAction =
  | "raise"
  | "deepen"
  | "respond"
  | "carry"
  | "none";

export type ChapterHookMode = "reliable" | "uncertain" | "none";

export type ChapterPullLabel = "明确" | "较弱" | "暂无" | "无法判断";

export type ImportantHookResultLabel =
  | "已回应"
  | "部分回应"
  | "继续保留"
  | "暂无可靠判断";

export type ReaderQuestionStatus =
  | "新提出"
  | "部分回应"
  | "已回应"
  | "继续保留";

export type ReaderQuestionCard = {
  loop_id: string;
  /** Chip-length form, cut to 18 chars. Use where the space is a chip. */
  question: string;
  /**
   * The question as the reader would ask it, uncut.
   *
   * `question` is truncated at 18 characters because it also serves as a hook's identity in
   * chips and titles. The card is the one place where the question IS the content — cut
   * there it reads 「首段即抛出'我是谁'的疑问，第二段…」, which is the setup with the question
   * removed. The card renders this and clamps in CSS, so long ones lose lines, not sense.
   */
  question_full: string;
  status: ReaderQuestionStatus;
  change_trail: string;
  /**
   * Kept for the developer table and downstream consumers. Not rendered on the card: it is
   * a lookup on `status` (see readerQuestionRoleOf), so on screen it restated the pill next
   * to it three times over.
   */
  role: string;
};

export type ChapterHookNodeJudgment = {
  short_label: ChapterHookNodeLabel | null;
  scene_action: ChapterHookSceneAction;
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
  scene_action: ChapterHookSceneAction;
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
  unlinked_response_signal: boolean;
};

/** @deprecated Prefer chapter_hook_mode. Kept for existing tests/UI attrs. */
export type ChapterHookEmptyKind = "none" | "low_confidence" | "has_content";

/** ChapterHookPresentationV1 — sole ordinary Hook UI fact source. */
export type ChapterHookSimplificationModel = {
  chapter_hook_mode: ChapterHookMode;
  empty: boolean;
  empty_kind: ChapterHookEmptyKind;
  empty_title: string | null;
  empty_note: string | null;
  reliable_hook_count: number;
  max_scene: number;
  overview: ChapterHookOverview;
  important_hooks: ImportantChapterHook[];
  reader_question_cards: ReaderQuestionCard[];
  scene_rows: ChapterHookSceneRow[];
  scene_actions: ChapterHookSceneAction[];
  ending_pull: ChapterEndingPull;
  tech_rows: ChapterHookTechRow[];
  page_blurb: string;
  summary_line: string;
};

/**
 * Render a canonical label in the book's own words.
 *
 * The four labels stay the internal identity — every derivation, test and stored artifact
 * keys on them — but they are the *suspense* reading of four structural actions, and they
 * were shown to every reader of every book. On 《再也不见》 that produced three findings that
 * all say the same thing: 「不足以构成强烈钩子」, 「缺乏吸引力」, 「作为章末钩子强度中等」. The book
 * does not run on suspense; the vocabulary recorded that as a defect.
 *
 * The vocabulary comes from the backend, which owns the book's profile (INV-P4). Missing
 * vocabulary means an unconfirmed profile or a legacy payload, and then the suspense
 * wording is the honest default — without a confirmed profile there is no basis for
 * claiming the reader is tracking a relationship rather than a question.
 */
export function hookLabelZh(
  label: ChapterHookNodeLabel | string | null | undefined,
  vocabulary?: HookVocabulary | null,
): string {
  if (!label) return "";
  if (!vocabulary) return String(label);
  const action = LABEL_TO_ACTION[label as ChapterHookNodeLabel];
  switch (action) {
    case "raise":
      return vocabulary.open || String(label);
    case "deepen":
      return vocabulary.deepen || String(label);
    case "respond":
      return vocabulary.answer || String(label);
    case "carry":
      return vocabulary.carry || String(label);
    default:
      // "—" and any future non-action label pass through untouched.
      return String(label);
  }
}

const ACTION_TO_LABEL: Record<Exclude<ChapterHookSceneAction, "none">, ChapterHookNodeLabel> = {
  raise: "提出疑问",
  deepen: "加深悬念",
  respond: "给出回应",
  carry: "留到下章",
};

const LABEL_TO_ACTION: Record<ChapterHookNodeLabel, ChapterHookSceneAction> = {
  提出疑问: "raise",
  加深悬念: "deepen",
  给出回应: "respond",
  留到下章: "carry",
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

function evidenceIdsOf(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((x) => String(x || "").trim())
    .filter((x) => Boolean(x) && !isInternalNoise(x));
}

function hasValidEvidence(ids: unknown): boolean {
  return evidenceIdsOf(ids).length > 0;
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

/**
 * Reject text that asserts there is NO hook here.
 *
 * The `question` field is supposed to hold the question the reader is left with. On all
 * three analysed books it holds the model's scoring rationale instead, negatives included:
 * 「场景开头无新钩子，仅延续前文」, 「不足以构成强烈钩子」, 「缺乏吸引力」. Those were rendered
 * verbatim onto cards headed 读者最想知道 — the panel telling the reader that what they most
 * want to know is that there is nothing to know.
 *
 * This is a stopgap at the display layer; the real fix is a contract that asks for the
 * question as a question and validates it. Until that lands, a card is better absent than
 * inverted. The patterns match assertions of absence and insufficiency, not merely low
 * scores, so a genuinely weak-but-real hook still shows.
 */
function assertsNoHook(text: string): boolean {
  const t = text.trim();
  if (/(无|没有|未)[^，。；]{0,4}(新)?钩子/.test(t)) return true;
  if (/不足以(构成|形成)/.test(t)) return true;
  if (/缺乏(吸引力|悬念|钩子)/.test(t)) return true;
  if (/(仅|只是)(延续|承接)前文/.test(t)) return true;
  return false;
}

/**
 * Drop the question mark the pipeline appends to sentences that already ended.
 *
 * Raw values arrive as 「场景开头无新钩子，仅延续前文。？」 — a full stop and then a question
 * mark. Collapsing `？+` to a single `？` (the previous behaviour) kept the pair.
 */
function normalizeQuestionPunctuation(text: string): string {
  return text
    .trim()
    .replace(/[?？]+$/g, "？")
    .replace(/([。．.!！])？$/g, "$1");
}

/** The cleaned question with no length cut. Null under the same conditions as the short form. */
function readerQuestionFullOf(loop: NarrativeLoopView): string | null {
  const raw = String(loop.question || loop.information_gap || "").trim();
  if (!raw || isInternalNoise(raw) || assertsNoHook(raw)) return null;
  const cleaned = normalizeQuestionPunctuation(raw);
  return isInternalNoise(cleaned) ? null : cleaned;
}

function readerQuestionOf(loop: NarrativeLoopView): string | null {
  const raw = String(loop.question || loop.information_gap || "").trim();
  if (!raw || isInternalNoise(raw) || assertsNoHook(raw)) return null;
  const cleaned = shortPlainTitle(normalizeQuestionPunctuation(raw), 18);
  if (!cleaned || isInternalNoise(cleaned)) return null;
  return cleaned;
}

function isReliableHook(loop: NarrativeLoopView): boolean {
  return Boolean(readerQuestionOf(loop));
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

/**
 * Hard gate for 「给出回应」:
 * reliable_hook AND linked_response AND valid_evidence (not score-only).
 */
export function sceneHasReliableLinkedResponse(
  loop: NarrativeLoopView,
  scene: number,
): boolean {
  if (!isReliableHook(loop)) return false;
  const open = openSceneOf(loop);
  if (open > scene) return false;

  const grade = String(loop.primary_relation?.grade || "").toLowerCase();
  if (grade === "unsupported") return false;
  if (loop.primary_relation?.blocked || loop.hard_blocked) return false;

  const pref = loop.primary_relation?.payoff_ref;
  const prefIsScore =
    pref &&
    (pref.source_type === "score_inferred" || String(pref.type || "") === "score_inferred");

  // Linked entity payoffs on this loop at this scene.
  const linkedEntities = entityPayoffs(loop).filter((p) => p.scene_ordinal === scene);
  for (const p of linkedEntities) {
    if (hasValidEvidence(p.evidence_paragraph_ids)) return true;
  }

  // Explicit primary_relation payoff_ref to this scene (non score_inferred) with evidence.
  if (
    pref &&
    !prefIsScore &&
    pref.scene_ordinal === scene &&
    (grade === "confirmed" || grade === "probable" || grade === "candidate")
  ) {
    if (hasValidEvidence(pref.evidence_paragraph_ids)) return true;
    // Entity payoff matched by scene may carry evidence under payoffs[].
    if (linkedEntities.some((p) => hasValidEvidence(p.evidence_paragraph_ids))) return true;
  }

  return false;
}

function sceneHasCarryToNext(
  loop: NarrativeLoopView,
  scene: number,
  maxScene: number,
): boolean {
  if (scene !== maxScene) return false;
  if (!isReliableHook(loop)) return false;
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

function formatSceneRef(sceneOrdinal: number): string {
  return `S${String(sceneOrdinal).padStart(2, "0")}`;
}

function readerQuestionStatusOf(
  loop: NarrativeLoopView,
  maxScene: number,
): ReaderQuestionStatus {
  const info = resolveHookMainStatus(loop);
  if (info.main_status === "resolved") return "已回应";
  if (info.main_status === "partial") return "部分回应";
  const open = openSceneOf(loop);
  const hasDeepen = (loop.developments || []).some(
    (d) => typeof d.scene_ordinal === "number" && d.scene_ordinal > open,
  );
  const hasRespond = entityPayoffs(loop).some((p) =>
    hasValidEvidence(p.evidence_paragraph_ids),
  );
  if (!hasDeepen && !hasRespond) return "新提出";
  if (isStillActiveNearChapterEnd(loop, maxScene)) return "继续保留";
  return "继续保留";
}

function readerQuestionRoleOf(
  loop: NarrativeLoopView,
  status: ReaderQuestionStatus,
  maxScene: number,
): string {
  if (status === "新提出") return "打开本章阅读期待";
  if (status === "部分回应") return "部分回应核心疑问";
  if (status === "已回应") return "收束本章相关疑问";
  if (isStillActiveNearChapterEnd(loop, maxScene)) return "推动读者继续阅读";
  return "维持阅读追问";
}

export function buildReaderQuestionChangeTrail(
  loop: NarrativeLoopView,
  maxScene: number,
): string {
  const parts: string[] = [];
  const open = openSceneOf(loop);
  parts.push(`${formatSceneRef(open)} 提出`);

  const deepenScenes = new Set<number>();
  for (const d of loop.developments || []) {
    if (typeof d.scene_ordinal === "number" && d.scene_ordinal !== open) {
      deepenScenes.add(d.scene_ordinal);
    }
  }
  for (const h of loop.hook || []) {
    if (
      typeof h.scene_ordinal === "number" &&
      h.scene_ordinal !== open &&
      !entityPayoffs(loop).some((p) => p.scene_ordinal === h.scene_ordinal)
    ) {
      deepenScenes.add(h.scene_ordinal);
    }
  }
  for (const scene of Array.from(deepenScenes).sort((a, b) => a - b)) {
    parts.push(`${formatSceneRef(scene)} 加深`);
  }

  const info = resolveHookMainStatus(loop);
  if (info.resolve_scene != null) {
    parts.push(`${formatSceneRef(info.resolve_scene)} 回应`);
  } else {
    for (let s = open + 1; s <= maxScene; s += 1) {
      if (sceneHasReliableLinkedResponse(loop, s)) {
        parts.push(`${formatSceneRef(s)} 回应`);
        break;
      }
    }
  }

  if (sceneHasCarryToNext(loop, maxScene, maxScene)) {
    parts.push(`${formatSceneRef(maxScene)} 留到下章`);
  }

  return parts.join(" · ");
}

export function buildReaderQuestionCards(
  loops: NarrativeLoopView[],
  maxScene: number,
  limit = 3,
): ReaderQuestionCard[] {
  const important = selectImportantChapterHooks(loops, maxScene, limit);
  return important.map((hook) => {
    const loop = loops.find((l) => l.loop_id === hook.loop_id);
    if (!loop) {
      return {
        loop_id: hook.loop_id,
        question: hook.reader_question,
        question_full: hook.reader_question,
        status: "继续保留" as ReaderQuestionStatus,
        change_trail: `${formatSceneRef(hook.open_scene)} 提出`,
        role: "推动读者继续阅读",
      };
    }
    const status = readerQuestionStatusOf(loop, maxScene);
    return {
      loop_id: hook.loop_id,
      question: hook.reader_question,
      question_full: readerQuestionFullOf(loop) || hook.reader_question,
      status,
      change_trail: buildReaderQuestionChangeTrail(loop, maxScene),
      role: readerQuestionRoleOf(loop, status, maxScene),
    };
  });
}

export function deriveChapterHookSummaryLine(input: {
  chapter_hook_mode: ChapterHookMode;
  reader_question_cards: ReaderQuestionCard[];
  ending_pull: ChapterEndingPull;
}): string {
  if (input.chapter_hook_mode === "none") return CHAPTER_HOOK_EMPTY_TITLE;
  if (input.chapter_hook_mode === "uncertain") return CHAPTER_HOOK_LOW_CONFIDENCE_TITLE;

  const cards = input.reader_question_cards;
  if (!cards.length) return CHAPTER_HOOK_EMPTY_TITLE;

  const primary = cards[0].question;
  const answered = cards.filter(
    (c) => c.status === "已回应" || c.status === "部分回应",
  ).length;
  const carried = cards.filter(
    (c) => c.status === "继续保留" || c.status === "新提出",
  ).length;
  const pull = input.ending_pull.status;

  if (answered > 0 && carried > 0 && pull === "明确") {
    return truncateZh(
      `本章在回应部分疑问的同时，章末仍围绕「${primary}」留下明确继续阅读牵引。`,
      72,
    );
  }
  if (answered > 0 && carried === 0) {
    return truncateZh(
      `本章围绕「${primary}」等问题给出了有效回应，相关阅读期待在本章内得到收束。`,
      72,
    );
  }
  if (answered === 0 && carried > 0 && pull === "明确") {
    return truncateZh(
      `本章主要提出并强化了「${primary}」等疑问，章末牵引明确，推动读者继续阅读。`,
      72,
    );
  }
  if (pull === "较弱") {
    return truncateZh("本章提出了若干阅读疑问，但章末跨章牵引尚不够明确。", 72);
  }
  if (pull === "暂无" && answered === 0) {
    return truncateZh(
      `本章围绕「${primary}」${cards.length > 1 ? "等疑问" : ""}展开，阅读期待仍在推进中。`,
      72,
    );
  }
  return truncateZh(
    `本章围绕「${primary}」${cards.length > 1 ? "等疑问" : ""}推进阅读，部分期待仍待后续章节回应。`,
    72,
  );
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
  if (!isReliableHook(loop)) return false;
  const open = openSceneOf(loop);
  if (open > maxScene) return false;
  const last = lastChangeSceneOf(loop, info, maxScene);
  return isNearChapterEnd(last, maxScene) || isNearChapterEnd(open, maxScene);
}

function labelToAction(label: ChapterHookNodeLabel | null): ChapterHookSceneAction {
  if (!label) return "none";
  return LABEL_TO_ACTION[label];
}

/**
 * Deterministic per-scene ordinary label.
 * Priority: 给出回应 > 留到下章 > 加深悬念 > 提出疑问 > none
 * Respond requires hard gate.
 */
export function deriveChapterHookNodeLabelV1(input: {
  sceneOrdinal: number;
  maxScene: number;
  loops: NarrativeLoopView[];
  topImportantLoopId?: string | null;
  chapterHookMode?: ChapterHookMode;
}): ChapterHookNodeJudgment {
  const {
    sceneOrdinal,
    maxScene,
    loops,
    topImportantLoopId,
    chapterHookMode = "reliable",
  } = input;

  if (chapterHookMode !== "reliable") {
    return {
      short_label: null,
      scene_action: "none",
      full_reason:
        chapterHookMode === "uncertain"
          ? "当前场景暂无可靠的钩子判断。"
          : "当前节点暂无可靠判断",
      related_hook_ids: [],
      source: "unavailable",
      confidence: "low",
    };
  }

  const reliable = loops.filter(isReliableHook);
  if (!reliable.length) {
    return {
      short_label: null,
      scene_action: "none",
      full_reason: "当前节点暂无可靠判断",
      related_hook_ids: [],
      source: "unavailable",
      confidence: "low",
    };
  }

  const answerLoops = reliable.filter((l) => sceneHasReliableLinkedResponse(l, sceneOrdinal));
  const carryLoops = reliable.filter((l) => sceneHasCarryToNext(l, sceneOrdinal, maxScene));
  const deepenLoops = reliable.filter((l) => sceneHasDeepen(l, sceneOrdinal));
  const raiseLoops = reliable.filter((l) => sceneHasRaise(l, sceneOrdinal));

  const topRaise =
    topImportantLoopId && raiseLoops.some((l) => l.loop_id === topImportantLoopId);

  let label: ChapterHookNodeLabel | null = null;
  let related: NarrativeLoopView[] = [];
  let reason: string | null = null;
  let confidence: "high" | "medium" | "low" = "medium";

  if (answerLoops.length && !topRaise) {
    label = "给出回应";
    related = answerLoops;
    reason = "本场景对已有可靠问题给出了有效关联回应。";
    confidence = "high";
  } else if (answerLoops.length && topRaise) {
    label = "给出回应";
    related = answerLoops;
    reason = "本场景对已有可靠问题给出了有效关联回应；同时可能提出新问题。";
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
      scene_action: "none",
      full_reason: "当前节点暂无可靠判断",
      related_hook_ids: [],
      source: "unavailable",
      confidence: "low",
    };
  }

  return {
    short_label: label,
    scene_action: LABEL_TO_ACTION[label],
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
      if (!isReliableHook(loop)) return null;
      const open = openSceneOf(loop);
      const info = resolveHookMainStatus(loop);
      const q = readerQuestionOf(loop);
      if (!q) return null;
      const importance = loopImportance(loop, open);
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
  mode: ChapterHookMode = "reliable",
): ChapterPullLabel {
  if (mode === "none") return "暂无";
  if (mode === "uncertain") return "无法判断";
  if (!loops.length) return "无法判断";
  const endLoops = loops.filter((loop) => isStillActiveNearChapterEnd(loop, maxScene));
  if (!endLoops.length) return "暂无";
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
  mode: ChapterHookMode = "reliable",
): ChapterEndingPull {
  if (mode === "none") {
    return {
      status: "暂无",
      left_behind: null,
      reader_wants: null,
      judgment: "暂无可靠判断",
      source: "derived",
    };
  }
  if (mode === "uncertain") {
    return {
      status: "无法判断",
      left_behind: null,
      reader_wants: null,
      judgment: "暂无可靠判断",
      source: "unavailable",
    };
  }

  const readable = loops.filter(isReliableHook);
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

  const status = deriveChapterPullLabel(readable, maxScene, mode);
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
  presentation?: ChapterHookSimplificationModel | null;
}): ChapterHookSceneInsight {
  const { visualization, sceneOrdinal, node } = input;
  const model = input.presentation ?? buildChapterHookSimplificationModel(visualization);
  const title = `${formatJourneySceneLabel(sceneOrdinal)} · 钩子洞察`;
  const row = model.scene_rows.find((r) => r.scene_ordinal === sceneOrdinal) ?? null;

  if (model.chapter_hook_mode === "uncertain") {
    return {
      title,
      body: CHAPTER_HOOK_SCENE_UNCERTAIN_INSIGHT,
      source: "unavailable",
      node_label: null,
    };
  }
  if (model.chapter_hook_mode === "none") {
    return {
      title,
      body: CHAPTER_HOOK_SCENE_NONE_INSIGHT,
      source: "unavailable",
      node_label: null,
    };
  }

  if (!row || row.scene_action === "none" || !row.short_label) {
    return {
      title,
      body: CHAPTER_HOOK_SCENE_NONE_INSIGHT,
      source: "unavailable",
      node_label: null,
    };
  }

  const loops = getNarrativeLoops(visualization).filter(isReliableHook);
  const related = loops.filter((l) => row.related_hook_ids.includes(l.loop_id));
  const q =
    related.map((l) => readerQuestionOf(l) || safeHookSummary(l)).find(Boolean) ||
    "相关阅读期待";

  let body: string;
  switch (row.short_label) {
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
      body = CHAPTER_HOOK_SCENE_NONE_INSIGHT;
  }
  body = truncateZh(body, 160);

  return {
    title,
    body,
    source: "derived",
    node_label: row.short_label,
  };
}

function buildTechRows(loops: NarrativeLoopView[]): ChapterHookTechRow[] {
  return loops.map((loop) => {
    const info = resolveHookMainStatus(loop);
    const evidence = [
      ...(info.evidence_paragraph_ids || []),
      ...(loop.evidence || []),
    ];
    const hasScoreSignal = Boolean(
      loop.primary_relation?.payoff_ref?.source_type === "score_inferred" ||
        Object.keys(loop.payoff_score_by_scene || {}).length,
    );
    const hasLinked = entityPayoffs(loop).some((p) =>
      hasValidEvidence(p.evidence_paragraph_ids),
    );
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
      unlinked_response_signal: hasScoreSignal && !hasLinked,
    };
  });
}

function resolveChapterHookMode(
  loops: NarrativeLoopView[],
  reliable: NarrativeLoopView[],
): ChapterHookMode {
  if (!loops.length) return "none";
  if (!reliable.length) return "uncertain";
  return "reliable";
}

function modeToEmptyKind(mode: ChapterHookMode): ChapterHookEmptyKind {
  if (mode === "none") return "none";
  if (mode === "uncertain") return "low_confidence";
  return "has_content";
}

/** Ordinary diagnosis-band / scene-index label for hook_payoff lens. */
export function ordinaryHookSceneBandLabel(
  presentation: ChapterHookSimplificationModel,
  sceneOrdinal: number,
): string {
  const row = presentation.scene_rows.find((r) => r.scene_ordinal === sceneOrdinal);
  if (!row || row.scene_action === "none" || !row.short_label) return "—";
  return row.short_label;
}

export function buildChapterHookSimplificationModel(
  visualization: ReaderJourneyVisualization,
): ChapterHookSimplificationModel {
  const loops = getNarrativeLoops(visualization);
  const maxScene = maxSceneOf(visualization);
  const reliable = loops.filter(isReliableHook);
  const chapter_hook_mode = resolveChapterHookMode(loops, reliable);
  const empty_kind = modeToEmptyKind(chapter_hook_mode);

  const important =
    chapter_hook_mode === "reliable"
      ? selectImportantChapterHooks(reliable, maxScene, 3)
      : [];
  const reader_question_cards =
    chapter_hook_mode === "reliable"
      ? buildReaderQuestionCards(reliable, maxScene, 3)
      : [];
  const topId = important[0]?.loop_id ?? null;

  let raised = 0;
  let answered = 0;
  let carried = 0;
  if (chapter_hook_mode === "reliable") {
    raised = reliable.filter((l) => {
      const open = openSceneOf(l);
      return open >= 1 && open <= maxScene;
    }).length;
    answered = reliable.filter((l) => {
      for (let s = openSceneOf(l); s <= maxScene; s += 1) {
        if (sceneHasReliableLinkedResponse(l, s)) return true;
      }
      return false;
    }).length;
    carried = reliable.filter((l) => {
      const info = resolveHookMainStatus(l);
      if (info.main_status !== "unresolved") return false;
      return isStillActiveNearChapterEnd(l, maxScene) || info.main_status === "unresolved";
    }).length;
    // continued_count: reliable still-open hooks (not auto every unresolved mid-chapter as "牵引")
    carried = reliable.filter(
      (l) => resolveHookMainStatus(l).main_status === "unresolved",
    ).length;
  }

  const ending_pull = deriveChapterEndingPullV1(loops, maxScene, chapter_hook_mode);
  const chapter_pull =
    chapter_hook_mode === "none"
      ? "暂无"
      : chapter_hook_mode === "uncertain"
        ? "无法判断"
        : ending_pull.status;

  const scene_rows: ChapterHookSceneRow[] = [];
  for (let s = 1; s <= maxScene; s += 1) {
    const j = deriveChapterHookNodeLabelV1({
      sceneOrdinal: s,
      maxScene,
      loops: reliable,
      topImportantLoopId: topId,
      chapterHookMode: chapter_hook_mode,
    });
    scene_rows.push({
      scene_ordinal: s,
      short_label: j.short_label,
      scene_action: j.scene_action,
      full_reason: j.full_reason,
      related_hook_ids: j.related_hook_ids,
      source: j.source,
    });
  }

  const overview: ChapterHookOverview = {
    raised: chapter_hook_mode === "reliable" ? raised : 0,
    answered: chapter_hook_mode === "reliable" ? answered : 0,
    carried: chapter_hook_mode === "reliable" ? carried : 0,
    chapter_pull,
  };

  let empty_title: string | null = null;
  let empty_note: string | null = null;
  if (chapter_hook_mode === "none") {
    empty_title = CHAPTER_HOOK_EMPTY_TITLE;
    empty_note = CHAPTER_HOOK_EMPTY_NOTE;
  } else if (chapter_hook_mode === "uncertain") {
    empty_title = CHAPTER_HOOK_LOW_CONFIDENCE_TITLE;
    empty_note = CHAPTER_HOOK_EMPTY_NOTE;
  }

  const summary_line = deriveChapterHookSummaryLine({
    chapter_hook_mode,
    reader_question_cards,
    ending_pull,
  });

  return {
    chapter_hook_mode,
    empty: chapter_hook_mode !== "reliable",
    empty_kind,
    empty_title,
    empty_note,
    reliable_hook_count: reliable.length,
    max_scene: maxScene,
    overview,
    important_hooks: important,
    reader_question_cards,
    scene_rows,
    scene_actions: scene_rows.map((r) => r.scene_action),
    ending_pull: {
      ...ending_pull,
      status: chapter_pull,
    },
    tech_rows: buildTechRows(loops),
    page_blurb: CHAPTER_HOOK_PAGE_BLURB,
    summary_line,
  };
}

export { ACTION_TO_LABEL, labelToAction };
