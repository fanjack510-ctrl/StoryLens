import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { JourneyCurveMetric } from "../types/readerJourneyVisualization";
import type {
  JourneyPageMode,
  JourneySelectionPatch,
  JourneySelectionSource,
  JourneySelectionState,
} from "../types/journeySelection";
import type { SceneResultItem } from "../types";
import {
  applyJourneyViewToSearchParams,
  resolveJourneyPageModeFromSearch,
} from "../components/readerJourney/journeyViewMode";
import { lensIdFromMetric } from "../components/readerJourney/readerJourneyLensExplanation";

const DEFAULT_METRIC: JourneyCurveMetric = "engagement";
const SCROLL_SUPPRESS_MS = 600;

function parseMetric(value: string | null): JourneyCurveMetric {
  const allowed: JourneyCurveMetric[] = [
    "engagement",
    "valence",
    "arousal",
    "curiosity",
    "tension",
    "payoff",
    "hook",
    "dropoff_risk",
  ];
  if (value && allowed.includes(value as JourneyCurveMetric)) {
    return value as JourneyCurveMetric;
  }
  return DEFAULT_METRIC;
}

function sceneByOrdinal(scenes: SceneResultItem[], ordinal: number | null) {
  if (ordinal == null) return undefined;
  return scenes.find((item) => item.scene.ordinal === ordinal);
}

type Options = {
  scenes: SceneResultItem[];
  enabled?: boolean;
};

