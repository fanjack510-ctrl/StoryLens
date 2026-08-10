import { Link, useSearchParams } from "react-router-dom";
import { isWholeBookFreeProductEnabled } from "../../services/wholeBookFreeProductFlag";
import {
  readEvidenceRestoreState,
  wholeBookFreeModuleHref,
} from "../../services/wholeBookFreeEvidenceDeepLink";
import type { ModuleKey } from "../../features/wholeBookV2/presentation/modules";

type Props = {
  bookId: number;
};

const ENTRY_TITLE = "全书分析";
const RETURN_TITLE = "返回分析";
const ENTRY_DESCRIPTION =
  "从完整原文出发，分析全书总览、故事、人物、悬念、节奏、章节与综合诊断。";

const MODULE_KEYS = new Set<string>([
  "overview",
  "story",
  "characters",
  "suspense",
  "pacing",
  "chapters",
  "assessment",
]);

/**
 * Book workspace secondary-toolbar entry for formal Free whole-book product.
 * Compact label only — description and start CTA live on the whole-book page.
 * When Evidence deep-link carries returnModule, re-enter that Free module
 * and forward restore* query state (filters / cursor / detail).
 */
export function WholeBookFreeEntry({ bookId }: Props) {
  const [searchParams] = useSearchParams();
  if (!isWholeBookFreeProductEnabled() || bookId <= 0) return null;

  const returnTo = searchParams.get("returnTo");
  const returnModuleRaw = searchParams.get("returnModule");
  const returnModule =
    returnTo === "whole-book" && returnModuleRaw && MODULE_KEYS.has(returnModuleRaw)
      ? (returnModuleRaw as ModuleKey)
      : null;
  const restore = returnModule ? readEvidenceRestoreState(searchParams) : undefined;
  const href = returnModule
    ? wholeBookFreeModuleHref(bookId, returnModule, restore)
    : `/books/${bookId}/whole-book`;
  const label = returnModule ? RETURN_TITLE : ENTRY_TITLE;

  return (
    <Link
      className="secondary whole-book-free-entry"
      data-testid="whole-book-free-entry"
      data-return-module={returnModule ?? undefined}
      to={href}
      title={ENTRY_DESCRIPTION}
      aria-label={label}
    >
      <span className="whole-book-free-entry__title">{label}</span>
    </Link>
  );
}
