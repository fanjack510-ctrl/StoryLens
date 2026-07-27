/**
 * Hook/Payoff dual-rail timeline model — reads NarrativeLoopView only.
 * Presentation layer; does not alter NarrativeLoopView fact rules.
 */

import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";
import {
  HARD_BLOCK_USER_MESSAGE,
  SOFT_CONFLICT_USER_MESSAGE,
  getNarrativeLoopConsistency,
  getNarrativeLoops,
  type NarrativeLoopPayoff,
  type NarrativeLoopView,
  type RelationGrade,
} from "./narrativeLoopView";
import { shortPlainTitle } from "./readerJourneyLensExplanation";

export type HookPayoffRailKind = "hook" | "payoff";

export type HookPayoffNodeKind =
  | "new_hook"
  | "partial"
  | "full"
  | "reversal"
  | "transformed"
  | "open"
  | "score_inferred";

export type HookPayoffLinkStroke = "solid" | "dashed" | "dotted";

export type HookPayoffTimelineNode = {
  id: string;
  loop_id: string;
  rail: HookPayoffRailKind;
  kind: HookPayoffNodeKind;
  scene_ordinal: number;
  title: string;
  hover: string;
  emphasis: boolean;
};

export type HookPayoffTimelineLink = {
  loop_id: string;
  from_id: string;
  to_id: string;
  grade: RelationGrade;
  stroke: HookPayoffLinkStroke;
  is_primary: boolean;
  deterministic: boolean;
};

export type HookPayoffChapterStats = {
  established: number;
  answered: number;
  waiting: number;
  delayed_risk: number;
};

export type HookPayoffTimelineModel = {
  stats: HookPayoffChapterStats;
  nodes: HookPayoffTimelineNode[];
  links: HookPayoffTimelineLink[];
  inconsistent: boolean;
  softConflict: boolean;
  warning: string | null;
  maxScene: number;
};

function strokeForGrade(grade: RelationGrade): HookPayoffLinkStroke | null {
  if (grade === "confirmed") return "solid";
  if (grade === "probable") return "dashed";
  if (grade === "candidate") return "dotted";
  return null;
}

function payoffKind(payoff: NarrativeLoopPayoff): HookPayoffNodeKind {
  const type = String(payoff.type || "");
  if (type === "full") return "full";
  if (type === "reversal") return "reversal";
  if (type === "transformed_question") return "transformed";
  if (type === "score_inferred" || payoff.source_type === "score_inferred") return "score_inferred";
  return "partial";
}

function isAnsweredStatus(status: string): boolean {
  return status === "resolved" || status === "transformed" || status === "abandoned";
}

function displayStatus(loop: NarrativeLoopView): string {
  return String(loop.display_status || loop.status || "open");
}

function isHardBlocked(loop: NarrativeLoopView): boolean {
  return Boolean(
    loop.hard_blocked ||
      loop.consistency_status === "inconsistent" ||
      loop.status === "inconsistent",
  );
}

export function buildHookPayoffChapterStats(loops: NarrativeLoopView[]): HookPayoffChapterStats {
  let established = 0;
  let answered = 0;
  let waiting = 0;
  let delayed_risk = 0;
  for (const loop of loops) {
    if (isHardBlocked(loop)) continue;
    established += 1;
    const status = displayStatus(loop);
    if (isAnsweredStatus(status)) {
      answered += 1;
    } else if (status === "partially_resolved") {
      waiting += 1;
      if ((loop.nodes_spanned || 1) >= 3) delayed_risk += 1;
    } else if (status === "open") {
      waiting += 1;
      if ((loop.nodes_spanned || 1) >= 2) delayed_risk += 1;
    }
  }
  return { established, answered, waiting, delayed_risk };
}

function primaryPayoffRef(loop: NarrativeLoopView): NarrativeLoopPayoff | null {
  const primary = loop.primary_relation;
  const pref = primary?.payoff_ref;
  if (!pref?.scene_ordinal) return null;
  const grade = primary?.grade;
  if (!grade || grade === "unsupported" || primary?.blocked) return null;
  const existing = (loop.payoffs || []).find((p) => p.scene_ordinal === pref.scene_ordinal);
  if (existing) return existing;
  return {
    scene_ordinal: pref.scene_ordinal,
    type: String(pref.type || "score_inferred"),
    source_type: pref.source_type || "score_inferred",
    summary: pref.summary || "",
    evidence_paragraph_ids: pref.evidence_paragraph_ids || [],
  };
}

