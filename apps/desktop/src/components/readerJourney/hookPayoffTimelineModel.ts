/**
 * Hook/Payoff dual-rail timeline model — reads NarrativeLoopView only.
 * Presentation layer; does not alter NarrativeLoopView fact rules.
 */

import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";
import {
  INCONSISTENT_USER_MESSAGE,
  getNarrativeLoopConsistency,
  getNarrativeLoops,
  type NarrativeLoopPayoff,
  type NarrativeLoopView,
} from "./narrativeLoopView";
import { shortPlainTitle } from "./readerJourneyLensExplanation";

export type HookPayoffRailKind = "hook" | "payoff";

export type HookPayoffNodeKind =
  | "new_hook"
  | "partial"
  | "full"
  | "reversal"
  | "transformed"
  | "open";

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
  warning: string | null;
  maxScene: number;
};

function payoffKind(payoff: NarrativeLoopPayoff): HookPayoffNodeKind {
  const type = String(payoff.type || "");
  if (type === "full") return "full";
  if (type === "reversal") return "reversal";
  if (type === "transformed_question") return "transformed";
  return "partial";
}

function isAnsweredStatus(status: string): boolean {
  return status === "resolved" || status === "transformed" || status === "abandoned";
}

export function buildHookPayoffChapterStats(loops: NarrativeLoopView[]): HookPayoffChapterStats {
  let established = 0;
  let answered = 0;
  let waiting = 0;
  let delayed_risk = 0;
  for (const loop of loops) {
    if (loop.consistency_status === "inconsistent" || loop.status === "inconsistent") continue;
    established += 1;
    if (isAnsweredStatus(String(loop.status))) {
      answered += 1;
    } else if (loop.status === "partially_resolved") {
      waiting += 1;
      if ((loop.nodes_spanned || 1) >= 3) delayed_risk += 1;
    } else if (loop.status === "open") {
      waiting += 1;
      if ((loop.nodes_spanned || 1) >= 2) delayed_risk += 1;
    }
  }
  return { established, answered, waiting, delayed_risk };
}

export function buildHookPayoffTimelineModel(
  visualization: ReaderJourneyVisualization,
  options: { selectedLoopId?: string | null; selectedSceneOrdinal?: number | null } = {},
): HookPayoffTimelineModel {
  const loops = getNarrativeLoops(visualization);
  const consistency = getNarrativeLoopConsistency(visualization);
  const inconsistent = consistency?.status === "inconsistent";
  const selectedLoopId = options.selectedLoopId || null;
  const selectedScene = options.selectedSceneOrdinal ?? null;
  const nodes: HookPayoffTimelineNode[] = [];
  const links: HookPayoffTimelineLink[] = [];
  let maxScene = 1;

  for (const loop of loops) {
    const loopInconsistent =
      loop.consistency_status === "inconsistent" || loop.status === "inconsistent";
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

    for (const payoff of loop.payoffs || []) {
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
      if (!loopInconsistent && !inconsistent) {
        links.push({
          loop_id: loop.loop_id,
          from_id: hookId,
          to_id: payoffId,
          deterministic: true,
        });
      }
    }

    if (
      !loop.payoffs?.length &&
      (loop.status === "open" || loop.status === "partially_resolved") &&
      !loopInconsistent
    ) {
      // Open extension marker on hook rail only — no fictional payoff.
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

  return {
    stats: buildHookPayoffChapterStats(loops),
    nodes,
    links,
    inconsistent: Boolean(inconsistent),
    warning: inconsistent ? INCONSISTENT_USER_MESSAGE : null,
    maxScene,
  };
}
