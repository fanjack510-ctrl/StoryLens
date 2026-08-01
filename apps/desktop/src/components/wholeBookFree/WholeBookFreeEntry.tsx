import { Link } from "react-router-dom";
import { isWholeBookFreeProductEnabled } from "../../services/wholeBookFreeProductFlag";

type Props = {
  bookId: number;
};

const ENTRY_TITLE = "全书分析";
const ENTRY_DESCRIPTION =
  "从完整原文出发，分析全书总览、主要人物、关键事件、故事结构和章节功能。";

/**
 * Book workspace secondary-toolbar entry for formal Free whole-book product.
 * Compact label only — description and start CTA live on the whole-book page.
 * Hidden when UI feature flag is off — not a primary-nav entry.
 */
export function WholeBookFreeEntry({ bookId }: Props) {
  if (!isWholeBookFreeProductEnabled() || bookId <= 0) return null;

  return (
    <Link
      className="secondary whole-book-free-entry"
      data-testid="whole-book-free-entry"
      to={`/books/${bookId}/whole-book`}
      title={ENTRY_DESCRIPTION}
      aria-label={ENTRY_TITLE}
    >
      <span className="whole-book-free-entry__title">{ENTRY_TITLE}</span>
    </Link>
  );
}
