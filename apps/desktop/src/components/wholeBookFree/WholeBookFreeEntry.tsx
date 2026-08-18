import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { shortFormApi } from "../../services/shortFormApi";
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
  // Hidden for books that take 短篇精读 instead. The two entries are exclusive rather than
  // side by side: which pipeline a book gets is a fact about the book, and offering both would
  // invite the user to choose an engine that structurally cannot read their piece — the
  // whole-book planner collapses to two narrative stages on anything this short.
  // Same query key as ShortFormEntry, so the pair costs one request.
  const shortForm = useQuery({
    queryKey: ["short-form-prepare", bookId],
    queryFn: () => shortFormApi.prepare(bookId),
    enabled: bookId > 0,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
  if (!isWholeBookFreeProductEnabled() || bookId <= 0) return null;
  if (shortForm.data?.is_short_form) return null;

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
