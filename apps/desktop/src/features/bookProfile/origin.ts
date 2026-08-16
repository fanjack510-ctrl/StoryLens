/** Where the profile page was opened from, and where confirming should return to.
 *
 *  The confirm button used to navigate to the whole-book page unconditionally, because when
 *  it was written the whole-book run was the only thing a profile gated. Now both analysis
 *  entries gate on it (10_ADAPTIVE_PROFILE_LAYER §4.3), so a user sent here from a chapter
 *  dialog was dropped into whole-book analysis — a different, more expensive thing than the
 *  one they asked for.
 *
 *  The origin travels in the URL rather than in component state so it survives a reload and
 *  a back/forward, and so the link that sends the user here is the single place that decides
 *  where they come back to.
 */

export type ProfileOrigin =
  | { kind: "chapter"; bookId: number; chapterId: number }
  | { kind: "whole-book"; bookId: number }
  | { kind: "direct"; bookId: number };

/** The href a caller uses to send the user to the profile page. */
export function profileHref(
  bookId: number,
  origin?: { from: "chapter"; chapterId: number } | { from: "whole-book" },
): string {
  const base = `/books/${bookId}/profile`;
  if (!origin) return base;
  if (origin.from === "chapter") {
    return `${base}?from=chapter&chapterId=${origin.chapterId}`;
  }
  return `${base}?from=whole-book`;
}

export function readProfileOrigin(bookId: number, params: URLSearchParams): ProfileOrigin {
  const from = params.get("from");
  if (from === "chapter") {
    const chapterId = Number(params.get("chapterId"));
    if (Number.isFinite(chapterId) && chapterId > 0) {
      return { kind: "chapter", bookId, chapterId };
    }
  }
  if (from === "whole-book") return { kind: "whole-book", bookId };
  return { kind: "direct", bookId };
}

/** Where confirming sends the user. A user who navigated here directly stays put: they came
 *  to look at the profile, not to start a run, and moving them would be an answer to a
 *  question they did not ask. */
export function returnHref(origin: ProfileOrigin): string | null {
  switch (origin.kind) {
    case "chapter":
      // `startAnalysis=1` re-opens the dialog the gate interrupted, so the user resumes the
      // thing they were doing instead of having to find it again.
      return `/books/${origin.bookId}?chapter=${origin.chapterId}&startAnalysis=1`;
    case "whole-book":
      return `/books/${origin.bookId}/whole-book`;
    default:
      return null;
  }
}

/** What the confirm button should say, so it never promises the wrong kind of analysis. */
export function confirmLabel(origin: ProfileOrigin): string {
  switch (origin.kind) {
    case "chapter":
      return "确认并分析本章";
    case "whole-book":
      return "确认并开始全书分析";
    default:
      return "保存画像";
  }
}
