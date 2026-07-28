import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { isWholeBookFreeProductEnabled } from "../../services/wholeBookFreeProductFlag";
import { wholeBookFreeProductApi } from "../../services/wholeBookFreeProductApi";

type Props = {
  bookId: number;
};

const ENTRY_TITLE = "全书分析";
const ENTRY_DESCRIPTION =
  "从完整原文出发，分析全书总览、主要人物、关键事件、故事结构和章节功能。";

function entryActionLabel(status: string | null | undefined): string {
  if (!status || status === "pending") return "开始全书分析";
  if (status === "running") return "查看分析进度";
  if (status === "completed") return "查看全书分析";
  if (status === "failed" || status === "recoverable" || status === "paused") {
    return "查看并恢复";
  }
  if (status === "cancelled") return "开始全书分析";
  return "开始全书分析";
}

/**
 * Book workspace secondary-toolbar entry for formal Free whole-book product.
 * Hidden when UI feature flag is off — not a primary-nav entry.
 */
export function WholeBookFreeEntry({ bookId }: Props) {
  const flagOn = isWholeBookFreeProductEnabled();
  const prepare = useQuery({
    queryKey: ["whole-book-free-entry", bookId],
    queryFn: () => wholeBookFreeProductApi.prepare(bookId),
    enabled: flagOn && bookId > 0,
    staleTime: 5_000,
    retry: false,
  });

  const run = prepare.data?.latest_run ?? prepare.data?.recoverable_run ?? null;
  const actionLabel = useMemo(() => entryActionLabel(run?.status), [run?.status]);
  const href = `/books/${bookId}/whole-book`;

  if (!flagOn) return null;

  return (
    <Link
      className="secondary whole-book-free-entry"
      data-testid="whole-book-free-entry"
      to={href}
      title={ENTRY_DESCRIPTION}
    >
      <span className="whole-book-free-entry__title">{ENTRY_TITLE}</span>
      <span className="whole-book-free-entry__desc">{ENTRY_DESCRIPTION}</span>
      <span className="whole-book-free-entry__action">{actionLabel}</span>
    </Link>
  );
}
