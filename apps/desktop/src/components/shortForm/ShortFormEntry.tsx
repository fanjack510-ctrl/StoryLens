import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { shortFormApi } from "../../services/shortFormApi";

type Props = { bookId: number };

/** Book-workspace entry for 短篇精读, shown only for books the whole-book engine cannot read.
 *
 *  The two entries are exclusive rather than side by side. Offering both would ask the user to
 *  pick between an engine that reads their piece and one that structurally cannot: the whole-book
 *  planner works in blocks → partitions → stages, and on a short piece that collapses to two
 *  stages, so its four-beat structure comes out of two. Which pipeline a book takes is a fact
 *  about the book, not a preference, so the entry follows the fact.
 */
export function ShortFormEntry({ bookId }: Props) {
  const prepare = useQuery({
    queryKey: ["short-form-prepare", bookId],
    queryFn: () => shortFormApi.prepare(bookId),
    enabled: bookId > 0,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  if (bookId <= 0 || !prepare.data?.is_short_form) return null;

  const analysed = Boolean(prepare.data.latest);
  return (
    <Link
      className="secondary short-form-entry"
      data-testid="short-form-entry"
      to={`/books/${bookId}/short-form`}
      title="整篇按场景切段，逐段给出故事进展、事件冲突、学习之处与读者情绪。"
      aria-label={analysed ? "查看短篇精读" : "短篇精读"}
    >
      <span>{analysed ? "查看短篇精读" : "短篇精读"}</span>
    </Link>
  );
}
