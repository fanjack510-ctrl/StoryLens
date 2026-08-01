import { Link, useSearchParams } from "react-router-dom";
import { isWholeBookFreeProductEnabled } from "../../services/wholeBookFreeProductFlag";
import { wholeBookFreeModuleHref } from "../../services/wholeBookFreeEvidenceDeepLink";
import type { WholeBookModuleKey } from "../../services/wholeBookFreeProductApi";

type Props = {
  bookId: number;
};

const ENTRY_TITLE = "全书分析";
const ENTRY_DESCRIPTION =
  "从完整原文出发，分析全书总览、主要人物、关键事件、故事结构和章节功能。";

const MODULE_KEYS = new Set<string>([
  "overview",
  "characters_events",
  "structure",
  "chapter_functions",
  "pro_depth",
]);

/**
 * Book workspace secondary-toolbar entry for formal Free whole-book product.
 * Compact label only — description and start CTA live on the whole-book page.
 * When Evidence deep-link carries returnModule, re-enter that Free module.
 */
export function WholeBookFreeEntry({ bookId }: Props) {
  const [searchParams] = useSearchParams();
  if (!isWholeBookFreeProductEnabled() || bookId <= 0) return null;

  const returnTo = searchParams.get("returnTo");
  const returnModuleRaw = searchParams.get("returnModule");
  const returnModule =
    returnTo === "whole-book" && returnModuleRaw && MODULE_KEYS.has(returnModuleRaw)
      ? (returnModuleRaw as WholeBookModuleKey)
      : null;
  const href = returnModule
    ? wholeBookFreeModuleHref(bookId, returnModule)
    : `/books/${bookId}/whole-book`;

  return (
    <Link
      className="secondary whole-book-free-entry"
      data-testid="whole-book-free-entry"
      to={href}
      title={ENTRY_DESCRIPTION}
      aria-label={ENTRY_TITLE}
    >
      <span className="whole-book-free-entry__title">{ENTRY_TITLE}</span>
    </Link>
  );
}
