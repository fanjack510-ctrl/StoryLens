import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { analysisApi } from "../../services/analysisApi";
import { isProNativeOverviewUiEnabled } from "../../services/proNativeOverviewFlag";
import {
  nativeOverviewHref,
  normalizeRunLifecycle,
  selectNativeOverviewReentryRun,
} from "../../services/runLifecycle";

type Props = {
  bookId: number;
  /** Kept for call-site compatibility; unused after Free entitlement (CHG-20260726-004). */
  onUpgrade?: () => void;
};

const ENTRY_LABEL = "原生全书概览";

/**
 * Book workspace entry for Native Overview (distinct from 章节聚合洞察).
 * Hidden when UI feature flag is off — not a formal product entry.
 * Free in StoryLens 1.1.x (CHG-20260726-004); no Pro paywall.
 *
 * CHG-20260727-014: deep-link to active/completed run when present.
 */
export function ProNativeOverviewEntry({ bookId }: Props) {
  const flagOn = isProNativeOverviewUiEnabled();
  const runs = useQuery({
    queryKey: ["runs", "native-overview-entry", bookId],
    queryFn: () => analysisApi.runs({ book_id: bookId }),
    enabled: flagOn && bookId > 0,
    staleTime: 5_000,
    refetchOnWindowFocus: true,
  });

  const reentry = useMemo(
    () => selectNativeOverviewReentryRun(runs.data, bookId),
    [runs.data, bookId],
  );
  const phase = normalizeRunLifecycle(reentry);
  const href =
    reentry && (phase === "active" || phase === "completed" || phase === "failed" || phase === "cancelled")
      ? nativeOverviewHref(bookId, reentry.id)
      : `/books/${bookId}/pro-native-overview`;

  if (!flagOn) return null;

  return (
    <Link
      className="secondary pro-native-overview-entry"
      data-testid="pro-native-overview-entry-free"
      to={href}
    >
      {ENTRY_LABEL}
    </Link>
  );
}
