import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { shortFormApi } from "../../services/shortFormApi";
import { isWholeBookFreeProductEnabled } from "../../services/wholeBookFreeProductFlag";
import {
  readEvidenceRestoreState,
  wholeBookFreeModuleHref,
} from "../../services/wholeBookFreeEvidenceDeepLink";
import {
  WHOLE_BOOK_FREE_MODULES,
  type WholeBookModuleKey,
} from "../../services/wholeBookFreeProductApi";

type Props = {
  bookId: number;
  /** 工具书按节读，那条路叫「读懂」不叫「全书分析」。
   *
   *  同一个入口对不同类型的书说不同的话，是因为它们本来就是不同的事：
   *  小说走的是评测/拆文，工具书走的是读懂。用一个「全书分析」盖住三种，
   *  等于让人自己进去猜这本书会得到什么。 */
  label?: string;
  /** 进去之后默认哪一种读法。
   *
   *  不带的话页面默认「评测」——于是一本专著的分析页顶上写着「评测 · 看自己的书：
   *  该改哪里」，还挂着「作品画像」和「改用短篇精读」。**书的类型这一层知道，
   *  分析页那一层不知道**，所以由这里把它带过去。 */
  mode?: "diagnostic" | "story_breakdown" | "comprehend";
};

const ENTRY_TITLE = "全书分析";
const RETURN_TITLE = "返回分析";
const ENTRY_DESCRIPTION =
  "从完整原文出发，分析全书总览、故事、人物、悬念、节奏、章节与综合诊断。";

/** 能被「返回分析」还原的模块。
 *
 *  从 `WHOLE_BOOK_FREE_MODULES` 派生，不再手抄一份。手抄的那份抄的是另一套命名
 *  （全书 V2 报告的 story / characters / suspense…），而链接的目的地
 *  `WholeBookFreeProductPage` 认的是这一套（characters_events / structure /
 *  chapter_functions）。两套名字对不上时不会报错——`returnModule` 静静地变成 null，
 *  「返回分析」退化成一个普通入口，用户点回去发现自己回到了列表开头，
 *  筛选、游标、展开的那一条全没了，而没有任何地方说出过什么。
 */
const MODULE_KEYS = new Set<string>(WHOLE_BOOK_FREE_MODULES.map((m) => m.key));

/**
 * Book workspace secondary-toolbar entry for formal Free whole-book product.
 * Compact label only — description and start CTA live on the whole-book page.
 * When Evidence deep-link carries returnModule, re-enter that Free module
 * and forward restore* query state (filters / cursor / detail).
 */
export function WholeBookFreeEntry({ bookId, label: labelOverride, mode }: Props) {
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
      ? (returnModuleRaw as WholeBookModuleKey)
      : null;
  const restore = returnModule ? readEvidenceRestoreState(searchParams) : undefined;
  const href = returnModule
    ? wholeBookFreeModuleHref(bookId, returnModule, restore)
    : mode
      ? `/books/${bookId}/whole-book?mode=${mode}`
      : `/books/${bookId}/whole-book`;
  const label = returnModule ? RETURN_TITLE : labelOverride || ENTRY_TITLE;

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