export function useJourneySelection({ scenes, enabled = true }: Options) {
  const [searchParams, setSearchParams] = useSearchParams();
  const suppressScrollSpyUntil = useRef(0);
  const programmaticScrollLockRef = useRef(false);

  const [state, setState] = useState<JourneySelectionState>(() => {
    const sceneParam = searchParams.get("scene");
    const parsedOrdinal = sceneParam ? Number(sceneParam) : null;
    const sceneItem = sceneByOrdinal(
      scenes,
      Number.isFinite(parsedOrdinal) ? parsedOrdinal : null,
    );
    return {
      pageMode: resolveJourneyPageModeFromSearch(searchParams),
      activePhaseId: null,
      activeSceneId: sceneItem ? sceneItem.scene.id : null,
      activeSceneOrdinal: sceneItem ? sceneItem.scene.ordinal : null,
      activeParagraphId: searchParams.get("paragraph"),
      activeEvidenceIds: [],
      selectionSource: "url" as JourneySelectionSource,
      selectedMetric: parseMetric(searchParams.get("metric")),
      selectedQuestionClusterId: searchParams.get("cluster"),
      flashParagraphId: null,
    };
  });

  const syncUrl = useCallback(
    (patch: JourneySelectionPatch) => {
      if (!enabled) return;
      // Functional updater: never clobber a concurrent lens/metric write from Workspace
      // with a stale searchParams snapshot.
      setSearchParams(
        (prev) => {
          const params = new URLSearchParams(prev);
          params.set("tab", "reader-journey");

          const mode = patch.pageMode ?? state.pageMode;
          applyJourneyViewToSearchParams(params, mode);

          const sceneOrdinal = patch.activeSceneOrdinal ?? state.activeSceneOrdinal;
          if (sceneOrdinal != null) params.set("scene", String(sceneOrdinal));
          else if (patch.activeSceneOrdinal === null) params.delete("scene");

          const paragraphId = patch.activeParagraphId ?? state.activeParagraphId;
          if (paragraphId) params.set("paragraph", paragraphId);
          else if (patch.activeParagraphId === null) params.delete("paragraph");

          if (patch.selectedMetric !== undefined) {
            const metric = patch.selectedMetric;
            params.set("metric", metric);
            // Keep lens in lockstep with metric when parent syncs metric.
            params.set("lens", lensIdFromMetric(metric));
          }

          const clusterId = patch.selectedQuestionClusterId ?? state.selectedQuestionClusterId;
          if (clusterId) params.set("cluster", clusterId);
          else if (patch.selectedQuestionClusterId === null) params.delete("cluster");

          return params;
        },
        { replace: true },
      );
    },
    [enabled, setSearchParams, state],
  );

  const applyPatch = useCallback(
    (patch: JourneySelectionPatch, sync = true) => {
      setState((current) => ({ ...current, ...patch }));
      if (sync) syncUrl(patch);
    },
    [syncUrl],
  );

  const beginProgrammaticScroll = useCallback(() => {
    programmaticScrollLockRef.current = true;
    suppressScrollSpyUntil.current = Date.now() + SCROLL_SUPPRESS_MS;
    window.setTimeout(() => {
      programmaticScrollLockRef.current = false;
    }, SCROLL_SUPPRESS_MS);
  }, []);

  const isScrollSpySuppressed = useCallback(
    () => programmaticScrollLockRef.current || Date.now() < suppressScrollSpyUntil.current,
    [],
  );

  const selectScene = useCallback(
    (
      sceneId: number,
      source: JourneySelectionSource = "journey_scene",
      paragraphId?: string | null,
      phaseId?: number | null,
    ) => {
      const item = scenes.find((s) => s.scene.id === sceneId);
      if (!item) return;
      applyPatch({
        activeSceneId: item.scene.id,
        activeSceneOrdinal: item.scene.ordinal,
        activeParagraphId: paragraphId ?? item.scene.start_paragraph_id,
        selectionSource: source,
        activeEvidenceIds: source === "scroll_spy" ? state.activeEvidenceIds : [],
        ...(phaseId !== undefined ? { activePhaseId: phaseId } : {}),
      });
    },
    [applyPatch, scenes, state.activeEvidenceIds],
  );

  const selectSceneByOrdinal = useCallback(
    (
      ordinal: number,
      source: JourneySelectionSource = "journey_scene",
      paragraphId?: string | null,
    ) => {
      const item = sceneByOrdinal(scenes, ordinal);
      if (!item) return;
      selectScene(item.scene.id, source, paragraphId);
    },
    [scenes, selectScene],
  );

  const selectPhase = useCallback(
    (
      phaseOrdinal: number | null,
      source: JourneySelectionSource = "journey_phase",
      firstSceneOrdinal?: number | null,
    ) => {
      const sceneItem =
        firstSceneOrdinal != null ? sceneByOrdinal(scenes, firstSceneOrdinal) : undefined;
      applyPatch({
        activePhaseId: phaseOrdinal,
        selectionSource: source,
        ...(sceneItem
          ? {
              activeSceneId: sceneItem.scene.id,
              activeSceneOrdinal: sceneItem.scene.ordinal,
              activeParagraphId: sceneItem.scene.start_paragraph_id,
              activeEvidenceIds: [] as string[],
            }
          : {}),
      });
    },
    [applyPatch, scenes],
  );

  const selectParagraph = useCallback(
    (paragraphId: string, sceneId: number, source: JourneySelectionSource = "text_paragraph") => {
      applyPatch({
        activeParagraphId: paragraphId,
        activeSceneId: sceneId,
        activeSceneOrdinal: scenes.find((s) => s.scene.id === sceneId)?.scene.ordinal ?? null,
        selectionSource: source,
        activeEvidenceIds: [],
      });
    },
    [applyPatch, scenes],
  );

  const locateEvidence = useCallback(
    (paragraphIds: string[], sceneId?: number | null) => {
      const flashId = paragraphIds[0] ?? null;
      applyPatch({
        activeEvidenceIds: paragraphIds,
        flashParagraphId: flashId,
        activeParagraphId: flashId,
        activeSceneId: sceneId ?? state.activeSceneId,
        activeSceneOrdinal:
          sceneId != null
            ? (scenes.find((s) => s.scene.id === sceneId)?.scene.ordinal ?? state.activeSceneOrdinal)
            : state.activeSceneOrdinal,
        selectionSource: "journey_evidence",
      });
      if (flashId) {
        window.setTimeout(() => {
          setState((current) =>
            current.flashParagraphId === flashId ? { ...current, flashParagraphId: null } : current,
          );
        }, 1500);
      }
    },
    [applyPatch, scenes, state.activeSceneId, state.activeSceneOrdinal],
  );

  const setMetric = useCallback(
    (metric: JourneyCurveMetric, options?: { syncUrl?: boolean }) => {
      applyPatch(
        { selectedMetric: metric, selectionSource: "journey_scene" },
        options?.syncUrl !== false,
      );
    },
    [applyPatch],
  );

  const setCluster = useCallback(
    (clusterId: string | null) => {
      applyPatch({ selectedQuestionClusterId: clusterId, selectionSource: "journey_cluster" });
    },
    [applyPatch],
  );

  const setPageMode = useCallback(
    (pageMode: JourneyPageMode) => {
      applyPatch({ pageMode, selectionSource: "init" });
    },
    [applyPatch],
  );

  useEffect(() => {
    if (!enabled || scenes.length === 0) return;
    const sceneParam = searchParams.get("scene");
    if (!sceneParam) return;
    const ordinal = Number(sceneParam);
    if (!Number.isFinite(ordinal)) return;
    const item = sceneByOrdinal(scenes, ordinal);
    if (!item) return;
    setState((current) => {
      if (current.activeSceneOrdinal === ordinal && current.activeSceneId === item.scene.id) {
        return current;
      }
      return {
        ...current,
        activeSceneOrdinal: ordinal,
        activeSceneId: item.scene.id,
        activeParagraphId: searchParams.get("paragraph") ?? item.scene.start_paragraph_id,
        pageMode: resolveJourneyPageModeFromSearch(searchParams),
        selectedMetric: parseMetric(searchParams.get("metric")),
        selectedQuestionClusterId: searchParams.get("cluster"),
        selectionSource: "url",
      };
    });
  }, [enabled, scenes, searchParams]);

  return {
    state,
    selectScene,
    selectSceneByOrdinal,
    selectPhase,
    selectParagraph,
    locateEvidence,
    setMetric,
    setCluster,
    setPageMode,
    beginProgrammaticScroll,
    isScrollSpySuppressed,
    programmaticScrollLockRef,
    suppressScrollSpyUntil,
  };
}