export function buildHookPayoffTimelineModel(
  visualization: ReaderJourneyVisualization,
  options: {
    selectedLoopId?: string | null;
    selectedSceneOrdinal?: number | null;
    showCandidateRelations?: boolean;
  } = {},
): HookPayoffTimelineModel {
  const loops = getNarrativeLoops(visualization);
  const consistency = getNarrativeLoopConsistency(visualization);
  const chapterHard = consistency?.status === "inconsistent";
  const chapterSoft = consistency?.status === "soft_conflict";
  const selectedLoopId = options.selectedLoopId || null;
  const selectedScene = options.selectedSceneOrdinal ?? null;
  const showCandidates = Boolean(options.showCandidateRelations);
  const nodes: HookPayoffTimelineNode[] = [];
  const links: HookPayoffTimelineLink[] = [];
  let maxScene = 1;
  let anySoft = chapterSoft;

  for (const loop of loops) {
    const hard = isHardBlocked(loop);
    if (loop.soft_conflict) anySoft = true;
    const emphasis =
      selectedLoopId != null
        ? loop.loop_id === selectedLoopId
        : selectedScene != null
          ? loop.open_from_scene === selectedScene ||
            (loop.payoffs || []).some((p) => p.scene_ordinal === selectedScene) ||
            (loop.hook || []).some((h) => h.scene_ordinal === selectedScene)
          : true;

    const hookScene =
      loop.open_from_scene ??
      loop.hook?.[0]?.scene_ordinal ??
      loop.developments?.[0]?.scene_ordinal ??
      1;
    maxScene = Math.max(maxScene, hookScene);
    const hookId = `${loop.loop_id}:hook:${hookScene}`;
    nodes.push({
      id: hookId,
      loop_id: loop.loop_id,
      rail: "hook",
      kind: "new_hook",
      scene_ordinal: hookScene,
      title: shortPlainTitle(loop.question || loop.information_gap || "新问题"),
      hover: loop.question || "新建立的读者问题",
      emphasis,
    });

    const primary = loop.primary_relation;
    const primaryGrade = (primary?.grade || null) as RelationGrade | null;
    const primaryRef = primaryPayoffRef(loop);

    const payoffNodes = new Map<string, NarrativeLoopPayoff>();
    for (const payoff of loop.payoffs || []) {
      payoffNodes.set(`${payoff.scene_ordinal}:${payoffKind(payoff)}`, payoff);
    }
    if (primaryRef) {
      payoffNodes.set(`${primaryRef.scene_ordinal}:${payoffKind(primaryRef)}`, primaryRef);
    }

    for (const payoff of payoffNodes.values()) {
      const scene = payoff.scene_ordinal;
      maxScene = Math.max(maxScene, scene);
      const kind = payoffKind(payoff);
      const payoffId = `${loop.loop_id}:payoff:${scene}:${kind}`;
      nodes.push({
        id: payoffId,
        loop_id: loop.loop_id,
        rail: "payoff",
        kind,
        scene_ordinal: scene,
        title: shortPlainTitle(payoff.summary || loop.question || "回应"),
        hover: payoff.summary || "对前文问题的回应",
        emphasis,
      });
    }

    if (!hard) {
      if (primaryRef && primaryGrade) {
        const stroke = strokeForGrade(primaryGrade);
        if (stroke) {
          const kind = payoffKind(primaryRef);
          const payoffId = `${loop.loop_id}:payoff:${primaryRef.scene_ordinal}:${kind}`;
          links.push({
            loop_id: loop.loop_id,
            from_id: hookId,
            to_id: payoffId,
            grade: primaryGrade,
            stroke,
            is_primary: true,
            deterministic: primaryGrade === "confirmed" && !loop.soft_conflict,
          });
        }
      } else if ((loop.payoffs || []).length) {
        // Legacy fallback when API has not attached primary_relation yet.
        const first = loop.payoffs![0];
        const kind = payoffKind(first);
        const payoffId = `${loop.loop_id}:payoff:${first.scene_ordinal}:${kind}`;
        const grade: RelationGrade = loop.soft_conflict ? "probable" : "confirmed";
        const stroke = strokeForGrade(grade)!;
        links.push({
          loop_id: loop.loop_id,
          from_id: hookId,
          to_id: payoffId,
          grade,
          stroke,
          is_primary: true,
          deterministic: grade === "confirmed",
        });
      }
    }

    if (!hard && showCandidates) {
      for (const candidate of loop.candidate_relations || []) {
        if (candidate.blocked || candidate.grade === "unsupported") continue;
        const stroke = strokeForGrade(candidate.grade as RelationGrade);
        const pref = candidate.payoff_ref;
        if (!stroke || !pref?.scene_ordinal) continue;
        const kind = payoffKind({
          scene_ordinal: pref.scene_ordinal,
          type: String(pref.type || "partial"),
          source_type: pref.source_type,
          summary: pref.summary,
        });
        const payoffId = `${loop.loop_id}:payoff:${pref.scene_ordinal}:${kind}`;
        if (!nodes.some((n) => n.id === payoffId)) {
          nodes.push({
            id: payoffId,
            loop_id: loop.loop_id,
            rail: "payoff",
            kind,
            scene_ordinal: pref.scene_ordinal,
            title: shortPlainTitle(pref.summary || loop.question || "候选回应"),
            hover: candidate.grade_label_zh || "候选回应",
            emphasis,
          });
        }
        links.push({
          loop_id: loop.loop_id,
          from_id: hookId,
          to_id: payoffId,
          grade: candidate.grade as RelationGrade,
          stroke,
          is_primary: false,
          deterministic: false,
        });
      }
    }

    const status = displayStatus(loop);
    if (
      !hard &&
      !primaryRef &&
      (status === "open" || status === "partially_resolved")
    ) {
      nodes.push({
        id: `${loop.loop_id}:open`,
        loop_id: loop.loop_id,
        rail: "hook",
        kind: "open",
        scene_ordinal: hookScene,
        title: shortPlainTitle(loop.residual_question || loop.question || "仍在等待"),
        hover: "问题仍在等待回应",
        emphasis,
      });
    }
  }

  for (const node of visualization.scene_nodes || []) {
    maxScene = Math.max(maxScene, node.scene_ordinal);
  }

  let warning: string | null = null;
  if (chapterHard) {
    warning = consistency?.user_message || HARD_BLOCK_USER_MESSAGE;
  } else if (anySoft || chapterSoft) {
    warning = consistency?.user_message || SOFT_CONFLICT_USER_MESSAGE;
  }

  return {
    stats: buildHookPayoffChapterStats(loops),
    nodes,
    links,
    inconsistent: Boolean(chapterHard),
    softConflict: Boolean(anySoft || chapterSoft) && !chapterHard,
    warning,
    maxScene,
  };
}
