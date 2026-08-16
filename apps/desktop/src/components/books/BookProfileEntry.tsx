import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getBookProfile } from "../../features/bookProfile/api";
import { profileHref } from "../../features/bookProfile/origin";

type Props = {
  bookId: number;
  /** Present when the workspace has a chapter open, so confirming can return to it. */
  chapterId?: number | null;
};

/**
 * 作品画像 as a first-class toolbar entry.
 *
 * The profile gates both analysis pipelines, and until now it was the only thing in that
 * position with no button: the route existed, one line of small print inside the whole-book
 * page linked to it, and a user who only ran chapter analysis had no way to discover it at
 * all. A prerequisite the user cannot see is one they experience as an error message.
 *
 * The entry states its status rather than just its name, because "have I done this yet" is
 * the actual question — and answering it here saves the trip that answering it on the
 * profile page would cost.
 */
export function BookProfileEntry({ bookId, chapterId }: Props) {
  const [state, setState] = useState<"loading" | "confirmed" | "unconfirmed">("loading");

  useEffect(() => {
    if (!bookId || bookId <= 0) return;
    let cancelled = false;
    void (async () => {
      try {
        const profile = await getBookProfile(bookId);
        if (!cancelled) setState(profile?.status === "confirmed" ? "confirmed" : "unconfirmed");
      } catch {
        // A backend that cannot answer is not a book without a profile; stay quiet rather
        // than tell the user to go confirm something we failed to read.
        if (!cancelled) setState("loading");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [bookId]);

  if (state === "loading") return null;

  const confirmed = state === "confirmed";
  return (
    <Link
      className="secondary book-profile-entry"
      data-testid="book-profile-entry"
      data-state={confirmed ? "confirmed" : "unconfirmed"}
      to={
        chapterId
          ? profileHref(bookId, { from: "chapter", chapterId })
          : profileHref(bookId)
      }
      title={
        confirmed
          ? "已确认作品画像；分析按这本书的类型侧重进行"
          : "分析前需要先确认作品画像——它决定分析按什么类型侧重进行"
      }
    >
      {confirmed ? "作品画像 ✓" : "作品画像 · 待确认"}
    </Link>
  );
}
