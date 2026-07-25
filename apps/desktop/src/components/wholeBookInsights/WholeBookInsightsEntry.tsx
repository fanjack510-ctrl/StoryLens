import { Link } from "react-router-dom";
import { useProductEdition } from "../../hooks/useProductEdition";
import { Badge } from "../common/States";

type Props = {
  bookId: number;
  onUpgrade: () => void;
};

/** Book workspace entry — free users see upgrade prompt without API calls. */
export function WholeBookInsightsEntry({ bookId, onUpgrade }: Props) {
  const edition = useProductEdition();
  const isPro = edition.loaded && edition.is_pro;

  if (isPro) {
    return (
      <Link
        className="secondary whole-book-insights-entry"
        data-testid="whole-book-insights-entry-pro"
        to={`/books/${bookId}/whole-book-insights`}
      >
        全书洞察 <Badge>Pro</Badge>
      </Link>
    );
  }

  return (
    <button
      type="button"
      className="secondary whole-book-insights-entry"
      data-testid="whole-book-insights-entry-free"
      onClick={onUpgrade}
    >
      全书洞察 <Badge>Pro</Badge>
    </button>
  );
}
