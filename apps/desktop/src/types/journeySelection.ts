import type { JourneyCurveMetric } from "./readerJourneyVisualization";

export type JourneyPageMode = "sync" | "journey" | "reading";

export type JourneySelectionSource =
  | "journey_scene"
  | "journey_phase"
  | "journey_hook"
  | "journey_payoff"
  | "journey_risk"
  | "journey_evidence"
  | "journey_cluster"
  | "journey_rhythm"
  | "text_scene"
  | "text_paragraph"
  | "scroll_spy"
  | "url"
  | "drawer"
  | "init";

export type JourneySelectionState = {
  pageMode: JourneyPageMode;
  activePhaseId: number | null;
  activeSceneId: number | null;
  activeSceneOrdinal: number | null;
  activeParagraphId: string | null;
  activeEvidenceIds: string[];
  selectionSource: JourneySelectionSource;
  selectedMetric: JourneyCurveMetric;
  selectedQuestionClusterId: string | null;
  flashParagraphId: string | null;
};

export type JourneySelectionPatch = Partial<
  Pick<
    JourneySelectionState,
    | "pageMode"
    | "activePhaseId"
    | "activeSceneId"
    | "activeSceneOrdinal"
    | "activeParagraphId"
    | "activeEvidenceIds"
    | "selectionSource"
    | "selectedMetric"
    | "selectedQuestionClusterId"
    | "flashParagraphId"
  >
>;
