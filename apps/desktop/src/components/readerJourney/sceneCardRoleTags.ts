/**
 * Scene/Beat card role tags — NarrativeLoopView facts only (presentation).
 * Does not use hook_markers / payoff_markers / risk_intervals as card facts.
 */

import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";
import {
  formatReadingResistanceLabel,
  READING_RESISTANCE_REASON_ZH,
} from "./journeyUiLabels";
import {
  getNarrativeLoops,
  getReadingResistance,
  type NarrativeLoopHook,
  type NarrativeLoopPayoff,
  type NarrativeLoopView,
  type ReadingResistanceItem,
} from "./narrativeLoopView";

export type SceneRoleTagKind = "hook" | "payoff" | "resistance";

export type SceneRoleTag = {
  kind: SceneRoleTagKind;
  label: string;
  title?: string;
};

const MAX_CARD_ROLE_TAGS = 2;

const HOOK_ROLE_TYPES = new Set([
  "new",
  "new_hook",
  "create",
  "establish",
  "strengthen",
  "reinforce",
  "amplify",
  "transform",
  "transformed_question",
  "question_transform",
  "information_gap",
  "gap",
]);

const PAYOFF_ROLE_TYPES = new Set([
  "partial",
  "full",
  "reversal",
  "transformed_question",
]);

function payoffLabel(type: string): string | null {
  if (type === "partial") return "部分回报";
  if (type === "full") return "明确回报";
  if (type === "reversal") return "反转回报";
  if (type === "transformed_question") return "转化回报";
  return null;
}

function hookLooksEstablishing(hook: NarrativeLoopHook, loop: NarrativeLoopView): boolean {
  const type = String(hook.type || "").toLowerCase();
  if (type && HOOK_ROLE_TYPES.has(type)) return true;
  if (loop.open_from_scene === hook.scene_ordinal) return true;
  if (hook.gap || hook.continue_drive) return true;
  // Untyped hook on this scene still counts as establishing when loop opens here.
  if (!type && loop.open_from_scene == null && (loop.hook || [])[0] === hook) return true;
  return false;
}

function sceneHasHookRole(loops: NarrativeLoopView[], sceneOrdinal: number): boolean {
  for (const loop of loops) {
    if (loop.hard_blocked || loop.consistency_status === "inconsistent") continue;
    if (loop.open_from_scene === sceneOrdinal) return true;
    for (const hook of loop.hook || []) {
      if (hook.scene_ordinal !== sceneOrdinal) continue;
      if (hookLooksEstablishing(hook, loop)) return true;
    }
    for (const dev of loop.developments || []) {
      if (dev.scene_ordinal !== sceneOrdinal) continue;
      const kind = String(dev.kind || "").toLowerCase();
      if (
        kind.includes("strengthen") ||
        kind.includes("reinforce") ||
        kind.includes("transform") ||
        kind.includes("gap")
      ) {
        return true;
      }
    }
  }
  return false;
}

function bestPayoffForScene(
  loops: NarrativeLoopView[],
  sceneOrdinal: number,
): NarrativeLoopPayoff | null {
  const rank = (type: string) => {
    if (type === "full") return 4;
    if (type === "reversal") return 3;
    if (type === "transformed_question") return 2;
    if (type === "partial") return 1;
    return 0;
  };
  let best: NarrativeLoopPayoff | null = null;
  for (const loop of loops) {
    if (loop.hard_blocked || loop.consistency_status === "inconsistent") continue;
    if (!loop.loop_id) continue;
    for (const payoff of loop.payoffs || []) {
      if (payoff.scene_ordinal !== sceneOrdinal) continue;
      const type = String(payoff.type || "");
      if (!PAYOFF_ROLE_TYPES.has(type)) continue;
      if (type === "score_inferred" || payoff.source_type === "score_inferred") continue;
      if (!best || rank(type) > rank(String(best.type || ""))) best = payoff;
    }
    const pref = loop.primary_relation?.payoff_ref;
    if (
      pref?.scene_ordinal === sceneOrdinal &&
      loop.primary_relation?.grade &&
      loop.primary_relation.grade !== "unsupported" &&
      !loop.primary_relation.blocked
    ) {
      const type = String(pref.type || "");
      if (PAYOFF_ROLE_TYPES.has(type)) {
        const synthetic: NarrativeLoopPayoff = {
          scene_ordinal: sceneOrdinal,
          type,
          summary: pref.summary,
          source_type: pref.source_type,
        };
        if (!best || rank(type) > rank(String(best.type || ""))) best = synthetic;
      }
    }
  }
  return best;
}

