/** Unified Reader Journey selection for chapter workspace (CHG-041 Round 3). */

import { parseBackendUtcTimestamp } from "./parseBackendUtcTimestamp";

export type JourneyCandidate = {
  id: number;
  status: string;
  scene_revision_id?: number | null;
  result_status?: string | null;
  started_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  completed_at?: string | null;
  failed_at?: string | null;
  paused_at?: string | null;
  total_scene_count?: number | null;
  completed_scene_count?: number | null;
  root_error_code?: string | null;
  retryable?: boolean | null;
};

export type ResolvedReaderJourney = {
  journey: JourneyCandidate | null;
  source:
    | "url"
    | "active_for_revision"
    | "succeeded_for_revision"
    | "failed_for_revision"
    | "none";
};

const ACTIVE = new Set([
  "queued",
  "running",
  "scene_profiles_running",
  "chapter_synthesis_running",
  "summary_running",
  "phase_analysis_running",
  "pending",
]);

function byIdDesc(a: JourneyCandidate, b: JourneyCandidate): number {
  return b.id - a.id;
}

/**
 * Priority:
 * 1. URL explicit journeyRun
 * 2. active journey for confirmed revision
 * 3. latest succeeded for confirmed revision
 * 4. latest failed/interrupted for confirmed revision
 * 5. none
 *
 * Explicit URL runs are historical deep links and are returned even when bound
 * to a different/superseded revision. Automatic selection remains revision-safe.
 * Never treats analysisRun id as a journey id.
 */
export function resolveCurrentReaderJourney(args: {
  explicitJourneyRunId?: number | null;
  confirmedRevisionId?: number | null;
  candidates: JourneyCandidate[];
}): ResolvedReaderJourney {
  const confirmedId = args.confirmedRevisionId ?? null;
  const explicit = args.explicitJourneyRunId ?? null;
  const pool = [...args.candidates].filter((item) => Number.isFinite(item.id));

  if (explicit != null) {
    const hit = pool.find((item) => item.id === explicit);
    if (hit) return { journey: hit, source: "url" };
    // Keep an explicit URL pointer so gates do not treat a deep link as
    // "never generated" while the by-id query is loading or 404ing.
    return {
      journey: {
        id: explicit,
        status: "pending",
        scene_revision_id: null,
        result_status: null,
      },
      source: "url",
    };
  }

  if (confirmedId == null) {
    return { journey: null, source: "none" };
  }

  const forRevision = pool
    .filter((item) => item.scene_revision_id === confirmedId)
    .filter((item) => item.result_status !== "superseded")
    .sort(byIdDesc);

  const active = forRevision.find((item) => ACTIVE.has((item.status || "").toLowerCase()));
  if (active) return { journey: active, source: "active_for_revision" };

  const succeeded = forRevision.find((item) => (item.status || "").toLowerCase() === "succeeded");
  if (succeeded) return { journey: succeeded, source: "succeeded_for_revision" };

  const failed = forRevision.find((item) => {
    const status = (item.status || "").toLowerCase();
    return (
      status === "failed" ||
      status === "cancelled" ||
      status === "budget_blocked" ||
      status === "interrupted" ||
      status === "paused" ||
      status === "scene_profiles_partial" ||
      status === "aborted_by_limit"
    );
  });
  if (failed) return { journey: failed, source: "failed_for_revision" };

  return { journey: null, source: "none" };
}

export function journeyElapsedMs(args: {
  journey: JourneyCandidate | null;
  nowMs?: number;
}): number | null {
  const journey = args.journey;
  if (!journey) return null;
  const start = parseBackendUtcTimestamp(journey.started_at || journey.created_at);
  if (start == null) return null;
  const status = (journey.status || "").toLowerCase();
  let end: number | null = null;
  if (status === "failed" || status === "budget_blocked" || status === "aborted_by_limit") {
    end = parseBackendUtcTimestamp(journey.failed_at || journey.completed_at || journey.updated_at);
  } else if (status === "paused") {
    end = parseBackendUtcTimestamp(journey.paused_at || journey.updated_at);
  } else if (status === "succeeded") {
    end = parseBackendUtcTimestamp(journey.completed_at || journey.updated_at);
  } else if (status === "interrupted" || status === "cancelled") {
    end = parseBackendUtcTimestamp(journey.completed_at || journey.updated_at || journey.failed_at);
  }
  if (end == null) {
    end = args.nowMs ?? Date.now();
  }
  if (!Number.isFinite(end) || end < start) return null;
  return end - start;
}

export function formatJourneyElapsed(ms: number | null | undefined): string | null {
  if (ms == null || !Number.isFinite(ms) || ms < 0) return null;
  const sec = Math.floor(ms / 1000);
  if (sec < 60) return `${sec} 秒`;
  const min = Math.floor(sec / 60);
  const rem = sec % 60;
  if (min < 60) return `${min} 分 ${rem} 秒`;
  const hr = Math.floor(min / 60);
  return `${hr} 小时 ${min % 60} 分`;
}

export function preserveJourneyRunInParams(
  params: URLSearchParams,
  journeyRunId: number | null | undefined,
): URLSearchParams {
  if (journeyRunId != null && Number.isFinite(journeyRunId)) {
    params.set("journeyRun", String(journeyRunId));
  }
  return params;
}
