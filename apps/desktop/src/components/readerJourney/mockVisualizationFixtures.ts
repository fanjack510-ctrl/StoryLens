/**
 * Visual-regression fixtures for Reader Journey Visualization v2.8.
 * Generic scene counts only — no book/chapter/run special cases.
 */
import type {
  JourneyCurvePoint,
  ReaderJourneyVisualization,
} from "../../types/readerJourneyVisualization";
import { buildMockReaderJourneyVisualization } from "./mockVisualization";

function cloneBase(): ReaderJourneyVisualization {
  return structuredClone(buildMockReaderJourneyVisualization());
}

function makeSeries(
  count: number,
  values: Array<number | null>,
): JourneyCurvePoint[] {
  return Array.from({ length: count }, (_, index) => {
    const value = index < values.length ? values[index]! : 50;
    if (value == null) {
      return { scene_ordinal: index + 1 };
    }
    return { scene_ordinal: index + 1, value };
  });
}

function resizeVisualization(
  sceneCount: number,
  curiosityValues?: Array<number | null>,
): ReaderJourneyVisualization {
  const base = cloneBase();
  const nodes = Array.from({ length: sceneCount }, (_, index) => {
    const ordinal = index + 1;
    const template = base.scene_nodes[index % base.scene_nodes.length]!;
    return {
      ...structuredClone(template),
      scene_id: 1000 + ordinal,
      scene_ordinal: ordinal,
      phase_ordinal:
        ordinal <= Math.ceil(sceneCount * 0.25)
          ? 1
          : ordinal <= Math.ceil(sceneCount * 0.5)
            ? 2
            : ordinal <= Math.ceil(sceneCount * 0.75)
              ? 3
              : 4,
    };
  });

  const values =
    curiosityValues ??
    nodes.map((_, i) => {
      if (i === 0) return 0;
      if (i === Math.floor(sceneCount / 2)) return 100;
      return 20 + ((i * 7) % 70);
    });

  const metrics = Object.keys(base.curve_series) as Array<keyof typeof base.curve_series>;
  const curve_series = { ...base.curve_series };
  for (const metric of metrics) {
    curve_series[metric] = makeSeries(sceneCount, values);
  }

  const phaseSize = Math.max(1, Math.floor(sceneCount / 4));
  const phases = [1, 2, 3, 4].map((ordinal) => {
    const start = (ordinal - 1) * phaseSize + 1;
    const end = ordinal === 4 ? sceneCount : Math.min(sceneCount, ordinal * phaseSize);
    const template = base.phases[(ordinal - 1) % base.phases.length]!;
    return {
      ...structuredClone(template),
      ordinal,
      start_scene_ordinal: start,
      end_scene_ordinal: Math.max(start, end),
      scene_span: Math.max(start, end) - start + 1,
    };
  });

  return {
    ...base,
    scene_nodes: nodes,
    curve_series,
    phases,
    risk_intervals: [
      {
        risk_type: "pacing",
        start_scene_ordinal: Math.max(1, Math.floor(sceneCount * 0.4)),
        end_scene_ordinal: Math.max(2, Math.floor(sceneCount * 0.55)),
        span: 2,
        summary: "节奏偏缓",
      },
    ],
    chapter_summary: {
      ...base.chapter_summary,
      chapter_title: `${sceneCount}-Scene Fixture`,
    },
  };
}

/** 3 Scene short chapter with 0 / null / 100. */
export function buildFixture3Scenes(): ReaderJourneyVisualization {
  return resizeVisualization(3, [0, null, 100]);
}

/** 13 Scene ordinary chapter (boundary values + trough). */
export function buildFixture13Scenes(): ReaderJourneyVisualization {
  const values: Array<number | null> = [
    0, 35, 42, 28, 55, 70, 48, 22, 60, 85, null, 40, 100,
  ];
  return resizeVisualization(13, values);
}

/** 30 Scene long chapter. */
export function buildFixture30Scenes(): ReaderJourneyVisualization {
  return resizeVisualization(30);
}

/** 60 Scene ultra-long chapter (brush). */
export function buildFixture60Scenes(): ReaderJourneyVisualization {
  return resizeVisualization(60);
}

export const VISUAL_REGRESSION_FIXTURES = {
  scenes_3: buildFixture3Scenes,
  scenes_13: buildFixture13Scenes,
  scenes_30: buildFixture30Scenes,
  scenes_60: buildFixture60Scenes,
} as const;