function coversOrdinal(item: ReadingResistanceItem, sceneOrdinal: number): boolean {
  const start = item.start_scene_ordinal;
  const end = item.end_scene_ordinal ?? start;
  if (typeof start !== "number" || !Number.isFinite(start)) return false;
  const endN = typeof end === "number" && Number.isFinite(end) ? end : start;
  return sceneOrdinal >= start && sceneOrdinal <= endN;
}

function primaryResistanceReason(item: ReadingResistanceItem): string | null {
  const fromZh = (item.reasons_zh || []).map((s) => String(s || "").trim()).filter(Boolean);
  if (fromZh[0]) return fromZh[0].replace(/^阅读阻力[｜|]/, "").trim() || fromZh[0];
  const codes = item.reason_codes || [];
  for (const code of codes) {
    const mapped = READING_RESISTANCE_REASON_ZH[String(code)];
    if (mapped) return mapped;
  }
  if (item.summary) {
    const s = String(item.summary).trim();
    if (s) return s.replace(/^阅读阻力[｜|]/, "").trim() || s;
  }
  const t = item.resistance_type ? READING_RESISTANCE_REASON_ZH[item.resistance_type] : null;
  return t || null;
}

function resistanceTagForScene(
  visualization: ReaderJourneyVisualization,
  sceneOrdinal: number,
): SceneRoleTag | null {
  const items = getReadingResistance(visualization).filter((item) =>
    coversOrdinal(item, sceneOrdinal),
  );
  for (const item of items) {
    const reason = primaryResistanceReason(item);
    if (!reason) continue;
    const label = formatReadingResistanceLabel(reason);
    return {
      kind: "resistance",
      label,
      title: item.summary || label,
    };
  }
  return null;
}

/**
 * Build up to two factual role tags for a scene/beat card.
 * Priority: hook/payoff first, then reading resistance.
 */
export function buildSceneRoleTags(
  visualization: ReaderJourneyVisualization | null | undefined,
  sceneOrdinal: number,
): SceneRoleTag[] {
  if (!visualization || !Number.isFinite(sceneOrdinal)) return [];
  const loops = getNarrativeLoops(visualization);
  const tags: SceneRoleTag[] = [];

  if (sceneHasHookRole(loops, sceneOrdinal)) {
    tags.push({ kind: "hook", label: "钩子", title: "本场建立或强化读者期待" });
  }

  const payoff = bestPayoffForScene(loops, sceneOrdinal);
  if (payoff) {
    const label = payoffLabel(String(payoff.type || ""));
    if (label) {
      tags.push({
        kind: "payoff",
        label,
        title: payoff.summary || label,
      });
    }
  }

  const resistance = resistanceTagForScene(visualization, sceneOrdinal);
  if (resistance) tags.push(resistance);

  // Prefer hook/payoff over resistance when overflowing.
  if (tags.length <= MAX_CARD_ROLE_TAGS) return tags;
  const preferred = tags.filter((t) => t.kind === "hook" || t.kind === "payoff");
  if (preferred.length >= MAX_CARD_ROLE_TAGS) return preferred.slice(0, MAX_CARD_ROLE_TAGS);
  const rest = tags.filter((t) => t.kind === "resistance");
  return [...preferred, ...rest].slice(0, MAX_CARD_ROLE_TAGS);
}

export const SCENE_CARD_MAX_ROLE_TAGS = MAX_CARD_ROLE_TAGS;
