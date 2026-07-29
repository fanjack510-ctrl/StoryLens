/**
 * Presentation-only stage band geometry for Reader Journey charts.
 * Does not mutate phase membership or stored journey results.
 */

import type {
  JourneyPhaseVisualization,
  JourneySceneNode,
  ReaderJourneyVisualization,
} from "../../types/readerJourneyVisualization";
import {
  journeyStageBandTitle,
  journeyStageTokenByKey,
  resolveJourneyStageKey,
  type JourneyStageKey,
  type JourneyStageVisualToken,
} from "./journeyVisualTokens";

export type JourneyStageBand = {
  id: string;
  stageKey: JourneyStageKey;
  label: string;
  token: JourneyStageVisualToken;
  /** Inclusive scene ordinals covered by this contiguous run. */
  startSceneOrdinal: number;
  endSceneOrdinal: number;
  /** Pixel X range in chart coordinates. */
  x1: number;
  x2: number;
  /** Quality warning when non-monotonic stage sequence is observed. */
  warning?: string;
};

export type SceneStageAssignment = {
  sceneOrdinal: number;
  stageKey: JourneyStageKey;
  label: string;
  token: JourneyStageVisualToken;
  phaseOrdinal: number | null;
};

function phaseByOrdinal(
  phases: JourneyPhaseVisualization[],
): Map<number, JourneyPhaseVisualization> {
  const map = new Map<number, JourneyPhaseVisualization>();
  for (const phase of phases) {
    map.set(phase.ordinal, phase);
  }
  return map;
}

/** Resolve stage for a scene without inventing thirds. */
export function resolveSceneStageAssignment(
  visualization: ReaderJourneyVisualization,
  sceneOrdinal: number,
  node?: JourneySceneNode | null,
): SceneStageAssignment {
  const phases = visualization.phases ?? [];
  const byOrdinal = phaseByOrdinal(phases);

  let phase: JourneyPhaseVisualization | undefined;
  if (node?.phase_ordinal != null) {
    phase = byOrdinal.get(node.phase_ordinal);
  }
  if (!phase) {
    phase = phases.find(
      (item) =>
        sceneOrdinal >= item.start_scene_ordinal &&
        sceneOrdinal <= item.end_scene_ordinal,
    );
  }

  if (!phase) {
    const token = journeyStageTokenByKey("unknown");
    return {
      sceneOrdinal,
      stageKey: "unknown",
      label: token.label,
      token,
      phaseOrdinal: node?.phase_ordinal ?? null,
    };
  }

  const stageKey = resolveJourneyStageKey(phase.title);
  const token = journeyStageTokenByKey(stageKey);
  return {
    sceneOrdinal,
    stageKey,
    label: journeyStageBandTitle(stageKey),
    token,
    phaseOrdinal: phase.ordinal,
  };
}

/**
 * Build contiguous stage runs from ordered scene ordinals.
 * Non-monotonic repeats (开端→发展→开端) become separate bands + warning.
 */
export function buildContiguousStageRuns(
  orderedOrdinals: number[],
  assignmentFor: (ordinal: number) => SceneStageAssignment,
): Array<{
  stageKey: JourneyStageKey;
  label: string;
  token: JourneyStageVisualToken;
  startSceneOrdinal: number;
  endSceneOrdinal: number;
  warning?: string;
}> {
  if (!orderedOrdinals.length) return [];

  const runs: Array<{
    stageKey: JourneyStageKey;
    label: string;
    token: JourneyStageVisualToken;
    startSceneOrdinal: number;
    endSceneOrdinal: number;
    warning?: string;
  }> = [];

  let current = assignmentFor(orderedOrdinals[0]);
  let runStart = orderedOrdinals[0];
  let runEnd = orderedOrdinals[0];
  const seenKeys = new Set<JourneyStageKey>([current.stageKey]);
  let nonMonotonic = false;

  for (let i = 1; i < orderedOrdinals.length; i += 1) {
    const ordinal = orderedOrdinals[i];
    const next = assignmentFor(ordinal);
    if (next.stageKey === current.stageKey && next.label === current.label) {
      runEnd = ordinal;
      continue;
    }
    if (seenKeys.has(next.stageKey) && next.stageKey !== "unknown") {
      nonMonotonic = true;
    }
    seenKeys.add(next.stageKey);
    runs.push({
      stageKey: current.stageKey,
      label: current.label,
      token: current.token,
      startSceneOrdinal: runStart,
      endSceneOrdinal: runEnd,
      warning: undefined,
    });
    current = next;
    runStart = ordinal;
    runEnd = ordinal;
  }

  runs.push({
    stageKey: current.stageKey,
    label: current.label,
    token: current.token,
    startSceneOrdinal: runStart,
    endSceneOrdinal: runEnd,
    warning: nonMonotonic
      ? "non_monotonic_stage_sequence"
      : undefined,
  });

  if (nonMonotonic) {
    for (const run of runs) {
      run.warning = run.warning ?? "non_monotonic_stage_sequence";
    }
  }

  return runs;
}

