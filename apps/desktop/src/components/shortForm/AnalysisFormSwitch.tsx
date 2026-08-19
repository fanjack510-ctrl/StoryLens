import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { shortFormApi, type AnalysisForm } from "../../services/shortFormApi";

type Props = {
  bookId: number;
  /** Which page this is sitting on, so it offers the other one. */
  on: AnalysisForm;
};

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
export function AnalysisFormSwitch({ bookId, on }: Props) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const other: AnalysisForm = on === "short" ? "long" : "short";

  const prepare = useQuery({
    queryKey: ["short-form-prepare", bookId],
    queryFn: () => shortFormApi.prepare(bookId),
    enabled: bookId > 0,
    retry: false,
  });

  const change = useMutation({
    mutationFn: () => shortFormApi.setForm(bookId, other),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["short-form-prepare", bookId] });
      navigate(other === "short" ? `/books/${bookId}/short-form` : `/books/${bookId}/whole-book`);
    },
  });

  if (bookId <= 0 || !prepare.data) return null;

  const answered = prepare.data.analysis_form !== "";
  return (
    <p className="analysis-form-switch" data-testid="analysis-form-switch">
      <span>
        {on === "short" ? "这本按短篇读" : "这本按长篇读"}
        {answered ? "" : "（按长度推断的，没人确认过）"}。
      </span>
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
      {change.isError && <span className="analysis-form-switch__error">切换失败，没有改动。</span>}
    </p>
  );
}
