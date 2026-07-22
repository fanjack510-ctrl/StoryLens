import type { Chapter } from "../../types";
import { chapterListLabel, bodyOrdinalOf } from "../../services/chapterNavigation";

type Props = {
  prev: Chapter | null;
  next: Chapter | null;
  chapters: Chapter[];
  onSelect: (chapterId: number) => void;
  compact?: boolean;
};

function labelFor(chapters: Chapter[], c: Chapter | null): string {
  if (!c) return "";
  const ordinal = bodyOrdinalOf(chapters, c.id);
  const num = chapterListLabel(c, ordinal);
  const title = c.display_title || c.title || "";
  return `第${num}章｜${title}`;
}

export function ChapterAdjacentNav({
  prev,
  next,
  chapters,
  onSelect,
  compact = false,
}: Props) {
  if (!prev && !next) return null;
  return (
    <nav
      className={`chapter-adjacent-nav${compact ? " chapter-adjacent-nav--compact" : ""}`}
      data-testid={compact ? "chapter-adjacent-nav-top" : "chapter-adjacent-nav"}
      aria-label="章节切换"
    >
      <button
        type="button"
        className="chapter-adjacent-btn"
        data-testid="chapter-prev"
        disabled={!prev}
        title={prev ? labelFor(chapters, prev) : undefined}
        onClick={() => prev && onSelect(prev.id)}
      >
        <span className="chapter-adjacent-dir">上一章</span>
        {prev && !compact ? (
          <span className="chapter-adjacent-title">{labelFor(chapters, prev)}</span>
        ) : null}
      </button>
      <button
        type="button"
        className="chapter-adjacent-btn chapter-adjacent-btn--next"
        data-testid="chapter-next"
        disabled={!next}
        title={next ? labelFor(chapters, next) : undefined}
        onClick={() => next && onSelect(next.id)}
      >
        <span className="chapter-adjacent-dir">下一章</span>
        {next && !compact ? (
          <span className="chapter-adjacent-title">{labelFor(chapters, next)}</span>
        ) : null}
      </button>
    </nav>
  );
}
