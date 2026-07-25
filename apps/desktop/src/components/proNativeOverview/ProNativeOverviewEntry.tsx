import { Link } from "react-router-dom";
import { useProductEdition } from "../../hooks/useProductEdition";
import { Badge } from "../common/States";
import { isProNativeOverviewUiEnabled } from "../../services/proNativeOverviewFlag";

type Props = {
  bookId: number;
  onUpgrade: () => void;
};

const ENTRY_LABEL = "Pro 原生全书概览";

/**
 * Book workspace entry for Native Overview (distinct from 章节聚合洞察).
 * Hidden when UI feature flag is off — not a formal product entry.
 */
export function ProNativeOverviewEntry({ bookId, onUpgrade }: Props) {
  const edition = useProductEdition();
  const flagOn = isProNativeOverviewUiEnabled();
  if (!flagOn) return null;

  const isPro = edition.loaded && edition.is_pro;

  if (isPro) {
    return (
      <Link
        className="secondary pro-native-overview-entry"
        data-testid="pro-native-overview-entry-pro"
        to={`/books/${bookId}/pro-native-overview`}
      >
        {ENTRY_LABEL} <Badge>Pro</Badge>
      </Link>
    );
  }

  return (
    <button
      type="button"
      className="secondary pro-native-overview-entry"
      data-testid="pro-native-overview-entry-free"
      onClick={onUpgrade}
    >
      {ENTRY_LABEL} <Badge>Pro</Badge>
    </button>
  );
}