/**
 * Midpoint band edges from actual scene X positions.
 * First band → plotLeft; last band → plotRight.
 */
export function computeStageBandPixelRanges(
  runs: Array<{ startSceneOrdinal: number; endSceneOrdinal: number }>,
  orderedOrdinals: number[],
  xFor: (ordinal: number) => number,
  plotLeft: number,
  plotRight: number,
): Array<{ x1: number; x2: number }> {
  if (!runs.length || !orderedOrdinals.length) return [];

  const indexOf = new Map<number, number>();
  orderedOrdinals.forEach((ordinal, index) => indexOf.set(ordinal, index));

  return runs.map((run) => {
    const startIdx = indexOf.get(run.startSceneOrdinal) ?? 0;
    const endIdx = indexOf.get(run.endSceneOrdinal) ?? startIdx;
    const xStartCenter = xFor(run.startSceneOrdinal);
    const xEndCenter = xFor(run.endSceneOrdinal);

    let x1: number;
    if (startIdx <= 0) {
      x1 = plotLeft;
    } else {
      const prevOrdinal = orderedOrdinals[startIdx - 1];
      x1 = (xFor(prevOrdinal) + xStartCenter) / 2;
    }

    let x2: number;
    if (endIdx >= orderedOrdinals.length - 1) {
      x2 = plotRight;
    } else {
      const nextOrdinal = orderedOrdinals[endIdx + 1];
      x2 = (xEndCenter + xFor(nextOrdinal)) / 2;
    }

    if (x2 < x1) {
      const mid = (x1 + x2) / 2;
      return { x1: mid, x2: mid };
    }
    return { x1, x2 };
  });
}

export function buildJourneyStageBands(
  visualization: ReaderJourneyVisualization,
  options: {
    sceneOrdinals: number[];
    xFor: (ordinal: number) => number;
    plotLeft: number;
    plotRight: number;
    nodeByOrdinal?: Map<number, JourneySceneNode>;
  },
): JourneyStageBand[] {
  const { sceneOrdinals, xFor, plotLeft, plotRight, nodeByOrdinal } = options;
  const ordered = [...sceneOrdinals].sort((a, b) => a - b);
  if (!ordered.length || !(visualization.phases?.length)) {
    return [];
  }

  const assignmentFor = (ordinal: number) =>
    resolveSceneStageAssignment(
      visualization,
      ordinal,
      nodeByOrdinal?.get(ordinal) ??
        visualization.scene_nodes.find((n) => n.scene_ordinal === ordinal) ??
        null,
    );

  const runs = buildContiguousStageRuns(ordered, assignmentFor);
  const pixels = computeStageBandPixelRanges(runs, ordered, xFor, plotLeft, plotRight);

  return runs.map((run, index) => ({
    id: `stage-band-${index}-${run.stageKey}-${run.startSceneOrdinal}-${run.endSceneOrdinal}`,
    stageKey: run.stageKey,
    label: run.label,
    token: run.token,
    startSceneOrdinal: run.startSceneOrdinal,
    endSceneOrdinal: run.endSceneOrdinal,
    x1: pixels[index]?.x1 ?? plotLeft,
    x2: pixels[index]?.x2 ?? plotRight,
    warning: run.warning,
  }));
}
