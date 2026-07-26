import { Link } from "react-router-dom";
import { isProNativeOverviewUiEnabled } from "../../services/proNativeOverviewFlag";

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
 */
export function ProNativeOverviewEntry({ bookId }: Props) {
  const flagOn = isProNativeOverviewUiEnabled();
  if (!flagOn) return null;

  return (
    <Link
      className="secondary pro-native-overview-entry"
      data-testid="pro-native-overview-entry-free"
      to={`/books/${bookId}/pro-native-overview`}
    >
      {ENTRY_LABEL}
    </Link>
  );
}
