/**
 * Presentation-layer atomic URL commit for Reader Journey selection.
 * Does not replace JourneySelectionState / useJourneySelection.
 */
import { INSPECTOR_PARAM, applyInspectorParam } from "./overviewMode";

export type JourneySelectionIntent =
  | {
      source: "curve" | "rhythm" | "scene-list" | "journey_scene" | "journey_rhythm";
      inspector: "scene";
      sceneOrdinal: number;
      phaseId?: number | null;
      paragraphId?: string | null;
      clearCluster?: boolean;
    }
  | {
      source: "phase-strip" | "journey_phase";
      inspector: "phase";
      phaseId: number;
      preserveScene: true;
    }
  | {
      source: "question-cluster";
      inspector: "question";
      clusterId: string;
      sceneOrdinal?: number;
      paragraphId?: string | null;
    }
  | {
      source: "hook" | "payoff" | "risk";
      inspector: "hook" | "payoff" | "risk";
      sceneOrdinal?: number;
      phaseId?: number | null;
      paragraphId?: string | null;
    }
  | {
      source: "evidence" | "journey_evidence" | "scroll_spy";
      preserveInspector: true;
      sceneOrdinal: number;
      paragraphId: string;
    }
  | {
      source: "clear-inspector";
      inspector: null;
    };

let transactionSeq = 0;

export function nextJourneyTransactionId(): number {
  transactionSeq += 1;
  return transactionSeq;
}

function ensureJourneyTab(next: URLSearchParams): void {
  if (!next.get("tab") && !next.get("resultTab")) {
    next.set("tab", "reader-journey");
  } else if (next.get("resultTab") === "reader-journey") {
    next.set("tab", "reader-journey");
    next.delete("resultTab");
  } else if (!next.get("tab")) {
    next.set("tab", "reader-journey");
  }
}

/** Merge one user-action intent into the latest search params (single commit). */
export function applyJourneySelectionIntent(
  previous: URLSearchParams,
  intent: JourneySelectionIntent,
): URLSearchParams {
  const next = new URLSearchParams(previous);
  ensureJourneyTab(next);

  if ("preserveInspector" in intent) {
    next.set("scene", String(intent.sceneOrdinal));
    next.set("paragraph", intent.paragraphId);
    return next;
  }

  if (intent.source === "clear-inspector") {
    return applyInspectorParam(next, null);
  }

  if ("preserveScene" in intent) {
    return applyInspectorParam(next, "phase");
  }

  if ("clusterId" in intent) {
    next.set("cluster", intent.clusterId);
    if (intent.sceneOrdinal != null) next.set("scene", String(intent.sceneOrdinal));
    if (intent.paragraphId) next.set("paragraph", intent.paragraphId);
    return applyInspectorParam(next, "question");
  }

  if (intent.source === "hook" || intent.source === "payoff" || intent.source === "risk") {
    if (intent.sceneOrdinal != null) next.set("scene", String(intent.sceneOrdinal));
    if (intent.paragraphId) next.set("paragraph", intent.paragraphId);
    return applyInspectorParam(next, intent.inspector);
  }

  // Remaining: scene selection intents only.
  const sceneIntent = intent;
  next.set("scene", String(sceneIntent.sceneOrdinal));
  if (sceneIntent.paragraphId) {
    next.set("paragraph", sceneIntent.paragraphId);
  }
  if ("clearCluster" in sceneIntent && sceneIntent.clearCluster) {
    next.delete("cluster");
  }
  return applyInspectorParam(next, "scene");
}

export function logJourneySelectionTransaction(payload: {
  transactionId: number;
  source: string;
  previousSearch: string;
  nextSearch: string;
}): void {
  if (!import.meta.env.DEV) return;
  console.debug("[JourneySelectionTransaction]", {
    transactionId: payload.transactionId,
    source: payload.source,
    previousSearch: payload.previousSearch,
    nextSearch: payload.nextSearch,
  });
}

export function readInspector(params: URLSearchParams): string | null {
  return params.get(INSPECTOR_PARAM);
}
