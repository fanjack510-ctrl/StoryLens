import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { shortFormApi, type AnalysisForm } from "../../services/shortFormApi";

type Props = { bookId: number };

/** Move a work between the two pipelines, from either page.
 *
 *  The choice is made at import, but it has to be changeable here or it is not really a
 *  choice: a value fixed at import with no way to correct it is wrong forever, which is
 *  exactly what happened to book titles — imported from the filename, never validated, and
 *  with no rename anywhere in the product.
 *
 *  Nothing is recomputed and nothing is discarded. A reading already paid for on the other
 *  side stays where it is; switching back finds it still there.
 */
export function AnalysisFormSwitch({ bookId }: Props) {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const prepare = useQuery({
    queryKey: ["short-form-prepare", bookId],
    queryFn: () => shortFormApi.prepare(bookId),
    enabled: bookId > 0,
    retry: false,
  });

  // Which form this book is on comes from the book, never from which page is rendering this.
  // Reading it off the page said "这本按长篇读" on the whole-book page for a book that was
  // marked 短篇 — describing the reader's location as if it were the book's property.
  const current: AnalysisForm = prepare.data?.is_short_form ? "short" : "long";
  const other: AnalysisForm = current === "short" ? "long" : "short";

  const change = useMutation({
    mutationFn: () => shortFormApi.setForm(bookId, other),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["short-form-prepare", bookId] });
      navigate(other === "short" ? `/books/${bookId}/short-form` : `/books/${bookId}/whole-book`);
    },
  });

  if (bookId <= 0 || !prepare.data) return null;

  const answered = prepare.data.analysis_form !== "";
  // The ceiling binds here too. Enforcing it only at import would not be enforcing it: this
  // button would walk straight around the cap and land on the failure it exists to prevent.
  // Only an explicit `false` blocks. A payload from an older sidecar carries neither field,
  // and a control that throws on a missing one would take the whole page down with it.
  const blocked = other === "short" && prepare.data.short_form_allowed === false;
  const ceiling = prepare.data.hard_max_chars ?? 150_000;
  return (
    <p className="analysis-form-switch" data-testid="analysis-form-switch">
      <span>
        {current === "short" ? "这本按短篇读" : "这本按长篇读"}
        {answered ? "" : "（按长度推断的，没人确认过）"}。
      </span>
      {blocked ? (
        <span className="analysis-form-switch__blocked">
          超过 {ceiling.toLocaleString()} 字，不能按短篇读——
          切段要把全文一次发给模型，装不下。
        </span>
      ) : (
        <button
          type="button"
          className="link"
          disabled={change.isPending}
          onClick={() => change.mutate()}
        >
          {change.isPending
            ? "正在切换…"
            : other === "short"
              ? "其实是短篇？改用短篇精读"
              : "其实是长篇？改用全书分析"}
        </button>
      )}
      {change.isError && <span className="analysis-form-switch__error">切换失败，没有改动。</span>}
    </p>
  );
}
