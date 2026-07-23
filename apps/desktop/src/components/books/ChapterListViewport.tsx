import { useEffect, useMemo, useRef, useState } from "react";
import type { Chapter } from "../../types";
import {
  bodyChapters,
  bodyOrdinalOf,
  buildChapterRanges,
  chapterListLabel,
  chaptersInRange,
  frontMatterChapters,
  rangeContainingOrdinal,
  scrollChapterListItemIntoViewIfNeeded,
  type ChapterRange,
} from "../../services/chapterNavigation";

type Props = {
  chapters: Chapter[];
  currentChapterId: number;
  onSelect: (chapterId: number) => void;
  onPrefetch?: (chapterId: number) => void;
  listRef?: React.RefObject<HTMLDivElement | null>;
};

export function ChapterListViewport({
  chapters,
  currentChapterId,
  onSelect,
  onPrefetch,
  listRef: externalRef,
}: Props) {
  const internalRef = useRef<HTMLDivElement>(null);
  const listRef = externalRef || internalRef;
  const body = useMemo(() => bodyChapters(chapters), [chapters]);
  const front = useMemo(() => frontMatterChapters(chapters), [chapters]);
  const ranges = useMemo(() => buildChapterRanges(body.length), [body.length]);
  const currentOrdinal = bodyOrdinalOf(chapters, currentChapterId);
  const [activeRange, setActiveRange] = useState<ChapterRange | null>(() =>
    rangeContainingOrdinal(ranges, currentOrdinal),
  );

  useEffect(() => {
    setActiveRange(rangeContainingOrdinal(ranges, currentOrdinal));
  }, [ranges, currentOrdinal]);

  const visible = chaptersInRange(chapters, activeRange || ranges[0] || null);

  useEffect(() => {
    scrollChapterListItemIntoViewIfNeeded(listRef.current, currentChapterId);
  }, [currentChapterId, activeRange, listRef, visible.length]);

  if (!chapters.length) {
    return (
      <div className="workspace-chapter-viewport" data-testid="workspace-chapter-viewport">
        <p className="workspace-chapter-empty" data-testid="workspace-chapter-empty">
          尚未识别到章节
        </p>
      </div>
    );
  }

  const renderRow = (c: Chapter, opts: { key: string; ordinal?: number | null; kind: "front" | "chapter" }) => {
    const title = c.display_title || c.title;
    const label = chapterListLabel(c, opts.ordinal);
    const selected = currentChapterId === c.id;
    return (
      <button
        type="button"
        className={`workspace-chapter-item workspace-chapter-item--${opts.kind}${selected ? " selected" : ""}`}
        data-chapter-id={c.id}
        data-row-kind={opts.kind}
        data-testid={selected ? "workspace-chapter-item-selected" : undefined}
        onClick={() => onSelect(c.id)}
        onMouseEnter={() => onPrefetch?.(c.id)}
        onFocus={() => onPrefetch?.(c.id)}
        key={opts.key}
        title={title}
        aria-label={`${label} ${title}`}
        aria-current={selected ? "true" : undefined}
      >
        <span className="workspace-chapter-num">{label}</span>
        <span className="workspace-chapter-title">{title}</span>
      </button>
    );
  };

  return (
    <div className="workspace-chapter-viewport" data-testid="workspace-chapter-viewport">
      {ranges.length > 1 ? (
        <div className="workspace-chapter-ranges" data-testid="workspace-sidebar-ranges">
          <select
            aria-label="章节区间"
            data-testid="workspace-sidebar-range-select"
            value={
              activeRange
                ? `${activeRange.startOrdinal}-${activeRange.endOrdinal}`
                : ""
            }
            onChange={(e) => {
              const [start, end] = e.target.value.split("-").map(Number);
              const next = ranges.find(
                (r) => r.startOrdinal === start && r.endOrdinal === end,
              );
              if (next) setActiveRange(next);
            }}
          >
            {ranges.map((r) => (
              <option key={r.label} value={`${r.startOrdinal}-${r.endOrdinal}`}>
                {r.label}
              </option>
            ))}
          </select>
        </div>
      ) : null}

      <div
        className="workspace-chapter-list"
        ref={listRef}
        data-testid="chapter-list-scroll-region"
        data-chapter-list="workspace-chapter-list"
      >
        {front.map((c) =>
          renderRow(c, { key: `front-${c.id}`, kind: "front" }),
        )}
        {visible.map((c) => {
          const ordinal = bodyOrdinalOf(chapters, c.id);
          return renderRow(c, { key: String(c.id), ordinal, kind: "chapter" });
        })}
      </div>
    </div>
  );
}
